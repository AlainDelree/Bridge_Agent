// panneau_lateral.js — panneau latéral « Infrastructure » de l'onglet Résultats
// (issue #628, refonte web étape 4 — sorti d'app.js selon ARCHITECTURE.md §6.7).
//
// RESPONSABILITÉ
//   Colonne latérale (non recouvrante, voir static/css/resultats.css) affichée
//   à côté de la liste de l'onglet Résultats : monitoring passif des watchers
//   CCL + services CCW connus, interrupteur GLOBAL du bip, contrôle du watcher
//   spool (issues_inbox), et — pour l'issue actuellement sélectionnée — le
//   seul toggle 🔔 Notifications (plus aucune action de fermeture/relance par
//   issue depuis l'issue #950, voir ci-dessous). Ouvert par défaut, état
//   mémorisé (persistance.js) et conservé d'un onglet à l'autre —
//   contrairement à l'ancien comportement (réinitialisé à chaque entrée dans
//   l'onglet Résultats).
//
// DÉPLACÉ SUR LA LIGNE, PLUS AUCUNE ACTION PAR ISSUE ICI (issue #641, refonte
// web étape 6 ; complété par l'issue #950, décision d'Alain : TOUTES les
// actions par issue vivent sur la ligne, jamais dans un panneau — un bouton
// de panneau peut viser une autre issue que celle crue sélectionnée après une
// sélection qui « saute », #943) : Interrompre l'issue, Retirer needs-human,
// Fermer définitivement (fermerIssue, bouton `pl-fermer-issue` retiré par
// #950) et le contrôle de son PROPRE à l'issue (#637, étape 7b) ne sont PLUS
// ici — voir static/js/actions_ligne.js, groupe de boutons directement sur la
// ligne de la liste. « Interrompre et relancer (watcher CCL) » (C2 de l'étude
// #938) reste ICI, niveau PROJET assumé (il arrête tout le watcher, pas
// seulement l'issue sélectionnée) — sa confirmation (interrompreIssue,
// static/js/app.js) liste désormais les autres issues en cours du projet.
//
// CE QUI N'EST PAS ICI (reste dans static/js/app.js, autres étapes de la
// refonte) : la liste des issues et le détail d'une issue (listeIssuesResultats,
// projetCourant/numeroCourant, construireHtmlIssue), les projets
// (nomsProjetsDisponibles), les actions réseau sur une issue (interrompreIssue,
// relancerIssue, fermerIssue, interrompreEtRelancer). Ce module les appelle via
// le pont (appelerAncien) — voir socle/pont.js — sans y référer en dur, et
// expose en retour les points d'entrée qu'app.js appelle encore
// (rafraichirPanneauLateralResultats, majBoutonTesterSonActif,
// sidebarRelancerWatcherCCL) comme globales `window.*`. démarrerPanneauLateral/
// arreterPanneauLateral, eux, ne sont plus exposés : depuis #632, ce module
// s'abonne lui-même à store.ongletActif (voir initPanneauLateral) — personne
// d'autre n'a jamais besoin de les appeler par leur nom.
//
// ONGLET CCW (issue #649, refonte web) : sorti dans static/js/ccw.js —
// obtenirCcwProjetsConnus/ccwChargerProjets/ccwRedemarrerProjet/
// ccwNettoyerVerrous sont désormais importés DIRECTEMENT (module ES → module
// ES), plus via le pont — voir l'en-tête de ccw.js pour le sens inverse
// (ccw.js → ce module, resté sur le pont pour éviter un cycle d'imports).
//
// MUTUALISATION /watchers (issue #628) : rafraichirWatchersPartages() est
// l'UNIQUE source de lecture de /watchers, écrite dans store.watchers — le
// bandeau de repli REP_TRAVAIL (static/js/app.js) s'y abonne désormais au lieu
// de fetcher lui-même (voir rafraichirReplisRepTravail dans app.js).

import { store } from './socle/store.js';
import { api } from './socle/api.js';
import { toasts } from './socle/toasts.js';
import { signalerEchecPossible } from './socle/panne_github.js';
import * as dom from './socle/dom.js';
import * as persistance from './socle/persistance.js';
import { appelerAncien } from './socle/pont.js';
// Import direct (issue #649, plutôt que par le pont — les deux sont des
// modules ES) : voir l'en-tête de ccw.js pour le sens inverse (pont conservé).
import { obtenirCcwProjetsConnus, ccwChargerProjets, ccwRedemarrerProjet, ccwNettoyerVerrous } from './ccw.js';

const CLE_PANNEAU_OUVERT = 'bridge_panneau_lateral_ouvert';

let intervalPanneauLateral = null;

// ─────────────────────────────────────────────────────────────────────────────
// LOGIQUE PURE (testée sous Node — voir static/js/tests/panneau_lateral.test.js)
//    Aucune dépendance au DOM ni au réseau.
// ─────────────────────────────────────────────────────────────────────────────

// Faut-il afficher le bouton « ⏹ Arrêter » sur la ligne d'un watcher CCL du
// panneau latéral (issue #655) : seulement s'il est actif — même patron que
// afficherBoutonDemarrer/afficherBoutonArreter pour les services CCW
// (static/js/ccw.js), mais un seul bouton ici (pas de « Démarrer » séparé,
// « ▶ Lancer »/« ↺ Relancer » restent un bouton unique déjà en place).
export function afficherBoutonArreterWatcherCcl(actif) { return !!actif; }

// Sélection des watchers CCL à traiter par « ↺ Relancer les allumés » (issue
// #753) : seulement les watchers ACTUELLEMENT ACTIFS (jamais un éteint, à la
// différence de « ↺ Relancer tous les CCL » qui allume aussi les éteints) et
// SANS issue en cours (un redémarrage l'interromprait) — même patron que
// planifierPoseTokenTous (static/js/ccw.js, issue #743) : décide par projet,
// jamais d'arrêt de force. Un éteint n'apparaît dans aucune des deux listes
// (hors périmètre de ce bouton, pas un « ignoré » à signaler).
//   - resumeParProjet : { <projet>: {enCours, enFile} | null | undefined } —
//     même forme que appelerAncien('resumeProjetMonitoring', projet), DÉJÀ
//     calculée en mémoire par le monitoring (aucun fetch réseau
//     supplémentaire ici).
export function selectionnerWatchersActifsARelancer(noms, watchersMap, resumeParProjet) {
  const relances = [];
  const ignores = [];
  (noms || []).forEach(function(nom) {
    const actif = !!(watchersMap && watchersMap[nom] && watchersMap[nom].actif);
    if (!actif) return;
    const resume = (resumeParProjet && resumeParProjet[nom]) || { enCours: 0 };
    if (resume.enCours > 0) ignores.push(nom); else relances.push(nom);
  });
  return { relances, ignores };
}

