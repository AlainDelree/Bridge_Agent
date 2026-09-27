// Tests de logique pure de l'onglet CCW (issue #649, refonte web — sorti
// d'app.js). Aucune dépendance au DOM ni au réseau — voir
// static/js/tests/README.md pour lancer ces tests (node --test).
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  couleurEtatCcw,
  libelleTopicCcw,
  afficherBoutonDemarrer,
  afficherBoutonArreter,
  selectionRestauree,
  ccwViderChampsFinalisation,
} from '../ccw.js';

// ─── couleurEtatCcw ─────────────────────────────────────────────────────────

test('couleurEtatCcw : running → vert, stopped → rouge, autre → gris', () => {
  assert.equal(couleurEtatCcw('running'), '#2e8b57');
  assert.equal(couleurEtatCcw('stopped'), '#c0392b');
  assert.equal(couleurEtatCcw('inconnu'), '#888');
  assert.equal(couleurEtatCcw(undefined), '#888');
});

// ─── libelleTopicCcw ────────────────────────────────────────────────────────

test('libelleTopicCcw : placeholder → avertissement à définir', () => {
  assert.deepEqual(libelleTopicCcw('placeholder'), { texte: '⚠ à définir', couleur: '#e0a800' });
});

test('libelleTopicCcw : ok → renseigné', () => {
  assert.deepEqual(libelleTopicCcw('ok'), { texte: '✓ renseigné', couleur: '#2e8b57' });
});

test('libelleTopicCcw : autre/absent → inconnu', () => {
  assert.deepEqual(libelleTopicCcw(undefined), { texte: '? inconnu', couleur: '#888' });
  assert.deepEqual(libelleTopicCcw('autre'), { texte: '? inconnu', couleur: '#888' });
});

// ─── afficherBoutonDemarrer / afficherBoutonArreter (issue #203) ───────────

test('afficherBoutonDemarrer : caché seulement si déjà running', () => {
  assert.equal(afficherBoutonDemarrer('running'), false);
  assert.equal(afficherBoutonDemarrer('stopped'), true);
  assert.equal(afficherBoutonDemarrer(undefined), true);
});

test('afficherBoutonArreter : caché seulement si déjà stopped', () => {
  assert.equal(afficherBoutonArreter('stopped'), false);
  assert.equal(afficherBoutonArreter('running'), true);
  assert.equal(afficherBoutonArreter(undefined), true);
});

// ─── selectionRestauree ─────────────────────────────────────────────────────

test('selectionRestauree : conserve la sélection si le projet existe toujours', () => {
  assert.equal(selectionRestauree(['alchess', 'scrabble'], 'scrabble'), 'scrabble');
});

test('selectionRestauree : repasse au placeholder si le projet a disparu', () => {
  assert.equal(selectionRestauree(['alchess', 'scrabble'], 'ecole'), '');
  assert.equal(selectionRestauree([], ''), '');
});

// ─── ccwViderChampsFinalisation (issue #666) ───────────────────────────────
// DOM minimal (pas de vrai navigateur) : trois éléments <input>/<select>
// factices, seul .value compte pour cette fonction.

test('ccwViderChampsFinalisation : vide topic + GH_TOKEN + OAUTH_TOKEN', () => {
  const champs = {
    'ccw-fin-topic': { value: 'ancien-topic' },
    'ccw-fin-gh':    { value: 'ancien-gh-token' },
    'ccw-fin-oauth': { value: 'ancien-oauth-token' },
  };
  const documentPrecedent = global.document;
  global.document = { getElementById: (id) => champs[id] };
  try {
    ccwViderChampsFinalisation();
    assert.equal(champs['ccw-fin-topic'].value, '');
    assert.equal(champs['ccw-fin-gh'].value, '');
    assert.equal(champs['ccw-fin-oauth'].value, '');
  } finally {
    global.document = documentPrecedent;
  }
});
