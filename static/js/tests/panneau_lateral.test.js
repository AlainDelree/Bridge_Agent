// Tests de logique pure du panneau latéral (issue #633, correctif anomalie
// #4 : les cases de notification devaient refléter les labels réels de
// l'issue sélectionnée, quel que soit le chemin par lequel elle est arrivée
// dans la liste). Aucune dépendance au DOM ni au réseau — voir
// static/js/tests/README.md pour lancer ces tests (node --test).
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { etatsCasesNotif } from '../panneau_lateral.js';

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

// Le contrôle « Son de cette issue » (#637) et ses fonctions pures ont été
// déplacés sur la ligne de la liste à l'étape 6 de la refonte (issue #641) —
// voir static/js/tests/actions_ligne.test.js. Le panneau ne les affiche plus.