// Résumé court affiché après « ↺ Relancer les allumés » — texte + type de
// toast à utiliser (issue #753) : simple succès (toast non comptabilisé,
// option de l'issue #747 — l'utilisateur vient de cliquer, il le voit déjà)
// tant qu'aucun projet n'a été ignoré ; dès qu'un projet occupé l'a été,
// avertissement (toujours comptabilisé, voir estComptabilise dans toasts.js)
// avec les noms des projets occupés.
export function resumerRelanceActifs(relances, ignores) {
  const n = (relances || []).length;
  const m = (ignores || []).length;
  let texte = n + ' relancé(s), ' + m + ' ignoré(s)';
  if (m > 0) texte += ' (' + ignores.join(', ') + ')';
  return { texte: texte, type: m > 0 ? 'avertissement' : 'succes' };
}

// Relance chaque projet de `projets` l'un après l'autre via `lancerUnProjet`
// (même patron que la boucle déjà en place dans sidebarRelancerTousEteints/
// sidebarRelancerTousCCL, extrait ici pour rester testable sous Node) : la
// relance en échec d'un projet n'empêche jamais les suivants d'être tentés.
export async function relancerSequentiellement(projets, lancerUnProjet) {
  for (const nom of (projets || [])) {
    try {
      await lancerUnProjet(nom);
    } catch (e) { /* une relance en échec ne doit pas bloquer les suivantes */ }
  }
}

// État des 3 cases « 🔔 Notifications » du panneau, dérivé des labels réels de
// l'issue sélectionnée (correctif anomalie #4, issue #633) : une case cochée
// reflète directement — et SEULEMENT — la présence du label GitHub
// correspondant, quel que soit le chemin par lequel l'issue est arrivée dans
// le store (chargement initial, ↻, creation_issue, debut_issue, fin_issue —
// voir le correctif de chargerTimingProjet dans resultats.js, qui garantit que
// ces labels restent à jour). `nomsLabels` : labels déjà normalisés en
// minuscules (voir rendrePanneauLateralActions).
export function etatsCasesNotif(nomsLabels) {
  const labels = nomsLabels || [];
  return {
    notif_pc: labels.includes('notif_pc'),
    notif_gsm: labels.includes('notif_gsm'),
    notif_tous: labels.includes('notif_tous'),
  };
}

// ─── Alerte « en file, watcher éteint » (issue #945) ───────────────────────
// Un projet a au moins une issue « en file » (ouverte, ni needs-human ni
// done — resumeProjetMonitoring côté app.js) alors que son watcher CCL est
// éteint : personne ne la traitera jusqu'à une relance manuelle. Même patron
// que le silence de flux /stream (veille.js #937) : un point de départ de
// grâce par projet, réarmé dès que la condition cesse d'être réunie
// (evaluerAlertesWatchers ci-dessous, orchestration), et un épisode déjà
// signalé pour n'émettre qu'UNE notification par épisode.
//
// Délai de grâce ~60 s (issue #945) : un watcher relancé automatiquement au
// dépôt d'une issue (redemarrer_si_eteint, app/watchers.py) met un instant à
// publier son fichier PID — sans ce délai, la fenêtre entre le dépôt et ce
// court lancement afficherait une fausse alerte à chaque création d'issue.
export const DELAI_GRACE_ALERTE_WATCHER_MS = 60000;

// Condition brute (issue #945), sans tenir compte du délai de grâce ni de
// l'épisode déjà signalé — ceux-ci restent du ressort de
// fautAlerterWatcherEteint/doitNotifierAlerteWatcher ci-dessous.
export function enAttenteWatcherEteint(enFile, watcherActif) {
  return (enFile || 0) > 0 && !watcherActif;
}

// `depuisMs` : ancienneté (ms) du dernier instant où enAttenteWatcherEteint
// est devenue vraie EN CONTINU pour ce projet — null si la condition n'est
// pas réunie à cet instant. True seulement une fois le délai de grâce dépassé.
export function fautAlerterWatcherEteint(depuisMs, seuilMs = DELAI_GRACE_ALERTE_WATCHER_MS) {
  return depuisMs != null && depuisMs >= seuilMs;
}

// Un seul déclenchement (toast) par épisode d'alerte (issue #945) — même
// principe que doitRechargerListePourSilence (veille.js #937) : vrai
// seulement à la transition qui fait passer l'alerte d'inactive à active.
export function doitNotifierAlerteWatcher(alerteActive, episodeDejaSignale) {
  return alerteActive && !episodeDejaSignale;
}

// Texte affiché sur le badge projet et la ligne du panneau Infrastructure
// (issue #945) — identique aux deux endroits.
export function texteAlerteWatcher(enFile) {
  return `${enFile} en file, watcher éteint`;
}

// ─── Bouton « Avancement » (issue #887) : commits + fichiers (committés/non
// committés) du worktree dédié à l'issue sélectionnée, lecture seule (GET
// /avancement/<projet>/<numero>) — pour estimer l'avancement d'une tâche en
// cours sans ouvrir de terminal. Rendu entièrement ici (pas via le pont) :
// fonctionnalité neuve, aucun code hérité d'app.js à réutiliser. ────────────

// Horodatage epoch (secondes) → heure lisible française, '—' si absent/
// invalide (pur, testé sous Node).
export function formaterHorodatageAvancement(epochSecondes) {
  if (!epochSecondes) return '—';
  const d = new Date(epochSecondes * 1000);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'medium' });
}

