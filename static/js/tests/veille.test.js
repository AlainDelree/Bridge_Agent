// Tests de logique pure de static/js/veille.js (issue #917, revu par #933) :
// bascule en veille après inactivité, borne du seul réglage restant (délai de
// veille), regroupement des doublons de fin_issue, décision de rouvrir le
// flux /stream selon l'ancienneté du dernier message, ancienneté de synchro.
// L'orchestration DOM (voile réel, absorption du premier clic/touche,
// minuteurs) n'est PAS testable sans navigateur — voir
// VERIFICATIONS_MANUELLES.md.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  DEFAUT_DELAI_VEILLE_MIN,
  RATTRAPAGE_CREATION_SEC,
  FENETRE_REGROUPEMENT_FIN_MS,
  INTERVALLE_BATTEMENT_STREAM_SEC,
  SEUIL_STREAM_SILENCIEUX_MS,
  normaliserDelaiVeilleMin,
  doitEntrerEnVeille,
  doitRechargerSurFin,
  fautRouvrirStream,
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

// ─── RATTRAPAGE_CREATION_SEC (issue #933 : valeur FIXE, plus un réglage) ────
test('RATTRAPAGE_CREATION_SEC : valeur fixe attendue (10s)', () => {
  assert.equal(RATTRAPAGE_CREATION_SEC, 10);
});

// ─── doitRechargerSurFin (issue #933 point 2 : regroupement des doublons) ───
test('doitRechargerSurFin : premier fin_issue connu pour cette issue → recharge', () => {
  assert.equal(doitRechargerSurFin(null, T0), true);
  assert.equal(doitRechargerSurFin(undefined, T0), true);
});

test('doitRechargerSurFin : doublon rapproché (sous la fenêtre) → pas de second rechargement', () => {
  assert.equal(doitRechargerSurFin(T0 - 500, T0, FENETRE_REGROUPEMENT_FIN_MS), false);
  assert.equal(doitRechargerSurFin(T0 - (FENETRE_REGROUPEMENT_FIN_MS - 1), T0, FENETRE_REGROUPEMENT_FIN_MS), false);
});

test('doitRechargerSurFin : au-delà de la fenêtre → nouveau rechargement autorisé', () => {
  assert.equal(doitRechargerSurFin(T0 - FENETRE_REGROUPEMENT_FIN_MS, T0, FENETRE_REGROUPEMENT_FIN_MS), true);
  assert.equal(doitRechargerSurFin(T0 - 10000, T0, FENETRE_REGROUPEMENT_FIN_MS), true);
});

// ─── fautRouvrirStream (issue #933 point 4) ──────────────────────────────────
test('fautRouvrirStream : aucune activité connue (null) → rouvrir', () => {
  assert.equal(fautRouvrirStream(null), true);
});

test('fautRouvrirStream : sous le seuil (3x l\'intervalle des battements) → pas besoin', () => {
  assert.equal(fautRouvrirStream(SEUIL_STREAM_SILENCIEUX_MS - 1), false);
  assert.equal(fautRouvrirStream(0), false);
});

test('fautRouvrirStream : au seuil ou au-delà → rouvrir', () => {
  assert.equal(fautRouvrirStream(SEUIL_STREAM_SILENCIEUX_MS), true);
  assert.equal(fautRouvrirStream(SEUIL_STREAM_SILENCIEUX_MS + 60000), true);
});

test('fautRouvrirStream : seuil = 3x l\'intervalle réel des battements serveur (30s)', () => {
  assert.equal(INTERVALLE_BATTEMENT_STREAM_SEC, 30);
  assert.equal(SEUIL_STREAM_SILENCIEUX_MS, 90000);
});

// ─── estSyncAncienne ──────────────────────────────────────────────────────────
test('estSyncAncienne : jamais synchronisé (null) → ancienne', () => {
  assert.equal(estSyncAncienne(null, T0), true);
});

test('estSyncAncienne : sous le seuil → pas ancienne', () => {
  assert.equal(estSyncAncienne(T0 - (SEUIL_STREAM_SILENCIEUX_MS - 1), T0), false);
});

test('estSyncAncienne : au seuil ou au-delà → ancienne', () => {
  assert.equal(estSyncAncienne(T0 - SEUIL_STREAM_SILENCIEUX_MS, T0), true);
  assert.equal(estSyncAncienne(T0 - 600 * 1000, T0), true);
});

test('estSyncAncienne : seuil personnalisé respecté', () => {
  assert.equal(estSyncAncienne(T0 - 119 * 1000, T0, 120000), false);
  assert.equal(estSyncAncienne(T0 - 120 * 1000, T0, 120000), true);
});
