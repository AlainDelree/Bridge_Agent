// veille.js — voile de veille/réveil, rafraîchissement périodique du projet
// sélectionné et réglages associés (issue #917).
//
// POURQUOI CE MODULE EXISTE
//   Avant cette issue, aucun rechargement périodique de la liste Résultats
//   n'avait jamais existé (voir l'étude #916) : la liste n'était alimentée
//   que par les événements /stream et des rattrapages ponctuels (retour de
//   masquage de l'onglet, reconnexion SSE, ↻ explicite). Décision d'Alain :
//   ne pas dépendre du flux /stream seul, ne pas prolonger indéfiniment des
//   délais de cache, mais rendre l'état de l'interface visible et la remettre
//   à jour au premier geste, avec des réglages qu'il ajuste lui-même.
//
// CE QUE CE MODULE FAIT
//   - Détecte l'inactivité (mouvement de souris, clic, clavier, défilement ;
//     fenêtre au premier plan ou non — voir l'en-tête de installerDetectionActivite
//     pour ce qui n'a PAS pu être vérifié sans navigateur réel) et affiche un
//     voile gris semi-opaque (#voile-veille, templates/fragments/voile_veille.html)
//     après `delaiVeilleMin` minutes sans activité (0 désactive la veille).
//   - Pendant la veille : AUCUN appel réseau périodique (le rafraîchissement
//     ci-dessous s'arrête) ; les petites requêtes locales existantes
//     (battement, watchers, panneau Infrastructure à 30s, badge inbox…) ne
//     sont PAS touchées par ce module.
//   - Le premier clic ou la première touche est ABSORBÉ par le voile (aucune
//     action sur ce qui se trouve dessous) : il lance le rechargement CIBLÉ
//     du/des projet(s) actuellement sélectionné(s) dans le filtre Résultats
//     (liste + timing, resultats.rafraichirSelection) et du panneau
//     Infrastructure, puis le préchargement des rapports visibles — jamais
//     une rafale sur tous les projets configurés. Délai maximum
//     (DELAI_MAX_REVEIL_MS) : au-delà, état d'erreur explicite avec bouton
//     Réessayer — jamais de disparition silencieuse du voile sans données.
//   - Hors veille : rafraîchissement périodique CIBLÉ (même périmètre que
//     ci-dessus) à `intervalleSec`, qui se reprogramme lui-même après chaque
//     tentative — succès → délai normal, échec → attente croissante plafonnée
//     (prochainDelaiMs), jamais d'arrêt définitif.
//   - À la création d'une issue (événement SSE `creation_issue`, dépôt de
//     fichier ou formulaire — tous deux finissent par le même événement, voir
//     app/fin_issue.py) : rechargement ciblé immédiat du PROJET CONCERNÉ par
//     l'événement, puis un second après `rattrapageSec` — en BACKUP du flux
//     /stream, qui a pu ne pas livrer ou pas être appliqué (cas réel observé
//     le 22/11/2026, étude #916 : 22 minutes sans requête ciblée après un
//     debut_issue). Rien pendant la veille (rattrapé par le réveil).
//   - À la (dé)sélection d'un projet dans le filtre Résultats (pastilles) :
//     surSelectionChangee(), appelée depuis app.js (basculerFiltreProjet/
//     basculerTousLesFiltres via le pont) — un projet qui vient d'être
//     sélectionné n'est rechargé QU'À CE MOMENT, pas avant (point 3 de
//     l'issue : « jamais les projets désélectionnés, qui ne sont rechargés
//     qu'à leur sélection ou sur action explicite »).
//   - Réglages modifiables par Alain (délai de veille, intervalle de
//     rafraîchissement, délai de rattrapage) : stockés via
//     window.Bridge.persistance (seul point d'accès autorisé au
//     localStorage), une seule valeur par réglage pour toute l'interface
//     (jamais par projet), effet immédiat sans rechargement de page — voir
//     initZoneVeille(). Affichés dans le panneau Infrastructure, partie
//     globale, près de l'interrupteur de son (templates/fragments/
//     panneau_lateral.html, #pl-zone-veille).
//
// CE QUE CE MODULE NE FAIT PAS
//   - Il ne gère ni le bandeau rouge « connexion perdue » (issue #917 point
//     8, dérivé de sourceEvents.onerror/onopen — static/js/app.js, hors
//     socle) ni la fenêtre de repli de la copie du rapport (issue #917 point
//     7 — static/js/resultats_coches.js).
//   - Il ne touche jamais au décompte TOUS projets (chargerTimingTous) ni au
//     ↻ explicite (rafraichirResultats, app.js) : ces chemins existants
//     restent inchangés, seul ce module utilise resultats.rafraichirSelection
//     (périmètre strictement restreint à la sélection courante).

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
export const DEFAUT_INTERVALLE_RAFRAICHISSEMENT_SEC = 60;
export const MIN_INTERVALLE_RAFRAICHISSEMENT_SEC = 15;
export const DEFAUT_DELAI_RATTRAPAGE_SEC = 10;

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