// Une ligne de fichier +N/-M — compteurs manquants (fichier binaire, issue
// #788) affichés '?' plutôt qu'un faux 0 ; chemin renommé affiché
// « ancien → nouveau ».
export function ligneFichierAvancement(f) {
  const ajoutees = (f.ajoutees === null || f.ajoutees === undefined) ? '?' : f.ajoutees;
  const supprimees = (f.supprimees === null || f.supprimees === undefined) ? '?' : f.supprimees;
  const chemin = f.ancien_chemin ? (f.ancien_chemin + ' → ' + f.chemin) : f.chemin;
  return dom.echapperHtml(chemin) + ' <span class="av-plus">+' + ajoutees + '</span>/'
       + '<span class="av-moins">-' + supprimees + '</span> (' + dom.echapperHtml(f.statut || '') + ')';
}

// Corps complet de la modale à partir de la réponse JSON de /avancement
// (pur — aucun accès réseau ici, juste le rendu). Deux formes de réponse :
//   - { disponible:false, message } : cas dégradé (lecture seule/active,
//     for-windows/CCW, worktree introuvable) — message serveur affiché tel
//     quel, jamais un échec brut.
//   - { disponible:true, ... } : détail complet (worktree, dernière
//     activité, commits, fichiers committés/non committés).
export function rendreCorpsAvancement(resultat) {
  if (!resultat) {
    return '<div class="av-ligne-vide">Réponse vide du serveur.</div>';
  }
  if (!resultat.disponible) {
    return '<div class="message">' + dom.echapperHtml(resultat.message || resultat.erreur
      || 'Aucun avancement à montrer.') + '</div>';
  }
  const commits = resultat.commits || [];
  const committes = resultat.fichiers_committes || [];
  const nonCommittes = resultat.fichiers_non_committes || [];

  let html = '<div class="av-section-titre">Worktree</div>'
           + '<div class="av-ligne">' + dom.echapperHtml(resultat.chemin || '?') + ' (branche '
           + dom.echapperHtml(resultat.branche || '?') + ')</div>'
           + '<div class="av-ligne">Dernière activité : '
           + formaterHorodatageAvancement(resultat.derniere_activite) + '</div>';

  html += '<div class="av-section-titre">Commits depuis '
        + dom.echapperHtml(resultat.branche_base || 'la base') + ' (' + commits.length + ')</div>';
  html += commits.length
    ? commits.map((c) => '<div class="av-ligne">' + dom.echapperHtml(c.hash) + ' — '
        + dom.echapperHtml(c.message) + ' <span style="color:#888">('
        + formaterHorodatageAvancement(c.horodatage) + ')</span></div>').join('')
    : '<div class="av-ligne-vide">Aucun commit depuis la base.</div>';

  html += '<div class="av-section-titre">Fichiers committés (' + committes.length + ')</div>';
  html += committes.length
    ? committes.map((f) => '<div class="av-ligne">' + ligneFichierAvancement(f) + '</div>').join('')
    : '<div class="av-ligne-vide">Aucun.</div>';

  html += '<div class="av-section-titre">Fichiers non committés (' + nonCommittes.length + ')</div>';
  html += nonCommittes.length
    ? nonCommittes.map((f) => '<div class="av-ligne">' + ligneFichierAvancement(f) + '</div>').join('')
    : '<div class="av-ligne-vide">Working tree propre.</div>';

  return html;
}

// Ouvre la modale, affiche un état « Chargement… » puis le résultat de GET
// /avancement/<nom>/<numero> — à la demande seulement (clic), jamais de
// sondage permanent (Alain préfère explicitement les mises à jour à la
// demande, cf. issue #887). `silencieux:true` : une réponse dégradée
// (disponible:false) est un succès HTTP 200, pas une erreur à signaler par
// toast ; seule une vraie panne réseau/serveur l'est (catch ci-dessous).
async function ouvrirAvancement(nom, numero, labelsCsv) {
  const overlay = dom.$('#modal-avancement');
  const titre   = dom.$('#modal-avancement-titre');
  const corps   = dom.$('#modal-avancement-corps');
  if (!overlay || !titre || !corps) return;
  titre.textContent = '📊 Avancement — ' + nom + ' #' + numero;
  corps.innerHTML = '<div class="av-ligne-vide">Chargement…</div>';
  overlay.classList.add('actif');
  try {
    const url = '/avancement/' + encodeURIComponent(nom) + '/' + encodeURIComponent(numero)
              + '?labels=' + encodeURIComponent(labelsCsv || '');
    const resultat = await api.get(url, { silencieux: true });
    corps.innerHTML = rendreCorpsAvancement(resultat);
  } catch (e) {
    corps.innerHTML = '<div class="message avertissement">Erreur : ' + dom.echapperHtml(e.message) + '</div>';
  }
}

function fermerAvancement() {
  const overlay = dom.$('#modal-avancement');
  if (overlay) overlay.classList.remove('actif');
}

// ─── État ouvert/fermé (persisté, ouvert par défaut) ───────────────────────
function panneauEstOuvert() {
  return persistance.lire(CLE_PANNEAU_OUVERT, true);
}

function appliquerEtatPanneau(ouvert) {
  const panneau = dom.$('#panneau-lateral-resultats');
  const toggle  = dom.$('#pl-toggle');
  if (!panneau || !toggle) return;
  panneau.classList.toggle('ferme', !ouvert);
  toggle.classList.toggle('actif', ouvert);
}

function basculerPanneauLateral() {
  const ouvert = !panneauEstOuvert();
  persistance.ecrire(CLE_PANNEAU_OUVERT, ouvert);
  appliquerEtatPanneau(ouvert);
}

// ─── Cycle de vie (piloté par store.ongletActif, voir initPanneauLateral) ──
function demarrerPanneauLateral() {
  appliquerEtatPanneau(panneauEstOuvert());
  rafraichirPanneauLateralResultats();
  initZoneSon();
  arreterPanneauLateral();
  intervalPanneauLateral = setInterval(rafraichirPanneauLateralResultats, 30000);
}

function arreterPanneauLateral() {
  if (intervalPanneauLateral) { clearInterval(intervalPanneauLateral); intervalPanneauLateral = null; }
}

async function rafraichirPanneauLateralResultats() {
  const panneau = dom.$('#panneau-resultats');
  if (!panneau || !panneau.classList.contains('actif')) return;
  // Les trois zones sont indépendantes : le monitoring se rafraîchit toujours,
  // les actions contextuelles se (re)rendent — ou se vident — selon la
  // sélection courante, sans attendre le fetch du monitoring.
  await rendrePanneauLateralMonitoring();
  await rendrePanneauLateralExtras();
  rendrePanneauLateralActions();
}

