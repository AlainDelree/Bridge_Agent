// Tests de logique pure de l'onglet « En attente » (issue #714, suite #713).
// Aucune dépendance au DOM ni au réseau — voir static/js/tests/README.md
// pour lancer ces tests (node --test).
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  formaterDateAttente,
  decisionBadgeAttente,
  descriptionLigneAttente,
  messageEchecAttente,
} from '../attente.js';

// ─── formaterDateAttente ────────────────────────────────────────────────────

test('formaterDateAttente : JJ/MM/AAAA HH:MM, zéro-rembourré', () => {
  assert.equal(formaterDateAttente(new Date(2024, 0, 5, 9, 7)), '05/01/2024 09:07');
});

test('formaterDateAttente : jour/mois/heure/minute à deux chiffres non modifiés', () => {
  assert.equal(formaterDateAttente(new Date(2026, 10, 23, 14, 32)), '23/11/2026 14:32');
});

test('formaterDateAttente : absent → chaîne vide', () => {
  assert.equal(formaterDateAttente(null), '');
  assert.equal(formaterDateAttente(undefined), '');
});

// ─── decisionBadgeAttente ───────────────────────────────────────────────────

test('decisionBadgeAttente : > 0 → affiché avec le compteur en texte', () => {
  assert.deepEqual(decisionBadgeAttente(1), { afficher: true, texte: '1' });
  assert.deepEqual(decisionBadgeAttente(12), { afficher: true, texte: '12' });
});

test('decisionBadgeAttente : 0/absent/null → masqué (rien d\'affiché)', () => {
  assert.deepEqual(decisionBadgeAttente(0), { afficher: false, texte: '' });
  assert.deepEqual(decisionBadgeAttente(undefined), { afficher: false, texte: '' });
  assert.deepEqual(decisionBadgeAttente(null), { afficher: false, texte: '' });
});

// ─── descriptionLigneAttente ────────────────────────────────────────────────

test('descriptionLigneAttente : reprend titre/projet/condition tels quels', () => {
  const item = { id: 'a.txt', titre: 'Mon titre', projet: 'bridge_agent',
                 date: Math.floor(new Date(2026, 0, 1, 10, 0).getTime() / 1000),
                 condition: 'après la fusion de l\'étape C' };
  const desc = descriptionLigneAttente(item);
  assert.equal(desc.titre, 'Mon titre');
  assert.equal(desc.projet, 'bridge_agent');
  assert.equal(desc.condition, 'après la fusion de l\'étape C');
  assert.equal(desc.date, '01/01/2026 10:00');
});

test('descriptionLigneAttente : titre/condition absents → replis explicites', () => {
  const desc = descriptionLigneAttente({ id: 'a.txt', projet: 'bridge_agent', date: 0 });
  assert.equal(desc.titre, '(sans titre)');
  assert.equal(desc.condition, '(condition non précisée)');
  assert.equal(desc.date, '');
});

test('descriptionLigneAttente : item absent ne lève pas d\'exception', () => {
  const desc = descriptionLigneAttente(null);
  assert.equal(desc.titre, '(sans titre)');
  assert.equal(desc.projet, '');
});

// ─── messageEchecAttente ────────────────────────────────────────────────────

test('messageEchecAttente : corps JSON avec champ erreur → message serveur', () => {
  const erreur = { corps: '{"succes":false,"erreur":"identifiant invalide."}' };
  assert.equal(messageEchecAttente(erreur, 'repli'), 'identifiant invalide.');
});

test('messageEchecAttente : corps non-JSON → repli', () => {
  assert.equal(messageEchecAttente({ corps: 'Internal Server Error' }, 'repli'), 'repli');
});

test('messageEchecAttente : corps JSON sans champ erreur → repli', () => {
  assert.equal(messageEchecAttente({ corps: '{"succes":false}' }, 'repli'), 'repli');
});

test('messageEchecAttente : erreur absente/sans corps → repli', () => {
  assert.equal(messageEchecAttente(null, 'repli'), 'repli');
  assert.equal(messageEchecAttente({}, 'repli'), 'repli');
});
