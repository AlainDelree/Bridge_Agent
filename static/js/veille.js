// veille.js — voile de veille/réveil, rechargement CIBLÉ de la liste sur
// événements (début/fin de traitement, création), surveillance du flux
// /stream et réglage associé (issues #917, réduit par #933).
//
// POURQUOI CE MODULE EXISTE
//   Avant l'issue #917, aucun rechargement périodique de la liste Résultats
//   n'avait jamais existé (voir l'étude #916) : la liste n'était alimentée
//   que par les événements /stream et des rattrapages ponctuels (retour de
//   masquage de l'onglet, reconnexion SSE, ↻ explicite). #917 avait ajouté
//   un rafraîchissement périodique du projet sélectionné, en BACKUP du flux
//   /stream. L'étude #933 a montré que ce polling à intervalle fixe n'était
//   ni nécessaire (les transitions utiles — création, début, fin de
//   traitement — sont déjà des événements identifiables) ni suffisant (une
//   ligne pouvait rester absente plusieurs secondes après sa création, sans
//   lien avec l'intervalle réglé) : il a donc été RETIRÉ par #933, remplacé
//   par un rechargement déclenché par ces événements eux-mêmes.
//
// CE QUE CE MODULE FAIT
//   - Détecte l'inactivité (mouvement de souris, clic, clavier, défilement ;
//     fenêtre au premier plan ou non — voir l'en-tête de installerDetectionActivite
//     pour ce qui n'a PAS pu être vérifié sans navigateur réel) et affiche un
//     voile gris semi-opaque (#voile-veille, templates/fragments/voile_veille.html)
//     après `delaiVeilleMin` minutes sans activité (0 désactive la veille —
//     SEUL réglage restant de ce module, issue #933 point 3).
//   - Pendant la veille : AUCUN appel réseau GitHub (les rechargements
//     déclenchés par événement ci-dessous sont suspendus) ; les petites
//     requêtes locales existantes (battement, watchers, panneau
//     Infrastructure à 30s, badge inbox…) ne sont PAS touchées par ce module.
//   - Le premier clic ou la première touche est ABSORBÉ par le voile (aucune
//     action sur ce qui se trouve dessous) : il lance le rechargement CIBLÉ
//     du/des projet(s) actuellement sélectionné(s) dans le filtre Résultats
//     (liste + timing, resultats.rafraichirSelection) et du panneau
//     Infrastructure, puis le préchargement des rapports visibles — jamais
//     une rafale sur tous les projets configurés. Délai maximum
//     (DELAI_MAX_REVEIL_MS) : au-delà, état d'erreur explicite avec bouton
//     Réessayer — jamais de disparition silencieuse du voile sans données.
//     Avant ce rechargement, le flux /stream est rouvert s'il est resté
//     silencieux trop longtemps (issue #933 point 4, voir §flux ci-dessous).
//   - À la création d'une issue (événement SSE `creation_issue`) : rechargement
//     ciblé immédiat du PROJET CONCERNÉ, puis un second après
//     RATTRAPAGE_CREATION_SEC (valeur FIXE, plus réglable depuis #933) — en
//     BACKUP du flux /stream. Rien pendant la veille (rattrapé par le réveil).
//   - Au DÉBUT et à la FIN de traitement d'une issue (événements SSE
//     `debut_issue`/`fin_issue`, issue #933 point 2) : rechargement ciblé de
//     la liste du PROJET CONCERNÉ seulement (`resultats.chargerListe`), avec
//     la raison transmise au journal serveur. Pour la fin, l'événement arrive
//     deux fois de suite pour une même issue (watcher.py) : regroupé, un seul
//     rechargement par fenêtre (voir doitRechargerSurFin). Rien pendant la
//     veille.
//   - Surveillance du flux /stream (issue #933 point 4, corrigée par #937) :
//     sans rafraîchissement périodique, une coupure silencieuse du flux ne se
//     verrait plus. Un minuteur local (aucun appel GitHub) vérifie
//     périodiquement l'ancienneté du dernier message reçu (événement OU
//     battement serveur — depuis #937, un événement SSE nommé `battement`
//     que le navigateur transmet réellement, voir sse.js ; avant #937 c'était
//     un commentaire SSE invisible du navigateur, jamais compté comme une
//     activité). Au-delà de SEUIL_STREAM_SILENCIEUX_MS (trois fois
//     l'intervalle des battements serveur, voir app/fin_issue.py::DELAI_PING)
//     ET d'un délai de grâce équivalent depuis la dernière connexion ou
//     réouverture explicite (issue #937, fautDeclarerStreamSilencieux — sans
//     quoi la toute première ouverture, ou une réouverture pas encore
//     confirmée, serait jugée silencieuse à tort, voire empêchée de jamais
//     réussir) : le flux est fermé puis rouvert explicitement, l'ancienneté
//     constatée journalisée (logs/charge_interface.log), et le(s) projet(s)
//     sélectionné(s) rechargés UNE SEULE FOIS par épisode de silence (pas à
//     chaque vérification si le flux reste réellement muet). Suspendu
//     pendant la veille ; vérifié explicitement au réveil (avant le
//     rechargement normal du réveil), qui réarme aussi ce délai de grâce.
//   - À la (dé)sélection d'un projet dans le filtre Résultats (pastilles) :
//     surSelectionChangee(), appelée depuis app.js (basculerFiltreProjet/
//     basculerTousLesFiltres via le pont) — un projet qui vient d'être
//     sélectionné n'est rechargé QU'À CE MOMENT, pas avant.
//   - Réglage modifiable par Alain (délai de veille) : stocké via
//     window.Bridge.persistance (seul point d'accès autorisé au
//     localStorage), effet immédiat sans rechargement de page — voir
//     initZoneVeille(). Affiché dans le panneau Infrastructure, partie
//     globale, près de l'interrupteur de son (templates/fragments/
//     panneau_lateral.html, #pl-zone-veille).
//
// CE QUE CE MODULE NE FAIT PLUS (retiré par l'issue #933)
//   - Rafraîchissement périodique à intervalle fixe du projet sélectionné
//     (réglage « Rafraîchir toutes les (s) », coût GitHub/h affiché) : les
//     événements début/fin de traitement ci-dessus en tiennent désormais
//     lieu, sans jamais interroger GitHub en l'absence de transition réelle.
//   - Réglage « Rattrapage création (s) » : le rattrapage à la création
//     reste, mais sa durée est désormais FIXE dans le code (RATTRAPAGE_CREATION_SEC).
//
// CE QUE CE MODULE NE FAIT PAS
//   - Il ne gère ni le bandeau rouge « connexion perdue » (issue #917 point
//     8, dérivé de sourceEvents.onerror/onopen — static/js/app.js, hors
//     socle) ni la fenêtre de repli de la copie du rapport (issue #917 point
//     7 — static/js/resultats_coches.js).
//   - Il ne touche jamais au décompte TOUS projets (chargerTimingTous) ni au
//     ↻ explicite (rafraichirResultats, app.js) : ces chemins existants
//     restent inchangés, seul ce module utilise resultats.rafraichirSelection/
//     resultats.chargerListe (périmètre strictement restreint au(x) projet(s)
//     concerné(s)).