// ─── Lecture mutualisée de /watchers (panneau + bandeau repli REP_TRAVAIL) ──
// Unique fetch, écrit dans store.watchers ({ nomProjet: {pid, actif, …} }).
// Tourne en continu dès le chargement de la page (comme le faisait déjà le
// bandeau de repli avant #628), en plus d'être rappelée à chaque rendu du
// monitoring pour rester fraîche sans attendre jusqu'à 30s à l'entrée de
// l'onglet.
async function rafraichirWatchersPartages() {
  try {
    const liste = await api.get('/watchers', { silencieux: true });
    const dict = {};
    (liste || []).forEach(w => { dict[w.nom] = w; });
    store.set('watchers', dict);
    evaluerAlertesWatchers(dict);
  } catch (e) { /* best-effort, silencieux : le store garde son dernier état connu */ }
}

// ─── Orchestration de l'alerte « en file, watcher éteint » (issue #945) ────
// État par projet, UNIQUE source (point de départ de grâce + épisode déjà
// signalé — voir les fonctions pures ci-dessus) : appelée depuis la seule
// lecture périodique de /watchers ci-dessus (rafraichirWatchersPartages,
// tourne en continu dès le chargement de la page, panneau ouvert ou non —
// condition nécessaire pour que le badge projet de la liste des résultats,
// toujours visible, reste à jour même si le panneau Infrastructure est
// fermé). Écrit le résultat dans store.alertesWatchers ({ nom: {alerte,
// enFile} }), lu par rendrePanneauLateralMonitoring ci-dessous ET par
// static/js/app.js (badge du filtre projet) — un seul calcul, deux affichages,
// jamais deux notifications pour le même épisode. Aucun appel réseau
// supplémentaire : watchersMap vient du fetch /watchers déjà en cours,
// resumeProjetMonitoring (app.js) lit listeIssuesResultats déjà en mémoire.
const referenceAlerteWatcherMs = new Map();    // nom -> ms (Date.now() du début de l'attente)
const episodeAlerteWatcherSignale = new Map(); // nom -> bool (toast déjà émis pour cet épisode)

function evaluerAlertesWatchers(watchersMap) {
  const noms = appelerAncien('nomsProjetsDisponibles') || [];
  const maintenant = Date.now();
  const dict = {};
  noms.forEach(function(nom) {
    const actif = !!(watchersMap[nom] && watchersMap[nom].actif);
    const resume = appelerAncien('resumeProjetMonitoring', nom) || { enCours: 0, enFile: 0 };
    if (!enAttenteWatcherEteint(resume.enFile, actif)) {
      referenceAlerteWatcherMs.delete(nom);
      episodeAlerteWatcherSignale.delete(nom);
      dict[nom] = { alerte: false, enFile: resume.enFile };
      return;
    }
    if (!referenceAlerteWatcherMs.has(nom)) referenceAlerteWatcherMs.set(nom, maintenant);
    const alerte = fautAlerterWatcherEteint(maintenant - referenceAlerteWatcherMs.get(nom));
    if (doitNotifierAlerteWatcher(alerte, !!episodeAlerteWatcherSignale.get(nom))) {
      episodeAlerteWatcherSignale.set(nom, true);
      toasts.avertissement(
        '⚠️ Projet « ' + nom + ' » : ' + texteAlerteWatcher(resume.enFile) + '.',
        true, { cle: 'alerte-watcher-' + nom },
      );
    }
    dict[nom] = { alerte: alerte, enFile: resume.enFile };
  });
  store.set('alertesWatchers', dict);
}

// ─── Zone haute : monitoring infrastructure (watchers CCL + services CCW) ──
async function rendrePanneauLateralMonitoring() {
  const zone = dom.$('#pl-zone-monitoring');
  if (!zone) return;
  await rafraichirWatchersPartages();
  const watchersMap       = store.get('watchers') || {};
  const alertesWatchers   = store.get('alertesWatchers') || {};
  const noms              = appelerAncien('nomsProjetsDisponibles') || [];
  const ccwProjetsConnus  = obtenirCcwProjetsConnus() || [];

  let html = '<div class="titre-section" style="margin-top:0">Monitoring infrastructure</div>'
           + '<div class="pl-sous">Tous projets actifs — actualisé toutes les 30 s</div>';

  html += '<div class="pl-resume-titre">Watchers CCL</div>';
  const cclEteints = [];
  const cclActifs = [];
  noms.forEach(function(nom) {
    const actif = !!(watchersMap[nom] && watchersMap[nom].actif);
    if (!actif) cclEteints.push(nom); else cclActifs.push(nom);
    const resume = appelerAncien('resumeProjetMonitoring', nom) || { enCours: 0, enFile: 0 };
    const enAlerte = !!(alertesWatchers[nom] && alertesWatchers[nom].alerte);
    // Issue #952 : visibilité panne réseau — champs purement locaux côté
    // watcher (fichier marqueur + comptage de fichiers), déjà portés par
    // l'UNIQUE lecture périodique de /watchers (aucun appel GitHub de plus).
    const enPanneReseau = !!(watchersMap[nom] && watchersMap[nom].en_panne_reseau);
    const nbEnAttente = (watchersMap[nom] && watchersMap[nom].publications_en_attente) || 0;
    html += '<div class="pl-ligne">'
          + '<span class="pl-ligne-libelle">' + (actif ? '🟢' : '⚫') + ' ' + dom.echapperHtml(nom) + '</span>'
          + '<span class="pl-ligne-btns">'
          + '<button class="pl-btn-mini" data-action="pl-relancer-ccl" data-projet="' + dom.echapperHtml(nom) + '">'
          + (actif ? '↺ Relancer' : '▶ Lancer') + '</button>'
          + (afficherBoutonArreterWatcherCcl(actif)
              ? '<button class="pl-btn-mini" data-action="pl-arreter-ccl" data-projet="' + dom.echapperHtml(nom) + '">⏹ Arrêter</button>'
              : '')
          + '</span>'
          + '</div>'
          + '<div class="pl-sous-projet">' + resume.enCours + ' en cours, ' + resume.enFile + ' en file</div>'
          + (enAlerte
              ? '<div class="pl-alerte-watcher">⚠️ ' + dom.echapperHtml(texteAlerteWatcher(resume.enFile)) + '</div>'
              : '')
          + (enPanneReseau || nbEnAttente
              ? '<div class="pl-alerte-watcher">⚠️ en attente du réseau — '
                + nbEnAttente + ' publication(s) en attente</div>'
              : '');
  });
  if (noms.length) {
    html += '<div class="pl-boutons-ccl">';
    if (cclEteints.length) {
      html += '<button class="pl-btn-vm" data-action="pl-relancer-eteints">▶ Lancer les éteints</button>';
    }
    if (cclActifs.length) {
      html += '<button class="pl-btn-vm" data-action="pl-relancer-actifs">↺ Relancer les allumés</button>';
    }
    html += '<button class="pl-btn-vm" data-action="pl-relancer-tous-ccl" '
          + 'title="Relance aussi les watchers éteints, les allume donc inutilement">'
          + '↺ Relancer tous les CCL</button>';
    html += '</div>';
  }

  html += '<div class="pl-resume-titre">Services CCW</div>';
  if (ccwProjetsConnus.length) {
    ccwProjetsConnus.forEach(function(p) {
      const actif = p.etat === 'running';
      html += '<div class="pl-ligne"><span class="pl-ligne-libelle">'
            + (actif ? '🟢' : '⚫') + ' ' + dom.echapperHtml(p.projet)
            + (actif ? '' : ' (' + dom.echapperHtml(p.etat || '?') + ')') + '</span></div>';
    });
  } else {
    html += '<div class="pl-lien" data-action="pl-charger-ccw">🔄 Vérifier les services CCW</div>';
  }

  html += '<div class="pl-sous" style="margin-top:10px">Mis à jour à '
        + new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
        + '</div>';
  zone.innerHTML = html;
}

