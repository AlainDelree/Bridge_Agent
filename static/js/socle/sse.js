// sse.js — gestion centralisée des canaux temps réel (issue #625, étape 1).
//
// RESPONSABILITÉ
//   Regrouper la gestion des canaux Server-Sent Events aujourd'hui dispersés
//   dans app.js (/stream début/fin d'issue, /events cycle de vie serveur, et à
//   terme /journal). Un canal = ouverture, écoute des événements nommés,
//   reconnexion, et répartition (dispatch) des événements reçus vers le store.
//
// CE QU'IL EXPOSE
//   - creerCanalSse(url, gestionnaires, opts) : fabrique un contrôleur de canal.
//   - sse : le contrôleur applicatif regroupant les canaux /stream et /events,
//           préconfigurés pour écrire dans le store — MAIS NON CONNECTÉS.
//
// ⚠️ CONTRAINTE ABSOLUE DE L'ÉTAPE 1 (issue #625) ⚠️
//   sse NE DOIT PAS ouvrir de connexion tant que l'ancien app.js gère les
//   siennes : une double connexion /stream ou /events dédoublerait les
//   rafraîchissements. C'est pourquoi index.js N'APPELLE PAS sse.connecter().
//   `new EventSource` n'est créé que dans connecter() → l'import reste sûr sous
//   Node (où EventSource n'existe pas). La bascule se fera à l'étape qui
//   retirera du vieux code la gestion SSE correspondante (voir ARCHITECTURE.md).

/**
 * Fabrique un contrôleur de canal SSE.
 *
 * @param {string} url  Route SSE (ex. '/stream').
 * @param {Object.<string, (e:MessageEvent)=>void>} gestionnaires
 *        Map { nomEvenement: handler }. La clé 'message' vise l'événement par
 *        défaut (onmessage) ; toute autre clé est un événement nommé.
 * @param {{onOuvert?:Function, onErreur?:Function}} [opts]
 */
export function creerCanalSse(url, gestionnaires = {}, opts = {}) {
  let source = null;

  function connecter() {
    if (source) return source;                     // idempotent : pas de doublon
    if (typeof EventSource === 'undefined') {
      throw new Error('EventSource indisponible (contexte non-navigateur)');
    }
    source = new EventSource(url);
    for (const [nom, handler] of Object.entries(gestionnaires)) {
      if (nom === 'message') source.onmessage = handler;
      else source.addEventListener(nom, handler);
    }
    // EventSource se reconnecte nativement après une coupure ; on n'ajoute de
    // logique manuelle que via opts.onErreur si un canal en a besoin.
    if (opts.onOuvert) source.onopen = opts.onOuvert;
    if (opts.onErreur) source.onerror = opts.onErreur;
    return source;
  }

  function fermer() {
    if (source) { source.close(); source = null; }
  }

  return {
    connecter,
    fermer,
    estOuvert: () => source !== null,
    get source() { return source; },
  };
}

// ─── Contrôleur applicatif — canaux préconfigurés, NON connectés ─────────────
// Les gestionnaires ci-dessous écrivent dans le store (répartition). Ils ne
// s'exécuteront QUE lorsqu'un futur pas de la refonte appellera connecter().
// Import paresseux du store pour éviter tout couplage au chargement.
import { store } from './store.js';

function surEvenementIssue(e) {
  // /stream émet 'debut_issue' / 'fin_issue' : { projet, numero } et
  // 'creation_issue' (issue #627/#9a) : { projet, numero, titre, fichier? }.
  // On note la dernière notification dans le store ; le module Résultats
  // (static/js/resultats.js, issue #627) y est abonné et applique un
  // traitement CIBLÉ (jamais un rechargement de tous les projets).
  try {
    const donnees = JSON.parse(e.data);
    store.set('derniereNotifIssue', { ...donnees, type: e.type });
  } catch { /* données non-JSON ignorées */ }
}

function surShutdown() {
  store.set('serveurArrete', true);
}

export const sse = {
  stream: creerCanalSse('/stream', {
    debut_issue: surEvenementIssue,
    fin_issue: surEvenementIssue,
    creation_issue: surEvenementIssue,
  }),
  events: creerCanalSse('/events', {
    shutdown: surShutdown,
  }),
  // Raccourci de garde : à n'appeler qu'une fois l'ancienne gestion SSE retirée.
  connecterTout() { this.stream.connecter(); this.events.connecter(); },
  fermerTout() { this.stream.fermer(); this.events.fermer(); },
};
