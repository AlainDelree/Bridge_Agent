// Tests de logique pure du module « case à cocher » (refonte étape 5b, issue #636).
// Aucune dépendance, aucun build, aucun DOM. Lancement (depuis la racine) :
//   node --test static/js/tests/
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  normaliserNumero,
  fusionnerCasesServeur,
  estCocheDansEtat,
  ajouterDansEtat,
  retirerDansEtat,
  decisionModeCopie,
  extraireCasesLegacy,
  premieresParProjet,
} from '../resultats_coches.js';

// ─── normaliserNumero ─────────────────────────────────────────────────────────
test('normaliserNumero : chaîne DOM → entier', () => {
  assert.equal(normaliserNumero('636'), 636);
  assert.equal(normaliserNumero(636), 636);
});

// ─── fusionnerCasesServeur ────────────────────────────────────────────────────
test('fusionnerCasesServeur : REMPLACE la liste du projet, dédoublonne, normalise', () => {
  const etat = { alpha: [1, 2] };
  const suivant = fusionnerCasesServeur(etat, 'alpha', ['3', 3, 4]);
  assert.deepEqual(suivant.alpha, [3, 4]);         // remplace (le serveur fait foi), dédoublonné
  assert.notEqual(suivant, etat);                  // immuable
});

test('fusionnerCasesServeur : conserve les AUTRES projets', () => {
  const etat = { alpha: [1], beta: [9] };
  const suivant = fusionnerCasesServeur(etat, 'alpha', [2]);
  assert.deepEqual(suivant.beta, [9]);
  assert.deepEqual(suivant.alpha, [2]);
});

test('fusionnerCasesServeur : liste vide/absente → tableau vide', () => {
  assert.deepEqual(fusionnerCasesServeur({}, 'x', []).x, []);
  assert.deepEqual(fusionnerCasesServeur(undefined, 'x', undefined).x, []);
});

// ─── estCocheDansEtat ─────────────────────────────────────────────────────────
test('estCocheDansEtat : compare en entier (tolère la chaîne DOM)', () => {
  const etat = { alpha: [1, 5] };
  assert.equal(estCocheDansEtat(etat, 'alpha', 5), true);
  assert.equal(estCocheDansEtat(etat, 'alpha', '5'), true);
  assert.equal(estCocheDansEtat(etat, 'alpha', 2), false);
  assert.equal(estCocheDansEtat(etat, 'inconnu', 1), false);
});

// ─── ajouter / retirer (immuables, idempotents) ───────────────────────────────
test('ajouterDansEtat : ajoute, idempotent, immuable', () => {
  const etat = { alpha: [1] };
  const a = ajouterDansEtat(etat, 'alpha', '2');
  assert.deepEqual(a.alpha, [1, 2]);
  assert.notEqual(a, etat);
  assert.equal(ajouterDansEtat(a, 'alpha', 2), a);   // déjà présent → même objet
});

test('ajouterDansEtat : crée le projet absent', () => {
  const a = ajouterDansEtat({}, 'neuf', 7);
  assert.deepEqual(a.neuf, [7]);
});

test('retirerDansEtat : retire, supprime la clé projet vidée, idempotent', () => {
  const etat = { alpha: [1, 2], beta: [9] };
  const r = retirerDansEtat(etat, 'alpha', 1);
  assert.deepEqual(r.alpha, [2]);
  const r2 = retirerDansEtat(r, 'alpha', 2);
  assert.equal('alpha' in r2, false);                // liste vidée → clé supprimée
  assert.deepEqual(r2.beta, [9]);
  assert.equal(retirerDansEtat(r2, 'alpha', 99), r2); // absent → même objet
});

// ─── decisionModeCopie ────────────────────────────────────────────────────────
test('decisionModeCopie : sécurisé + clipboard.write + ClipboardItem → moderne', () => {
  assert.equal(decisionModeCopie(true, { write: () => {} }, true), 'moderne');
});

test('decisionModeCopie : contexte non sécurisé (--lan) → repli', () => {
  assert.equal(decisionModeCopie(false, { write: () => {} }, true), 'repli');
});

test('decisionModeCopie : clipboard absent ou sans write → repli', () => {
  assert.equal(decisionModeCopie(true, null, true), 'repli');
  assert.equal(decisionModeCopie(true, { writeText: () => {} }, true), 'repli');
});

test('decisionModeCopie : ClipboardItem indisponible → repli', () => {
  assert.equal(decisionModeCopie(true, { write: () => {} }, false), 'repli');
});

// ─── extraireCasesLegacy (migration idempotente du localStorage) ──────────────
test('extraireCasesLegacy : ne retient que les clés resultat-coche:* = "1"', () => {
  const entrees = [
    { cle: 'resultat-coche:alpha:12', valeur: '1' },
    { cle: 'resultat-coche:beta:3', valeur: '1' },
    { cle: 'resultat-coche:alpha:99', valeur: '0' },   // valeur ≠ '1' → ignorée
    { cle: 'bridge_limite_issues_projet', valeur: '5' }, // autre clé → ignorée
    { cle: 'resultat-coche:mauvais', valeur: '1' },      // pas de numéro → ignorée
  ];
  const { cases, cles } = extraireCasesLegacy(entrees);
  assert.deepEqual(cases, [
    { projet: 'alpha', numero: 12 },
    { projet: 'beta', numero: 3 },
  ]);
  assert.deepEqual(cles, ['resultat-coche:alpha:12', 'resultat-coche:beta:3']);
});

test('extraireCasesLegacy : nom de projet contenant un « : » (découpe sur le dernier)', () => {
  const { cases } = extraireCasesLegacy([{ cle: 'resultat-coche:a:b:42', valeur: '1' }]);
  assert.deepEqual(cases, [{ projet: 'a:b', numero: 42 }]);
});

test('extraireCasesLegacy : numéro non entier ignoré, entrée vide tolérée', () => {
  const { cases } = extraireCasesLegacy([
    { cle: 'resultat-coche:alpha:abc', valeur: '1' },
    { cle: 'resultat-coche:alpha:', valeur: '1' },
  ]);
  assert.deepEqual(cases, []);
  assert.deepEqual(extraireCasesLegacy(undefined).cases, []);
});

// ─── premieresParProjet (périmètre pastilles = « Cocher tout ») ────────────────
test('premieresParProjet : borne aux N premières par projet (ordre conservé)', () => {
  const issues = [
    { projet: 'a', number: 5 }, { projet: 'b', number: 50 },
    { projet: 'a', number: 4 }, { projet: 'a', number: 3 },
    { projet: 'b', number: 49 },
  ];
  const r = premieresParProjet(issues, 2);
  assert.deepEqual(r.a, [5, 4]);   // 3 hors limite
  assert.deepEqual(r.b, [50, 49]);
});

test('premieresParProjet : limite Infinity → toutes les issues chargées (remise à zéro)', () => {
  const issues = [
    { projet: 'a', number: 1 }, { projet: 'a', number: 2 }, { projet: 'b', number: 3 },
  ];
  const r = premieresParProjet(issues, Infinity);
  assert.deepEqual(r.a, [1, 2]);
  assert.deepEqual(r.b, [3]);
});
