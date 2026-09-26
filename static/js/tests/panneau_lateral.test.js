// Tests de logique pure du panneau latéral (issue #633, correctif anomalie
// #4 : les cases de notification devaient refléter les labels réels de
// l'issue sélectionnée, quel que soit le chemin par lequel elle est arrivée
// dans la liste). Aucune dépendance au DOM ni au réseau — voir
// static/js/tests/README.md pour lancer ces tests (node --test).
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  etatsCasesNotif,
  sonIssueDepuisReponse,
  normaliserChoixSonIssue,
  etatsOptionsSonIssue,
} from '../panneau_lateral.js';

test('etatsCasesNotif : aucun label → les 3 cases décochées', () => {
  assert.deepEqual(etatsCasesNotif([]), {
    notif_pc: false, notif_gsm: false, notif_tous: false,
  });
});

test('etatsCasesNotif : liste absente (undefined) → les 3 cases décochées', () => {
  assert.deepEqual(etatsCasesNotif(undefined), {
    notif_pc: false, notif_gsm: false, notif_tous: false,
  });
});

test('etatsCasesNotif : notif_pc seul (cas relecture_bridge #77)', () => {
  assert.deepEqual(etatsCasesNotif(['for-linux', 'mode_write', 'notif_pc']), {
    notif_pc: true, notif_gsm: false, notif_tous: false,
  });
});

test('etatsCasesNotif : les 3 labels présents → les 3 cases cochées', () => {
  assert.deepEqual(etatsCasesNotif(['notif_pc', 'notif_gsm', 'notif_tous']), {
    notif_pc: true, notif_gsm: true, notif_tous: true,
  });
});

test('etatsCasesNotif : labels sans rapport n\'affectent aucune case', () => {
  assert.deepEqual(etatsCasesNotif(['for-windows', 'done', 'needs-human']), {
    notif_pc: false, notif_gsm: false, notif_tous: false,
  });
});

// ─── Son PAR ISSUE (issue #637, étape 7b) ──────────────────────────────────

test('sonIssueDepuisReponse : {son: "plat"} → "plat"', () => {
  assert.equal(sonIssueDepuisReponse({ son: 'plat' }), 'plat');
});

test('sonIssueDepuisReponse : {son: "cloche"} → "cloche"', () => {
  assert.equal(sonIssueDepuisReponse({ son: 'cloche' }), 'cloche');
});

test('sonIssueDepuisReponse : {son: null} (aucun choix propre) → null', () => {
  assert.equal(sonIssueDepuisReponse({ son: null }), null);
});

test('sonIssueDepuisReponse : réponse absente/vide/valeur inconnue → null', () => {
  assert.equal(sonIssueDepuisReponse(null), null);
  assert.equal(sonIssueDepuisReponse(undefined), null);
  assert.equal(sonIssueDepuisReponse({}), null);
  assert.equal(sonIssueDepuisReponse({ son: 'autre-chose' }), null);
});

test('normaliserChoixSonIssue : "plat"/"cloche" inchangés', () => {
  assert.equal(normaliserChoixSonIssue('plat'), 'plat');
  assert.equal(normaliserChoixSonIssue('cloche'), 'cloche');
});

test('normaliserChoixSonIssue : "" (bouton « Global ») → null', () => {
  assert.equal(normaliserChoixSonIssue(''), null);
});

test('normaliserChoixSonIssue : valeur inattendue → null (retombe sur global)', () => {
  assert.equal(normaliserChoixSonIssue('autre-chose'), null);
  assert.equal(normaliserChoixSonIssue(undefined), null);
});

test('etatsOptionsSonIssue : aucun choix propre (null) → option "Global" active seule', () => {
  assert.deepEqual(etatsOptionsSonIssue(null), { global: true, plat: false, cloche: false });
});

test('etatsOptionsSonIssue : choix "plat" → option "Plat" active seule', () => {
  assert.deepEqual(etatsOptionsSonIssue('plat'), { global: false, plat: true, cloche: false });
});

test('etatsOptionsSonIssue : choix "cloche" → option "Cloche" active seule', () => {
  assert.deepEqual(etatsOptionsSonIssue('cloche'), { global: false, plat: false, cloche: true });
});

test('etatsOptionsSonIssue : bascule des 3 états, un seul actif à la fois', () => {
  [null, 'plat', 'cloche'].forEach((valeur) => {
    const etats = etatsOptionsSonIssue(valeur);
    const nbActifs = Object.values(etats).filter(Boolean).length;
    assert.equal(nbActifs, 1, `un seul état actif attendu pour ${valeur}`);
  });
});
