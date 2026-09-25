// Tests de logique pure du module Résultats (refonte étape 3, issue #627).
// Aucune dépendance, aucun build, aucun DOM. Lancement (depuis la racine) :
//   node --test static/js/tests/
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  formaterDuree,
  calculerBadgeTempsRestant,
  calculerBadgeEstimation,
  planifierEvenementSse,
  fusionnerChargement,
} from '../resultats.js';

// Repère temporel fixe pour des calculs déterministes.
const T0 = new Date('2026-09-25T12:00:00Z').getTime();
const ilYA = (s) => new Date(T0 - s * 1000).toISOString();

// ─── formaterDuree ───────────────────────────────────────────────────────────
test('formaterDuree : secondes, minutes, jamais négatif', () => {
  assert.equal(formaterDuree(0), '0s');
  assert.equal(formaterDuree(45), '45s');
  assert.equal(formaterDuree(60), '1min');
  assert.equal(formaterDuree(200), '3min 20s');
  assert.equal(formaterDuree(-10), '0s');
});

// ─── calculerBadgeTempsRestant (décompte TIMEOUT) ────────────────────────────
test('badge temps : rien sans données', () => {
  assert.deepEqual(calculerBadgeTempsRestant(null, T0), { masque: true });
});

test('badge temps : « en file » tant qu\'aucun ACK (debut null)', () => {
  const r = calculerBadgeTempsRestant({ debut: null, timeout: 300, max_essais: 3 }, T0);
  assert.equal(r.texte, '⏳ en file');
  assert.match(r.classe, /tr-attente/);
});

test('badge temps : priorité sans limite', () => {
  const r = calculerBadgeTempsRestant({ debut: ilYA(10), sans_limite: true }, T0);
  assert.equal(r.texte, '⏳ en cours (pas de limite)');
  assert.match(r.classe, /tr-illimite/);
});

test('badge temps : décompte du 1er cycle (ok puis bientôt)', () => {
  const t = { debut: ilYA(60), timeout: 300, max_essais: 1, backoff: 0 };
  const r = calculerBadgeTempsRestant(t, T0);
  assert.equal(r.texte, '⏳ 4min');            // 300 - 60 = 240 s
  assert.match(r.classe, /tr-ok/);
  const t2 = { debut: ilYA(280), timeout: 300, max_essais: 1, backoff: 0 };
  const r2 = calculerBadgeTempsRestant(t2, T0);
  assert.match(r2.classe, /tr-bientot/);       // 20 s restant ≤ 30
});

test('badge temps : au-delà du 1er cycle → retry, pas un échec', () => {
  const t = { debut: ilYA(360), timeout: 300, max_essais: 3, backoff: 0 };
  const r = calculerBadgeTempsRestant(t, T0);
  assert.match(r.texte, /tentative 2\/3/);
  assert.match(r.classe, /tr-retry/);
});

test('badge temps : budget épuisé → signale un fetch #334 à programmer', () => {
  const t = { debut: ilYA(1000), timeout: 300, max_essais: 3, backoff: 0 };
  const r = calculerBadgeTempsRestant(t, T0);
  assert.match(r.texte, /budget épuisé/);
  assert.equal(r.budgetEpuise, true);
});

test('badge temps : dépassement déjà vérifié → « rafraîchir ↻ », pas de reprogrammation', () => {
  const t = { debut: ilYA(1000), timeout: 300, max_essais: 3, backoff: 0 };
  const r = calculerBadgeTempsRestant(t, T0, { verifie: true });
  assert.match(r.texte, /rafraîchir ↻/);
  assert.notEqual(r.budgetEpuise, true);        // ne reprogramme aucun fetch
});

// ─── calculerBadgeEstimation ─────────────────────────────────────────────────
test('badge estimation : masqué sans estimation', () => {
  assert.deepEqual(calculerBadgeEstimation({ estimation: null }, T0), { masque: true });
});

test('badge estimation : « pas encore de données »', () => {
  const r = calculerBadgeEstimation({ estimation: { fiabilite: 'aucune', mediane: null } }, T0);
  assert.match(r.texte, /pas encore de données/);
  assert.match(r.classe, /est-aucune/);
});

