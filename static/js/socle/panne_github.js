// panne_github.js — alerte explicite de panne GitHub (issue #732).
//
// RESPONSABILITÉ
//   À la réception d'un échec gh que le serveur a classé « panne probable »
//   (champ panne_probable:true dans la réponse JSON d'une route /issues-liste,
//   /issue, /envoyer ou /relancer-issue — jamais sur une erreur normale
//   404/401/403/422 ni sur la limite de débit, déjà signalée par le bandeau ⚡),
//   interroge GET /github-statut (app/github_status.py, cache serveur ~60s) et
//   affiche un message clair via toasts — SÉPARÉMENT de la réponse en échec
//   elle-même (jamais synchrone avec elle, jamais bloquant).
//
//   Tant que /github-statut répond panne:true, une nouvelle vérification a
//   lieu toutes les 60s (INTERVALLE_VERIFICATION_MS) ; dès qu'il répond
//   panne:false après avoir répondu panne:true, un message « GitHub est
//   rétabli. » est affiché une seule fois et le cycle de vérification s'arrête
//   — repris au prochain échec classé « panne probable ».
//
// CE QU'IL EXPOSE
//   - signalerEchecPossible(reponseJson) : à appeler avec le JSON (déjà
//     parsé) d'une réponse d'une des routes ci-dessus.
//   - extraireJsonErreur(erreurApi) : pour les appelants passant par
//     socle/api.js (ErreurApi.corps est le texte brut de la réponse, jamais
//     reparsé automatiquement côté api.js).
//   - doitDeclencherVerification/calculerTransition/calculerTypeToast : pure,
//     testées sous Node (static/js/tests/panne_github.test.js).

import { toasts } from './toasts.js';

const INTERVALLE_VERIFICATION_MS = 60000;
const MESSAGE_RETABLI = 'GitHub est rétabli.';

let verificationEnCours = false;
let dernierEtatPanne = false;

// ─── Fonctions PURES ────────────────────────────────────────────────────────

/** True si la réponse JSON d'une route gh porte le signal serveur de panne
 * probable — jamais déclenché sur une erreur normale (404/401/403/422) ni sur
 * la limite de débit. */
export function doitDeclencherVerification(reponseJson) {
  return !!(reponseJson && reponseJson.panne_probable);
}

/** Message « GitHub est rétabli. » au passage panne → plus de panne, sinon
 * null — pure, appelée une fois par transition. */
export function calculerTransition(etaitEnPanne, estEnPanne) {
  return (etaitEnPanne && !estEnPanne) ? MESSAGE_RETABLI : null;
}

/** Type de toast selon la gravité renvoyée par /github-statut : un incident
 * GitHub ou une page de statut injoignable reste une erreur (persistant,
 * bouton de fermeture) ; une cause locale (connexion/jeton) est un simple
 * avertissement — GitHub, lui, fonctionne. */
export function calculerTypeToast(gravite) {
  return gravite === 'ok' ? 'avertissement' : 'erreur';
}

/** Reconstruit le JSON d'erreur à partir d'une ErreurApi (socle/api.js) :
 * `corps` y est le texte brut de la réponse (jamais reparsé par api.js en cas
 * de !response.ok) — null si absent ou non-JSON, jamais levé. */
export function extraireJsonErreur(erreurApi) {
  if (!erreurApi || typeof erreurApi.corps !== 'string' || !erreurApi.corps) return null;
  try { return JSON.parse(erreurApi.corps); } catch { return null; }
}

// ─── Vérification différée (impure — réseau, toasts) ───────────────────────

async function verifierEtAfficher() {
  let donnees = null;
  try {
    const rep = await fetch('/github-statut');
    donnees = await rep.json();
  } catch {
    // Vérification elle-même en échec (serveur local injoignable, p.ex. onglet
    // ouvert avant le redémarrage de new_issue.py) : aucune erreur visible de
    // plus (contrainte de l'issue #732) — on retentera au prochain cycle.
  }

  const estEnPanne = !!(donnees && donnees.panne);
  const transition = calculerTransition(dernierEtatPanne, estEnPanne);
  if (transition) {
    toasts.info(transition);
  } else if (donnees && donnees.message) {
    toasts[calculerTypeToast(donnees.gravite)](donnees.message);
  }
  dernierEtatPanne = estEnPanne;

  if (estEnPanne) {
    setTimeout(verifierEtAfficher, INTERVALLE_VERIFICATION_MS);
  } else {
    verificationEnCours = false;
  }
}

/**
 * Point d'entrée appelé par chaque callsite gh surveillé (listes d'issues,
 * détail, création, relance, labels) avec le JSON de sa réponse. Ne fait rien
 * si le serveur n'a pas classé l'échec comme « panne probable », ou si une
 * chaîne de vérification est déjà en cours (anti-doublon : un seul polling
 * actif à la fois, quel que soit le nombre d'échecs simultanés).
 */
export function signalerEchecPossible(reponseJson) {
  if (!doitDeclencherVerification(reponseJson)) return;
  if (verificationEnCours) return;
  verificationEnCours = true;
  verifierEtAfficher();
}