async function sidebarChargerCcw() {
  await ccwChargerProjets();
}

// ─── Interrupteur global plat/cloche du bip (#pl-zone-son, issue #527) ─────
// Déplacé tel quel (issue #628) : comportement inchangé, seule la brique
// réseau change (api.* au lieu de fetch() en dur).
async function initZoneSon() {
  const seg = dom.$('#pl-son-segmente');
  if (!seg) return;
  let son = 'plat';
  try {
    const donnees = await api.get('/son-actif', { silencieux: true });
    if (donnees && (donnees.son === 'plat' || donnees.son === 'cloche')) son = donnees.son;
  } catch (e) { /* défaut 'plat' conservé */ }
  refleterSonActif(son);
}

function refleterSonActif(son) {
  const optPlat   = dom.$('#pl-son-opt-plat');
  const optCloche = dom.$('#pl-son-opt-cloche');
  if (optPlat)   optPlat.classList.toggle('actif', son === 'plat');
  if (optCloche) optCloche.classList.toggle('actif', son === 'cloche');
}

// Grise « Tester le son » tant qu'aucune ligne n'est sélectionnée (issue #533).
function majBoutonTesterSonActif() {
  const btn = dom.$('#pl-btn-tester-son');
  if (!btn) return;
  const { projet } = appelerAncien('obtenirIssueSelectionnee') || {};
  btn.disabled = !projet;
  btn.title = projet ? '' : 'Aucune ligne sélectionnée';
}

async function choisirSonActif(son) {
  refleterSonActif(son);   // optimiste : réactivité immédiate au clic
  try {
    await api.post('/son-actif', { son: son });
  } catch (e) { /* déjà signalé par api.post (toast) */ }
}

async function testerSonActif() {
  const { projet } = appelerAncien('obtenirIssueSelectionnee') || {};
  if (!projet) return;
  try {
    await api.post('/tester-son', { projet: projet });
  } catch (e) { /* déjà signalé par api.post (toast) */ }
}

// ─── Zone médiane : watcher spool (issues_inbox, issue #485) ──────────────
async function rendrePanneauLateralExtras() {
  const zone = dom.$('#pl-zone-extras');
  if (!zone) return;
  let etat = null;
  try {
    etat = await api.get('/issues-inbox/etat', { silencieux: true });
  } catch (e) { etat = null; }
  if (!etat) { zone.innerHTML = ''; return; }

  const actif = !!etat.watcher_actif;
  let html = '<div class="pl-resume-titre">Watcher spool</div>';
  html += '<div class="pl-ligne"><span class="pl-ligne-libelle">'
        + (actif ? '🟢' : '⚫') + ' Watcher spool (issues_inbox)</span>'
        + '<button class="pl-btn-mini" data-action="pl-demarrer-watcher-inbox">'
        + (actif ? '↺ Relancer' : '▶ Démarrer') + '</button>'
        + '</div>';
  if (actif) {
    const restant = (etat.watcher_restant_s === null || etat.watcher_restant_s === undefined)
      ? 'indéfini' : formaterDureeRestante(etat.watcher_restant_s);
    html += '<div class="pl-sous-projet">Extinction : ' + restant + '</div>';
    html += '<div class="pl-boutons-ccl">'
          + '<button class="pl-btn-vm" data-action="pl-arreter-watcher-inbox">⏹ Arrêter</button>'
          + '</div>';
  }
  // Historique récent du watcher spool (issue #639) : rejoint ici depuis
  // l'ancien onglet « Résultats inbox », supprimé. Repli discret dans un
  // <details> fermé par défaut — n'alourdit le panneau que si on l'ouvre.
  // Mêmes dernières lignes de logs/issues_inbox.log qu'exposées par
  // /issues-inbox/etat, déjà chargé ci-dessus (aucun fetch supplémentaire).
  const lignes = etat.historique || [];
  html += '<details class="pl-inbox-historique">'
        + '<summary>Historique récent</summary>'
        + '<div class="inbox-historique">'
        + (lignes.length ? dom.echapperHtml(lignes.join('\n'))
                         : '(aucun historique pour le moment)')
        + '</div></details>';
  zone.innerHTML = html;
}

function formaterDureeRestante(secondes) {
  const totalMin = Math.max(1, Math.ceil(secondes / 60));
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return h > 0 ? (h + 'h' + String(m).padStart(2, '0')) : (m + ' min');
}

