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
  planifierPoseTokenTous,
  resumerResultatsPoseTokenTous,
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

// ─── planifierPoseTokenTous / resumerResultatsPoseTokenTous (issue #743) ───

const PROJETS_TROIS = [{ projet: 'Alchess' }, { projet: 'Scrabble' }, { projet: 'Rummikub' }];

test('planifierPoseTokenTous : service occupé (enCours > 0) → sauté, jamais posé', () => {
  const resume = { Alchess: { enCours: 1, enFile: 0 }, Scrabble: { enCours: 0, enFile: 0 }, Rummikub: { enCours: 0, enFile: 2 } };
  const plan = planifierPoseTokenTous(PROJETS_TROIS, resume, false);
  assert.deepEqual(plan.map(e => e.action), ['sauter', 'poser', 'poser']);
  assert.match(plan[0].raison, /occupé/);
  assert.equal(plan[0].indetermine, false);
});

test('planifierPoseTokenTous : état indéterminable (resume absent) → sauté par défaut', () => {
  const resume = { Alchess: null, Scrabble: { enCours: 0, enFile: 0 }, Rummikub: undefined };
  const plan = planifierPoseTokenTous(PROJETS_TROIS, resume, false);
  assert.deepEqual(plan.map(e => e.action), ['sauter', 'poser', 'sauter']);
  assert.equal(plan[0].indetermine, true);
  assert.equal(plan[2].indetermine, true);
});

test('planifierPoseTokenTous : état indéterminable + confirmation explicite → posé', () => {
  const resume = { Alchess: null, Scrabble: { enCours: 0, enFile: 0 }, Rummikub: undefined };
  const plan = planifierPoseTokenTous(PROJETS_TROIS, resume, true);
  assert.deepEqual(plan.map(e => e.action), ['poser', 'poser', 'poser']);
});

test('planifierPoseTokenTous : occupé l\'emporte même avec confirmation des indéterminés', () => {
  const resume = { Alchess: { enCours: 2, enFile: 0 }, Scrabble: { enCours: 0, enFile: 0 }, Rummikub: { enCours: 0, enFile: 0 } };
  const plan = planifierPoseTokenTous(PROJETS_TROIS, resume, true);
  assert.equal(plan[0].action, 'sauter');
  assert.match(plan[0].raison, /occupé/);
});

test('resumerResultatsPoseTokenTous : décompte par statut, aucune valeur de jeton dans le résultat', () => {
  const resultats = [
    { projet: 'Alchess',  statut: 'OK',          detail: '' },
    { projet: 'Scrabble', statut: 'à vérifier',  detail: 'log suspect' },
    { projet: 'Rummikub', statut: 'échec',       detail: 'Erreur réseau' },
    { projet: 'Ecole',    statut: 'sauté',       detail: 'occupé (1 issue(s) en cours)' },
  ];
  assert.deepEqual(resumerResultatsPoseTokenTous(resultats),
    { OK: 1, 'à vérifier': 1, 'échec': 1, 'sauté': 1 });
});

test('resumerResultatsPoseTokenTous : liste vide → tous les compteurs à 0', () => {
  assert.deepEqual(resumerResultatsPoseTokenTous([]),
    { OK: 0, 'à vérifier': 0, 'échec': 0, 'sauté': 0 });
});
