// interruption_projet.js — boutons de niveau PROJET du panneau Infrastructure
// (issue #954, suite #947/#949/#950/#951 : « Tout interrompre pour ce
// projet », « Redémarrer le watcher », « Interrompre et relancer (watcher
// CCL) », « Arrêter »).
//
// POURQUOI CE MODULE
//   Avant cette issue, ces boutons agissaient directement sur le WATCHER
//   entier d'un projet (SIGTERM ou kill d'arbre complet, voir
//   docs/contexte/interruption_issue.md) : toute issue en cours du projet
//   était arrêtée en même temps, parfois sans même le dire clairement
//   (#938/#947). Principe d'Alain (#954) : plus aucune action de ce panneau
//   ne doit arrêter une ou plusieurs issues sans qu'elles soient NOMMÉES et
//   que le choix soit explicite — l'arrêt de plusieurs issues d'un coup
//   devient une action à part entière (« Tout interrompre pour ce projet »),
//   jamais un effet de bord d'un bouton qui parle du watcher.
//
//   Ce module réutilise EXCLUSIVEMENT les routes existantes
//   (#947 /issues-en-cours, #949 /demander-interruption-issue,
//   /lancer-watcher, /relancer-issue, /arreter-watcher) — orchestration
//   côté client, comme la fermeture d'une issue en cours (#951,
//   static/js/app.js::fermerIssueEnCoursDepuisLigne). Seule exception,
//   documentée dans app/watchers.py : la mémorisation/purge (fichier sous
//   logs/, jamais REP_TRAVAIL) de la liste des issues qu'une séquence de
//   redémarrage vient de relancer, pour ne jamais en relancer une qui était
//   déjà interrompue/needs-human AVANT le clic.
//
//   Hors périmètre, comme pour #949 : issues en file (jamais démarrées),
//   diagnostic automatique d'échec, processus détachés par l'outil Bash
//   interne de `claude` (setsid) — voir docs/contexte/interruption_issue.md.
//
// ISSUES INTERACTIVES (session tmux, #949 ne les couvre jamais) — jamais
// d'arrêt silencieux : ce module les détecte (mecanismeInterruptionLigne,
// static/js/actions_ligne.js — même détection que le bouton « Interrompre »
// d'une ligne, pour ne jamais diverger) et les signale toujours dans la
// confirmation, sans jamais les toucher automatiquement — seul le chemin
// HISTORIQUE (bouton « Interrompre » de leur propre ligne, qui arrête tout
// le watcher) peut les arrêter, choix explicite séparé.
//
// CE QUI N'EST PAS ICI
//   - Les boutons par ISSUE (Annuler/Interrompre/Relancer/Fermer) restent
//     sur static/js/actions_ligne.js + static/js/app.js (#950/#951).
//   - Le rendu du panneau Infrastructure (boutons, libellés) reste dans
//     static/js/panneau_lateral.js, qui importe et appelle ce module.

import { store } from './socle/store.js';
import { api } from './socle/api.js';
import { toasts } from './socle/toasts.js';
import { appelerAncien } from './socle/pont.js';
import { mecanismeInterruptionLigne } from './actions_ligne.js';

// ─────────────────────────────────────────────────────────────────────────────
// 1. LOGIQUE PURE (testée sous Node — voir static/js/tests/interruption_projet.test.js)
//    Aucune dépendance au DOM ni au réseau.
// ─────────────────────────────────────────────────────────────────────────────

// Faut-il afficher le bouton « ⛔ Tout interrompre » sur la ligne d'un
// watcher CCL du panneau — seulement s'il y a au moins une issue en cours
// pour CE projet (réutilise le résumé déjà calculé par
// resumeProjetMonitoring, aucun fetch supplémentaire ici).
export function afficherBoutonToutInterrompre(enCours) {
  return (enCours || 0) > 0;
}

