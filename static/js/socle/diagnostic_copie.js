// diagnostic_copie.js — journal de diagnostic DURABLE de la copie
// presse-papier de l'onglet Résultats (issue #878), DÉSACTIVÉ PAR DÉFAUT.
//
// POURQUOI CE MODULE EXISTE
//   Alain observe, de façon intermittente, des clics sur la case de copie
//   qui n'ont AUCUN EFFET (ni vidage, ni copie) — notamment juste après la
//   fin d'une issue (la ligne se redessine) ou après un long retour d'onglet
//   (flux /stream reconnecté). Aucune des deux situations n'est reproductible
//   dans l'environnement de l'agent (comportement réel du navigateur) : ce
//   journal collecte, SUR LA MACHINE D'ALAIN, les métadonnées nécessaires
//   pour corréler un futur clic sans effet avec un redessin ou une
//   reconnexion récente.
//
// ACTIVATION — PAS un réglage de navigateur
//   `DIAGNOSTIC_COPIE = oui` dans `identite_locale.conf` (racine du dépôt),
//   lu au démarrage du serveur (app/vues.py::index via identite.py) et
//   transmis à la page par `window.DIAGNOSTIC_COPIE`
//   (templates/fragments/scripts.html) — délibérément PAS une clé
//   localStorage : ce réglage doit survivre aux rechargements, aux
//   changements de navigateur et aux fermetures d'onglet. Désactivé par
//   défaut : diagnosticActif() ci-dessous est l'UNIQUE point de décision,
//   lu par CHAQUE fonction exportée — tant qu'il renvoie false, ce module
//   n'écrit RIEN (ni réseau, ni console, ni file d'attente localStorage).
//
// OÙ LIRE LE RÉSULTAT
//   `logs/diagnostic_copie.log` (gitignoré, rotation par taille — voir
//   app/diagnostic_copie.py), UNE ligne par clic sur une case de copie, et la
//   MÊME ligne dans la console du navigateur (F12). Champs d'une ligne :
//   date/heure, navigateur, temps écoulé depuis le dernier événement /stream,
//   état de la connexion /stream, présence de l'élément cliqué dans le
//   document, fraîcheur du redessin de sa ligne, numéro d'issue, et le
//   résultat de l'étape observée (déclenchement du `change`, ou résultat de
//   la copie elle-même — succès/vide/échec/non prêt).
//
// RÉSILIENCE RÉSEAU (c'est justement le cas à diagnostiquer)
//   Chaque ligne est D'ABORD mise en file locale (localStorage, bornée),
//   PUIS l'envoi est tenté (fetch keepalive, fire-and-forget — jamais
//   attendu par l'appelant, donc jamais un retard pour le clic ni pour
//   l'écriture presse-papier). Si le serveur est injoignable, la ligne reste
//   en file et sera réessayée au chargement suivant (rejouerFileEnAttente,
//   appelée par resultats_coches.js::initialiser).

import * as persistance from './persistance.js';

const CLE_FILE = 'diagnostic-copie:file-en-attente';
// Borne défensive : au-delà, les lignes les plus ANCIENNES non envoyées sont
// perdues plutôt que de laisser grossir localStorage indéfiniment si le
// serveur reste injoignable longtemps — un cas déjà anormal en soi.
export const BORNE_FILE = 50;
const URL_DIAGNOSTIC = '/diagnostic-copie';

// Unique point de décision — lu par TOUTES les fonctions ci-dessous. Posé
// par templates/fragments/scripts.html (avant le chargement de ce module).
export function diagnosticActif() {
  return typeof window !== 'undefined' && window.DIAGNOSTIC_COPIE === true;
}

// ─────────────────────────────────────────────────────────────────────────────
// LOGIQUE PURE (testée sous Node — static/js/tests/diagnostic_copie.test.js)
// ─────────────────────────────────────────────────────────────────────────────

