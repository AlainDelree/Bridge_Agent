// Tests de logique pure du module Résultats (refonte étape 3, issue #627).
// Aucune dépendance, aucun build, aucun DOM. Lancement (depuis la racine) :
//   node --test static/js/tests/
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  formaterDuree,
  calculerBadgeTempsRestant,
  calculerBadgeEstimation,
  calculerBadgeModele,
  libelleModele,
  calculerBadgeSansRedacteur,
  planifierEvenementSse,
  fusionnerChargement,
  fusionnerTimingProjet,
  construireIssueCreation,
  FENETRE_RECENTE_TIMING_MS,
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

// ─── calculerBadgeModele / libelleModele (issue #638) ────────────────────────
test('libelleModele : nom court par famille, repli sans préfixe claude-', () => {
  assert.equal(libelleModele('claude-opus-4-8'), 'opus');
  assert.equal(libelleModele('claude-haiku-4-5'), 'haiku');
  assert.equal(libelleModele('claude-fable-5'), 'fable');
  assert.equal(libelleModele('claude-sonnet-5'), 'sonnet');
  assert.equal(libelleModele('claude-experimental'), 'experimental');  // repli
  assert.equal(libelleModele(''), '');
  assert.equal(libelleModele(null), '');
});

test('badge modèle : rien sans champ MODELE (modele null/absent)', () => {
  assert.deepEqual(calculerBadgeModele(null, 'claude-sonnet-5'), { afficher: false });
  assert.deepEqual(calculerBadgeModele(undefined, 'claude-sonnet-5'), { afficher: false });
  assert.deepEqual(calculerBadgeModele('', 'claude-sonnet-5'), { afficher: false });
});

test('badge modèle : rien quand le modèle forcé EST le défaut du projet', () => {
  assert.deepEqual(calculerBadgeModele('claude-sonnet-5', 'claude-sonnet-5'), { afficher: false });
  // Insensible à la casse.
  assert.deepEqual(calculerBadgeModele('CLAUDE-OPUS-4-8', 'claude-opus-4-8'), { afficher: false });
});

test('badge modèle : affiché quand le modèle effectif diffère du défaut', () => {
  const r = calculerBadgeModele('claude-opus-4-8', 'claude-sonnet-5');
  assert.equal(r.afficher, true);
  assert.equal(r.label, 'opus');
  assert.match(r.titre, /claude-opus-4-8/);
  assert.match(r.titre, /claude-sonnet-5/);
});

test('badge modèle : défaut projet non-Sonnet (issue force Sonnet) → affiché', () => {
  // Projet dont le défaut est Opus : une issue forçant Sonnet diffère du défaut.
  const r = calculerBadgeModele('claude-sonnet-5', 'claude-opus-4-8');
  assert.equal(r.afficher, true);
  assert.equal(r.label, 'sonnet');
  // Défaut projet manquant → « claude-sonnet-5 » implicite : Opus diffère.
  assert.equal(calculerBadgeModele('claude-opus-4-8').afficher, true);
});

// ─── calculerBadgeSansRedacteur (issue #647) ─────────────────────────────────
test('badge sans REDACTEUR : rien sans le label sans-redacteur', () => {
  assert.deepEqual(calculerBadgeSansRedacteur([]), { afficher: false });
  assert.deepEqual(calculerBadgeSansRedacteur(null), { afficher: false });
  assert.deepEqual(calculerBadgeSansRedacteur(['bridge', 'for-linux']), { afficher: false });
});

test('badge sans REDACTEUR : affiché quand le label sans-redacteur est présent', () => {
  const r = calculerBadgeSansRedacteur(['bridge', 'for-linux', 'sans-redacteur']);
  assert.equal(r.afficher, true);
  assert.equal(r.titre, 'Créée sans REDACTEUR');
});

test('badge sans REDACTEUR : reconnaît le format objet {name} de gh issue list', () => {
  const r = calculerBadgeSansRedacteur([{ name: 'bridge' }, { name: 'sans-redacteur' }]);
  assert.equal(r.afficher, true);
});

test('badge sans REDACTEUR : insensible à la casse du label', () => {
  assert.equal(calculerBadgeSansRedacteur(['Sans-Redacteur']).afficher, true);
});

// ─── construireIssueCreation (contenu enrichi de creation_issue, issue #640) ──
// L'événement SSE creation_issue transporte désormais modele/modele_defaut
// dans `timing` (voir app.fin_issue.emettre_creation_issue, backend) — cette
// fonction est le point UNIQUE qui les lit côté navigateur pour construire
// l'entrée du store d'une issue tout juste créée.
test('construireIssueCreation : reprend modele/modele_defaut depuis timing', () => {
  const it = construireIssueCreation('projet_test', 42, 'Une tâche', ['bridge', 'for-linux'],
    { timeout: 300, modele: 'claude-opus-4-8', modele_defaut: 'claude-sonnet-5' });
  assert.equal(it.projet, 'projet_test');
  assert.equal(it.number, 42);
  assert.equal(it.title, 'Une tâche');
  assert.equal(it.state, 'OPEN');
  assert.deepEqual(it.labels, ['bridge', 'for-linux']);
  assert.equal(it.modele, 'claude-opus-4-8');
  assert.equal(it.modele_defaut, 'claude-sonnet-5');
});

test('construireIssueCreation : modele/modele_defaut absents de timing → null (pas undefined)', () => {
  const it = construireIssueCreation('projet_test', 42, 'Une tâche', [], { timeout: 300 });
  assert.equal(it.modele, null);
  assert.equal(it.modele_defaut, null);
});

