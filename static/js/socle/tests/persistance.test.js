// Tests de persistance.js avec un faux localStorage (issue #625, étape 1).
import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';

// Faux localStorage injecté AVANT tout appel (persistance résout le backend à
// l'exécution, pas à l'import).
class FauxStorage {
  constructor() { this.m = new Map(); }
  getItem(k) { return this.m.has(k) ? this.m.get(k) : null; }
  setItem(k, v) { this.m.set(k, String(v)); }
  removeItem(k) { this.m.delete(k); }
  key(i) { return Array.from(this.m.keys())[i] ?? null; }
  get length() { return this.m.size; }
}
globalThis.localStorage = new FauxStorage();

const p = await import('../persistance.js');

beforeEach(() => { globalThis.localStorage = new FauxStorage(); });

test('ecrire/lire round-trip JSON', () => {
  p.ecrire('k', { a: 1, b: [2, 3] });
  assert.deepEqual(p.lire('k'), { a: 1, b: [2, 3] });
});

test('lire renvoie le défaut si absent ou corrompu', () => {
  assert.equal(p.lire('absente', 'defaut'), 'defaut');
  globalThis.localStorage.setItem('cassee', '{pas du json');
  assert.equal(p.lire('cassee', 'repli'), 'repli');
});

test('lireTexte/ecrireTexte conservent le texte brut (clés historiques)', () => {
  p.ecrireTexte('bridge_projet_actif', 'scrabble');
  assert.equal(p.lireTexte('bridge_projet_actif'), 'scrabble');
  // lireTexte ne fait pas de JSON.parse : une valeur non-JSON reste lisible.
  assert.equal(p.lireTexte('bridge_projet_actif'), 'scrabble');
});

test('supprimer retire une clé', () => {
  p.ecrire('k', 1);
  p.supprimer('k');
  assert.equal(p.lire('k', null), null);
});

test('supprimerParPrefixe ne retire que le préfixe visé', () => {
  p.ecrireTexte('bridge_cache_detail_p_1', 'x');
  p.ecrireTexte('bridge_cache_detail_p_2', 'y');
  p.ecrireTexte('bridge_projet_actif', 'z');
  p.supprimerParPrefixe('bridge_cache_detail_');
  assert.equal(p.lireTexte('bridge_cache_detail_p_1'), null);
  assert.equal(p.lireTexte('bridge_cache_detail_p_2'), null);
  assert.equal(p.lireTexte('bridge_projet_actif'), 'z');
});

test('CLES documente les clés historiques attendues', () => {
  assert.equal(p.CLES.projetActif, 'bridge_projet_actif');
  assert.equal(p.CLES.prefixeCacheDetail, 'bridge_cache_detail_');
});