// Minimum 15s pour protéger le quota GitHub (issue #917 point 5) — toute
// valeur en dessous (y compris 0 ou négative) est remontée au minimum,
// jamais rejetée en silence vers le défaut (Alain a explicitement demandé un
// PLANCHER, pas un simple défaut de repli).
export function normaliserIntervalleRafraichissementSec(valeur) {
  const n = Number(valeur);
  if (!Number.isFinite(n) || n <= 0) return DEFAUT_INTERVALLE_RAFRAICHISSEMENT_SEC;
  return Math.max(MIN_INTERVALLE_RAFRAICHISSEMENT_SEC, Math.round(n));
}

export function normaliserDelaiRattrapageSec(valeur) {
  const n = Number(valeur);
  if (!Number.isFinite(n) || n <= 0) return DEFAUT_DELAI_RATTRAPAGE_SEC;
  return Math.max(1, Math.round(n));
}

// true si l'interface doit entrer en veille — delaiVeilleMin <= 0 désactive
// la veille (jamais vrai). `derniereActiviteMs` null (aucune activité jamais
// enregistrée, ex. tests) → jamais de veille par défaut d'horloge manquante.
export function doitEntrerEnVeille(derniereActiviteMs, maintenantMs, delaiVeilleMin) {
  if (!delaiVeilleMin || delaiVeilleMin <= 0) return false;
  if (derniereActiviteMs == null) return false;
  return (maintenantMs - derniereActiviteMs) >= delaiVeilleMin * 60000;
}

// Attente croissante plafonnée (issue #917 point 3) : après N échecs
// consécutifs du rafraîchissement périodique, le délai double à chaque fois
// (plafonné à 10 échecs pour éviter tout dépassement numérique), jusqu'à
// `plafondMs` — jamais d'arrêt définitif, toujours une prochaine tentative.
export const PLAFOND_ATTENTE_ECHEC_MS = 10 * 60 * 1000;   // 10 min
export function prochainDelaiMs(nbEchecsConsecutifs, intervalleBaseMs, plafondMs = PLAFOND_ATTENTE_ECHEC_MS) {
  if (!nbEchecsConsecutifs || nbEchecsConsecutifs <= 0) return intervalleBaseMs;
  const delai = intervalleBaseMs * Math.pow(2, Math.min(nbEchecsConsecutifs, 10));
  return Math.min(plafondMs, delai);
}

// Ordre de grandeur du coût en appels GitHub par heure (issue #917 point 5),
// affiché à titre indicatif près du réglage d'intervalle. Un cycle de
// rafraichirSelection() fait DEUX appels `gh` par projet sélectionné
// (/issues-liste + /issues-en-attente, voir app/issues.py) — les cases
// cochées et le panneau Infrastructure sont purement locaux, hors compte.
export const APPELS_GH_PAR_CYCLE = 2;
export function calculerCoutGithubParHeure(intervalleSec, nbProjetsSelectionnes = 1, appelsParCycle = APPELS_GH_PAR_CYCLE) {
  if (!intervalleSec || intervalleSec <= 0) return 0;
  const nb = Math.max(0, nbProjetsSelectionnes || 0);
  return Math.round(appelsParCycle * nb * 3600 / intervalleSec);
}

