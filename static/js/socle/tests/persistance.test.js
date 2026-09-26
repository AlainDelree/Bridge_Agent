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

test('toutesLesEntrees renvoie chaque clé avec sa valeur brute', () => {
  p.ecrireTexte('bridge_projet_actif', 'scrabble');
  p.ecrireTexte('resultat-coche:scrabble:12', '1');
  const entrees = p.toutesLesEntrees();
  assert.deepEqual(new Set(entrees.map(e => e.cle)),
    new Set(['bridge_projet_actif', 'resultat-coche:scrabble:12']));
  assert.equal(entrees.find(e => e.cle === 'bridge_projet_actif').valeur, 'scrabble');
});

// ─── Sélection des clés de cache détail à purger (issue #644) ─────────────

test('clesCacheDetailPourProjets ne retient que les projets donnés', () => {
  const cles = [
    'bridge_cache_detail_scrabble_1',
    'bridge_cache_detail_scrabble_2',
    'bridge_cache_detail_autre_3',
    'bridge_projet_actif',
  ];
  assert.deepEqual(p.clesCacheDetailPourProjets(cles, ['scrabble']),
    ['bridge_cache_detail_scrabble_1', 'bridge_cache_detail_scrabble_2']);
  assert.deepEqual(p.clesCacheDetailPourProjets(cles, []), []);
  assert.deepEqual(
    new Set(p.clesCacheDetailPourProjets(cles, ['scrabble', 'autre'])),
    new Set(['bridge_cache_detail_scrabble_1', 'bridge_cache_detail_scrabble_2', 'bridge_cache_detail_autre_3']));
});

test('clesCacheDetailPourProjets ne confond pas deux projets à préfixe commun', () => {
  const cles = ['bridge_cache_detail_scrabble2_1', 'bridge_cache_detail_scrabble_1'];
  assert.deepEqual(p.clesCacheDetailPourProjets(cles, ['scrabble']),
    ['bridge_cache_detail_scrabble_1']);
});

test('clesCacheDetailHorsProjets retient les projets absents des actifs', () => {
  const cles = [
    'bridge_cache_detail_scrabble_1',
    'bridge_cache_detail_autre_3',
    'bridge_projet_actif',
  ];
  assert.deepEqual(p.clesCacheDetailHorsProjets(cles, ['scrabble']),
    ['bridge_cache_detail_autre_3']);
  // Aucun projet actif → tout le cache détail est « hors projets ».
  assert.deepEqual(
    new Set(p.clesCacheDetailHorsProjets(cles, [])),
    new Set(['bridge_cache_detail_scrabble_1', 'bridge_cache_detail_autre_3']));
  // Tous les projets actifs → rien à purger.
  assert.deepEqual(p.clesCacheDetailHorsProjets(cles, ['scrabble', 'autre']), []);
});

test('purgerCacheDetailProjets(null) purge tout le cache détail', () => {
  p.ecrireTexte('bridge_cache_detail_scrabble_1', 'x');
  p.ecrireTexte('bridge_cache_detail_autre_2', 'y');
  p.ecrireTexte('bridge_projet_actif', 'scrabble');
  p.purgerCacheDetailProjets(null);
  assert.equal(p.lireTexte('bridge_cache_detail_scrabble_1'), null);
  assert.equal(p.lireTexte('bridge_cache_detail_autre_2'), null);
  assert.equal(p.lireTexte('bridge_projet_actif'), 'scrabble');
});

test('purgerCacheDetailProjets(noms) purge seulement les projets donnés', () => {
  p.ecrireTexte('bridge_cache_detail_scrabble_1', 'x');
  p.ecrireTexte('bridge_cache_detail_autre_2', 'y');
  p.purgerCacheDetailProjets(['scrabble']);
  assert.equal(p.lireTexte('bridge_cache_detail_scrabble_1'), null);
  assert.equal(p.lireTexte('bridge_cache_detail_autre_2'), 'y');
});

test('purgerCacheDetailHorsProjets épargne les projets actifs', () => {
  p.ecrireTexte('bridge_cache_detail_scrabble_1', 'x');
  p.ecrireTexte('bridge_cache_detail_autre_2', 'y');
  p.purgerCacheDetailHorsProjets(['scrabble']);
  assert.equal(p.lireTexte('bridge_cache_detail_scrabble_1'), 'x');
  assert.equal(p.lireTexte('bridge_cache_detail_autre_2'), null);
});

test('purgerProjet retire le cache détail ET l\'entrée dans les filtres', () => {
  p.ecrireTexte('bridge_cache_detail_scrabble_1', 'x');
  p.ecrireTexte('bridge_cache_detail_scrabble_2', 'y');
  p.ecrireTexte('bridge_cache_detail_autre_3', 'z');
  p.ecrire('bridge_filtres_resultats', { scrabble: false, autre: true });
  p.purgerProjet('scrabble');
  assert.equal(p.lireTexte('bridge_cache_detail_scrabble_1'), null);
  assert.equal(p.lireTexte('bridge_cache_detail_scrabble_2'), null);
  assert.equal(p.lireTexte('bridge_cache_detail_autre_3'), 'z');
  assert.deepEqual(p.lire('bridge_filtres_resultats'), { autre: true });
});

test('purgerProjet ne plante pas si le projet est absent des filtres', () => {
  p.ecrire('bridge_filtres_resultats', { autre: true });
  assert.doesNotThrow(() => p.purgerProjet('scrabble'));
  assert.deepEqual(p.lire('bridge_filtres_resultats'), { autre: true });
});