import { store } from './socle/store.js';
import * as dom from './socle/dom.js';
import * as persistance from './socle/persistance.js';
import { appelerAncien } from './socle/pont.js';
import { resultats } from './resultats.js';
import { resultatsCoches } from './resultats_coches.js';

// ─────────────────────────────────────────────────────────────────────────────
// 1. LOGIQUE PURE (testée sous Node — voir static/js/tests/veille.test.js)
// ─────────────────────────────────────────────────────────────────────────────

export const DEFAUT_DELAI_VEILLE_MIN = 30;

// Valeur absente ou invalide → défaut (issue #917 point 5). 0 est une valeur
// valide pour le délai de veille (désactivation explicite) — distincte d'une
// valeur invalide : `null`/`undefined`/'' sont écartés explicitement AVANT la
// conversion en nombre, Number(null) et Number('') valant tous deux 0 (ce qui
// confondrait sinon « absente » avec « 0 minute, désactivée »).
export function normaliserDelaiVeilleMin(valeur) {
  if (valeur == null || valeur === '') return DEFAUT_DELAI_VEILLE_MIN;
  const n = Number(valeur);
  if (!Number.isFinite(n) || n < 0) return DEFAUT_DELAI_VEILLE_MIN;
  return Math.round(n);
}

// true si l'interface doit entrer en veille — delaiVeilleMin <= 0 désactive
// la veille (jamais vrai). `derniereActiviteMs` null (aucune activité jamais
// enregistrée, ex. tests) → jamais de veille par défaut d'horloge manquante.
export function doitEntrerEnVeille(derniereActiviteMs, maintenantMs, delaiVeilleMin) {
  if (!delaiVeilleMin || delaiVeilleMin <= 0) return false;
  if (derniereActiviteMs == null) return false;
  return (maintenantMs - derniereActiviteMs) >= delaiVeilleMin * 60000;
}

