// Tests de logique pure de l'alerte explicite de panne GitHub, issue #732.
// Aucune dépendance au DOM ni au réseau : seules les fonctions PURES
// exportées par static/js/socle/panne_github.js sont testées ici — la
// vérification réelle (fetch /github-statut, toasts, polling 60s) est
// vérifiée manuellement (voir VERIFICATIONS_MANUELLES.md).
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  doitDeclencherVerification,
  calculerTransition,
  calculerTypeToast,
  extraireJsonErreur,
} from '../socle/panne_github.js';

// ─── doitDeclencherVerification ─────────────────────────────────────────────

test('doitDeclencherVerification : vrai seulement si panne_probable:true', () => {
  assert.equal(doitDeclencherVerification({ panne_probable: true }), true);
  assert.equal(doitDeclencherVerification({ panne_probable: false }), false);
});

test('doitDeclencherVerification : absent, null ou réponse normale → faux (jamais sur 404/401/422)', () => {
  assert.equal(doitDeclencherVerification({ erreur: 'Projet introuvable.' }), false);
  assert.equal(doitDeclencherVerification(null), false);
  assert.equal(doitDeclencherVerification(undefined), false);
  assert.equal(doitDeclencherVerification({}), false);
});

// ─── calculerTransition ──────────────────────────────────────────────────────

test('calculerTransition : panne → plus de panne = message de rétablissement', () => {
  assert.equal(calculerTransition(true, false), 'GitHub est rétabli.');
});

test('calculerTransition : pas de transition (toujours en panne, ou jamais en panne) → null', () => {
  assert.equal(calculerTransition(true, true), null);
  assert.equal(calculerTransition(false, false), null);
  assert.equal(calculerTransition(false, true), null);   // début d'incident, pas un rétablissement
});

// ─── calculerTypeToast ───────────────────────────────────────────────────────

test('calculerTypeToast : gravité "ok" (cause locale) → avertissement', () => {
  assert.equal(calculerTypeToast('ok'), 'avertissement');
});

test('calculerTypeToast : incident ou page injoignable → erreur', () => {
  assert.equal(calculerTypeToast('incident'), 'erreur');
  assert.equal(calculerTypeToast('injoignable'), 'erreur');
});

// ─── extraireJsonErreur ──────────────────────────────────────────────────────

test('extraireJsonErreur : reparse le corps texte d\'une ErreurApi (socle/api.js)', () => {
  const erreurApi = { corps: '{"erreur":"HTTP 502","panne_probable":true}' };
  assert.deepEqual(extraireJsonErreur(erreurApi), { erreur: 'HTTP 502', panne_probable: true });
});

test('extraireJsonErreur : corps absent, vide ou non-JSON → null, jamais levé', () => {
  assert.equal(extraireJsonErreur(null), null);
  assert.equal(extraireJsonErreur({}), null);
  assert.equal(extraireJsonErreur({ corps: '' }), null);
  assert.equal(extraireJsonErreur({ corps: 'pas du json' }), null);
});
