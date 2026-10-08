// Tests de logique pure du journal des messages éphémères (toasts), issue
// #730. Aucune dépendance au DOM ni au réseau : on ne teste ici que les
// fonctions PURES exportées par static/js/socle/toasts.js — l'affichage réel
// (DOM, setTimeout, mouseenter/mouseleave, sessionStorage) est vérifié
// manuellement (voir VERIFICATIONS_MANUELLES.md).
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  dureeAffichage,
  ajouterEntreeJournal,
  majNonLusApresAjout,
  calculerDelaiRestant,
  formaterHeureJournal,
} from '../socle/toasts.js';

// ─── dureeAffichage : durée de vie selon le type ───────────────────────────

test('dureeAffichage : info/succes → 4000ms (disparaissent seuls)', () => {
  assert.equal(dureeAffichage('info'), 4000);
  assert.equal(dureeAffichage('succes'), 4000);
});

test('dureeAffichage : erreur/avertissement → null (aucune fermeture automatique)', () => {
  assert.equal(dureeAffichage('erreur'), null);
  assert.equal(dureeAffichage('avertissement'), null);
});

test('dureeAffichage : type inconnu → repli sur la durée par défaut (4000ms)', () => {
  assert.equal(dureeAffichage('inconnu'), 4000);
});

// ─── ajouterEntreeJournal : taille maximale, ordre ─────────────────────────

test('ajouterEntreeJournal : sous la taille max → simple ajout en fin, ordre conservé', () => {
  const journal = [{ id: 1 }, { id: 2 }];
  const suite = ajouterEntreeJournal(journal, { id: 3 }, 5);
  assert.deepEqual(suite.map(e => e.id), [1, 2, 3]);
});

test('ajouterEntreeJournal : au-delà de la taille max → les plus anciennes sont retirées (FIFO)', () => {
  let journal = [];
  for (let i = 1; i <= 4; i++) journal = ajouterEntreeJournal(journal, { id: i }, 3);
  assert.deepEqual(journal.map(e => e.id), [2, 3, 4]);
  assert.equal(journal.length, 3);
});

test('ajouterEntreeJournal : taille max par défaut (50) côté module', () => {
  let journal = [];
  for (let i = 1; i <= 52; i++) journal = ajouterEntreeJournal(journal, { id: i });
  assert.equal(journal.length, 50);
  assert.deepEqual([journal[0].id, journal[journal.length - 1].id], [3, 52]);
});

test('ajouterEntreeJournal : pure — ne modifie pas le tableau reçu', () => {
  const journal = [{ id: 1 }];
  const suite = ajouterEntreeJournal(journal, { id: 2 }, 10);
  assert.equal(journal.length, 1);
  assert.equal(suite.length, 2);
  assert.notEqual(suite, journal);
});

// ─── majNonLusApresAjout : compteur de messages non consultés ─────────────

test('majNonLusApresAjout : panneau fermé → incrémente', () => {
  assert.equal(majNonLusApresAjout(0, false), 1);
  assert.equal(majNonLusApresAjout(3, false), 4);
});

test('majNonLusApresAjout : panneau ouvert → remis à zéro (vu immédiatement)', () => {
  assert.equal(majNonLusApresAjout(5, true), 0);
  assert.equal(majNonLusApresAjout(0, true), 0);
});

test('majNonLusApresAjout : plusieurs messages consécutifs, panneau resté fermé', () => {
  let nonLus = 0;
  for (let i = 0; i < 4; i++) nonLus = majNonLusApresAjout(nonLus, false);
  assert.equal(nonLus, 4);
});

// ─── calculerDelaiRestant : pause/reprise du compte à rebours ─────────────

test('calculerDelaiRestant : aucun temps écoulé → durée inchangée', () => {
  assert.equal(calculerDelaiRestant(4000, 1000, 1000), 4000);
});

test('calculerDelaiRestant : temps écoulé déduit de la durée restante', () => {
  assert.equal(calculerDelaiRestant(4000, 1000, 2500), 2500);
});

test('calculerDelaiRestant : jamais négatif (temps écoulé dépasse la durée)', () => {
  assert.equal(calculerDelaiRestant(1000, 0, 5000), 0);
});

test('calculerDelaiRestant : scénario pause puis reprise, en deux phases actives', () => {
  // Toast de 4000ms, actif 1500ms, mis en pause (survol) → repart avec 2500ms.
  let restant = calculerDelaiRestant(4000, 0, 1500);
  assert.equal(restant, 2500);
  // Reprise (souris quitte le toast) : nouvelle phase active, encore 2500ms
  // écoulées → entièrement consommé, jamais négatif.
  restant = calculerDelaiRestant(restant, 0, 2500);
  assert.equal(restant, 0);
});

// ─── formaterHeureJournal : horodatage du journal ──────────────────────────

test('formaterHeureJournal : HH:MM:SS, zéro-rembourré', () => {
  assert.equal(formaterHeureJournal(new Date(2026, 9, 8, 9, 7, 3)), '09:07:03');
});

test('formaterHeureJournal : heure/minute/seconde à deux chiffres non modifiées', () => {
  assert.equal(formaterHeureJournal(new Date(2026, 9, 8, 23, 59, 42)), '23:59:42');
});
