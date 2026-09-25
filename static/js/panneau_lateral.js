// panneau_lateral.js — panneau latéral « Infrastructure » de l'onglet Résultats
// (issue #628, refonte web étape 4 — sorti d'app.js selon ARCHITECTURE.md §6.7).
//
// RESPONSABILITÉ
//   Colonne latérale (non recouvrante, voir static/css/resultats.css) affichée
//   à côté de la liste de l'onglet Résultats : monitoring passif des watchers
//   CCL + services CCW connus, interrupteur global du bip, contrôle du watcher
//   spool (issues_inbox), actions contextuelles sur l'issue sélectionnée.
//   Ouvert par défaut, état mémorisé (persistance.js) et conservé d'un onglet
//   à l'autre — contrairement à l'ancien comportement (réinitialisé à chaque
//   entrée dans l'onglet Résultats).
//
// CE QUI N'EST PAS ICI (reste dans static/js/app.js, autres étapes de la
// refonte) : la liste des issues et le détail d'une issue (listeIssuesResultats,
// projetCourant/numeroCourant, construireHtmlIssue), les projets
// (nomsProjetsDisponibles), les actions réseau sur une issue (interrompreIssue,
// relancerIssue, fermerIssue, interrompreEtRelancer) et l'onglet CCW
// (ccwChargerProjets, ccwRedemarrerProjet, ccwNettoyerVerrous). Ce module les
// appelle via le pont (appelerAncien) — voir socle/pont.js — sans y référer en
// dur, et expose en retour les points d'entrée qu'app.js appelle encore
// (rafraichirPanneauLateralResultats, majBoutonTesterSonActif,
// sidebarRelancerWatcherCCL) comme globales `window.*`. démarrerPanneauLateral/
// arreterPanneauLateral, eux, ne sont plus exposés : depuis #632, ce module
// s'abonne lui-même à store.ongletActif (voir initPanneauLateral) — personne
// d'autre n'a jamais besoin de les appeler par leur nom.
//
// MONITORING VM SUPPRIMÉ (issue #628) : l'ancien appel à /ccw/vm-statut (route
// disparue côté serveur depuis #447, VirtualBox retiré) et le bouton
// sidebarDemarrerVm (jamais défini) n'existent plus.
//
// MUTUALISATION /watchers (issue #628) : rafraichirWatchersPartages() est
// l'UNIQUE source de lecture de /watchers, écrite dans store.watchers — le
// bandeau de repli REP_TRAVAIL (static/js/app.js) s'y abonne désormais au lieu
// de fetcher lui-même (voir rafraichirReplisRepTravail dans app.js).

import { store } from './socle/store.js';
import { api } from './socle/api.js';
import { toasts } from './socle/toasts.js';
import * as dom from './socle/dom.js';
import * as persistance from './socle/persistance.js';
import { appelerAncien } from './socle/pont.js';

const CLE_PANNEAU_OUVERT = 'bridge_panneau_lateral_ouvert';

let intervalPanneauLateral = null;

// ─────────────────────────────────────────────────────────────────────────────
// LOGIQUE PURE (testée sous Node — voir static/js/tests/panneau_lateral.test.js)
//    Aucune dépendance au DOM ni au réseau.
// ─────────────────────────────────────────────────────────────────────────────

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
  } catch (e) { /* best-effort, silencieux : le store garde son dernier état connu */ }
}