// Rattrapage à la création d'une issue (issue #917 point 3) : valeur FIXE
// depuis #933 (n'est plus un réglage — voir l'en-tête de ce module).
export const RATTRAPAGE_CREATION_SEC = 10;

// ─── Regroupement des doublons de fin_issue (issue #933 point 2) ────────────
// watcher.py poste deux fois `fin_issue` à quelques secondes d'intervalle
// pour une même issue (constat de l'étude #933) : un seul rechargement par
// fenêtre, pas un par événement. Logique pure, testable sans minuteur réel :
// `dernierRechargementMs` est l'horodatage du dernier rechargement déjà
// déclenché pour CETTE issue (null si aucun encore).
export const FENETRE_REGROUPEMENT_FIN_MS = 3000;
export function doitRechargerSurFin(dernierRechargementMs, maintenantMs, fenetreMs = FENETRE_REGROUPEMENT_FIN_MS) {
  if (dernierRechargementMs == null) return true;
  return (maintenantMs - dernierRechargementMs) >= fenetreMs;
}

// ─── Surveillance du flux /stream (issue #933 point 4) ──────────────────────
// Intervalle réel des battements serveur du flux /stream (app/fin_issue.py,
// DELAI_PING = 30s — PAS le canal /events du cycle de vie serveur, dont le
// heartbeat suit sa propre logique, inchangée, dans static/js/app.js).
// Seuil retenu : trois fois cet intervalle, demandé par l'issue — au-delà,
// le flux est considéré silencieux (coupure non détectée par EventSource,
// ex. proxy/tunnel qui absorbe la coupure sans déclencher onerror).
export const INTERVALLE_BATTEMENT_STREAM_SEC = 30;
export const SEUIL_STREAM_SILENCIEUX_MS = 3 * INTERVALLE_BATTEMENT_STREAM_SEC * 1000;
export function fautRouvrirStream(depuisDernierMessageMs, seuilMs = SEUIL_STREAM_SILENCIEUX_MS) {
  return depuisDernierMessageMs == null || depuisDernierMessageMs >= seuilMs;
}

