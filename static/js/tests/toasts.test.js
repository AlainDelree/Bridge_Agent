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
  estComptabilise,
  entreeComptabilisee,
  cleToast,
  dureeEffective,
  cleEffective,
  contenuRemplacement,
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

// ─── estComptabilise / majNonLusApresAjout(comptabilise) : pastille vs actions
//     triviales (issue #747) ───────────────────────────────────────────────

test('estComptabilise : info/succes → suit l’option demandée par l’appelant', () => {
  assert.equal(estComptabilise('info', false), false);
  assert.equal(estComptabilise('succes', false), false);
  assert.equal(estComptabilise('info', true), true);
  assert.equal(estComptabilise('succes', true), true);
});

test('estComptabilise : sans option → comptabilisé par défaut (comportement d’avant #747)', () => {
  assert.equal(estComptabilise('info'), true);
  assert.equal(estComptabilise('succes'), true);
});

test('estComptabilise : erreur/avertissement → toujours comptabilisés, option ignorée', () => {
  assert.equal(estComptabilise('erreur', false), true);
  assert.equal(estComptabilise('avertissement', false), true);
  assert.equal(estComptabilise('erreur', true), true);
});

test('majNonLusApresAjout : comptabilise=false → compteur inchangé (panneau fermé)', () => {
  assert.equal(majNonLusApresAjout(3, false, false), 3);
  assert.equal(majNonLusApresAjout(0, false, false), 0);
});

test('majNonLusApresAjout : comptabilise=true (ou absent) → incrémente comme avant #747', () => {
  assert.equal(majNonLusApresAjout(3, false, true), 4);
  assert.equal(majNonLusApresAjout(3, false), 4);
});

test('majNonLusApresAjout : panneau ouvert → remis à zéro même si comptabilise=false', () => {
  assert.equal(majNonLusApresAjout(5, true, false), 0);
});

test('entreeComptabilisee : comptabilise=false → non comptabilisée', () => {
  assert.equal(entreeComptabilisee({ comptabilise: false }), false);
});

test('entreeComptabilisee : comptabilise=true → comptabilisée', () => {
  assert.equal(entreeComptabilisee({ comptabilise: true }), true);
});

test('entreeComptabilisee : entrée ancienne sans le champ → lue comme comptabilisée (compatibilité session)', () => {
  assert.equal(entreeComptabilisee({ id: 1, type: 'succes', texte: 'Ancien message', horodatage: 0 }), true);
});

// ─── cleToast (issue #782) : clé de regroupement anti-empilement ──────────
// Sans texte de secours, deux appels identiques doivent se fusionner (clé
// identique, comportement d'avant #782, issue #635) ; avec un texte de
// secours, chaque appel doit rester un toast séparé (clé jamais réutilisée),
// sinon le contenu sélectionnable d'un appel précédent serait effacé.

test('cleToast : sans texte de secours → même (type, texte) ⇒ même clé (fusion attendue)', () => {
  assert.equal(cleToast('erreur', 'Copie impossible.', undefined, 1), cleToast('erreur', 'Copie impossible.', undefined, 2));
});

test('cleToast : sans texte de secours → clé composée de type + texte', () => {
  assert.equal(cleToast('erreur', 'Copie impossible.'), 'erreur Copie impossible.');
});

test('cleToast : avec texte de secours → clé UNIQUE même pour un (type, texte) identique', () => {
  const cle1 = cleToast('erreur', 'Copie impossible.', 'Issue #1 — texte A', 1);
  const cle2 = cleToast('erreur', 'Copie impossible.', 'Issue #2 — texte B', 2);
  assert.notEqual(cle1, cle2);
});

test('cleToast : avec texte de secours → deux appels successifs (compteur croissant) ne se fusionnent jamais', () => {
  const vues = new Set();
  for (let i = 1; i <= 5; i++) vues.add(cleToast('erreur', 'Copie impossible.', 'texte', i));
  assert.equal(vues.size, 5);
});

// ─── dureeEffective (issue #807) : durée explicite facultative ────────────
// Messages de panne de connexion répétitifs (résultats.js, panne_github.js) :
// erreur/avertissement doivent pouvoir disparaître seuls (durée explicite),
// sans que cela touche au comportement par défaut (persistant) des autres.

