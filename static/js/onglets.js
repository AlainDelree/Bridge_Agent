// onglets.js — mécanique de la barre d'onglets, sortie d'app.js (issue #626,
// refonte web étape 2).
//
// RESPONSABILITÉ
//   Bascule entre onglets : (dés)active la classe "actif" sur l'onglet cliqué
//   et son panneau, publie l'onglet actif dans le store (pour que chaque zone
//   puisse réagir à son activation/désactivation), et appelle — via le pont,
//   pendant la transition — les initialisations existantes de chaque onglet
//   dans l'ancien app.js (voir initialisationsPour ci-dessous).
//
// RÉSULTATS / PANNEAU LATÉRAL (issue #632) : ces deux zones ne passent PLUS
// par le pont ici — elles s'abonnent elles-mêmes à store.ongletActif (voir
// resultats.js#initialiser et panneau_lateral.js#initPanneauLateral). Avant
// #632, ce fichier appelait via le pont des fonctions d'app.js déjà retirées
// par #626/#627 (chargerListeIssues/demarrerTempsRestant/demarrerPanneauLateral
// notamment) : la liste ne se chargeait donc jamais au premier affichage.
//
// ASSOCIATION ONGLET <-> PANNEAU
//   Par IDENTIFIANT (attribut data-onglet porté par chaque .onglet, comparé à
//   l'id "panneau-<nom>" de chaque .panneau), PAS par position dans le DOM :
//   contrairement à l'ancien basculerOnglet() (tableau de noms parcouru dans
//   l'ordre des éléments), réordonner les onglets ne casse plus l'association.
//
// ONGLET PAR DÉFAUT
//   Résultats est l'onglet actif au chargement de la page (issue #626).
//   L'activation elle-même est séparée de l'installation de la délégation de
//   clic (voir activerOngletParDefaut ci-dessous) : index.js ne l'appelle
//   qu'une fois TOUS les modules de fonctionnalité initialisés (leurs
//   abonnements à store.ongletActif doivent déjà exister), quel que soit
//   l'ordre des autres appels d'initialisation.

import { store } from './socle/store.js';
import { appelerAncien } from './socle/pont.js';
import { surAction } from './socle/dom.js';

const ONGLET_PAR_DEFAUT = 'resultats';

/**
 * Liste (pure, testable) des noms de fonctions de l'ancien app.js à appeler
 * — via le pont — pour initialiser l'onglet `nom`. Résultats n'y figure plus
 * (issue #632) : le module Résultats et le panneau latéral réagissent
 * directement à store.ongletActif, sans passer par ici ni par le pont.
 */
export function initialisationsPour(nom) {
  const appels = [];
  if (nom === 'journal') appels.push('demarrerJournal');
  if (nom === 'config') appels.push('chargerConfig');
  if (nom === 'ccw') appels.push('ccwOuvrirOnglet');
  // L'onglet « Résultats inbox » a été supprimé (issue #639) : son contenu a
  // rejoint la liste Résultats (lignes fichier reçu/refusé + badge d'alerte) et
  // le panneau latéral (historique du watcher spool).
  return appels;
}

/** Active l'onglet `nom` : classes DOM, store, initialisations de transition. */
export function activerOnglet(nom) {
  if (typeof document !== 'undefined') {
    document.querySelectorAll('.onglet').forEach((o) =>
      o.classList.toggle('actif', o.dataset.onglet === nom));
    document.querySelectorAll('.panneau').forEach((p) =>
      p.classList.toggle('actif', p.id === 'panneau-' + nom));
  }
  store.set('ongletActif', nom);
  for (const fonction of initialisationsPour(nom)) appelerAncien(fonction);
}

/** Branche la délégation de clic sur la barre d'onglets — appelé une seule
 *  fois par index.js au chargement de la page. */
export function initialiserOnglets() {
  surAction('.onglet', 'click', (evenement, element) => activerOnglet(element.dataset.onglet));
}

/** Active l'onglet par défaut (Résultats). À appeler par index.js APRÈS avoir
 *  initialisé tous les modules de fonctionnalité (resultats.js,
 *  panneau_lateral.js…) pour que leurs abonnements à store.ongletActif soient
 *  déjà en place quand cette activation initiale les déclenche (issue #632). */
export function activerOngletParDefaut() {
  activerOnglet(ONGLET_PAR_DEFAUT);
}