// ─── Grâce/réouverture — pas de déclenchement en boucle (issue #937) ────────
// `fautRouvrirStream` seul répond « oui » dans deux cas qui ne sont PAS un
// flux silencieux : (a) juste après le chargement de la page, avant qu'une
// première ouverture ait pu être confirmée (`depuisDernierMessageMs` vaut
// encore `null`) ; (b) juste après une fermeture/réouverture EXPLICITE
// décidée par cette même surveillance, tant que l'ouverture n'a pas eu le
// temps d'être confirmée. Sans garde-fou, le cas (b) est même auto-entretenu :
// rouvrir détruit la tentative de connexion en cours avant qu'elle n'ait pu
// réussir, ce qui la fait paraître encore « jamais ouverte » à la vérification
// suivante (constat du 23/11/2026, juste après un redémarrage de l'interface).
// `depuisReferenceMs` porte l'ancienneté du dernier point de départ de grâce
// connu (connexion initiale OU dernière réouverture explicite — voir
// demarrerSurveillanceStream/verifierEtRouvrirStreamSiSilencieux ci-dessous) :
// le silence n'est déclaré que si CE délai a, lui aussi, dépassé le seuil.
export function fautDeclarerStreamSilencieux(
  depuisDernierMessageMs, depuisReferenceMs, seuilMs = SEUIL_STREAM_SILENCIEUX_MS,
) {
  return fautRouvrirStream(depuisDernierMessageMs, seuilMs) && depuisReferenceMs >= seuilMs;
}

// true si CE silence doit encore déclencher un rechargement de la liste
// (issue #937 point 3) : si le flux reste réellement muet, la surveillance
// continue de le rouvrir à chaque vérification au-delà du seuil, mais UN
// SEUL rechargement par épisode de silence — pas un par vérification.
// `episodeDejaSignale` est remis à faux dès que le flux redonne signe de vie
// (voir verifierEtRouvrirStreamSiSilencieux).
export function doitRechargerListePourSilence(episodeDejaSignale) {
  return !episodeDejaSignale;
}

