// Tests de logique pure de l'onglet Journal watcher (issue #650, refonte web
// étape 11 — sorti d'app.js vers static/js/journal.js). Aucune dépendance au
// DOM ni au réseau (demarrerJournal/viderTerminal touchent le DOM et l'EventSource,
// vérifiés manuellement — voir VERIFICATIONS_MANUELLES.md) : on ne teste ici que
// classeLigneJournal(), pure et indépendante du DOM.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { classeLigneJournal } from '../journal.js';

test('classeLigneJournal : [WARNING] ou ⚠ → log-warn', () => {
  assert.equal(classeLigneJournal('2026-09-26 [WARNING] repli en cours'), 'log-warn');
  assert.equal(classeLigneJournal('⚠ TIMEOUT approché'), 'log-warn');
});

test('classeLigneJournal : [ERROR] → log-err', () => {
  assert.equal(classeLigneJournal('2026-09-26 [ERROR] échec du clone'), 'log-err');
});

test('classeLigneJournal : ✓ ou "succès" → log-ok', () => {
  assert.equal(classeLigneJournal('✓ issue #650 traitée'), 'log-ok');
  assert.equal(classeLigneJournal('clôture en succès'), 'log-ok');
});

test('classeLigneJournal : aucun marqueur reconnu → log-info', () => {
  assert.equal(classeLigneJournal('2026-09-26 démarrage du cycle'), 'log-info');
  assert.equal(classeLigneJournal(''), 'log-info');
});

test('classeLigneJournal : [ERROR] prime sur ✓/succès si les deux sont présents', () => {
  assert.equal(classeLigneJournal('[ERROR] annulation malgré succès partiel'), 'log-err');
});

test('classeLigneJournal : [WARNING] prime sur [ERROR] (ordre des tests, comme l\'ancien code)', () => {
  assert.equal(classeLigneJournal('[WARNING] puis [ERROR] en cascade'), 'log-warn');
});
