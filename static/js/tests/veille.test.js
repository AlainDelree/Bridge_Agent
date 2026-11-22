// Tests de logique pure de static/js/veille.js (issue #917) : bascule en
// veille après inactivité, valeurs par défaut/bornes des réglages,
// reprogrammation après erreur avec attente croissante plafonnée, coût
// GitHub indicatif, ancienneté de synchro. L'orchestration DOM (voile réel,
// absorption du premier clic/touche, minuteurs) n'est PAS testable sans
// navigateur — voir VERIFICATIONS_MANUELLES.md.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  DEFAUT_DELAI_VEILLE_MIN,
  DEFAUT_INTERVALLE_RAFRAICHISSEMENT_SEC,
  MIN_INTERVALLE_RAFRAICHISSEMENT_SEC,
  DEFAUT_DELAI_RATTRAPAGE_SEC,
  PLAFOND_ATTENTE_ECHEC_MS,
  APPELS_GH_PAR_CYCLE,
  normaliserDelaiVeilleMin,
  normaliserIntervalleRafraichissementSec,
  normaliserDelaiRattrapageSec,
  doitEntrerEnVeille,
  prochainDelaiMs,
  calculerCoutGithubParHeure,
  estSyncAncienne,
} from '../veille.js';

const T0 = new Date('2026-11-22T12:00:00Z').getTime();

// ─── normaliserDelaiVeilleMin ────────────────────────────────────────────────
test('normaliserDelaiVeilleMin : valeur absente/invalide → défaut (30)', () => {
  assert.equal(normaliserDelaiVeilleMin(undefined), DEFAUT_DELAI_VEILLE_MIN);
  assert.equal(normaliserDelaiVeilleMin(null), DEFAUT_DELAI_VEILLE_MIN);
  assert.equal(normaliserDelaiVeilleMin('abc'), DEFAUT_DELAI_VEILLE_MIN);
  assert.equal(normaliserDelaiVeilleMin(NaN), DEFAUT_DELAI_VEILLE_MIN);
  assert.equal(normaliserDelaiVeilleMin(-5), DEFAUT_DELAI_VEILLE_MIN);
});

test('normaliserDelaiVeilleMin : 0 est une valeur valide (désactive la veille)', () => {
  assert.equal(normaliserDelaiVeilleMin(0), 0);
  assert.equal(normaliserDelaiVeilleMin('0'), 0);
});

test('normaliserDelaiVeilleMin : valeur valide arrondie', () => {
  assert.equal(normaliserDelaiVeilleMin(45), 45);
  assert.equal(normaliserDelaiVeilleMin('10.6'), 11);
});

// ─── normaliserIntervalleRafraichissementSec ─────────────────────────────────
test('normaliserIntervalleRafraichissementSec : valeur absente/invalide → défaut (60)', () => {
  assert.equal(normaliserIntervalleRafraichissementSec(undefined), DEFAUT_INTERVALLE_RAFRAICHISSEMENT_SEC);
  assert.equal(normaliserIntervalleRafraichissementSec('x'), DEFAUT_INTERVALLE_RAFRAICHISSEMENT_SEC);
  assert.equal(normaliserIntervalleRafraichissementSec(0), DEFAUT_INTERVALLE_RAFRAICHISSEMENT_SEC);
  assert.equal(normaliserIntervalleRafraichissementSec(-10), DEFAUT_INTERVALLE_RAFRAICHISSEMENT_SEC);
});

test('normaliserIntervalleRafraichissementSec : plancher à 15s, jamais rejeté vers le défaut', () => {
  assert.equal(normaliserIntervalleRafraichissementSec(5), MIN_INTERVALLE_RAFRAICHISSEMENT_SEC);
  assert.equal(normaliserIntervalleRafraichissementSec(15), 15);
  assert.equal(normaliserIntervalleRafraichissementSec(120), 120);
});

// ─── normaliserDelaiRattrapageSec ────────────────────────────────────────────
test('normaliserDelaiRattrapageSec : valeur absente/invalide → défaut (10)', () => {
  assert.equal(normaliserDelaiRattrapageSec(undefined), DEFAUT_DELAI_RATTRAPAGE_SEC);
  assert.equal(normaliserDelaiRattrapageSec(0), DEFAUT_DELAI_RATTRAPAGE_SEC);
  assert.equal(normaliserDelaiRattrapageSec(-3), DEFAUT_DELAI_RATTRAPAGE_SEC);
});