// Démarre/relance le watcher spool directement, sans boîte de dialogue
// (issue #754 — la question de durée posée ici jusque-là répondait à un
// besoin disparu, #485 : le spool ne surveille qu'un dossier local, sans
// coût GitHub). Toujours sans durée limite (duree_min=0, comportement par
// défaut déjà en place) — même patron disable/libellé/rétablissement que
// les autres boutons du panneau (sidebarRelancerWatcherCCL,
// sidebarArreterWatcherInbox…) ; aucun toast de succès, le point vert du
// panneau confirme l'action après rafraîchissement.
export async function sidebarDemarrerWatcherInbox(btn) {
  const label = btn ? btn.textContent : null;
  if (btn) { btn.disabled = true; btn.textContent = 'Démarrage…'; }
  try {
    await api.post('/issues-inbox/demarrer-watcher', { duree_min: 0 });
  } catch (e) { /* déjà signalé par api.post (toast) */ }
  if (btn) { btn.disabled = false; if (label !== null) btn.textContent = label; }
  await rafraichirPanneauLateralResultats();
}

async function sidebarArreterWatcherInbox(btn) {
  const ok = await toasts.confirmer('Arrêter le watcher spool (issues_inbox) ?', { texteConfirmer: 'Arrêter' });
  if (!ok) return;
  const label = btn ? btn.textContent : null;
  if (btn) { btn.disabled = true; btn.textContent = 'Arrêt…'; }
  try {
    await api.post('/issues-inbox/arreter-watcher');
  } catch (e) { /* déjà signalé par api.post (toast) */ }
  if (btn) { btn.disabled = false; if (label !== null) btn.textContent = label; }
  await rafraichirPanneauLateralResultats();
}

// ─── Zone basse : actions contextuelles sur l'issue sélectionnée ──────────
function libelleModeIssue(nomsLabels) {
  const modeEcr = appelerAncien('modeEcritureDepuisLabels', nomsLabels);
  if (modeEcr === 'ecriture')       return '⚠️ Écriture';
  if (modeEcr === 'lecture_active') return '✏️ Lecture active';
  return '📖 Lecture seule';
}

function rendrePanneauLateralActions() {
  const zone = dom.$('#pl-zone-actions');
  if (!zone) return;
  const { projet: nom, numero, issue: it } = appelerAncien('obtenirIssueSelectionnee') || {};
  if (!nom || !numero) { zone.innerHTML = ''; return; }
  const nomsLabels = it ? (it.labels || []).map(l => ((l && l.name) || l || '').toLowerCase()) : [];
  const ferme = !!(it && (it.state || '').toUpperCase() === 'CLOSED');

  // Même condition que l'ancien bouton « Interrompre » du détail d'issue
  // (retiré du détail par l'issue #628, cette action ne vit plus qu'ici) :
  // issue ouverte, ni done ni needs-human.
  const interromptible = !!it && !ferme
    && !nomsLabels.includes('done') && !nomsLabels.includes('needs-human');
  const ccwProjetsConnus = obtenirCcwProjetsConnus() || [];
  const service = ccwProjetsConnus.find(p => (p.projet || '').toLowerCase() === nom.toLowerCase()) || null;
  const windows = nomsLabels.includes('for-windows');
  const libelleWatcherCible = windows ? 'watcher CCW' : 'watcher CCL';

  let html = '<hr class="pl-sep">'
           + '<div class="titre-section" style="margin-top:0">Actions — '
           + dom.echapperHtml(nom) + ' #' + dom.echapperHtml(numero) + '</div>';
  if (it) {
    html += '<div class="pl-mode-issue">' + libelleModeIssue(nomsLabels) + '</div>';
  }
  if (interromptible) {
    const etatsNotif = etatsCasesNotif(nomsLabels);
    html += '<div class="pl-notifs">'
          + '<div class="pl-notifs-titre">🔔 Notifications</div>'
          + rendreCheckboxNotif(nom, numero, 'notif_pc',   'Bureau', etatsNotif.notif_pc)
          + rendreCheckboxNotif(nom, numero, 'notif_gsm',  'GSM',    etatsNotif.notif_gsm)
          + rendreCheckboxNotif(nom, numero, 'notif_tous', 'Tous',   etatsNotif.notif_tous)
          + '<div id="pl-notif-erreur" class="pl-notif-erreur"></div>'
          + '</div>';
  }
  html += '<div class="pl-actions">';
  if (interromptible) {
    // Bouton « Avancement » (issue #887) : commits + fichiers du worktree
    // dédié à CETTE issue, lecture seule — voir ouvrirAvancement() plus bas.
    // Mêmes labels que ceux déjà normalisés ci-dessus (nomsLabels), transmis
    // au serveur en paramètre de requête : évite un second appel GitHub pour
    // déterminer le mode (écriture/lecture active/lecture seule/for-windows).
    html += '<button data-action="pl-avancement" data-projet="' + dom.echapperHtml(nom)
          + '" data-numero="' + Number(numero) + '" data-labels="'
          + dom.echapperHtml(nomsLabels.join(',')) + '">📊 Avancement</button>';
  }
  html += '<button data-action="pl-relancer-ccl" data-projet="' + dom.echapperHtml(nom) + '">'
        + '↺ Relancer watcher CCL</button>';
  if (interromptible) {
    html += '<button class="danger" data-action="pl-interrompre-relancer" data-projet="' + dom.echapperHtml(nom)
          + '" data-numero="' + Number(numero) + '">⛔ Interrompre et relancer (' + libelleWatcherCible + ')</button>';
  }
  // Bouton « ✖ Fermer l'issue » retiré d'ici par l'issue #950 (décision
  // d'Alain : toutes les actions par issue sur la ligne) — voir le bouton
  // « Fermer » de static/js/actions_ligne.js (même route /fermer-issue,
  // commentaire GitHub corrigé côté serveur, aucun changement de mécanisme).
  if (service) {
    html += '<button data-action="pl-ccw-relancer" data-projet="' + dom.echapperHtml(nom) + '">'
          + '↺ Relancer watcher CCW</button>'
          + '<button class="danger" data-action="pl-ccw-nettoyer" data-projet="' + dom.echapperHtml(nom) + '">'
          + '🔒 Nettoyer verrous CCW + redémarrer</button>';
  }
  html += '</div>';
  // Lien de repli sans objet pour une issue for-linux (issue #633) : le
  // service CCW n'existe que côté Windows, ce lien n'a de sens que si le
  // service en question pourrait exister pour CETTE issue.
  if (windows && !ccwProjetsConnus.length) {
    html += '<div class="pl-lien" data-action="pl-charger-ccw">🔄 Vérifier le service CCW de ce projet</div>';
  }
  zone.innerHTML = html;
}