// Libellé du bouton Lancer/Relancer selon l'état du watcher (issue #954,
// renommage : « Relancer » prêtait à confusion avec la relance d'une
// issue — ce bouton redémarre le WATCHER, pas une issue précise).
export function libelleBoutonWatcherCcl(actif) {
  return actif ? '↺ Redémarrer le watcher' : '▶ Lancer';
}

// Classe chaque issue « en cours » (route #947) en deux groupes : celles que
// l'interruption CIBLÉE (#949) peut atteindre (`normales`) et celles qu'elle
// ne peut JAMAIS atteindre (`interactives`, session tmux — même détection
// que le bouton « Interrompre » d'une ligne, mecanismeInterruptionLigne).
// `issues` : [{numero, titre, mode, labels}] — enrichi par l'appelant réseau
// ci-dessous (titre/labels lus depuis le store, AUCUN appel GitHub
// supplémentaire ici, même contrainte que #951).
export function classifierIssuesEnCoursProjet(issues) {
  const normales = [];
  const interactives = [];
  (issues || []).forEach((it) => {
    const interactif = mecanismeInterruptionLigne(it.labels) === 'watcher_complet';
    const entree = { numero: it.numero, titre: it.titre || '', mode: it.mode, labels: it.labels || [], interactif };
    (interactif ? interactives : normales).push(entree);
  });
  return { normales, interactives };
}

// Faut-il demander confirmation avant d'agir (issue #954) : dès qu'il y a au
// moins une issue en cours (normale OU interactive) à nommer — sinon,
// comportement direct inchangé (ex. « Lancer » un watcher éteint).
export function fautConfirmerActionProjet(normales, interactives) {
  return (normales || []).length > 0 || (interactives || []).length > 0;
}

// « #12 — titre », ou « #12 » sans titre connu.
export function libelleIssueCourte(it) {
  return '#' + it.numero + (it.titre ? ' — ' + it.titre : '');
}

export function listeLibellesIssues(items) {
  return (items || []).map(libelleIssueCourte).join(', ');
}

// Message de confirmation de « Tout interrompre pour ce projet » (issue
// #954, point 1) — appelé seulement quand normales.length > 0 (sinon rien à
// interrompre, voir toutInterrompreProjet ci-dessous).
export function messageToutInterrompreProjet(nom, normales, interactives) {
  let msg = 'Tout interrompre pour le projet « ' + nom + ' » ?\n\n'
    + (normales || []).length + ' issue(s) en cours seront interrompue(s) : '
    + listeLibellesIssues(normales) + '.\n\n'
    + 'Rien n\'est fermé : les worktrees et commits sont conservés, chaque issue '
    + 'passera en needs-human et pourra être relancée depuis sa ligne. Le watcher reste actif.';
  if ((interactives || []).length) {
    msg += '\n\n⚠️ ' + interactives.length + ' issue(s) interactive(s) (session tmux) ne '
      + 'seront PAS touchée(s) — ce mécanisme ne les couvre jamais : ' + listeLibellesIssues(interactives)
      + '. Pour les arrêter, utilisez le bouton « Interrompre » de leur propre ligne '
      + '(chemin historique, arrête aussi le watcher entier).';
  }
  return msg;
}

// Message de confirmation de « Redémarrer le watcher » / « Interrompre et
// relancer » (issue #954, point 3) — toujours affiché dès qu'il y a au
// moins une issue en cours (normale ou interactive).
export function messageRedemarrerWatcherProjet(nom, normales, interactives) {
  let msg = 'Redémarrer le watcher du projet « ' + nom + ' » ?\n\n';
  if ((normales || []).length) {
    msg += normales.length + ' issue(s) en cours seront interrompue(s) proprement, le watcher '
      + 'sera redémarré, puis ces mêmes issues seront relancées automatiquement : '
      + listeLibellesIssues(normales) + '.';
  } else {
    msg += 'Aucune issue (non interactive) en cours : le watcher sera simplement redémarré.';
  }
  if ((interactives || []).length) {
    msg += '\n\n⚠️ ' + interactives.length + ' issue(s) interactive(s) (session tmux) ne sont pas '
      + 'concernée(s) par cette action : ' + listeLibellesIssues(interactives) + ' — elles continuent '
      + 'sans interruption, et seront reprises automatiquement par le watcher une fois redémarré.';
  }
  return msg;
}