// Construit la ligne de diagnostic à partir du contexte fourni par l'appelant
// — AUCUN accès DOM/réseau/horloge ici (tout est passé en argument) pour
// rester testable sous Node. `ctx` : { date, navigateur, projet, numero,
// depuisDernierEvenementSseMs, etatSse, elementDansDocument,
// ligneRedessineeRecemment, etape, resultat }.
export function construireLigneDiagnostic(ctx) {
  const c = ctx || {};
  const champs = [
    'date=' + (c.date || ''),
    'navigateur=' + (c.navigateur || ''),
    'projet=' + (c.projet || ''),
    'issue=' + (c.numero != null ? c.numero : ''),
    'depuisDernierEvenementSse=' + formaterDureeMs(c.depuisDernierEvenementSseMs),
    'etatSse=' + libelleEtatSse(c.etatSse),
    'elementDansDocument=' + formaterBooleen(c.elementDansDocument),
    'ligneRedessineeRecemment=' + formaterBooleen(c.ligneRedessineeRecemment),
    'etape=' + (c.etape || 'inconnue'),
    'resultat=' + (c.resultat || 'inconnu'),
  ];
  return champs.join(' · ');
}

function formaterDureeMs(ms) {
  return (typeof ms === 'number' && Number.isFinite(ms)) ? ms + 'ms' : 'inconnu';
}

function formaterBooleen(v) {
  return v === true ? 'oui' : v === false ? 'non' : 'inconnu';
}

// readyState d'EventSource (0/1/2) → libellé lisible dans le fichier de log.
export function libelleEtatSse(etat) {
  if (etat === 0) return 'connexion';
  if (etat === 1) return 'ouvert';
  if (etat === 2) return 'ferme';
  return 'inconnu';
}

// Vrai si l'horodatage de redessin `redessineeA` (ms epoch, dataset de la
// ligne) est assez récent pour être suspect — pure, testée sous Node.
export const SEUIL_REDESSIN_RECENT_MS = 5000;
export function ligneRedessineeRecemment(redessineeA, maintenant, seuilMs = SEUIL_REDESSIN_RECENT_MS) {
  return typeof redessineeA === 'number' && Number.isFinite(redessineeA)
    && (maintenant - redessineeA) < seuilMs;
}

// Tronque la file à la borne (garde les plus RÉCENTES) — pure, testée sous Node.
export function borneFile(liste, borne = BORNE_FILE) {
  return (liste || []).slice(-borne);
}

// ─────────────────────────────────────────────────────────────────────────────
// FILE D'ATTENTE LOCALE (localStorage, via persistance.js)
// ─────────────────────────────────────────────────────────────────────────────

function lireFile() {
  const liste = persistance.lire(CLE_FILE, []);
  return Array.isArray(liste) ? liste : [];
}

function ecrireFile(liste) {
  persistance.ecrire(CLE_FILE, borneFile(liste));
}

function enfiler(ligne) {
  const liste = lireFile();
  liste.push(ligne);
  ecrireFile(liste);
}

function retirer(ligne) {
  ecrireFile(lireFile().filter((l) => l !== ligne));
}

// fetch keepalive (pas sendBeacon) : sendBeacon ne renvoie qu'une acceptation
// SYNCHRONE par le navigateur (pas une confirmation serveur), insuffisante
// pour décider si la ligne doit rester en file — fetch donne un .then/.catch
// réel sur l'aboutissement réseau. keepalive:true pour survivre à une
// éventuelle navigation pendant l'envoi, comme sendBeacon.
function envoyer(ligne) {
  if (typeof fetch !== 'function') return;
  fetch(URL_DIAGNOSTIC, { method: 'POST', body: ligne, keepalive: true })
    .then(() => retirer(ligne))
    .catch(() => { /* serveur injoignable : la ligne reste en file, voir rejouerFileEnAttente */ });
}

// ─────────────────────────────────────────────────────────────────────────────
// POINTS D'ENTRÉE (appelés par resultats_coches.js)
// ─────────────────────────────────────────────────────────────────────────────

// Appelée à chaque clic sur une case de copie (succès, échec, ou absence de
// `change` détectée par le délai d'attente — voir resultats_coches.js). NE
// FAIT RIEN si DIAGNOSTIC_COPIE est désactivé : ni console, ni réseau, ni
// écriture localStorage.
export function diagnostiquer(ctx) {
  if (!diagnosticActif()) return;
  const ligne = construireLigneDiagnostic(ctx);
  console.log('[diagnostic-copie] ' + ligne);
  enfiler(ligne);
  envoyer(ligne);
}

// Appelée une fois au chargement de la page (resultats_coches.js::initialiser)
// : réessaie les lignes restées en file depuis une session précédente où le
// serveur était injoignable au moment du clic — justement le cas à
// diagnostiquer (voir l'en-tête de ce module), ne JAMAIS les perdre en
// silence.
export function rejouerFileEnAttente() {
  if (!diagnosticActif()) return;
  for (const ligne of lireFile()) envoyer(ligne);
}
