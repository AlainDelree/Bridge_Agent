// Tests de la logique pure de onglets.js (issue #626, étape 2 ; mis à jour
// issue #632). activerOnglet()/initialiserOnglets() touchent le DOM
// (querySelectorAll, classList) et sont vérifiés manuellement dans le
// navigateur (voir VERIFICATIONS_MANUELLES.md) : Node n'a pas de document. On
// ne teste ici que initialisationsPour(), pure et indépendante du DOM.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { initialisationsPour } from '../onglets.js';

test('resultats : plus aucun appel pont — le module réagit lui-même au store (issue #632)', () => {
  assert.deepEqual(initialisationsPour('resultats'), []);
});

test('un onglet non listé (ex. creation) ne déclenche aucun appel pont', () => {
  assert.deepEqual(initialisationsPour('creation'), []);
});

test('journal : démarrage du journal', () => {
  assert.deepEqual(initialisationsPour('journal'), ['demarrerJournal']);
});

test('config : chargement de la config', () => {
  assert.deepEqual(initialisationsPour('config'), ['chargerConfig']);
});

test('ccw : ouverture de l\'onglet CCW', () => {
  assert.deepEqual(initialisationsPour('ccw'), ['ccwOuvrirOnglet']);
});

test('inbox : onglet supprimé (issue #639), plus aucune initialisation', () => {
  assert.deepEqual(initialisationsPour('inbox'), []);
});

test('aucune trace de l\'onglet Watchers, supprimé (issue #626)', () => {
  assert.deepEqual(initialisationsPour('watchers'), []);
});
