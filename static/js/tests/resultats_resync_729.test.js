// Tests de comportement (DOM + réseau minimalement mockés) du rattrapage des
// événements manqués dans l'onglet Résultats (issue #729) :
//   - le ↻ (resultats.rafraichir) recharge aussi les cases cochées, dans le
//     MÊME périmètre de projets que la liste/le décompte (filtre #428) — la
//     resynchronisation automatique #705 (app.js::resynchroniserResultatsAuRetour)
//     rejoue exactement cette même fonction, donc couverte par les mêmes tests ;
//   - l'activation de l'onglet, elle, recharge liste+décompte+cases EN
//     ARRIÈRE-PLAN quand la dernière synchro réseau est périmée (ou jamais
//     eue), sans filtre de projets (rattrapage volontairement complet).
//
// Patron identique à resultats_activation.test.js (DOM minimal, pas de vrai
// navigateur). `resultatsCoches` est importé directement : surcharger sa
// méthode rechargerCases affecte aussi les appels internes de resultats.js,
// qui référence le MÊME objet (module Node mis en cache, un seul import).
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { resultats } from '../resultats.js';
import { resultatsCoches } from '../resultats_coches.js';

function installerDomMinimal(nomsProjet) {
  global.document = {
    getElementById: (id) => (id === 'projet'
      ? { options: nomsProjet.map((v) => ({ value: v })) }
      : null),
    querySelectorAll: () => [],
  };
  global.window = globalThis;
  window.__resultatsListeVide = () => {};
  window.__resultatsMiroirListe = () => {};
  window.__resultatsSetTiming = () => {};
  window.appliquerListeIssues = () => {};
  window.majIndicateurListe = () => {};
  window.limiteIssuesProjet = () => 5;
  window.restaurerCasesCocheesResultats = () => {};
  window.majPastillesFiltres = () => {};
}

// Réponses vides mais valides : aucun échec réseau (pas de toast.erreur, qui
// toucherait le DOM non mocké).
function installerFetchMinimal() {
  const appels = [];
  global.fetch = async (url) => {
    appels.push(url);
    let body = null;
    if (url.includes('/issues-liste/')) body = [];
    else if (url.includes('/issues-en-attente/')) body = [];
    else if (url.includes('/cases-cochees/')) body = { numeros: [] };
    return { ok: true, text: async () => JSON.stringify(body) };
  };
  return appels;
}

function flush() {
  return new Promise((r) => setImmediate(r));
}

test('rafraichir (↻) recharge aussi les cases cochées, même périmètre que la liste (filtre #428)', async () => {
  installerDomMinimal(['a', 'b']);
  const appelsFetch = installerFetchMinimal();
  const appelsRecharger = [];
  const original = resultatsCoches.rechargerCases;
  resultatsCoches.rechargerCases = (projets) => { appelsRecharger.push(projets); return Promise.resolve(); };
  try {
    await resultats.rafraichir(['a']);   // filtre #428 : un seul projet actif
    assert.deepEqual(appelsRecharger, [['a']],
      'rechargerCases doit recevoir EXACTEMENT le sous-ensemble de projets transmis à rafraichir');
    assert.ok(appelsFetch.some((u) => u.includes('/issues-liste/a')));
    assert.ok(!appelsFetch.some((u) => u.includes('/issues-liste/b')),
      'le projet hors filtre ne doit pas être refetché par la liste');
  } finally {
    resultatsCoches.rechargerCases = original;
  }
});

test('rafraichir (↻) sans filtre explicite (« Tous ») recharge les cases de tous les projets', async () => {
  installerDomMinimal(['a', 'b']);
  installerFetchMinimal();
  const appelsRecharger = [];
  const original = resultatsCoches.rechargerCases;
  resultatsCoches.rechargerCases = (projets) => { appelsRecharger.push(projets); return Promise.resolve(); };
  try {
    await resultats.rafraichir(undefined);
    assert.deepEqual(appelsRecharger, [undefined]);
  } finally {
    resultatsCoches.rechargerCases = original;
  }
});

test('activation de l\'onglet après le seuil de péremption : recharge liste + décompte + cases en arrière-plan', async () => {
  installerDomMinimal(['a']);
  const appelsFetch = installerFetchMinimal();
  const appelsRecharger = [];
  const original = resultatsCoches.rechargerCases;
  resultatsCoches.rechargerCases = (projets) => { appelsRecharger.push(projets); return Promise.resolve(); };
  try {
    resultats.onActiverOnglet();                  // 1ère activation → chargement initial
    await flush();
    const appelsApresInitial = appelsFetch.length;
    assert.ok(appelsApresInitial > 0, 'le chargement initial doit avoir fetché au moins une fois');
    assert.notEqual(resultats.texteDerniereSync(), 'jamais synchronisé');

    resultats.onDesactiverOnglet();
    resultats.onActiverOnglet();                   // réactivation immédiate → synchro récente
    await flush();
    assert.equal(appelsFetch.length, appelsApresInitial,
      'pas de rechargement réseau si la dernière synchro est encore récente');

    const vraiNow = Date.now;
    Date.now = () => vraiNow() + 40000;             // simule 40 s écoulées (seuil #705/#729 = 30 s)
    try {
      resultats.onDesactiverOnglet();
      resultats.onActiverOnglet();                 // réactivation après le seuil → rattrapage réseau
      await flush();
    } finally {
      Date.now = vraiNow;
    }
    assert.ok(appelsFetch.length > appelsApresInitial,
      'rechargement réseau déclenché passé le seuil (événement potentiellement manqué)');
    assert.ok(appelsRecharger.length >= 1,
      'les cases cochées sont aussi rechargées lors du rattrapage en arrière-plan');
  } finally {
    resultatsCoches.rechargerCases = original;
    resultats.onDesactiverOnglet();                // stoppe l'intervalle de badges (setInterval)
  }
});