// ─── Zone haute : monitoring infrastructure (watchers CCL + services CCW) ──
async function rendrePanneauLateralMonitoring() {
  const zone = dom.$('#pl-zone-monitoring');
  if (!zone) return;
  await rafraichirWatchersPartages();
  const watchersMap       = store.get('watchers') || {};
  const noms              = appelerAncien('nomsProjetsDisponibles') || [];
  const ccwProjetsConnus  = appelerAncien('obtenirCcwProjetsConnus') || [];

  let html = '<div class="titre-section" style="margin-top:0">Monitoring infrastructure</div>'
           + '<div class="pl-sous">Tous projets actifs — actualisé toutes les 30 s</div>';

  html += '<div class="pl-resume-titre">Watchers CCL</div>';
  const cclEteints = [];
  noms.forEach(function(nom) {
    const actif = !!(watchersMap[nom] && watchersMap[nom].actif);
    if (!actif) cclEteints.push(nom);
    const resume = appelerAncien('resumeProjetMonitoring', nom) || { enCours: 0, enFile: 0 };
    html += '<div class="pl-ligne">'
          + '<span class="pl-ligne-libelle">' + (actif ? '🟢' : '⚫') + ' ' + dom.echapperHtml(nom) + '</span>'
          + '<button class="pl-btn-mini" data-action="pl-relancer-ccl" data-projet="' + dom.echapperHtml(nom) + '">'
          + (actif ? '↺ Relancer' : '▶ Lancer') + '</button>'
          + '</div>'
          + '<div class="pl-sous-projet">' + resume.enCours + ' en cours, ' + resume.enFile + ' en file</div>';
  });
  if (noms.length) {
    html += '<div class="pl-boutons-ccl">';
    if (cclEteints.length) {
      html += '<button class="pl-btn-vm" data-action="pl-relancer-eteints">▶ Lancer les éteints</button>';
    }
    html += '<button class="pl-btn-vm" data-action="pl-relancer-tous-ccl">↺ Relancer tous les CCL</button>';
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
  await appelerAncien('ccwChargerProjets');
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
        + '<button class="pl-btn-mini" data-action="pl-duree-watcher-ouvrir">'
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
  zone.innerHTML = html;
}

function formaterDureeRestante(secondes) {
  const totalMin = Math.max(1, Math.ceil(secondes / 60));
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return h > 0 ? (h + 'h' + String(m).padStart(2, '0')) : (m + ' min');
}

function sidebarOuvrirDureeWatcherInbox() {
  const overlay = dom.$('#modal-duree-watcher-inbox');
  if (!overlay) return;
  const radioIndef = dom.$('#dwi-indefini');
  if (radioIndef) radioIndef.checked = true;
  const champMin = dom.$('#dwi-minutes');
  if (champMin) champMin.value = '';
  overlay.classList.add('actif');
}

function sidebarFermerDureeWatcherInbox() {
  const overlay = dom.$('#modal-duree-watcher-inbox');
  if (overlay) overlay.classList.remove('actif');
}

async function sidebarConfirmerDureeWatcherInbox(btn) {
  const choix = dom.$('input[name="dwi-choix"]:checked');
  let dureeMin = 0;
  if (choix && choix.value === '30') {
    dureeMin = 30;
  } else if (choix && choix.value === 'perso') {
    const champ = dom.$('#dwi-minutes');
    dureeMin = parseInt(champ ? champ.value : '', 10);
    if (!Number.isFinite(dureeMin) || dureeMin <= 0) {
      toasts.avertissement('Indiquez un nombre de minutes valide (> 0).');
      return;
    }
  }
  const label = btn ? btn.textContent : null;
  if (btn) { btn.disabled = true; btn.textContent = 'Démarrage…'; }
  try {
    await api.post('/issues-inbox/demarrer-watcher', { duree_min: dureeMin });
  } catch (e) { /* déjà signalé par api.post (toast) */ }
  if (btn) { btn.disabled = false; if (label !== null) btn.textContent = label; }
  sidebarFermerDureeWatcherInbox();
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
  const ccwProjetsConnus = appelerAncien('obtenirCcwProjetsConnus') || [];
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
  html += '<div class="pl-actions">'
        + '<button data-action="pl-relancer-ccl" data-projet="' + dom.echapperHtml(nom) + '">'
        + '↺ Relancer watcher CCL</button>';
  if (interromptible) {
    html += '<button class="danger" data-action="pl-interrompre-relancer" data-projet="' + dom.echapperHtml(nom)
          + '" data-numero="' + Number(numero) + '">⛔ Interrompre et relancer (' + libelleWatcherCible + ')</button>';
    html += '<button class="danger" data-action="pl-interrompre" data-projet="' + dom.echapperHtml(nom)
          + '" data-numero="' + Number(numero) + '">⛔ Interrompre l\'issue</button>';
  }
  if (!ferme && nomsLabels.includes('needs-human')) {
    html += '<button data-action="pl-retirer-needs-human" data-projet="' + dom.echapperHtml(nom)
          + '" data-numero="' + Number(numero) + '">🔄 Retirer needs-human</button>';
    html += '<button class="danger-plein" data-action="pl-fermer-issue" data-projet="' + dom.echapperHtml(nom)
          + '" data-numero="' + Number(numero) + '">✖ Fermer l\'issue</button>';
  }
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
    if (!ok) erreur = (json && json.erreur) || 'échec de la mise à jour du label.';
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
  dom.surAction('[data-action="pl-relancer-eteints"]', 'click',
    (e, el) => sidebarRelancerTousEteints(el));
  dom.surAction('[data-action="pl-relancer-tous-ccl"]', 'click',
    (e, el) => sidebarRelancerTousCCL(el));
  dom.surAction('[data-action="pl-charger-ccw"]', 'click',
    () => sidebarChargerCcw());

  dom.surAction('[data-action="pl-duree-watcher-ouvrir"]', 'click',
    () => sidebarOuvrirDureeWatcherInbox());
  dom.surAction('[data-action="pl-arreter-watcher-inbox"]', 'click',
    (e, el) => sidebarArreterWatcherInbox(el));
  dom.surAction('[data-action="pl-duree-watcher-annuler"]', 'click',
    () => sidebarFermerDureeWatcherInbox());
  dom.surAction('[data-action="pl-duree-watcher-confirmer"]', 'click',
    (e, el) => sidebarConfirmerDureeWatcherInbox(el));

  dom.surAction('[data-action="pl-interrompre-relancer"]', 'click',
    (e, el) => appelerAncien('interrompreEtRelancer', el.dataset.projet, Number(el.dataset.numero)));
  dom.surAction('[data-action="pl-interrompre"]', 'click',
    (e, el) => appelerAncien('interrompreIssue', el.dataset.projet, Number(el.dataset.numero)));
  dom.surAction('[data-action="pl-retirer-needs-human"]', 'click',
    (e, el) => appelerAncien('relancerIssue', el.dataset.projet, Number(el.dataset.numero)));
  dom.surAction('[data-action="pl-fermer-issue"]', 'click',
    (e, el) => appelerAncien('fermerIssue', el.dataset.projet, Number(el.dataset.numero)));
  dom.surAction('[data-action="pl-ccw-relancer"]', 'click',
    (e, el) => appelerAncien('ccwRedemarrerProjet', el.dataset.projet, el));
  dom.surAction('[data-action="pl-ccw-nettoyer"]', 'click',
    (e, el) => appelerAncien('ccwNettoyerVerrous', el.dataset.projet, el));

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