function rendreCheckboxNotif(nom, numero, label, libelle, coche) {
  return '<label class="pl-notif-ligne">'
       + '<input type="checkbox"' + (coche ? ' checked' : '') + ' data-action="pl-notif-toggle" data-projet="' + dom.echapperHtml(nom)
       + '" data-numero="' + Number(numero) + '" data-label="' + label + '"> '
       + dom.echapperHtml(libelle) + '</label>';
}

async function toggleLabelNotif(nom, numero, label, cb) {
  const actif = cb.checked;
  cb.disabled = true;
  let ok = false, erreur = '';
  try {
    const json = await api.post('/modifier-label-notif',
      { projet: nom, numero: numero, label: label, actif: actif }, { silencieux: true });
    ok = !!(json && json.succes);
    if (!ok) {
      erreur = (json && json.erreur) || 'échec de la mise à jour du label.';
      // Alerte explicite de panne GitHub (issue #732) : cette route répond
      // toujours en HTTP 200 (succes:false en JSON) — pas d'ErreurApi ici.
      signalerEchecPossible(json);
    }
  } catch (e) {
    erreur = 'Erreur réseau : ' + e.message;
  }
  cb.disabled = false;
  if (!ok) {
    cb.checked = !actif;
    afficherErreurNotifDiscrete(erreur);
    return;
  }
  // Mise à jour locale de listeIssuesResultats (sans refetch réseau, via le
  // pont — cette liste appartient à la fonctionnalité « liste des issues »,
  // toujours dans app.js), puis re-rendu du panneau d'actions.
  appelerAncien('actualiserLabelIssueLocal', nom, numero, label, actif);
  rendrePanneauLateralActions();
}

function afficherErreurNotifDiscrete(message) {
  const zone = dom.$('#pl-notif-erreur');
  if (!zone) return;
  zone.textContent = '⚠ ' + message;
  setTimeout(function() {
    if (zone.textContent === '⚠ ' + message) zone.textContent = '';
  }, 4000);
}

// ─── Relance des watchers CCL (individuelle / groupée) ─────────────────────
async function sidebarRelancerWatcherCCL(nom, btn) {
  const label = btn ? btn.textContent : null;
  if (btn) { btn.disabled = true; btn.textContent = 'Relance…'; }
  try {
    await api.post('/lancer-watcher', { projet: nom, relancer: true });
  } catch (e) { /* déjà signalé par api.post (toast) */ }
  if (btn) { btn.disabled = false; if (label !== null) btn.textContent = label; }
  await rafraichirPanneauLateralResultats();
}

// Arrêt immédiat d'un watcher CCL (issue #655) : jusqu'ici un watcher actif ne
// s'éteignait que par son délai d'auto-extinction (Configuration) — même
// mécanique de confirmation que sidebarArreterWatcherInbox (watcher spool).
// Avertissement listant les tâches actuellement en cours de ce projet
// (route #947, /issues-en-cours) — ajouté à la confirmation (issue #950,
// point 7, #938 point 2.3 : ce bouton ne tue PAS le `claude` en cours,
// contrairement à « Interrompre et relancer », il laisse juste le watcher
// orphelin, sans que le libellé ou la confirmation ne le disent jusqu'ici).
// Best-effort : une erreur réseau n'empêche jamais la confirmation.
async function avertissementTachesEnCours(nom) {
  try {
    const rep = await api.get('/issues-en-cours/' + encodeURIComponent(nom), { silencieux: true });
    const issues = Array.isArray(rep && rep.issues) ? rep.issues : [];
    if (!issues.length) return '';
    const liste = issues.map(i => '#' + (i && i.numero != null ? i.numero : '?')).join(', ');
    return '\n\n⚠️ ' + issues.length + ' tâche(s) en cours (' + liste + ') ne seront PAS '
         + 'interrompues (process orphelin, non supervisé) — à réserver à une opération de '
         + 'maintenance (déploiement).';
  } catch (e) {
    return '';
  }
}

async function sidebarArreterWatcherCCL(nom, btn) {
  const avert = await avertissementTachesEnCours(nom);
  const ok = await toasts.confirmer('Arrêter le watcher CCL du projet « ' + nom + ' » ?' + avert,
    { texteConfirmer: 'Arrêter' });
  if (!ok) return;
  const label = btn ? btn.textContent : null;
  if (btn) { btn.disabled = true; btn.textContent = 'Arrêt…'; }
  try {
    await api.post('/arreter-watcher', { projet: nom });
  } catch (e) { /* déjà signalé par api.post (toast) */ }
  if (btn) { btn.disabled = false; if (label !== null) btn.textContent = label; }
  await rafraichirPanneauLateralResultats();
}

async function sidebarRelancerTousEteints(btn) {
  if (btn) { btn.disabled = true; btn.textContent = 'Relance…'; }
  try {
    const liste = await api.get('/watchers', { silencieux: true });
    const watchersMap = {};
    (liste || []).forEach(w => { watchersMap[w.nom] = w; });
    const noms = appelerAncien('nomsProjetsDisponibles') || [];
    const eteints = noms.filter(n => !(watchersMap[n] && watchersMap[n].actif));
    for (const nom of eteints) {
      try {
        await api.post('/lancer-watcher', { projet: nom, relancer: true }, { silencieux: true });
      } catch (e) { /* une relance en échec ne doit pas bloquer les suivantes */ }
    }
  } catch (e) {
    toasts.erreur('Erreur réseau : ' + e.message);
  }
  if (btn) { btn.disabled = false; btn.textContent = '▶ Lancer les éteints'; }
  await rafraichirPanneauLateralResultats();
}

