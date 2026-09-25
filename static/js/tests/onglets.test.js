// Tests de la logique pure de onglets.js (issue #626, étape 2).
// activerOnglet()/initialiserOnglets() touchent le DOM (querySelectorAll,
// classList) et sont vérifiés manuellement dans le navigateur (voir
// VERIFICATIONS_MANUELLES.md) : Node n'a pas de document. On ne teste ici que
// initialisationsPour(), pure et indépendante du DOM.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { initialisationsPour } from '../onglets.js';

test('resultats : initialisation identique à celle du clic actuel', () => {
  assert.deepEqual(initialisationsPour('resultats'),
    ['chargerListeIssues', 'demarrerTempsRestant', 'demarrerPanneauLateral']);
});

test('un onglet non-resultats arrête le temps restant et le panneau latéral', () => {
  assert.deepEqual(initialisationsPour('creation'),
    ['arreterTempsRestant', 'arreterPanneauLateral']);
});

test('journal : arrêt resultats + démarrage du journal', () => {
  assert.deepEqual(initialisationsPour('journal'),
    ['arreterTempsRestant', 'arreterPanneauLateral', 'demarrerJournal']);
});

test('config : arrêt resultats + chargement de la config', () => {
  assert.deepEqual(initialisationsPour('config'),
    ['arreterTempsRestant', 'arreterPanneauLateral', 'chargerConfig']);
});

test('ccw : arrêt resultats + ouverture de l\'onglet CCW', () => {
  assert.deepEqual(initialisationsPour('ccw'),
    ['arreterTempsRestant', 'arreterPanneauLateral', 'ccwOuvrirOnglet']);
});

test('inbox : arrêt resultats + rafraîchissement de l\'inbox', () => {
  assert.deepEqual(initialisationsPour('inbox'),
    ['arreterTempsRestant', 'arreterPanneauLateral', 'rafraichirInbox']);
});

test('aucune trace de l\'onglet Watchers, supprimé (issue #626)', () => {
  assert.deepEqual(initialisationsPour('watchers'),
    ['arreterTempsRestant', 'arreterPanneauLateral']);
});
