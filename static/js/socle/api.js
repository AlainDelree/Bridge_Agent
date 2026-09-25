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
//   - class ErreurApi { statut, url, corps }
//
// opts accepte toutes les options de fetch(), plus :
//   - silencieux: true  → ne pas afficher de toast d'erreur (l'erreur est quand
//                         même levée). Utile pour les rafraîchissements de fond.

import { toasts } from './toasts.js';

export class ErreurApi extends Error {
  constructor(message, { statut = null, url = null, corps = null } = {}) {
    super(message);
    this.name = 'ErreurApi';
    this.statut = statut;
    this.url = url;
    this.corps = corps;
  }
}

async function requete(url, options = {}) {
  const { silencieux = false, ...optionsFetch } = options;
  let reponse;
  try {
    reponse = await fetch(url, optionsFetch);
  } catch (e) {
    const err = new ErreurApi(`Serveur injoignable (${url}) : ${e.message}`, { url });
    if (!silencieux) toasts.erreur(err.message);
    throw err;
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
};