test('construireIssueCreation : timing absent (émetteur non enrichi) → repli sans planter', () => {
  const it = construireIssueCreation('projet_test', 42, 'Une tâche', [], null);
  assert.equal(it.modele, null);
  assert.equal(it.modele_defaut, null);
  assert.deepEqual(it.labels, []);
});

test('construireIssueCreation : titre absent → repli sur « #numero »', () => {
  const it = construireIssueCreation('projet_test', 42, '', null, {});
  assert.equal(it.title, '#42');
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

// ─── planifierEvenementSse : défense en profondeur projets inconnus (#635) ───
// Un événement /stream best-effort issu d'un projet fictif (ex. tests de
// watcher.py exécutant le vrai code, tests/test_worktree_parallelisation_337.py)
// doit être ignoré SANS toast, avant même de regarder son type.
test('planifierEvenementSse : projet inconnu ignoré (aucun toast)', () => {
  const etat = { issues: {} };
  const projetsConnus = ['bridge_agent', 'rummikub'];
  assert.deepEqual(
    planifierEvenementSse(etat, { type: 'fin_issue', projet: 'test611par', numero: 93375 }, projetsConnus),
    { action: 'ignorer', cle: 'test611par#93375', connue: false });
  assert.deepEqual(
    planifierEvenementSse(etat, { type: 'debut_issue', projet: 'test576max1', numero: 93761 }, projetsConnus),
    { action: 'ignorer', cle: 'test576max1#93761', connue: false });
  assert.deepEqual(
    planifierEvenementSse(etat, { type: 'creation_issue', projet: 'test576max2', numero: 93764 }, projetsConnus),
    { action: 'ignorer', cle: 'test576max2#93764', connue: false });
});

test('planifierEvenementSse : projet connu non affecté par le filtre', () => {
  const etat = { issues: {} };
  const projetsConnus = ['bridge_agent', 'rummikub'];
  assert.equal(
    planifierEvenementSse(etat, { type: 'fin_issue', projet: 'bridge_agent', numero: 1 }, projetsConnus).action,
    'fin');
});

test('planifierEvenementSse : sans liste de projets connus, comportement inchangé', () => {
  const etat = { issues: {} };
  assert.equal(planifierEvenementSse(etat, { type: 'fin_issue', projet: 'nimporte_quoi', numero: 1 }).action, 'fin');
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

// ─── fusionnerTimingProjet (issue #634 : décalage GitHub après création) ─────
test('fusionnerTimingProjet : issue récente absente de la réponse → conservée', () => {
  const ancienTiming = {
    'p#1': { timeout: 300, max_essais: 3, backoff: 5, debut: null, sans_limite: false, estimation: null },
  };
  // #1 vient d'être créée (5s), absente de la réponse (gh pas encore à jour) : conservée telle quelle.
  const issuesConnues = { 'p#1': { createdAt: ilYA(5) } };
  const timing = fusionnerTimingProjet(ancienTiming, 'p', [], issuesConnues, T0);
  assert.deepEqual(timing['p#1'], ancienTiming['p#1']);
});

test('fusionnerTimingProjet : issue fermée (absente, pas récente) → retirée', () => {
  const ancienTiming = {
    'p#1': { timeout: 300, max_essais: 3, backoff: 5, debut: ilYA(600), sans_limite: false, estimation: null },
  };
  // #1 créée il y a longtemps (au-delà de la fenêtre de récence), absente de
  // la réponse : /issues-en-attente ne renvoie plus les issues closes/needs-human.
  const issuesConnues = { 'p#1': { createdAt: ilYA(FENETRE_RECENTE_TIMING_MS / 1000 + 60) } };
  const timing = fusionnerTimingProjet(ancienTiming, 'p', [], issuesConnues, T0);
  assert.equal(timing['p#1'], undefined);
});

test('fusionnerTimingProjet : absente ET inconnue du store (jamais vue) → retirée par défaut', () => {
  const ancienTiming = { 'p#1': { timeout: 300, max_essais: 3, backoff: 5, debut: null,
                                   sans_limite: false, estimation: null } };
  const timing = fusionnerTimingProjet(ancienTiming, 'p', [], {}, T0);
  assert.equal(timing['p#1'], undefined);
});

test('fusionnerTimingProjet : présente dans la réponse → toujours remplacée par les données fraîches', () => {
  const ancienTiming = { 'p#1': { timeout: 300, max_essais: 3, backoff: 5, debut: null,
                                   sans_limite: false, estimation: null } };
  const liste = [{ number: 1, timeout: 300, max_essais: 3, backoff: 5,
                    debut: ilYA(30), sans_limite: false, estimation: { mediane: 120, n: 5, fiabilite: 'correct' } }];
  const timing = fusionnerTimingProjet(ancienTiming, 'p', liste, {}, T0);
  assert.equal(timing['p#1'].debut, ilYA(30));
  assert.deepEqual(timing['p#1'].estimation, { mediane: 120, n: 5, fiabilite: 'correct' });
});

test('fusionnerTimingProjet : n\'affecte jamais le timing des AUTRES projets', () => {
  const ancienTiming = {
    'p#1': { timeout: 300, max_essais: 3, backoff: 5, debut: null, sans_limite: false, estimation: null },
    'autre#9': { timeout: 300, max_essais: 3, backoff: 5, debut: null, sans_limite: false, estimation: null },
  };
  const timing = fusionnerTimingProjet(ancienTiming, 'p', [], {}, T0);
  assert.deepEqual(timing['autre#9'], ancienTiming['autre#9']);
});