test('normaliserDelaiRattrapageSec : valeur valide conservée (plancher à 1s)', () => {
  assert.equal(normaliserDelaiRattrapageSec(1), 1);
  assert.equal(normaliserDelaiRattrapageSec(20), 20);
});

// ─── doitEntrerEnVeille ───────────────────────────────────────────────────────
test('doitEntrerEnVeille : delaiVeilleMin <= 0 → jamais de veille', () => {
  assert.equal(doitEntrerEnVeille(T0 - 10 * 60000, T0, 0), false);
  assert.equal(doitEntrerEnVeille(T0 - 999 * 60000, T0, -1), false);
});

test('doitEntrerEnVeille : aucune activité connue (null) → pas de veille', () => {
  assert.equal(doitEntrerEnVeille(null, T0, 30), false);
});

test('doitEntrerEnVeille : sous le délai réglé → pas encore', () => {
  assert.equal(doitEntrerEnVeille(T0 - 29 * 60000, T0, 30), false);
});

test('doitEntrerEnVeille : délai atteint ou dépassé → veille', () => {
  assert.equal(doitEntrerEnVeille(T0 - 30 * 60000, T0, 30), true);
  assert.equal(doitEntrerEnVeille(T0 - 45 * 60000, T0, 30), true);
});

// ─── prochainDelaiMs ──────────────────────────────────────────────────────────
test('prochainDelaiMs : aucun échec → délai normal', () => {
  assert.equal(prochainDelaiMs(0, 60000), 60000);
  assert.equal(prochainDelaiMs(undefined, 60000), 60000);
});

test('prochainDelaiMs : attente croissante (doublement) après chaque échec', () => {
  assert.equal(prochainDelaiMs(1, 60000), 120000);
  assert.equal(prochainDelaiMs(2, 60000), 240000);
  assert.equal(prochainDelaiMs(3, 60000), 480000);
});

test('prochainDelaiMs : plafonnée, jamais d\'arrêt définitif', () => {
  assert.equal(prochainDelaiMs(10, 60000), PLAFOND_ATTENTE_ECHEC_MS);
  assert.equal(prochainDelaiMs(50, 60000), PLAFOND_ATTENTE_ECHEC_MS);   // pas d'explosion numérique
  assert.ok(Number.isFinite(prochainDelaiMs(1000, 60000)));
});

test('prochainDelaiMs : plafond personnalisé respecté', () => {
  assert.equal(prochainDelaiMs(5, 60000, 90000), 90000);
});

// ─── calculerCoutGithubParHeure ──────────────────────────────────────────────
test('calculerCoutGithubParHeure : défauts (60s, 1 projet) → 2 appels/cycle × 60 cycles/h', () => {
  assert.equal(calculerCoutGithubParHeure(60, 1), APPELS_GH_PAR_CYCLE * 60);
});

test('calculerCoutGithubParHeure : plusieurs projets sélectionnés → coût multiplié', () => {
  assert.equal(calculerCoutGithubParHeure(60, 3), APPELS_GH_PAR_CYCLE * 60 * 3);
});

test('calculerCoutGithubParHeure : intervalle plus long → coût réduit', () => {
  assert.ok(calculerCoutGithubParHeure(120, 1) < calculerCoutGithubParHeure(60, 1));
});

test('calculerCoutGithubParHeure : intervalle invalide → 0, jamais une exception', () => {
  assert.equal(calculerCoutGithubParHeure(0, 1), 0);
  assert.equal(calculerCoutGithubParHeure(-5, 1), 0);
});

// ─── estSyncAncienne ──────────────────────────────────────────────────────────
test('estSyncAncienne : jamais synchronisé (null) → ancienne', () => {
  assert.equal(estSyncAncienne(null, T0, 60), true);
});

test('estSyncAncienne : sous 3x l\'intervalle → pas ancienne', () => {
  assert.equal(estSyncAncienne(T0 - 179 * 1000, T0, 60), false);
});

test('estSyncAncienne : à 3x l\'intervalle ou au-delà → ancienne', () => {
  assert.equal(estSyncAncienne(T0 - 180 * 1000, T0, 60), true);
  assert.equal(estSyncAncienne(T0 - 600 * 1000, T0, 60), true);
});

test('estSyncAncienne : facteur personnalisé respecté', () => {
  assert.equal(estSyncAncienne(T0 - 119 * 1000, T0, 60, 2), false);
  assert.equal(estSyncAncienne(T0 - 120 * 1000, T0, 60, 2), true);
});