test('dureeEffective : sans durée demandée → repli sur dureeAffichage(type) (comportement inchangé)', () => {
  assert.equal(dureeEffective('erreur', undefined), dureeAffichage('erreur'));
  assert.equal(dureeEffective('avertissement', undefined), dureeAffichage('avertissement'));
  assert.equal(dureeEffective('info', undefined), dureeAffichage('info'));
});

test('dureeEffective : durée explicite demandée pour erreur/avertissement → cette durée prime (plus de persistance)', () => {
  assert.equal(dureeEffective('erreur', 10000), 10000);
  assert.equal(dureeEffective('avertissement', 10000), 10000);
});

test('dureeEffective : persistance par défaut des erreurs/avertissements maintenue (null) hors durée explicite', () => {
  assert.equal(dureeEffective('erreur', undefined), null);
  assert.equal(dureeEffective('avertissement', undefined), null);
});

test('dureeEffective : valeur non numérique (null, chaîne) → ignorée, repli sur le type', () => {
  assert.equal(dureeEffective('erreur', null), null);
  assert.equal(dureeEffective('info', 'oops'), dureeAffichage('info'));
});

// ─── cleEffective (issue #807) : clé de regroupement explicite facultative ─
// Les messages de panne de connexion changent de texte à chaque occurrence
// (liste de projets en échec) : une clé fixe, choisie par l'appelant, évite
// qu'ils s'empilent indéfiniment (contrairement à cleToast, basée sur le texte).

test('cleEffective : sans clé demandée → identique à cleToast (comportement inchangé)', () => {
  assert.equal(
    cleEffective('erreur', 'Résultats — échec : a', undefined, undefined, undefined),
    cleToast('erreur', 'Résultats — échec : a', undefined, undefined));
});

test('cleEffective : clé explicite demandée → prime sur le texte, même si celui-ci change', () => {
  const cle1 = cleEffective('erreur', 'Résultats — échec : a, b', undefined, undefined, 'resultats-echec-chargement');
  const cle2 = cleEffective('erreur', 'Résultats — échec : a, b, c', undefined, undefined, 'resultats-echec-chargement');
  assert.equal(cle1, cle2);
  assert.equal(cle1, 'resultats-echec-chargement');
});

test('cleEffective : deux sources différentes (clés explicites distinctes) ne se mélangent jamais', () => {
  const cleA = cleEffective('erreur', 'texte A', undefined, undefined, 'resultats-echec-chargement');
  const cleB = cleEffective('avertissement', 'texte B', undefined, undefined, 'resultats-decompte-non-recharge');
  assert.notEqual(cleA, cleB);
});

// ─── contenuRemplacement (issue #807) : remplacement vs fusion par compteur ─

test('contenuRemplacement : fusion par défaut (remplacer=false) → compteur incrémenté, texte suffixé « (×N) » (inchangé, issue #635)', () => {
  const r1 = contenuRemplacement('Même message.', 1, false);
  assert.deepEqual(r1, { texte: 'Même message. (×2)', compteur: 2 });
  const r2 = contenuRemplacement('Même message.', 2, false);
  assert.deepEqual(r2, { texte: 'Même message. (×3)', compteur: 3 });
});

test('contenuRemplacement : remplacement (remplacer=true) → contenu REMPLACÉ par le nouveau texte, pas de compteur', () => {
  const r = contenuRemplacement('Résultats — échec de chargement : a, b, c.', 1, true);
  assert.deepEqual(r, { texte: 'Résultats — échec de chargement : a, b, c.', compteur: 1 });
});

test('contenuRemplacement : remplacement successif → le contenu suit le texte le plus récent, jamais de « (×N) »', () => {
  let etat = { texte: null, compteur: 1 };
  for (const texte of ['échec : a', 'échec : a, b', 'échec : a, b, c']) {
    etat = contenuRemplacement(texte, etat.compteur, true);
  }
  assert.equal(etat.texte, 'échec : a, b, c');
  assert.equal(etat.texte.includes('×'), false);
});
