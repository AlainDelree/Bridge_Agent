// Tests de logique pure des actions sur la ligne d'une issue OUVERTE (issue
// #641, refonte web étape 6). Aucune dépendance au DOM ni au réseau — voir
// static/js/tests/README.md pour lancer ces tests (node --test).
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  actionLigneOuverte,
  sonIssueDepuisReponse,
  normaliserChoixSonIssue,
  etatsOptionsSonIssue,
  fusionnerSonsProjet,
  sonConnuDansCache,
} from '../actions_ligne.js';

// ─── actionLigneOuverte : quelle action afficher selon les labels ──────────

test('actionLigneOuverte : needs-human → "needs-human" (prime sur tout)', () => {
  assert.equal(actionLigneOuverte(['needs-human']), 'needs-human');
  assert.equal(actionLigneOuverte(['mode_write', 'needs-human']), 'needs-human');
});

test('actionLigneOuverte : mode_write seul (sans needs-human) → "interrompre"', () => {
  assert.equal(actionLigneOuverte(['mode_write']), 'interrompre');
  assert.equal(actionLigneOuverte(['for-linux', 'mode_write']), 'interrompre');
});

test('actionLigneOuverte : done seul, ou aucun label pertinent → null (pas d\'action)', () => {
  assert.equal(actionLigneOuverte(['done']), null);
  assert.equal(actionLigneOuverte(['for-linux']), null);
  assert.equal(actionLigneOuverte([]), null);
  assert.equal(actionLigneOuverte(undefined), null);
});

test('actionLigneOuverte : accepte des labels objets {name} comme des chaînes', () => {
  assert.equal(actionLigneOuverte([{ name: 'needs-human' }]), 'needs-human');
  assert.equal(actionLigneOuverte([{ name: 'mode_write' }]), 'interrompre');
});

// ─── Son PAR ISSUE (issue #630/#637, réutilisées telles quelles) ──────────

test('sonIssueDepuisReponse : {son: "plat"} → "plat"', () => {
  assert.equal(sonIssueDepuisReponse({ son: 'plat' }), 'plat');
});

test('sonIssueDepuisReponse : {son: "cloche"} → "cloche"', () => {
  assert.equal(sonIssueDepuisReponse({ son: 'cloche' }), 'cloche');
});

test('sonIssueDepuisReponse : réponse absente/vide/valeur inconnue → null', () => {
  assert.equal(sonIssueDepuisReponse(null), null);
  assert.equal(sonIssueDepuisReponse(undefined), null);
  assert.equal(sonIssueDepuisReponse({}), null);
  assert.equal(sonIssueDepuisReponse({ son: 'autre-chose' }), null);
});

test('normaliserChoixSonIssue : "plat"/"cloche" inchangés, "" et valeur inattendue → null', () => {
  assert.equal(normaliserChoixSonIssue('plat'), 'plat');
  assert.equal(normaliserChoixSonIssue('cloche'), 'cloche');
  assert.equal(normaliserChoixSonIssue(''), null);
  assert.equal(normaliserChoixSonIssue('autre-chose'), null);
  assert.equal(normaliserChoixSonIssue(undefined), null);
});

test('etatsOptionsSonIssue : un seul état actif à la fois, "Global" par défaut', () => {
  assert.deepEqual(etatsOptionsSonIssue(null), { global: true, plat: false, cloche: false });
  assert.deepEqual(etatsOptionsSonIssue('plat'), { global: false, plat: true, cloche: false });
  assert.deepEqual(etatsOptionsSonIssue('cloche'), { global: false, plat: false, cloche: true });
});

// ─── Cache du son par projet (GET /son-issue/<projet> en bloc, issue #641) ─

test('fusionnerSonsProjet : ne retient que les valeurs "plat"/"cloche"', () => {
  const cache = fusionnerSonsProjet({}, 'bridge_agent', { 630: 'cloche', 631: 'plat', 632: 'autre', 633: null });
  assert.deepEqual(cache, { bridge_agent: { '630': 'cloche', '631': 'plat' } });
});

test('fusionnerSonsProjet : REMPLACE le projet concerné, conserve les autres', () => {
  const avant = { proj_a: { '1': 'cloche' }, proj_b: { '2': 'plat' } };
  const apres = fusionnerSonsProjet(avant, 'proj_a', { 1: 'plat', 3: 'cloche' });
  assert.deepEqual(apres, { proj_a: { '1': 'plat', '3': 'cloche' }, proj_b: { '2': 'plat' } });
});

test('sonConnuDansCache : lit un choix connu ou retombe sur null (suit le global)', () => {
  const cache = { bridge_agent: { '630': 'cloche' } };
  assert.equal(sonConnuDansCache(cache, 'bridge_agent', 630), 'cloche');
  assert.equal(sonConnuDansCache(cache, 'bridge_agent', '630'), 'cloche');
  assert.equal(sonConnuDansCache(cache, 'bridge_agent', 631), null);
  assert.equal(sonConnuDansCache(cache, 'autre_projet', 630), null);
  assert.equal(sonConnuDansCache(null, 'bridge_agent', 630), null);
});
