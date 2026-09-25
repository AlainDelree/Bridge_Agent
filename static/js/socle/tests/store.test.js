// Tests de logique pure du store (issue #625, étape 1).
// Aucune dépendance, aucun build. Lancement : voir static/js/socle/tests/README.md
//   node --test static/js/socle/tests/
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { creerStore, store, cleIssue } from '../store.js';

test('cleIssue construit une clé projet#numero stable', () => {
  assert.equal(cleIssue('scrabble', 42), 'scrabble#42');
  assert.equal(cleIssue('scrabble', '42'), 'scrabble#42');
});

test('creerStore : get renvoie tout l\'état ou une tranche', () => {
  const s = creerStore({ a: 1, b: 2 });
  assert.deepEqual(s.get(), { a: 1, b: 2 });
  assert.equal(s.get('a'), 1);
  assert.equal(s.get('inconnu'), undefined);
});

test('creerStore : set(cle, valeur) écrit une tranche', () => {
  const s = creerStore({ a: 1 });
  s.set('a', 9);
  assert.equal(s.get('a'), 9);
  s.set('b', 3);
  assert.equal(s.get('b'), 3);
});

test('creerStore : set(objet) fusionne plusieurs tranches', () => {
  const s = creerStore({ a: 1, b: 2 });
  s.set({ a: 10, c: 30 });
  assert.deepEqual(s.get(), { a: 10, b: 2, c: 30 });
});

test('creerStore : maj transforme à partir de l\'ancienne valeur', () => {
  const s = creerStore({ n: 5 });
  s.maj('n', (v) => v + 1);
  assert.equal(s.get('n'), 6);
});

test('creerStore : abonner est notifié des clés modifiées', () => {
  const s = creerStore({ a: 1 });
  const recu = [];
  const desabonner = s.abonner((etat, cles) => recu.push({ cles, a: etat.a }));
  s.set('a', 2);
  s.set({ a: 3, b: 4 });
  assert.deepEqual(recu[0], { cles: ['a'], a: 2 });
  assert.deepEqual(recu[1].cles.sort(), ['a', 'b']);
  desabonner();
  s.set('a', 99);
  assert.equal(recu.length, 2, 'plus notifié après désabonnement');
});

test('creerStore : abonnerCle ne notifie que sa clé', () => {
  const s = creerStore({ a: 1, b: 1 });
  let vuA = 0, vuB = 0;
  s.abonnerCle('a', () => vuA++);
  s.abonnerCle('b', () => vuB++);
  s.set('a', 2);
  assert.equal(vuA, 1);
  assert.equal(vuB, 0);
  s.set({ a: 3, b: 3 });
  assert.equal(vuA, 2);
  assert.equal(vuB, 1);
});

test('creerStore : immuabilité — get() ne renvoie pas la même référence après set', () => {
  const s = creerStore({ a: 1 });
  const avant = s.get();
  s.set('a', 2);
  const apres = s.get();
  assert.notEqual(avant, apres, 'set remplace l\'objet d\'état (copie)');
  assert.equal(avant.a, 1, 'l\'ancien instantané reste inchangé');
});

test('store applicatif : tranches par défaut présentes', () => {
  const etat = store.get();
  for (const cle of ['issues', 'selection', 'filtres', 'projets',
                     'watchers', 'issuesInbox', 'son', 'rateLimit']) {
    assert.ok(cle in etat, `tranche manquante : ${cle}`);
  }
  assert.equal(etat.son, 'plat');
});

test('store applicatif : issues indexées par projet+numéro', () => {
  store.remplacerIssues([
    { projet: 'p1', number: 10, title: 'un' },
    { projet: 'p2', number: 10, title: 'deux' },
  ]);
  assert.equal(store.lireIssue('p1', 10).title, 'un');
  assert.equal(store.lireIssue('p2', 10).title, 'deux');
  assert.equal(store.lireIssue('p1', 999), null);
  assert.equal(store.listerIssues().length, 2);

  store.ecrireIssue({ projet: 'p1', number: 11, title: 'trois' });
  assert.equal(store.lireIssue('p1', 11).title, 'trois');
  assert.equal(store.listerIssues().length, 3);
});

test('store applicatif : ecrireIssue exige projet et number', () => {
  assert.throws(() => store.ecrireIssue({ title: 'sans clé' }), /projet.*number/);
});