// true si l'affichage « sync HH:MM:SS » doit être coloré comme ancien (issue
// #917 point 6) : jamais synchronisé, ou plus ancien que `seuilMs` — depuis
// #933 (plus d'intervalle de rafraîchissement réglable), ce seuil est le même
// que celui de la surveillance du flux ci-dessus plutôt qu'un multiple d'un
// réglage disparu.
export function estSyncAncienne(dernierSyncMs, maintenantMs, seuilMs = SEUIL_STREAM_SILENCIEUX_MS) {
  if (dernierSyncMs == null) return true;
  return (maintenantMs - dernierSyncMs) >= seuilMs;
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. ORCHESTRATION NAVIGATEUR (DOM + réseau + store)
//    Rien de ce qui suit ne s'exécute à l'import ; tout part d'initVeille().
// ─────────────────────────────────────────────────────────────────────────────

const INTERVALLE_VERIF_INACTIVITE_MS = 5000;   // vérif locale, aucun réseau
// Délai maximum du réveil (issue #917 point 2) — même ordre de grandeur que
// api.js::TIMEOUT_DEFAUT_MS (chaque requête individuelle est déjà bornée à ce
// délai ; celui-ci borne la séquence ENTIÈRE liste+timing du réveil).
const DELAI_MAX_REVEIL_MS = 30000;
const DELAI_DEBOUNCE_SELECTION_MS = 300;
// Fréquence de vérification du flux (issue #933 point 4) — locale, aucun
// réseau tant que rien d'anormal n'est détecté ; plus fine que le seuil lui-
// même pour le détecter avec une marge raisonnable.
const INTERVALLE_VERIF_STREAM_MS = 15000;

let derniereActiviteMs = null;
let enVeilleActif = false;          // true dès l'entrée en veille, jusqu'au réveil RÉUSSI
let etatVoile = 'eveille';          // 'eveille' | 'veille' | 'reveil' | 'erreur'
let generationReveil = 0;           // un réveil supplanté (nouvelle entrée en veille) devient silencieux
let minuteurVerifInactivite = null;
let minuteurVerifStream = null;
let minuteurDebounceSelection = null;
// Dernier rechargement déclenché par un fin_issue, par issue (issue #933
// point 2) — clé "projet#numero" -> horodatage ms, voir doitRechargerSurFin.
const dernierRechargementFin = new Map();
// Point de départ de grâce de la surveillance du flux (issue #937) — réarmé
// à chaque (re)démarrage de la surveillance (connexion initiale, réveil) ET
// à chaque réouverture explicite décidée par elle-même (voir
// demarrerSurveillanceStream/verifierEtRouvrirStreamSiSilencieux) : tant que
// ce délai n'a pas, lui aussi, dépassé le seuil, le silence n'est jamais
// déclaré (voir fautDeclarerStreamSilencieux).
let referenceSilenceStreamMs = null;
// Un seul rechargement de liste par épisode de silence (issue #937 point 3)
// — vrai dès le premier rechargement déclenché pour l'épisode en cours,
// remis à faux dès que le flux redonne signe de vie.
let episodeSilenceStreamSignale = false;

function maintenant() { return Date.now(); }

function lireReglages() {
  return {
    delaiVeilleMin: normaliserDelaiVeilleMin(
      persistance.lire(persistance.CLES.veilleDelaiMin, DEFAUT_DELAI_VEILLE_MIN)),
  };
}

// Projets actuellement sélectionnés dans le filtre Résultats (pastilles) —
// fonction DE L'ANCIEN app.js, non portée dans cette issue : via le pont,
// comme le reste des lectures d'état restées côté app.js. Jamais undefined.
function projetsSelectionnes() {
  return appelerAncien('projetsActifsDansFiltreResultats') || [];
}

// ─── Détection d'inactivité ──────────────────────────────────────────────────
// Événements « petits » (souris/molette/tactile) : simple mise à jour de
// l'horodatage, aucune absorption. Le clavier est traité à part ci-dessous
// (installerAbsorptionVoile) car il doit AUSSI, pendant la veille, absorber
// la première touche avant qu'elle n'atteigne l'élément focus — un simple
// listener d'activité ne suffit pas pour ça.
//
// NON VÉRIFIÉ SANS NAVIGATEUR RÉEL (à vérifier manuellement, voir le rapport
// de clôture et VERIFICATIONS_MANUELLES.md) : si ces événements continuent
// bien à se déclencher quand la fenêtre n'a PAS le focus (autre application
// au premier plan) — le comportement dépend du système de fenêtrage et du
// navigateur, pas seulement de ce code.
const EVENEMENTS_ACTIVITE_SOURIS = ['mousemove', 'mousedown', 'wheel', 'touchstart', 'scroll'];

function surActivite() { derniereActiviteMs = maintenant(); }

function installerDetectionActivite() {
  if (typeof window === 'undefined') return;
  for (const type of EVENEMENTS_ACTIVITE_SOURIS) {
    window.addEventListener(type, surActivite, { passive: true, capture: true });
  }
}

function verifierInactivite() {
  if (enVeilleActif) return;
  const { delaiVeilleMin } = lireReglages();
  if (doitEntrerEnVeille(derniereActiviteMs, maintenant(), delaiVeilleMin)) entrerEnVeille();
}

// ─── Voile (affichage) ───────────────────────────────────────────────────────
function afficherVoile() {
  const voile = dom.$('#voile-veille');
  const texte = dom.$('#voile-veille-texte');
  const bouton = dom.$('#voile-veille-reessayer');
  if (!voile || !texte) return;
  voile.classList.add('actif');
  voile.classList.toggle('erreur', etatVoile === 'erreur');
  if (bouton) bouton.style.display = etatVoile === 'erreur' ? '' : 'none';
  if (etatVoile === 'reveil') texte.textContent = 'Mise à jour…';
  else if (etatVoile === 'erreur') {
    texte.textContent = 'Mise à jour impossible (délai dépassé ou erreur réseau) — '
      + 'les données affichées peuvent être périmées.';
  } else {
    texte.textContent = 'Interface en veille — cliquez pour la réveiller';
  }
}

function masquerVoile() {
  const voile = dom.$('#voile-veille');
  if (voile) voile.classList.remove('actif', 'erreur');
}

// ─── Transitions d'état ──────────────────────────────────────────────────────
function entrerEnVeille() {
  enVeilleActif = true;
  etatVoile = 'veille';
  arreterSurveillanceStream();
  afficherVoile();
}

function sortirDeVeille() {
  enVeilleActif = false;
  etatVoile = 'eveille';
  derniereActiviteMs = maintenant();
  masquerVoile();
  demarrerSurveillanceStream();
}

// Séquence réelle du réveil : vérifie d'abord l'ancienneté du dernier message
// du flux /stream et le rouvre si besoin (issue #933 point 4, AVANT le
// rechargement normal — aucun appel GitHub supplémentaire, rouvrir le flux
// est purement local), puis rechargement ciblé liste+timing + panneau
// Infrastructure + préchargement des rapports visibles (file plafonnée
// existante, issue #835) — jamais une rafale sur tous les projets.
async function executerReveil(projets) {
  verifierEtRouvrirStreamSiSilencieux();
  const resultat = await resultats.rafraichirSelection(projets, { raison: 'reveil' });
  rafraichirPanneauInfra();
  if (typeof resultatsCoches.precharderVisibles === 'function') resultatsCoches.precharderVisibles();
  return resultat;
}

function rafraichirPanneauInfra() {
  if (typeof window !== 'undefined' && typeof window.rafraichirPanneauLateralResultats === 'function') {
    window.rafraichirPanneauLateralResultats();
  }
}

async function attendreAvecDelaiMax(promesse, delaiMs) {
  let minuteur = null;
  const expiration = new Promise((resoudre) => {
    minuteur = setTimeout(() => resoudre({ succes: false, expire: true }), delaiMs);
  });
  try {
    return await Promise.race([promesse, expiration]);
  } finally {
    clearTimeout(minuteur);
  }
}

async function lancerReveil() {
  const monGen = ++generationReveil;
  etatVoile = 'reveil';
  afficherVoile();
  let resultat;
  try {
    resultat = await attendreAvecDelaiMax(executerReveil(projetsSelectionnes()), DELAI_MAX_REVEIL_MS);
  } catch (e) {
    resultat = { succes: false };
  }
  if (monGen !== generationReveil) return;   // supplanté (nouvelle entrée en veille/nouveau réveil)
  if (resultat && resultat.succes) sortirDeVeille();
  else { etatVoile = 'erreur'; afficherVoile(); }
}

// ─── Absorption du premier clic/de la première touche ───────────────────────
function installerAbsorptionVoile() {
  if (typeof document === 'undefined') return;
  const voile = dom.$('#voile-veille');
  if (voile) {
    voile.addEventListener('click', (e) => {
      if (!enVeilleActif) return;
      e.preventDefault();
      e.stopPropagation();
      if (etatVoile === 'veille') lancerReveil();
    });
  }
  const bouton = dom.$('#voile-veille-reessayer');
  if (bouton) {
    bouton.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (enVeilleActif && etatVoile === 'erreur') lancerReveil();
    });
  }
  // Clavier (issue #917 point 1) : à la différence d'un clic, la première
  // touche ne vise pas forcément le voile (elle vise l'élément qui a le
  // focus) — un listener en phase de CAPTURE sur window, posé AVANT que
  // l'événement n'atteigne cet élément, est le seul moyen de l'absorber.
  // Double comme signal d'activité (surActivite ci-dessus en fait de même
  // pour souris/molette/tactile) : aucun conflit, stopPropagation() n'empêche
  // jamais un AUTRE listener posé sur le MÊME nœud de s'exécuter.
  if (typeof window !== 'undefined') {
    window.addEventListener('keydown', (e) => {
      derniereActiviteMs = maintenant();
      if (!enVeilleActif) return;
      e.preventDefault();
      e.stopPropagation();
      if (etatVoile === 'veille') lancerReveil();
    }, { capture: true });
  }
}