// « ↺ Relancer les allumés » (issue #753) : à la différence de « ▶ Lancer les
// éteints » (qui allume) et « ↺ Relancer tous les CCL » (qui relance TOUT, y
// compris les éteints — d'où leur mise en veille GitHub pendant 20 min pour
// rien), ce bouton ne touche QUE les watchers déjà actifs, et saute ceux qui
// ont une issue en cours (resumeProjetMonitoring, déjà en mémoire côté
// app.js — aucun fetch réseau supplémentaire ici, voir
// selectionnerWatchersActifsARelancer).
async function sidebarRelancerActifs(btn) {
  const label = btn ? btn.textContent : null;
  if (btn) { btn.disabled = true; btn.textContent = 'Relance…'; }
  let relances = [], ignores = [];
  try {
    const liste = await api.get('/watchers', { silencieux: true });
    const watchersMap = {};
    (liste || []).forEach(w => { watchersMap[w.nom] = w; });
    const noms = appelerAncien('nomsProjetsDisponibles') || [];
    const resumeParProjet = {};
    noms.forEach(function(nom) { resumeParProjet[nom] = appelerAncien('resumeProjetMonitoring', nom); });
    ({ relances, ignores } = selectionnerWatchersActifsARelancer(noms, watchersMap, resumeParProjet));
    await relancerSequentiellement(relances,
      nom => api.post('/lancer-watcher', { projet: nom, relancer: true }, { silencieux: true }));
    const resume = resumerRelanceActifs(relances, ignores);
    if (resume.type === 'avertissement') toasts.avertissement(resume.texte);
    else toasts.succes(resume.texte, false);
  } catch (e) {
    toasts.erreur('Erreur réseau : ' + e.message);
  }
  if (btn) { btn.disabled = false; if (label !== null) btn.textContent = label; }
  await rafraichirPanneauLateralResultats();
}

async function sidebarRelancerTousCCL(btn) {
  if (btn) { btn.disabled = true; btn.textContent = 'Relance…'; }
  try {
    const noms = appelerAncien('nomsProjetsDisponibles') || [];
    for (const nom of noms) {
      try {
        await api.post('/lancer-watcher', { projet: nom, relancer: true }, { silencieux: true });
      } catch (e) { /* une relance en échec ne doit pas bloquer les suivantes */ }
    }
  } catch (e) {
    toasts.erreur('Erreur réseau : ' + e.message);
  }
  if (btn) { btn.disabled = false; btn.textContent = '↺ Relancer tous les CCL'; }
  await rafraichirPanneauLateralResultats();
}

// ─── Délégation d'événements (remplace les onclick= inline, §6.7 étape 2) ──
function installerDelegationPanneau() {
  dom.surAction('[data-action="pl-toggle"]',     'click', () => basculerPanneauLateral());
  dom.surAction('[data-action="pl-son-plat"]',   'click', () => choisirSonActif('plat'));
  dom.surAction('[data-action="pl-son-cloche"]', 'click', () => choisirSonActif('cloche'));
  dom.surAction('[data-action="pl-tester-son"]', 'click', () => testerSonActif());

  dom.surAction('[data-action="pl-relancer-ccl"]', 'click',
    (e, el) => sidebarRelancerWatcherCCL(el.dataset.projet, el));
  dom.surAction('[data-action="pl-arreter-ccl"]', 'click',
    (e, el) => sidebarArreterWatcherCCL(el.dataset.projet, el));
  dom.surAction('[data-action="pl-relancer-eteints"]', 'click',
    (e, el) => sidebarRelancerTousEteints(el));
  dom.surAction('[data-action="pl-relancer-actifs"]', 'click',
    (e, el) => sidebarRelancerActifs(el));
  dom.surAction('[data-action="pl-relancer-tous-ccl"]', 'click',
    (e, el) => sidebarRelancerTousCCL(el));
  dom.surAction('[data-action="pl-charger-ccw"]', 'click',
    () => sidebarChargerCcw());

  dom.surAction('[data-action="pl-demarrer-watcher-inbox"]', 'click',
    (e, el) => sidebarDemarrerWatcherInbox(el));
  dom.surAction('[data-action="pl-arreter-watcher-inbox"]', 'click',
    (e, el) => sidebarArreterWatcherInbox(el));

  dom.surAction('[data-action="pl-avancement"]', 'click',
    (e, el) => ouvrirAvancement(el.dataset.projet, Number(el.dataset.numero), el.dataset.labels));
  dom.surAction('[data-action="pl-fermer-avancement"]', 'click',
    () => fermerAvancement());

  dom.surAction('[data-action="pl-interrompre-relancer"]', 'click',
    (e, el) => appelerAncien('interrompreEtRelancer', el.dataset.projet, Number(el.dataset.numero)));
  dom.surAction('[data-action="pl-ccw-relancer"]', 'click',
    (e, el) => ccwRedemarrerProjet(el.dataset.projet, el));
  dom.surAction('[data-action="pl-ccw-nettoyer"]', 'click',
    (e, el) => ccwNettoyerVerrous(el.dataset.projet, el));

  dom.surAction('[data-action="pl-notif-toggle"]', 'change',
    (e, el) => toggleLabelNotif(el.dataset.projet, Number(el.dataset.numero), el.dataset.label, el));
}

/** Point d'entrée, appelé une fois par index.js. */
export function initPanneauLateral() {
  installerDelegationPanneau();
  rafraichirWatchersPartages();
  setInterval(rafraichirWatchersPartages, 30000);

  // Démarrage/arrêt du panneau : abonnement direct au store (issue #632), à
  // la place de l'ancien appel via le pont depuis onglets.js (qui visait des
  // globales demarrerPanneauLateral/arreterPanneauLateral jamais publiées par
  // app.js — cf. rapport de clôture). Cet abonnement doit être posé AVANT que
  // index.js n'active l'onglet par défaut (voir onglets.js#activerOngletParDefaut).
  store.abonnerCle('ongletActif', (nom) => {
    if (nom === 'resultats') demarrerPanneauLateral(); else arreterPanneauLateral();
  });
  // Rafraîchissement à chaque transition d'issue /stream (issue #375) :
  // abonnement direct au store, remplace l'appel `appelerAncien` fait
  // auparavant par resultats.js (communication de module à module par le pont
  // — issue #632).
  store.abonnerCle('derniereNotifIssue', () => rafraichirPanneauLateralResultats());

  // Points d'entrée encore appelés par app.js (classique, ne peut pas
  // importer ce module) — exposés en globales, voir socle/pont.js §6.4 pour
  // le principe (ici dans le sens inverse : socle exposé à l'ancien).
  window.rafraichirPanneauLateralResultats = rafraichirPanneauLateralResultats;
  window.majBoutonTesterSonActif = majBoutonTesterSonActif;
  // Appelée par interrompreEtRelancer() (static/js/app.js) côté CCL.
  window.sidebarRelancerWatcherCCL = sidebarRelancerWatcherCCL;
}
