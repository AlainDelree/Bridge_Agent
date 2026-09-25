// Test de l'activation de l'onglet Résultats (issue #632, raccord vague 1).
// Avant ce correctif, onglets.js déclenchait cette activation via le pont
// (chargerListeIssues/demarrerTempsRestant/demarrerPanneauLateral), en visant
// des fonctions déjà retirées d'app.js : la liste ne se chargeait donc jamais.
// Depuis #632, resultats.onActiverOnglet()/onDesactiverOnglet() sont appelées
// directement par l'abonnement à store.ongletActif (voir resultats.js#initialiser)
// — ce test vérifie leur comportement au niveau où il compte : le chargement
// initial ne doit se produire qu'une seule fois, quel que soit le nombre
// d'allers-retours sur l'onglet.
//
// Aucun projet configuré (document minimal, sans <select id="projet">) : le
// « chargement initial » se résume à l'appel __resultatsListeVide côté ancien
// code — suffisant pour observer combien de fois chargerListe() a réellement
// tenté un chargement, sans dépendre du réseau ni d'un vrai DOM.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { resultats } from '../resultats.js';

test('activation de Résultats : chargement initial déclenché une seule fois', async () => {
  global.document = {
    getElementById: () => null,           // pas de <select id="projet"> → nomsProjets() = []
    querySelectorAll: () => [],
  };
  global.window = globalThis;
  let appelsChargementInitial = 0;
  window.__resultatsListeVide = () => { appelsChargementInitial++; };
  window.__resultatsMiroirListe = () => {};
  window.__resultatsSetTiming = () => {};
  window.appliquerListeIssues = () => {};    // ré-activation → rendreListeComplete()

  try {
    resultats.onActiverOnglet();                       // 1ère activation → chargement initial
    await new Promise((r) => setImmediate(r));
    resultats.onDesactiverOnglet();
    resultats.onActiverOnglet();                        // ré-activation → simple re-rendu, PAS de rechargement
    await new Promise((r) => setImmediate(r));

    assert.equal(appelsChargementInitial, 1,
      "l'activation de Résultats ne doit déclencher le chargement initial qu'une seule fois");
  } finally {
    resultats.onDesactiverOnglet();                     // stoppe l'intervalle de badges (setInterval)
  }
});
