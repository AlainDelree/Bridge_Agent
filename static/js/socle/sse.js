// sse.js — gestion centralisée du canal /stream (issue #625, étape 1 ;
// connecté depuis l'étape 3, issue #627).
//
// RESPONSABILITÉ
//   Un canal = ouverture, écoute des événements nommés, reconnexion, et
//   répartition (dispatch) des événements reçus vers le store. `/events`
//   (cycle de vie serveur : heartbeat, shutdown) reste géré directement par
//   l'ancien app.js (`sourceEvents`), qui n'est jamais passé par ce module.
//
// CE QU'IL EXPOSE
//   - creerCanalSse(url, gestionnaires, opts) : fabrique un contrôleur de canal.
//   - sse.stream : le canal /stream, préconfiguré pour écrire dans le store.
//     Connecté par static/js/resultats.js::initialiser() (issue #627) — pas ici,
//     pour qu'un import de ce module reste sûr sous Node (où EventSource
//     n'existe pas : `new EventSource` n'est créé que dans connecter()).

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
  // Horodatage du dernier événement reçu (tout type confondu) OU de la
  // dernière (ré)ouverture — issue #878, journal de diagnostic de la copie
  // presse-papier : un clic « sans effet » suivant une longue inactivité
  // d'onglet coïncide-t-il avec un flux resté silencieux longtemps ? Lecture
  // SEULE (etat()/depuisDerniereActiviteMs() ci-dessous) : ne décide jamais
  // d'une reconnexion, EventSource s'en charge nativement.
  let derniereActiviteMs = null;

  // optsAppel.onOuvert (issue #705) : surcharge opts.onOuvert pour CET appel —
  // permet à un module appelant (ex. resultats.js) de réagir aux reconnexions
  // sans que ce module générique sache rien de la logique métier déclenchée.
  function connecter(optsAppel = {}) {
    if (source) return source;                     // idempotent : pas de doublon
    if (typeof EventSource === 'undefined') {
      throw new Error('EventSource indisponible (contexte non-navigateur)');
    }
    source = new EventSource(url);
    for (const [nom, handler] of Object.entries(gestionnaires)) {
      const handlerAvecActivite = (e) => { derniereActiviteMs = Date.now(); handler(e); };
      if (nom === 'message') source.onmessage = handlerAvecActivite;
      else source.addEventListener(nom, handlerAvecActivite);
    }
    // EventSource se reconnecte nativement après une coupure ; on n'ajoute de
    // logique manuelle que via opts.onErreur si un canal en a besoin.
    const onOuvert = optsAppel.onOuvert || opts.onOuvert;
    source.onopen = (e) => {
      derniereActiviteMs = Date.now();
      if (onOuvert) onOuvert(e);
    };
    if (opts.onErreur) source.onerror = opts.onErreur;
    return source;
  }

  function fermer() {
    if (source) { source.close(); source = null; }
  }

  // État readyState du canal (0 CONNECTING / 1 OPEN / 2 CLOSED), ou null
  // avant toute connexion — issue #878.
  function etat() { return source ? source.readyState : null; }

  // Millisecondes depuis le dernier événement/ouverture, ou null si aucune
  // activité n'a encore eu lieu — issue #878.
  function depuisDerniereActiviteMs(maintenant = Date.now()) {
    return derniereActiviteMs == null ? null : maintenant - derniereActiviteMs;
  }

  return { connecter, fermer, etat, depuisDerniereActiviteMs };
}

// ─── Contrôleur applicatif — canal /stream préconfiguré ──────────────────────
// Les gestionnaires ci-dessous écrivent dans le store (répartition), exécutés
// une fois static/js/resultats.js::initialiser() appelée (issue #627).
// Import paresseux du store pour éviter tout couplage au chargement.
import { store } from './store.js';

function surEvenementIssue(e) {
  // /stream émet 'debut_issue' / 'fin_issue' : { projet, numero } et
  // 'creation_issue' (issue #627/#9a, enrichi #634) :
  // { projet, numero, titre, labels, timing, fichier? }.
  // On note la dernière notification dans le store ; le module Résultats
  // (static/js/resultats.js, issue #627) y est abonné et applique un
  // traitement CIBLÉ (jamais un rechargement de tous les projets).
  try {
    const donnees = JSON.parse(e.data);
    store.set('derniereNotifIssue', { ...donnees, type: e.type });
  } catch { /* données non-JSON ignorées */ }
}

// /stream émet aussi (issue #639, fusion « Résultats inbox » dans Résultats) :
//   fichier_recu   : { fichier }
//   fichier_refuse : { fichier, titre?, motif }
// Ces événements ne concernent pas une issue précise (pas de projet/numéro) :
// ils sont notés dans une tranche DÉDIÉE du store (derniereNotifFichier), à
// laquelle le module Résultats (static/js/resultats.js) est abonné pour
// insérer/transformer les lignes « fichier reçu / refusé » de la liste.
function surEvenementFichier(e) {
  try {
    const donnees = JSON.parse(e.data);
    store.set('derniereNotifFichier', { ...donnees, type: e.type });
  } catch { /* données non-JSON ignorées */ }
}

// /stream émet aussi (issue #720, décoche automatique après une RELANCE
// réussie, §3.14) : case_decochee : { projet, numero }. Noté dans une
// tranche DÉDIÉE du store (derniereNotifCase), consommée par
// static/js/resultats_coches.js — pas resultats.js, la case « traité/lu »
// étant une préoccupation distincte (voir l'en-tête de ce module).
function surEvenementCase(e) {
  try {
    const donnees = JSON.parse(e.data);
    store.set('derniereNotifCase', { ...donnees, type: e.type });
  } catch { /* données non-JSON ignorées */ }
}

export const sse = {
  stream: creerCanalSse('/stream', {
    debut_issue: surEvenementIssue,
    fin_issue: surEvenementIssue,
    creation_issue: surEvenementIssue,
    fichier_recu: surEvenementFichier,
    fichier_refuse: surEvenementFichier,
    case_decochee: surEvenementCase,
  }),
};