test('badge estimation : médiane figée avant ACK', () => {
  const r = calculerBadgeEstimation(
    { debut: null, estimation: { fiabilite: 'sur', mediane: 120, n: 20 } }, T0);
  assert.equal(r.texte, '≈ 2min');
  assert.match(r.classe, /est-sur/);
});

test('badge estimation : décompte live puis dépassement (ton neutre)', () => {
  const t = { debut: ilYA(60), estimation: { fiabilite: 'correct', mediane: 120, n: 8 } };
  assert.equal(calculerBadgeEstimation(t, T0).texte, '≈ 1min');  // 120 - 60
  const t2 = { debut: ilYA(200), estimation: { fiabilite: 'correct', mediane: 120, n: 8 } };
  const r2 = calculerBadgeEstimation(t2, T0);
  assert.equal(r2.texte, '≈ estimation dépassée');
  assert.match(r2.classe, /est-depasse/);
});

// ─── planifierEvenementSse (cœur du correctif #627) ──────────────────────────
test('planifierEvenementSse : debut_issue ne passe JAMAIS par la vérif post-dépassement', () => {
  const etat = { issues: { 'p#42': { projet: 'p', number: 42 } } };
  // Issue déjà connue : ancien bug = verifierIssueApresDepassement. Désormais : action « debut ».
  assert.deepEqual(planifierEvenementSse(etat, { type: 'debut_issue', projet: 'p', numero: 42 }),
                   { action: 'debut', cle: 'p#42', connue: true });
  // Issue inconnue : toujours « debut » (rechargera le timing ciblé + ajoutera la ligne).
  assert.deepEqual(planifierEvenementSse(etat, { type: 'debut_issue', projet: 'p', numero: 99 }),
                   { action: 'debut', cle: 'p#99', connue: false });
});

test('planifierEvenementSse : fin_issue et creation_issue', () => {
  const etat = { issues: {} };
  assert.equal(planifierEvenementSse(etat, { type: 'fin_issue', projet: 'p', numero: 1 }).action, 'fin');
  assert.equal(planifierEvenementSse(etat, { type: 'creation_issue', projet: 'p', numero: 1 }).action, 'creer');
  assert.equal(planifierEvenementSse(etat, { type: 'inconnu', projet: 'p', numero: 1 }).action, 'ignorer');
});

// ─── fusionnerChargement (correctif anomalie #3 : échec ≠ disparition) ────────
test('fusionnerChargement : un projet en échec conserve ses issues précédentes', () => {
  const anciennes = [
    { projet: 'a', number: 1, createdAt: '2026-01-01T00:00:00Z' },
    { projet: 'b', number: 2, createdAt: '2026-01-02T00:00:00Z' },
  ];
  const fusion = fusionnerChargement(anciennes, ['a', 'b'], [
    { projet: 'a', succes: true,  issues: [{ number: 3, createdAt: '2026-01-03T00:00:00Z' }] },
    { projet: 'b', succes: false, issues: [] },   // échec → on garde b#2
  ]);
  const cles = fusion.map(it => it.projet + '#' + it.number);
  assert.ok(cles.includes('b#2'), 'issue du projet en échec conservée');
  assert.ok(cles.includes('a#3'), 'nouvelle issue du projet réussi présente');
  assert.ok(!cles.includes('a#1'), 'ancienne issue du projet réussi remplacée');
});

test('fusionnerChargement : projets non refetchés conservés, tri par date décroissante', () => {
  const anciennes = [{ projet: 'c', number: 9, createdAt: '2026-05-01T00:00:00Z' }];
  const fusion = fusionnerChargement(anciennes, ['a'], [
    { projet: 'a', succes: true, issues: [{ number: 1, createdAt: '2026-06-01T00:00:00Z' }] },
  ]);
  assert.equal(fusion.length, 2);
  assert.equal(fusion[0].projet, 'a');   // 2026-06 avant 2026-05
  assert.equal(fusion[1].projet, 'c');
});