// ─── Surveillance du flux /stream (issue #933 point 4) ──────────────────────
function arreterSurveillanceStream() {
  if (minuteurVerifStream) { clearInterval(minuteurVerifStream); minuteurVerifStream = null; }
}

function demarrerSurveillanceStream() {
  arreterSurveillanceStream();
  // Point de départ de la grâce (issue #937, voir referenceSilenceStreamMs) :
  // repart de zéro à chaque (re)démarrage de la surveillance — connexion
  // initiale (page chargée) comme réveil — pour ne jamais juger un flux
  // silencieux avant qu'une ouverture n'ait eu le temps d'être confirmée.
  referenceSilenceStreamMs = maintenant();
  episodeSilenceStreamSignale = false;
  minuteurVerifStream = setInterval(verifierEtRouvrirStreamSiSilencieux, INTERVALLE_VERIF_STREAM_MS);
}

// Vérifie l'ancienneté du dernier message reçu sur /stream (événement ou
// battement serveur, issue #937 — AVANT ce correctif, le battement serveur
// était un commentaire SSE invisible du navigateur, voir sse.js) ; au-delà
// du seuil ET du délai de grâce depuis la dernière connexion/réouverture
// (fautDeclarerStreamSilencieux), ferme et rouvre explicitement le canal,
// journalise l'ancienneté constatée (logs/charge_interface.log, issue #937
// point 4), puis recharge la liste du/des projet(s) sélectionné(s) — UNE
// SEULE FOIS par épisode de silence (issue #937 point 3), pas à chaque
// vérification si le flux reste réellement muet. Aucun autre appel GitHub.
// Rien pendant la veille (appelée aussi au réveil, AVANT le rechargement
// normal — voir executerReveil).
function verifierEtRouvrirStreamSiSilencieux() {
  if (enVeilleActif) return;
  const maintenantMs = maintenant();
  const depuisActivite = resultats.derniereActiviteStreamMs();
  if (depuisActivite != null && !fautRouvrirStream(depuisActivite)) {
    // Flux sain : fin de l'épisode de silence en cours, s'il y en avait un.
    episodeSilenceStreamSignale = false;
    return;
  }
  const depuisReference = maintenantMs - referenceSilenceStreamMs;
  if (!fautDeclarerStreamSilencieux(depuisActivite, depuisReference)) return;
  resultats.journaliserReouvertureStream(depuisActivite);
  resultats.reconnecterStream();
  referenceSilenceStreamMs = maintenantMs;
  if (!doitRechargerListePourSilence(episodeSilenceStreamSignale)) return;
  const projets = projetsSelectionnes();
  if (projets.length) {
    episodeSilenceStreamSignale = true;
    resultats.chargerListe(projets, { raison: 'flux_silencieux' });
  }
}