// true si l'affichage « sync HH:MM:SS » doit être coloré comme ancien (issue
// #917 point 6) : jamais synchronisé, ou plus ancien que trois fois
// l'intervalle réglé. `facteur` exposé pour la testabilité, défaut 3 (valeur
// demandée par l'issue).
export function estSyncAncienne(dernierSyncMs, maintenantMs, intervalleSec, facteur = 3) {
  if (dernierSyncMs == null) return true;
  return (maintenantMs - dernierSyncMs) >= intervalleSec * 1000 * facteur;
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

let derniereActiviteMs = null;
let enVeilleActif = false;          // true dès l'entrée en veille, jusqu'au réveil RÉUSSI
let etatVoile = 'eveille';          // 'eveille' | 'veille' | 'reveil' | 'erreur'
let generationReveil = 0;           // un réveil supplanté (nouvelle entrée en veille) devient silencieux
let minuteurVerifInactivite = null;
let minuteurPeriodique = null;
let nbEchecsConsecutifs = 0;
let minuteurDebounceSelection = null;

function maintenant() { return Date.now(); }

function lireReglages() {
  return {
    delaiVeilleMin: normaliserDelaiVeilleMin(
      persistance.lire(persistance.CLES.veilleDelaiMin, DEFAUT_DELAI_VEILLE_MIN)),
    intervalleSec: normaliserIntervalleRafraichissementSec(
      persistance.lire(persistance.CLES.veilleIntervalleSec, DEFAUT_INTERVALLE_RAFRAICHISSEMENT_SEC)),
    rattrapageSec: normaliserDelaiRattrapageSec(
      persistance.lire(persistance.CLES.veilleRattrapageSec, DEFAUT_DELAI_RATTRAPAGE_SEC)),
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
  arreterRafraichissementPeriodique();
  afficherVoile();
}

function sortirDeVeille() {
  enVeilleActif = false;
  etatVoile = 'eveille';
  derniereActiviteMs = maintenant();
  masquerVoile();
  demarrerRafraichissementPeriodique();
}

// Séquence réelle du réveil : rechargement ciblé liste+timing + panneau
// Infrastructure + préchargement des rapports visibles (file plafonnée
// existante, issue #835) — jamais une rafale sur tous les projets.
async function executerReveil(projets) {
  const resultat = await resultats.rafraichirSelection(projets);
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

// ─── Rafraîchissement périodique (hors veille) ───────────────────────────────
function arreterRafraichissementPeriodique() {
  if (minuteurPeriodique) { clearTimeout(minuteurPeriodique); minuteurPeriodique = null; }
}

function programmerProchainRafraichissement(delaiMs) {
  arreterRafraichissementPeriodique();
  minuteurPeriodique = setTimeout(executerRafraichissementPeriodique, delaiMs);
}

async function executerRafraichissementPeriodique() {
  if (enVeilleActif) return;   // garde-fou : le minuteur est arrêté à l'entrée en veille
  const projets = projetsSelectionnes();
  const reglages = lireReglages();
  if (!projets.length) {
    programmerProchainRafraichissement(reglages.intervalleSec * 1000);
    return;
  }
  let resultat;
  try {
    resultat = await resultats.rafraichirSelection(projets);
  } catch (e) {
    resultat = { succes: false };
  }
  rafraichirPanneauInfra();
  if (enVeilleActif) return;   // entré en veille PENDANT ce rafraîchissement
  if (resultat && resultat.succes) {
    nbEchecsConsecutifs = 0;
    programmerProchainRafraichissement(lireReglages().intervalleSec * 1000);
  } else {
    nbEchecsConsecutifs += 1;
    programmerProchainRafraichissement(prochainDelaiMs(nbEchecsConsecutifs, lireReglages().intervalleSec * 1000));
  }
}

function demarrerRafraichissementPeriodique() {
  nbEchecsConsecutifs = 0;
  programmerProchainRafraichissement(lireReglages().intervalleSec * 1000);
}

// ─── Rattrapage à la création d'une issue (issue #917 point 3) ──────────────
// En BACKUP du flux /stream (qui a déjà, de son côté, affiché la ligne
// optimiste depuis les données de l'événement — voir surCreationIssue,
// resultats.js) : un VRAI rechargement réseau du projet concerné, immédiat
// puis après le délai de rattrapage réglé — jamais pendant la veille (rien à
// afficher tant que l'interface n'est pas réveillée).
function surNotifCreation(notif) {
  if (!notif || notif.type !== 'creation_issue' || !notif.projet || enVeilleActif) return;
  const projet = notif.projet;
  resultats.rafraichirSelection([projet]);
  const rattrapageMs = lireReglages().rattrapageSec * 1000;
  setTimeout(() => {
    if (!enVeilleActif) resultats.rafraichirSelection([projet]);
  }, rattrapageMs);
}

// ─── (Dé)sélection d'un projet dans le filtre Résultats ─────────────────────
// Appelée depuis app.js (basculerFiltreProjet/basculerTousLesFiltres, via le
// pont) : un projet qui vient d'être sélectionné n'est rechargé QU'À CE
// MOMENT (issue #917 point 3), jamais pendant qu'il était désélectionné.
// Débounce court : plusieurs pastilles cliquées très vite ne déclenchent
// qu'UN seul rechargement de l'ensemble final.
function surSelectionChangee() {
  majAfficheCoutGithub();
  if (enVeilleActif) return;
  clearTimeout(minuteurDebounceSelection);
  minuteurDebounceSelection = setTimeout(() => {
    resultats.rafraichirSelection(projetsSelectionnes());
    rafraichirPanneauInfra();
  }, DELAI_DEBOUNCE_SELECTION_MS);
}

// ─── Réglages (panneau Infrastructure, partie globale) ──────────────────────
function majAfficheCoutGithub() {
  const zone = dom.$('#pl-veille-cout');
  if (!zone) return;
  const nbProjets = Math.max(1, projetsSelectionnes().length);
  const cout = calculerCoutGithubParHeure(lireReglages().intervalleSec, nbProjets);
  zone.textContent = '≈ ' + cout + ' appel(s) GitHub/h pour ' + nbProjets
    + ' projet(s) actuellement sélectionné(s) dans le filtre Résultats.';
}

function initZoneVeille() {
  const inputDelai = dom.$('#pl-veille-delai');
  const inputIntervalle = dom.$('#pl-veille-intervalle');
  const inputRattrapage = dom.$('#pl-veille-rattrapage');
  const reglages = lireReglages();
  if (inputDelai) inputDelai.value = String(reglages.delaiVeilleMin);
  if (inputIntervalle) inputIntervalle.value = String(reglages.intervalleSec);
  if (inputRattrapage) inputRattrapage.value = String(reglages.rattrapageSec);
  majAfficheCoutGithub();

  if (inputDelai) {
    inputDelai.addEventListener('change', () => {
      persistance.ecrire(persistance.CLES.veilleDelaiMin, normaliserDelaiVeilleMin(inputDelai.value));
      inputDelai.value = String(lireReglages().delaiVeilleMin);
    });
  }
  if (inputIntervalle) {
    inputIntervalle.addEventListener('change', () => {
      persistance.ecrire(persistance.CLES.veilleIntervalleSec,
        normaliserIntervalleRafraichissementSec(inputIntervalle.value));
      inputIntervalle.value = String(lireReglages().intervalleSec);
      majAfficheCoutGithub();
      // Effet immédiat (issue #917 point 5), sans attendre le prochain tick
      // déjà programmé avec l'ancien intervalle.
      if (!enVeilleActif) programmerProchainRafraichissement(lireReglages().intervalleSec * 1000);
    });
  }
  if (inputRattrapage) {
    inputRattrapage.addEventListener('change', () => {
      persistance.ecrire(persistance.CLES.veilleRattrapageSec,
        normaliserDelaiRattrapageSec(inputRattrapage.value));
      inputRattrapage.value = String(lireReglages().rattrapageSec);
    });
  }
}

// ─── Affichage « sync ancienne » (issue #917 point 6) ───────────────────────
// Appelée par l'ancien app.js (construireBoutonsFiltre, via le pont) à chaque
// (re)construction de la barre près du ↻, comme texteDerniereSync().
function syncEstAncienne() {
  return estSyncAncienne(resultats.dernierSyncMs(), maintenant(), lireReglages().intervalleSec);
}

// ─── Amorçage (appelé une fois par index.js) ─────────────────────────────────
export function initVeille() {
  derniereActiviteMs = maintenant();
  initZoneVeille();
  installerAbsorptionVoile();
  installerDetectionActivite();
  store.abonnerCle('derniereNotifIssue', (notif) => surNotifCreation(notif));
  if (minuteurVerifInactivite) clearInterval(minuteurVerifInactivite);
  minuteurVerifInactivite = setInterval(verifierInactivite, INTERVALLE_VERIF_INACTIVITE_MS);
  demarrerRafraichissementPeriodique();
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