// Message de confirmation d'« Arrêter » (issue #954, point 3) — enrichi par
// rapport au texte historique : nomme les issues en cours, précise
// qu'elles sont interrompues proprement avant l'arrêt (plus de `claude`
// laissé orphelin pour elles), et le sort distinct des interactives.
export function messageArreterWatcherProjet(nom, normales, interactives) {
  if (!(normales || []).length && !(interactives || []).length) {
    return 'Arrêter le watcher du projet « ' + nom + ' » ?';
  }
  let msg = 'Arrêter le watcher du projet « ' + nom + ' » ?\n\n';
  if ((normales || []).length) {
    msg += normales.length + ' issue(s) en cours seront d\'abord interrompue(s) proprement '
      + '(plus de process laissé orphelin) avant l\'arrêt : ' + listeLibellesIssues(normales) + '. '
      + 'Elles repasseront en needs-human — aucune relance automatique, à relancer depuis leur '
      + 'ligne après avoir relancé le watcher (« Lancer »).';
  }
  if ((interactives || []).length) {
    msg += '\n\n⚠️ ' + interactives.length + ' issue(s) interactive(s) (session tmux) ne peuvent PAS '
      + 'être arrêtées proprement par cette action : ' + listeLibellesIssues(interactives) + ' — elles '
      + 'resteront ACTIVES mais sans watcher pour les superviser. Pour les arrêter aussi, utilisez le '
      + 'bouton « Interrompre » de leur propre ligne (chemin historique, arrête tout le watcher).';
  }
  return msg;
}