// ─── Rechargement sur création/début/fin de traitement d'une issue ──────────
// En BACKUP du flux /stream (qui a déjà, de son côté, traité l'événement de
// façon optimiste/ciblée — voir resultats.js::traiterNotif) : un VRAI
// rechargement réseau de la LISTE du projet concerné, jamais pendant la
// veille (rattrapé par le réveil). `rechargerListeProjetPourIssue` transmet
// au journal serveur la raison et, si l'issue est déjà connue localement, son
// `createdAt` (pour que le serveur calcule une ancienneté en cas
// d'avertissement — jamais un appel GitHub supplémentaire pour l'obtenir).
function rechargerListeProjetPourIssue(projet, numero, raison) {
  const connue = store.lireIssue(projet, numero);
  const opts = { raison, numero };
  if (connue && connue.createdAt) opts.creeLe = connue.createdAt;
  resultats.chargerListe([projet], opts);
}

// creation_issue (issue #917 point 3, rattrapage désormais à durée FIXE,
// issue #933) : rechargement ciblé IMMÉDIAT du projet concerné, puis un
// second après RATTRAPAGE_CREATION_SEC.
function surNotifCreation(notif) {
  if (!notif || notif.type !== 'creation_issue' || !notif.projet || enVeilleActif) return;
  const projet = notif.projet;
  resultats.chargerListe([projet], { raison: 'creation' });
  setTimeout(() => {
    if (!enVeilleActif) resultats.chargerListe([projet], { raison: 'rattrapage' });
  }, RATTRAPAGE_CREATION_SEC * 1000);
}

