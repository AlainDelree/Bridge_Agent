// Tests de logique pure du panneau latéral (issue #633, correctif anomalie
// #4 : les cases de notification devaient refléter les labels réels de
// l'issue sélectionnée, quel que soit le chemin par lequel elle est arrivée
// dans la liste). Aucune dépendance au DOM ni au réseau — voir
// static/js/tests/README.md pour lancer ces tests (node --test).
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  etatsCasesNotif, afficherBoutonArreterWatcherCcl,
  selectionnerWatchersActifsARelancer, resumerRelanceActifs, relancerSequentiellement,
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

// ─── afficherBoutonArreterWatcherCcl (issue #655) ──────────────────────────
// Bouton « ⏹ Arrêter » d'un watcher CCL du panneau latéral : visible
// seulement quand le watcher est actif — même patron que
// afficherBoutonDemarrer/afficherBoutonArreter pour les services CCW
// (static/js/tests/ccw.test.js).
test('afficherBoutonArreterWatcherCcl : watcher actif → bouton affiché', () => {
  assert.equal(afficherBoutonArreterWatcherCcl(true), true);
});

test('afficherBoutonArreterWatcherCcl : watcher inactif → bouton masqué', () => {
  assert.equal(afficherBoutonArreterWatcherCcl(false), false);
});

test('afficherBoutonArreterWatcherCcl : état absent (undefined) → bouton masqué', () => {
  assert.equal(afficherBoutonArreterWatcherCcl(undefined), false);
});

// Le contrôle « Son de cette issue » (#637) et ses fonctions pures ont été
// déplacés sur la ligne de la liste à l'étape 6 de la refonte (issue #641) —
// voir static/js/tests/actions_ligne.test.js. Le panneau ne les affiche plus.

// ─── selectionnerWatchersActifsARelancer / resumerRelanceActifs (issue #753) ──
// « ↺ Relancer les allumés » : uniquement les watchers CCL actuellement
// actifs, jamais un éteint, et jamais un actif dont une issue est en cours.
test('selectionnerWatchersActifsARelancer : watcher éteint → jamais relancé, ni ignoré', () => {
  const watchersMap = { alpha: { actif: false } };
  const resultat = selectionnerWatchersActifsARelancer(['alpha'], watchersMap, {});
  assert.deepEqual(resultat, { relances: [], ignores: [] });
});

test('selectionnerWatchersActifsARelancer : watcher actif sans issue en cours → relancé', () => {
  const watchersMap = { alpha: { actif: true } };
  const resumeParProjet = { alpha: { enCours: 0, enFile: 2 } };
  const resultat = selectionnerWatchersActifsARelancer(['alpha'], watchersMap, resumeParProjet);
  assert.deepEqual(resultat, { relances: ['alpha'], ignores: [] });
});

test('selectionnerWatchersActifsARelancer : watcher actif avec issue en cours → ignoré, pas relancé', () => {
  const watchersMap = { alpha: { actif: true } };
  const resumeParProjet = { alpha: { enCours: 1, enFile: 0 } };
  const resultat = selectionnerWatchersActifsARelancer(['alpha'], watchersMap, resumeParProjet);
  assert.deepEqual(resultat, { relances: [], ignores: ['alpha'] });
});

test('selectionnerWatchersActifsARelancer : resume absent (non chargé) → traité comme sans issue en cours', () => {
  const watchersMap = { alpha: { actif: true } };
  const resultat = selectionnerWatchersActifsARelancer(['alpha'], watchersMap, {});
  assert.deepEqual(resultat, { relances: ['alpha'], ignores: [] });
});

test('selectionnerWatchersActifsARelancer : mélange de projets (éteint, occupé, libre)', () => {
  const watchersMap = {
    alpha: { actif: false },
    beta:  { actif: true },
    gamma: { actif: true },
  };
  const resumeParProjet = { beta: { enCours: 2 }, gamma: { enCours: 0 } };
  const resultat = selectionnerWatchersActifsARelancer(['alpha', 'beta', 'gamma'], watchersMap, resumeParProjet);
  assert.deepEqual(resultat, { relances: ['gamma'], ignores: ['beta'] });
});

test('resumerRelanceActifs : aucun ignoré → résumé succès, sans parenthèse de noms', () => {
  const resultat = resumerRelanceActifs(['alpha', 'beta'], []);
  assert.deepEqual(resultat, { texte: '2 relancé(s), 0 ignoré(s)', type: 'succes' });
});

test('resumerRelanceActifs : au moins un ignoré → résumé avertissement, avec les noms', () => {
  const resultat = resumerRelanceActifs(['alpha'], ['beta', 'gamma']);
  assert.deepEqual(resultat, { texte: '1 relancé(s), 2 ignoré(s) (beta, gamma)', type: 'avertissement' });
});

test('resumerRelanceActifs : rien à relancer ni à ignorer (aucun watcher actif)', () => {
  const resultat = resumerRelanceActifs([], []);
  assert.deepEqual(resultat, { texte: '0 relancé(s), 0 ignoré(s)', type: 'succes' });
});

test('relancerSequentiellement : la relance en échec d\'un projet ne bloque pas les suivants', async () => {
  const tentes = [];
  await relancerSequentiellement(['alpha', 'beta', 'gamma'], (nom) => {
    tentes.push(nom);
    if (nom === 'beta') return Promise.reject(new Error('échec réseau'));
    return Promise.resolve();
  });
  assert.deepEqual(tentes, ['alpha', 'beta', 'gamma']);
});

test('relancerSequentiellement : liste vide → aucun appel', async () => {
  let appels = 0;
  await relancerSequentiellement([], () => { appels += 1; return Promise.resolve(); });
  assert.equal(appels, 0);
});