// Résumé lisible après l'attente d'arrêt (issue #954, point 1) : quelles
// issues se sont arrêtées, lesquelles non.
export function resumeArretCibles(arretees, nonArretees) {
  const a = arretees || [];
  const n = nonArretees || [];
  let texte = a.length + ' issue(s) arrêtée(s)' + (a.length ? ' (#' + a.join(', #') + ')' : '') + '.';
  if (n.length) {
    texte += ' ' + n.length + ' non arrêtée(s) à temps (#' + n.join(', #') + ') — toujours en cours '
      + 'ou passée(s) en needs-human entre-temps, réessayez.';
  }
  return { texte: texte, type: n.length ? 'avertissement' : 'succes' };
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. RÉSEAU + DOM (vérifié manuellement, voir VERIFICATIONS_MANUELLES.md)
// ─────────────────────────────────────────────────────────────────────────────

// Même ordre de grandeur que la fermeture propre d'une issue en cours
// (#951) : attente non bloquante, sondage purement local (#947), jamais de
// boucle synchrone.
const DELAI_MAX_ATTENTE_ARRET_PROJET_MS = 30000;
const INTERVALLE_SONDAGE_ARRET_PROJET_MS = 3000;

async function attendreArretCibles(nom, numeros,
  delaiMaxMs = DELAI_MAX_ATTENTE_ARRET_PROJET_MS,
  intervalleMs = INTERVALLE_SONDAGE_ARRET_PROJET_MS) {
  const ensemble = new Set((numeros || []).map(Number));
  if (!ensemble.size) return { arretees: [], nonArretees: [] };
  const limite = Date.now() + delaiMaxMs;
  let presents = new Set(ensemble);
  while (Date.now() < limite) {
    await new Promise((resoudre) => setTimeout(resoudre, intervalleMs));
    try {
      const rep = await api.get('/issues-en-cours/' + encodeURIComponent(nom), { silencieux: true });
      const enCours = new Set((rep && rep.issues ? rep.issues : []).map((i) => i.numero));
      presents = new Set([...ensemble].filter((n) => enCours.has(n)));
      if (presents.size === 0) break;
    } catch (e) { /* retenté au tour suivant, même principe que #951 */ }
  }
  return {
    arretees: [...ensemble].filter((n) => !presents.has(n)),
    nonArretees: [...presents],
  };
}

// Dépose la demande d'interruption CIBLÉE (#949) pour chaque numéro de
// `numeros` — best-effort, la vérification d'arrêt (attendreArretCibles)
// tranche de toute façon, même patron que fermerIssueInteractiveAvecAutres
// (static/js/app.js, #951).
async function demanderInterruptionCiblee(depot, numeros) {
  for (const numero of numeros) {
    try {
      await api.post('/demander-interruption-issue', { depot: depot, numero: Number(numero) }, { silencieux: true });
    } catch (e) { /* best-effort — attendreArretCibles tranche */ }
  }
}

// Issues actuellement en cours de `nom`, classées normales/interactives —
// titre et labels lus depuis le store du socle (déjà en mémoire, AUCUN
// appel GitHub supplémentaire — même contrainte que #951).
export async function recupererIssuesEnCoursClasseesProjet(nom) {
  const rep = await api.get('/issues-en-cours/' + encodeURIComponent(nom));
  const bruts = Array.isArray(rep && rep.issues) ? rep.issues : [];
  const enrichies = bruts.map((it) => {
    const issue = store.lireIssue(nom, it.numero);
    const labels = issue ? (issue.labels || []).map((l) => (l && l.name) || l || '') : [];
    return { numero: it.numero, mode: it.mode, titre: issue ? issue.title : '', labels: labels };
  });
  return classifierIssuesEnCoursProjet(enrichies);
}

// ─── Garde anti-double-clic (issue #954, point 4) — DISTINCTE de
// _interruptionsEnCours et _fermeturesEnCours (static/js/app.js, #748/#951) :
// un ensemble de noms de PROJET (ces actions portent sur le watcher entier
// d'un projet, pas sur une issue précise) partagé par les 4 boutons de
// niveau projet, pour qu'un clic sur l'un désactive aussi les autres pendant
// l'attente.
const _actionsProjetEnCours = new Set();

function demarrerActionProjet(nom) {
  if (_actionsProjetEnCours.has(nom)) return false;
  _actionsProjetEnCours.add(nom);
  return true;
}

function terminerActionProjet(nom) {
  _actionsProjetEnCours.delete(nom);
}

// Désactive/réactive visuellement les 4 boutons de niveau projet de `nom` —
// indicateur « ⏳ … » pendant l'attente (issue #954, point 4), même patron
// que _marquerFermetureEnCours (static/js/app.js, #951).
function marquerActionProjetEnCours(nom, active) {
  if (typeof document === 'undefined') return;
  const selecteurs = [
    '[data-action="pl-relancer-ccl"][data-projet="' + CSS.escape(nom) + '"]',
    '[data-action="pl-arreter-ccl"][data-projet="' + CSS.escape(nom) + '"]',
    '[data-action="pl-tout-interrompre-projet"][data-projet="' + CSS.escape(nom) + '"]',
    '[data-action="pl-interrompre-relancer"][data-projet="' + CSS.escape(nom) + '"]',
  ];
  selecteurs.forEach((selecteur) => {
    document.querySelectorAll(selecteur).forEach((bouton) => {
      bouton.disabled = active;
      if (active) {
        if (bouton.dataset.libelleAvantAttente === undefined) {
          bouton.dataset.libelleAvantAttente = bouton.textContent;
        }
        bouton.textContent = '⏳ …';
      } else if (bouton.dataset.libelleAvantAttente !== undefined) {
        bouton.textContent = bouton.dataset.libelleAvantAttente;
        delete bouton.dataset.libelleAvantAttente;
      }
    });
  });
}

async function rafraichirApresActionProjet() {
  if (typeof window === 'undefined') return;
  if (window.rafraichirPanneauLateralResultats) await window.rafraichirPanneauLateralResultats();
  await appelerAncien('chargerListeIssues');
}

// ─── « Tout interrompre pour ce projet » (issue #954, point 1) ────────────
export async function toutInterrompreProjet(nom, _btn) {
  if (!demarrerActionProjet(nom)) {
    toasts.avertissement('Une action est déjà en cours pour ce projet.');
    return;
  }
  marquerActionProjetEnCours(nom, true);
  try {
    const depot = appelerAncien('depotDuProjet', nom);
    if (!depot) {
      toasts.erreur('Dépôt GitHub introuvable pour le projet « ' + nom + ' ».');
      return;
    }
    const { normales, interactives } = await recupererIssuesEnCoursClasseesProjet(nom);
    if (!normales.length) {
      toasts.avertissement(interactives.length
        ? 'Aucune issue interrompable pour ce projet — seule(s) des issue(s) interactive(s) sont en '
          + 'cours (' + listeLibellesIssues(interactives) + '), utilisez le bouton « Interrompre » de '
          + 'leur ligne.'
        : 'Aucune issue en cours pour ce projet.');
      return;
    }
    const ok = await toasts.confirmer(messageToutInterrompreProjet(nom, normales, interactives),
      { titre: 'Tout interrompre', texteConfirmer: 'Tout interrompre' });
    if (!ok) return;

    const numeros = normales.map((it) => it.numero);
    await demanderInterruptionCiblee(depot, numeros);
    const { arretees, nonArretees } = await attendreArretCibles(nom, numeros);
    const resume = resumeArretCibles(arretees, nonArretees);
    if (resume.type === 'avertissement') toasts.avertissement(resume.texte);
    else toasts.succes(resume.texte);
    await rafraichirApresActionProjet();
  } finally {
    terminerActionProjet(nom);
    marquerActionProjetEnCours(nom, false);
  }
}

// ─── « Redémarrer le watcher » / « Interrompre et relancer (watcher CCL) »
// (issue #954, point 3) — même séquence pour les deux boutons. ────────────
export async function redemarrerWatcherAvecRelance(nom, _btn) {
  if (!demarrerActionProjet(nom)) {
    toasts.avertissement('Une action est déjà en cours pour ce projet.');
    return;
  }
  marquerActionProjetEnCours(nom, true);
  try {
    const depot = appelerAncien('depotDuProjet', nom);
    const { normales, interactives } = await recupererIssuesEnCoursClasseesProjet(nom);

    if (fautConfirmerActionProjet(normales, interactives)) {
      const ok = await toasts.confirmer(messageRedemarrerWatcherProjet(nom, normales, interactives),
        { titre: 'Redémarrer le watcher', texteConfirmer: 'Redémarrer' });
      if (!ok) return;
    }

    const numeros = normales.map((it) => it.numero);
    if (numeros.length) {
      if (!depot) {
        toasts.erreur('Dépôt GitHub introuvable pour le projet « ' + nom + ' » — redémarrage annulé.');
        return;
      }
      await demanderInterruptionCiblee(depot, numeros);
      const { nonArretees } = await attendreArretCibles(nom, numeros);
      if (nonArretees.length) {
        toasts.erreur('Redémarrage ANNULÉ : ' + nonArretees.length + ' issue(s) ne se sont pas arrêtée(s) '
          + 'à temps (#' + nonArretees.join(', #') + ') — le watcher n\'a pas été touché, rien n\'a été '
          + 'relancé. Réessayez.');
        return;
      }
    }

    let resultatRedemarrage;
    try {
      resultatRedemarrage = await api.post('/lancer-watcher',
        { projet: nom, relancer: true, issues_a_relancer: numeros });
    } catch (e) {
      return; // déjà signalé par api.post (toast) — état du watcher inchangé côté serveur
    }
    if (!resultatRedemarrage || !resultatRedemarrage.succes) {
      toasts.erreur('Échec du redémarrage : ' + ((resultatRedemarrage && resultatRedemarrage.erreur)
        || 'erreur inconnue.'));
      if (numeros.length) await api.post('/purger-issues-a-relancer', { projet: nom }, { silencieux: true });
      return;
    }
    if (resultatRedemarrage.differe) {
      toasts.avertissement('Redémarrage différé (une tâche tournait encore sur ce projet) — il sera fait '
        + 'automatiquement dès qu\'elle se termine. Les issues ciblées ne seront PAS relancées '
        + 'automatiquement : relancez-les vous-même depuis leur ligne une fois le watcher reparti.');
      if (numeros.length) await api.post('/purger-issues-a-relancer', { projet: nom }, { silencieux: true });
      await rafraichirApresActionProjet();
      return;
    }

    const relances = [];
    const echecs = [];
    for (const it of normales) {
      try {
        const rep = await api.post('/relancer-issue',
          { depot: depot, numero: it.numero, labels: it.labels || [] }, { silencieux: true });
        (rep && rep.succes && rep.statut_global !== 'echec' ? relances : echecs).push(it.numero);
      } catch (e) {
        echecs.push(it.numero);
      }
    }
    await api.post('/purger-issues-a-relancer', { projet: nom }, { silencieux: true });

    let texte = 'Watcher redémarré.';
    if (relances.length) texte += ' ' + relances.length + ' issue(s) relancée(s) automatiquement (#'
      + relances.join(', #') + ').';
    if (echecs.length) texte += ' ' + echecs.length + ' échec(s) de relance (#' + echecs.join(', #') + ') '
      + '— relancez-les depuis leur ligne.';
    toasts[echecs.length ? 'avertissement' : 'succes'](texte);
    await rafraichirApresActionProjet();
  } finally {
    terminerActionProjet(nom);
    marquerActionProjetEnCours(nom, false);
  }
}

// ─── « Arrêter » le watcher du projet (issue #954, point 3, enrichi) ──────
export async function arreterWatcherProjet(nom, _btn) {
  if (!demarrerActionProjet(nom)) {
    toasts.avertissement('Une action est déjà en cours pour ce projet.');
    return;
  }
  marquerActionProjetEnCours(nom, true);
  try {
    const depot = appelerAncien('depotDuProjet', nom);
    const { normales, interactives } = await recupererIssuesEnCoursClasseesProjet(nom);

    const ok = await toasts.confirmer(messageArreterWatcherProjet(nom, normales, interactives),
      { titre: 'Arrêter le watcher', texteConfirmer: 'Arrêter' });
    if (!ok) return;

    const numeros = normales.map((it) => it.numero);
    if (numeros.length) {
      if (!depot) {
        toasts.erreur('Dépôt GitHub introuvable pour le projet « ' + nom + ' » — arrêt annulé.');
        return;
      }
      await demanderInterruptionCiblee(depot, numeros);
      const { nonArretees } = await attendreArretCibles(nom, numeros);
      if (nonArretees.length) {
        toasts.erreur('Watcher NON arrêté : ' + nonArretees.length + ' issue(s) ne se sont pas arrêtée(s) '
          + 'à temps (#' + nonArretees.join(', #') + '). Réessayez.');
        return;
      }
    }

    let resultat;
    try {
      resultat = await api.post('/arreter-watcher', { projet: nom });
    } catch (e) {
      return; // déjà signalé par api.post (toast)
    }
    if (!resultat || !resultat.succes) {
      toasts.erreur('Échec de l\'arrêt : ' + ((resultat && resultat.message) || 'erreur inconnue.'));
      return;
    }
    let texte = 'Watcher arrêté.';
    if (numeros.length) texte += ' ' + numeros.length + ' issue(s) interrompue(s) proprement avant l\'arrêt.';
    if (interactives.length) texte += ' ' + interactives.length + ' issue(s) interactive(s) restent actives, '
      + 'non supervisées.';
    toasts.succes(texte);
    await rafraichirApresActionProjet();
  } finally {
    terminerActionProjet(nom);
    marquerActionProjetEnCours(nom, false);
  }
}
