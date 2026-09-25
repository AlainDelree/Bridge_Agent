// pont.js — mécanisme de transition ancien code ⇄ socle (issue #625, étape 1).
//
// POURQUOI CE FICHIER EXISTE
//   L'ancien static/js/app.js reste chargé comme SCRIPT CLASSIQUE (pas comme
//   module) : ses ~233 fonctions doivent rester globales car >70 gestionnaires
//   inline du HTML (onclick="…") et des handlers générés en texte les appellent
//   par leur nom, et le mode strict des modules casserait du code ancien.
//   Or un module, lui, est isolé (rien n'est global). pont.js est LE SEUL point
//   de contact entre les deux mondes, dans les deux sens :
//
//   1. ancien → socle : window.Bridge expose les briques (store, api, toasts,
//      dom, sse, persistance). L'ancien app.js peut donc, temporairement, lire
//      le store ou lever un toast via window.Bridge.toasts.info(...).
//
//   2. socle → ancien : appelerAncien('nomFonction', ...args) appelle une
//      fonction globale de l'ancien app.js sans y faire référence en dur (elle
//      n'est pas importable). Renvoie undefined + un warn si absente.
//
// COHABITATION ANCIEN CODE ⇄ STORE
//   À l'étape 1, le store ne pilote rien : l'ancien code reste la seule source
//   de vérité vivante. Quand une donnée migrera dans le store (étapes suivantes)
//   et que l'ancien code en a encore besoin, on posera ICI un miroir explicite
//   (store.abonnerCle(...) → variable/DOM ancien), à retirer avec le reste.
//
// SUPPRESSION À LA DERNIÈRE ÉTAPE
//   Ce fichier est conçu pour disparaître ENTIÈREMENT quand app.js sera vidé :
//   supprimer pont.js, l'appel installerPont() dans index.js, et toute
//   référence à window.Bridge / appelerAncien. Aucune autre brique ne dépend de
//   pont.js — le socle reste fonctionnel sans lui.

export const NOM_GLOBAL = 'Bridge';

/**
 * Installe le pont : publie les briques sous window.Bridge et renvoie l'objet.
 * @param {object} briques  { store, api, toasts, dom, sse, persistance }
 */
export function installerPont(briques) {
  if (typeof window === 'undefined') return null;
  const pont = Object.assign(window[NOM_GLOBAL] || {}, briques, { appelerAncien });
  window[NOM_GLOBAL] = pont;
  return pont;
}

/**
 * Appelle une fonction globale de l'ancien app.js par son nom.
 * @param {string} nom  Nom de la fonction globale (ex. 'rafraichirResultats').
 * @returns la valeur de retour de la fonction, ou undefined si introuvable.
 */
export function appelerAncien(nom, ...args) {
  const fn = typeof window !== 'undefined' ? window[nom] : undefined;
  if (typeof fn !== 'function') {
    console.warn(`[pont] fonction ancienne introuvable : ${nom}`);
    return undefined;
  }
  return fn(...args);
}
