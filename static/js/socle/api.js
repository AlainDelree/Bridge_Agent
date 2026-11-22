// api.js — point d'accès unique aux routes Flask (issue #625, étape 1).
//
// RESPONSABILITÉ
//   Un seul chemin pour parler au serveur. Contrairement aux ~68 fetch() en
//   dur de l'ancien app.js (qui testent un champ métier du JSON et laissent
//   passer les 500), api.* VÉRIFIE SYSTÉMATIQUEMENT response.ok et remonte
//   toute erreur de façon VISIBLE via toasts — plus jamais d'erreur avalée en
//   silence. Les erreurs sont aussi levées (ErreurApi) pour que l'appelant
//   puisse réagir ; passer { silencieux:true } supprime seulement le toast.
//
// CE QU'IL EXPOSE
//   - api.get(url, opts)                -> Promise<any>   (JSON parsé, ou null)
//   - api.post(url, corps, opts)        -> Promise<any>
//   - api.supprimer(url, opts)          -> Promise<any>
//   - api.requete(url, opts)            -> Promise<Response>  (bas niveau)
//   - api.lireJson(url, opts)           -> Promise<any>       (bas niveau)
//   - class ErreurApi { statut, url, corps }
//
// opts accepte toutes les options de fetch(), plus :
//   - silencieux: true  → ne pas afficher de toast d'erreur (l'erreur est quand
//                         même levée). Utile pour les rafraîchissements de fond.
//   - timeoutMs: N       → délai maximum avant abandon (issue #917 point 7,
//                         défaut TIMEOUT_DEFAUT_MS = 30s) : AUCUNE requête de
//                         l'interface ne doit plus rester bloquée
//                         indéfiniment (rafraîchissement périodique, copie du
//                         rapport...). `0`/`null` désactive le délai pour cet
//                         appel précis. `err.timeout` vaut true quand l'échec
//                         vient de ce délai (plutôt que d'une vraie coupure
//                         réseau), pour que l'appelant distingue les deux si
//                         besoin.

import { toasts } from './toasts.js';

export class ErreurApi extends Error {
  constructor(message, { statut = null, url = null, corps = null, timeout = false } = {}) {
    super(message);
    this.name = 'ErreurApi';
    this.statut = statut;
    this.url = url;
    this.corps = corps;
    this.timeout = timeout;
  }
}

// Délai maximum par défaut d'une requête (issue #917 point 7) — « de l'ordre
// de 30 s », valeur unique pour toute l'interface (rafraîchissement, copie).
export const TIMEOUT_DEFAUT_MS = 30000;

// Compteur de requêtes réseau (issue #835 point 4) : incrémenté pour CHAQUE
// appel (succès ou échec) — sert au résumé de la précharge, envoyé par
// resultats_coches.js à la fin de chaque série de préparations.
let nbRequetes = 0;

async function requete(url, options = {}) {
  const { silencieux = false, timeoutMs = TIMEOUT_DEFAUT_MS, ...optionsFetch } = options;
  nbRequetes += 1;
  // AbortController indisponible (vieux navigateur/Node sans global) : la
  // requête part alors sans délai plutôt que d'échouer à la construction.
  const controleur = (timeoutMs && typeof AbortController !== 'undefined') ? new AbortController() : null;
  const minuteur = controleur ? setTimeout(() => controleur.abort(), timeoutMs) : null;
  let reponse;
  try {
    reponse = await fetch(url, controleur ? { ...optionsFetch, signal: controleur.signal } : optionsFetch);
  } catch (e) {
    const expire = !!(controleur && controleur.signal && controleur.signal.aborted);
    const message = expire
      ? `Délai dépassé (${Math.round(timeoutMs / 1000)}s) sur ${url}`
      : `Serveur injoignable (${url}) : ${e.message}`;
    const err = new ErreurApi(message, { url, timeout: expire });
    if (!silencieux) toasts.erreur(err.message);
    throw err;
  } finally {
    if (minuteur) clearTimeout(minuteur);
  }
  if (!reponse.ok) {
    let corps = '';
    try { corps = (await reponse.text()).slice(0, 500); } catch { /* ignoré */ }
    const err = new ErreurApi(
      `Erreur ${reponse.status} sur ${url}`,
      { statut: reponse.status, url, corps });
    if (!silencieux) toasts.erreur(err.message);
    throw err;
  }
  return reponse;
}

// Lit la réponse en JSON, en tolérant un corps vide (renvoie null).
async function lireJson(url, options) {
  const reponse = await requete(url, options);
  const texte = await reponse.text();
  if (!texte) return null;
  try {
    return JSON.parse(texte);
  } catch (e) {
    const err = new ErreurApi(`Réponse non-JSON de ${url} : ${e.message}`, { url, corps: texte.slice(0, 500) });
    if (!options || !options.silencieux) toasts.erreur(err.message);
    throw err;
  }
}

function optionsJson(corps, opts = {}) {
  const options = { ...opts };
  if (corps !== undefined && corps !== null) {
    options.headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    options.body = JSON.stringify(corps);
  }
  return options;
}

export const api = {
  get: (url, opts) => lireJson(url, { ...opts, method: 'GET' }),
  post: (url, corps, opts) => lireJson(url, { ...optionsJson(corps, opts), method: 'POST' }),
  supprimer: (url, opts) => lireJson(url, { ...opts, method: 'DELETE' }),
  requete,
  lireJson,
  // Nombre total de requêtes faites depuis le chargement de la page (issue
  // #835 point 4) — un compteur simple, pas un historique : l'appelant
  // mesure une série en comparant deux lectures (avant/après).
  nombreRequetes: () => nbRequetes,
};
