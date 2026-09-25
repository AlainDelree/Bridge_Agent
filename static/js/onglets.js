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
// ASSOCIATION ONGLET <-> PANNEAU
//   Par IDENTIFIANT (attribut data-onglet porté par chaque .onglet, comparé à
//   l'id "panneau-<nom>" de chaque .panneau), PAS par position dans le DOM :
//   contrairement à l'ancien basculerOnglet() (tableau de noms parcouru dans
//   l'ordre des éléments), réordonner les onglets ne casse plus l'association.
//
// ONGLET PAR DÉFAUT
//   Résultats est l'onglet actif au chargement de la page (issue #626) :
//   initialiserOnglets() active 'resultats' dès son appel, avec exactement
//   l'initialisation qu'il reçoit aujourd'hui quand on clique dessus.
//
// NE PAS MODIFIER ICI ce que fait l'activation de Résultats (rechargement de
// la liste, badges, panneau latéral) : périmètre de l'étape 3 de la refonte.

import { store } from './socle/store.js';
import { appelerAncien } from './socle/pont.js';
import { surAction } from './socle/dom.js';

const ONGLET_PAR_DEFAUT = 'resultats';

/**
 * Liste (pure, testable) des noms de fonctions de l'ancien app.js à appeler
 * — via le pont — pour initialiser l'onglet `nom`. Reprend exactement la
 * logique de l'ancien basculerOnglet().
 */
export function initialisationsPour(nom) {
  const appels = [];
  if (nom === 'resultats') {
    appels.push('chargerListeIssues', 'demarrerTempsRestant', 'demarrerPanneauLateral');
  } else {
    appels.push('arreterTempsRestant', 'arreterPanneauLateral');
  }
  if (nom === 'journal') appels.push('demarrerJournal');
  if (nom === 'config') appels.push('chargerConfig');
  if (nom === 'ccw') appels.push('ccwOuvrirOnglet');
  if (nom === 'inbox') appels.push('rafraichirInbox');
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

/** Branche la délégation de clic sur la barre d'onglets et active l'onglet par
 *  défaut — appelé une seule fois par index.js au chargement de la page. */
export function initialiserOnglets() {
  surAction('.onglet', 'click', (evenement, element) => activerOnglet(element.dataset.onglet));
  activerOnglet(ONGLET_PAR_DEFAUT);
}