// debut_issue/fin_issue (issue #933 point 2) : rechargement ciblé de la
// liste du projet concerné. Pour fin_issue, regroupe les doublons rapprochés
// (watcher.py le poste deux fois de suite pour une même issue) — un seul
// rechargement par fenêtre, voir doitRechargerSurFin.
function surNotifDebutOuFin(notif) {
  if (!notif || !notif.projet || notif.numero == null || enVeilleActif) return;
  if (notif.type === 'debut_issue') {
    rechargerListeProjetPourIssue(notif.projet, notif.numero, 'debut');
  } else if (notif.type === 'fin_issue') {
    const cle = notif.projet + '#' + notif.numero;
    const maintenantMs = maintenant();
    if (!doitRechargerSurFin(dernierRechargementFin.get(cle), maintenantMs)) return;
    dernierRechargementFin.set(cle, maintenantMs);
    rechargerListeProjetPourIssue(notif.projet, notif.numero, 'fin');
  }
}

// ─── (Dé)sélection d'un projet dans le filtre Résultats ─────────────────────
// Appelée depuis app.js (basculerFiltreProjet/basculerTousLesFiltres, via le
// pont) : un projet qui vient d'être sélectionné n'est rechargé QU'À CE
// MOMENT (issue #917 point 3), jamais pendant qu'il était désélectionné.
// Débounce court : plusieurs pastilles cliquées très vite ne déclenchent
// qu'UN seul rechargement de l'ensemble final.
function surSelectionChangee() {
  if (enVeilleActif) return;
  clearTimeout(minuteurDebounceSelection);
  minuteurDebounceSelection = setTimeout(() => {
    resultats.rafraichirSelection(projetsSelectionnes());
    rafraichirPanneauInfra();
  }, DELAI_DEBOUNCE_SELECTION_MS);
}

// ─── Réglage (panneau Infrastructure, partie globale) ───────────────────────
function initZoneVeille() {
  const inputDelai = dom.$('#pl-veille-delai');
  const reglages = lireReglages();
  if (inputDelai) inputDelai.value = String(reglages.delaiVeilleMin);

  if (inputDelai) {
    inputDelai.addEventListener('change', () => {
      persistance.ecrire(persistance.CLES.veilleDelaiMin, normaliserDelaiVeilleMin(inputDelai.value));
      inputDelai.value = String(lireReglages().delaiVeilleMin);
    });
  }
}

// ─── Affichage « sync ancienne » (issue #917 point 6) ───────────────────────
// Appelée par l'ancien app.js (construireBoutonsFiltre, via le pont) à chaque
// (re)construction de la barre près du ↻, comme texteDerniereSync().
function syncEstAncienne() {
  return estSyncAncienne(resultats.dernierSyncMs(), maintenant());
}

// ─── Amorçage (appelé une fois par index.js) ─────────────────────────────────
export function initVeille() {
  derniereActiviteMs = maintenant();
  initZoneVeille();
  installerAbsorptionVoile();
  installerDetectionActivite();
  store.abonnerCle('derniereNotifIssue', (notif) => surNotifCreation(notif));
  store.abonnerCle('derniereNotifIssue', (notif) => surNotifDebutOuFin(notif));
  if (minuteurVerifInactivite) clearInterval(minuteurVerifInactivite);
  minuteurVerifInactivite = setInterval(verifierInactivite, INTERVALLE_VERIF_INACTIVITE_MS);
  demarrerSurveillanceStream();
}

// Objet publié sous window.Bridge.veille (via installerPont dans index.js) :
// surSelectionChangee/syncEstAncienne sont l'API consommée par l'ancien
// app.js pendant la transition (basculerFiltreProjet/basculerTousLesFiltres,
// construireBoutonsFiltre) — initVeille, elle, n'est jamais appelée via le
// pont (index.js l'appelle directement par import ES), exposée ici
// uniquement pour la testabilité, comme les autres modules par
// fonctionnalité (resultats.js, panneau_lateral.js).
export const veille = {
  initVeille,
  surSelectionChangee,
  syncEstAncienne,
};
