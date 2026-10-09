// ccw.js — onglet CCW : pilotage du PC fixe Windows CCW et de ses projets
// depuis Linux, via les routes /ccw/* (SSH/SCP côté serveur) — sorti d'app.js
// (issue #649, refonte web, étape parallèle à #641/#642/#644 — ARCHITECTURE.md
// §6.7). Aucune valeur de token n'est jamais journalisée ni passée en argument :
// la sortie affichée provient des scripts distants, qui ne les affichent pas
// eux-mêmes — contrainte héritée d'app.js, INCHANGÉE ici.
//
// COUPLAGE AVEC LE PANNEAU LATÉRAL (rapport #632, préservé par #649)
//   panneau_lateral.js affiche la zone « Services CCW » et deux actions
//   contextuelles (Relancer/Nettoyer verrous) : il importe désormais ce module
//   DIRECTEMENT (obtenirCcwProjetsConnus, ccwChargerProjets, ccwRedemarrerProjet,
//   ccwNettoyerVerrous) au lieu de passer par le pont — les deux étant des
//   modules ES, l'import direct est plus simple et plus sûr (erreur de
//   compilation immédiate si un nom disparaît, plutôt qu'un warn silencieux au
//   runtime).
//
//   Le sens INVERSE (ce module → panneau latéral) reste, lui, sur le pont :
//   ccwChargerProjets doit déclencher rafraichirPanneauLateralResultats() après
//   avoir mis à jour ccwProjetsConnus (issue #375, aucun second polling SSH
//   côté panneau). Importer panneau_lateral.js ICI créerait un cycle d'imports
//   ES (panneau_lateral.js → ccw.js → panneau_lateral.js) : panneau_lateral.js
//   n'exporte d'ailleurs pas cette fonction (seulement `window.
//   rafraichirPanneauLateralResultats`, pour l'ancien app.js). On réutilise donc
//   ce global déjà publié via `appelerAncien(...)` — usage du pont dans le sens
//   module → module qu'il ne dessert normalement pas (voir socle/pont.js),
//   mais qui évite le cycle sans dupliquer la fonction.
//
// AUTRES POINTS D'ENTRÉE ENCORE APPELÉS PAR L'ANCIEN app.js (CLASSIQUE, ne peut
// pas importer ce module) — exposés en globales, même principe que
// panneau_lateral.js §6.4 :
//   - `ccwOuvrirOnglet` : initialisation de l'onglet, appelée par onglets.js via
//     le mécanisme générique `appelerAncien(fonction)` d'initialisationsPour('ccw')
//     (inchangé, ce mécanisme atteint aussi bien app.js qu'une globale publiée
//     par un module — voir static/js/tests/pont_globales.test.js).
//   - `ccwRedemarrerProjet` : appelée directement (bare call) par
//     interrompreEtRelancer() dans app.js (issue #381), pour relancer le
//     service CCW d'un projet for-windows après interruption.
//
// CE QUI N'EST PAS ICI : la case « Projet CCW » de la modale Nouveau projet
// (bootstrap initial, npCcw*) reste dans app.js — fonctionnalité distincte
// (création), non couverte par cette étape (voir VERIFICATIONS_MANUELLES.md,
// sections « Onglet CCW » et « Nouveau projet » séparées).

import { api } from './socle/api.js';
import { toasts } from './socle/toasts.js';
import * as dom from './socle/dom.js';
import { appelerAncien } from './socle/pont.js';

// ─────────────────────────────────────────────────────────────────────────────
// LOGIQUE PURE (testée sous Node — voir static/js/tests/ccw.test.js)
//    Aucune dépendance au DOM ni au réseau.
// ─────────────────────────────────────────────────────────────────────────────

// Couleur de l'état d'un service CCW (colonne État du tableau).
export function couleurEtatCcw(etat) {
  return etat === 'running' ? '#2e8b57' : etat === 'stopped' ? '#c0392b' : '#888';
}

// Texte + couleur du statut du TOPIC_NTFY (colonne TOPIC_NTFY du tableau).
export function libelleTopicCcw(topicStatut) {
  if (topicStatut === 'placeholder') return { texte: '⚠ à définir', couleur: '#e0a800' };
  if (topicStatut === 'ok') return { texte: '✓ renseigné', couleur: '#2e8b57' };
  return { texte: '? inconnu', couleur: '#888' };
}

// Faut-il afficher le bouton « Démarrer » / « Arrêter » pour ce service, selon
// son état courant (issue #203 : indépendants du bouton Redémarrer).
export function afficherBoutonDemarrer(etat) { return etat !== 'running'; }
export function afficherBoutonArreter(etat) { return etat !== 'stopped'; }

// Sélection à restaurer dans le <select> « Finaliser » après un rechargement de
// la liste : la sélection précédente si le projet existe toujours, sinon vide
// (placeholder) — ne jamais garder la sélection d'un projet disparu.
export function selectionRestauree(noms, selectionCourante) {
  return noms.includes(selectionCourante) ? selectionCourante : '';
}

// Plan d'exécution de « Poser ce jeton Claude sur tous les services » (issue
// #743, point 4) : pour chaque projet connu, décide s'il faut le traiter
// (action 'poser') ou le sauter (action 'sauter', jamais redémarré de force).
//   - resumeParProjet : { <projet>: {enCours, enFile} | null | undefined } —
//     même forme que appelerAncien('resumeProjetMonitoring', projet), DÉJÀ
//     calculée en mémoire par l'interface (aucun fetch réseau supplémentaire
//     ici) ;
//   - continuerIndetermines : true si l'appelant a déjà obtenu une
//     confirmation explicite pour les projets dont l'état n'est pas
//     déterminable (resume absent/non numérique) — sans cette confirmation,
//     ils sont sautés par précaution plutôt que redémarrés à l'aveugle.
export function planifierPoseTokenTous(projets, resumeParProjet, continuerIndetermines) {
  return projets.map(function(p) {
    const resume = resumeParProjet ? resumeParProjet[p.projet] : null;
    const determinable = !!resume && typeof resume.enCours === 'number';
    if (determinable && resume.enCours > 0) {
      return { projet: p.projet, action: 'sauter', indetermine: false,
               raison: 'occupé (' + resume.enCours + ' issue(s) en cours)' };
    }
    if (!determinable && !continuerIndetermines) {
      return { projet: p.projet, action: 'sauter', indetermine: true,
               raison: 'état « en cours » indéterminable, non confirmé' };
    }
    return { projet: p.projet, action: 'poser', indetermine: !determinable, raison: '' };
  });
}

// Décompte par statut d'un résumé « Poser ce jeton Claude sur tous les
// services » — un élément par service, {projet, statut, detail}, statut dans
// {'OK', 'à vérifier', 'échec', 'sauté'}.
export function resumerResultatsPoseTokenTous(resultats) {
  const compte = { OK: 0, 'à vérifier': 0, 'échec': 0, 'sauté': 0 };
  resultats.forEach(function(r) {
    if (Object.prototype.hasOwnProperty.call(compte, r.statut)) compte[r.statut]++;
  });
  return compte;
}

// ─────────────────────────────────────────────────────────────────────────────
// ÉTAT PARTAGÉ (issue #375) : dernière liste connue des services CCW, lue par
// le panneau latéral (import direct, voir en-tête) — jamais interrogée
// directement par lui (pas de second polling des appels SSH coûteux).
// ─────────────────────────────────────────────────────────────────────────────
let ccwProjetsConnus = [];

export function obtenirCcwProjetsConnus() {
  return ccwProjetsConnus;
}

// ─────────────────────────────────────────────────────────────────────────────
// RENDU / DOM
// ─────────────────────────────────────────────────────────────────────────────

// Affiche un message (succès/erreur/avertissement) dans un élément .message.
function ccwMessage(idEl, texte, type) {
  const el = document.getElementById(idEl);
  if (!el) return;
  el.textContent = texte || '';
  el.className = 'message' + (type ? ' ' + type : '');
  el.style.display = texte ? 'block' : 'none';
}

// Affiche la sortie brute d'un script distant dans le terminal CCW commun.
function ccwAfficherSortie(sortie) {
  const term = document.getElementById('ccw-sortie');
  if (!term) return;
  if (sortie && sortie.trim()) {
    term.textContent = sortie;
    term.style.display = 'block';
  } else {
    term.textContent = '';
    term.style.display = 'none';
  }
}

// Active/désactive un bouton pendant une opération longue (SSH).
function ccwOccupe(idBtn, occupe, labelOccupe) {
  const b = document.getElementById(idBtn);
  if (!b) return;
  if (occupe) {
    b.dataset.label = b.dataset.label || b.textContent;
    b.textContent = labelOccupe || 'Patientez…';
    b.disabled = true;
  } else {
    if (b.dataset.label) b.textContent = b.dataset.label;
    b.disabled = false;
  }
}

// Ouverture de l'onglet : liste des projets (le PC fixe est toujours allumé,
// plus d'état de VM à vérifier — issue #447). Appelée via le pont par
// onglets.js (voir en-tête).
export function ccwOuvrirOnglet() {
  ccwChargerProjets();
}

function rendreLigneProjetCcw(p) {
  const topic = libelleTopicCcw(p.topicStatut);
  return '<tr style="border-bottom:1px solid #f2f2f0;cursor:pointer"'
    + ' data-action="ccw-preselectionner" data-projet="' + dom.echapperHtml(p.projet) + '"'
    + ' title="Cliquer pour pré-sélectionner ce projet dans « Finaliser »">'
    + '<td style="padding:8px 12px;font-size:13px">' + dom.echapperHtml(p.projet)
      + (p.base ? ' <span style="color:#aaa;font-size:11px">(base)</span>' : '') + '</td>'
    + '<td style="padding:8px 12px;font-size:12px;color:#777;font-family:monospace">'
      + dom.echapperHtml(p.service) + '</td>'
    + '<td style="padding:8px 12px;font-size:13px;color:' + couleurEtatCcw(p.etat) + '">'
      + dom.echapperHtml(p.etat || '—') + '</td>'
    + '<td style="padding:8px 12px;font-size:13px"><span style="color:' + topic.couleur + '">'
      + topic.texte + '</span></td>'
    // Actions par ligne : « Redémarrer » (issue #180) toujours dispo, plus
    // « Démarrer » / « Arrêter » indépendants (issue #203) affichés selon
    // l'état — Démarrer seulement si stopped, Arrêter seulement si running,
    // comme pour les watchers Linux. Délégation (dom.surAction, voir
    // installerDelegationCcw) : chaque bouton porte son propre data-action, le
    // gestionnaire de la ligne (ccw-preselectionner) ignore les clics dont la
    // cible est un <button> (voir installerDelegationCcw).
    + '<td style="padding:8px 12px;white-space:nowrap">'
      + '<button data-action="ccw-redemarrer" data-projet="' + dom.echapperHtml(p.projet) + '"'
      + ' style="font-size:12px;padding:4px 10px">Redémarrer</button>'
      + (afficherBoutonDemarrer(p.etat)
          ? ' <button data-action="ccw-demarrer" data-projet="' + dom.echapperHtml(p.projet) + '"'
            + ' style="font-size:12px;padding:4px 10px">Démarrer</button>'
          : '')
      + (afficherBoutonArreter(p.etat)
          ? ' <button data-action="ccw-arreter" data-projet="' + dom.echapperHtml(p.projet) + '"'
            + ' style="font-size:12px;padding:4px 10px">Arrêter</button>'
          : '')
      + '</td>'
    + '</tr>';
}

export async function ccwChargerProjets() {
  const corps = document.getElementById('ccw-corps-projets');
  const selectFin = document.getElementById('ccw-fin-nom');
  ccwMessage('ccw-msg-projets', 'Interrogation du PC fixe…', '');
  corps.innerHTML = '';
  let j;
  try {
    j = await api.get('/ccw/projets', { silencieux: true });
  } catch (e) {
    ccwMessage('ccw-msg-projets', 'Erreur réseau : ' + e.message, 'erreur');
    return;
  }
  if (!j.succes) {
    ccwMessage('ccw-msg-projets', j.erreur || 'Erreur inconnue.', 'erreur');
    return;
  }
  const projets = j.projets || [];
  // Seul point d'écriture de ccwProjetsConnus (issue #375) : le panneau
  // latéral de l'onglet Résultats lit cette variable sans jamais fetcher
  // /ccw/projets lui-même (pas de second polling des appels SSH).
  ccwProjetsConnus = projets;
  appelerAncien('rafraichirPanneauLateralResultats');
  // Mémorise la sélection courante pour la restaurer si le projet existe encore.
  const selectionCourante = selectFin ? selectFin.value : '';
  if (projets.length === 0) {
    ccwMessage('ccw-msg-projets', 'Aucun service CCW-Watcher* enregistré sur le PC fixe.', '');
    if (selectFin)
      selectFin.innerHTML = '<option value="" disabled selected>-- Choisir un projet --</option>';
    return;
  }
  ccwMessage('ccw-msg-projets', '', '');
  corps.innerHTML = projets.map(rendreLigneProjetCcw).join('');
  // Alimente le <select> du formulaire « Finaliser » : seuls les projets
  // réellement listés ci-dessus sont sélectionnables (plus de saisie libre).
  if (selectFin) {
    const noms = projets.map(function(p) { return p.projet; });
    selectFin.innerHTML = '<option value="" disabled>-- Choisir un projet --</option>'
      + projets.map(function(p) {
          return '<option value="' + dom.echapperHtml(p.projet) + '">'
               + dom.echapperHtml(p.projet) + '</option>';
        }).join('');
    selectFin.value = selectionRestauree(noms, selectionCourante);
  }
}

// Remet à zéro les trois champs de la section « Finaliser » (topic + les deux
// tokens) : après une soumission (succès ou échec, les tokens ne doivent
// jamais rester affichés en clair) ou dès que le projet sélectionné change
// (issue #666 — sinon un token resté affiché pour l'ancien projet pourrait
// être posé par erreur sur le nouveau si Alain clique « Finaliser » sans
// remarquer le changement).
export function ccwViderChampsFinalisation() {
  document.getElementById('ccw-fin-topic').value = '';
  document.getElementById('ccw-fin-gh').value    = '';
  document.getElementById('ccw-fin-oauth').value = '';
}

// Confort : un clic sur une ligne du tableau « Projets CCW existants »
// pré-sélectionne ce projet dans le <select> de la section « Finaliser ».
function ccwPreselectionnerProjet(nom) {
  const selectFin = document.getElementById('ccw-fin-nom');
  if (!selectFin) return;
  // Ne sélectionne que si l'option existe réellement dans le <select>.
  const options = selectFin.options;
  for (let i = 0; i < options.length; i++) {
    if (options[i].value === nom) {
      selectFin.value = nom;
      ccwViderChampsFinalisation();
      break;
    }
  }
}

// Redémarre le service d'un projet CCW (issue #180) : simple « nssm restart »
// côté VM, sans reposer topic ni tokens. Le bouton passé (btn) est désactivé le
// temps de l'opération. Résultat affiché dans le bandeau + le terminal communs.
export async function ccwRedemarrerProjet(nom, btn) {
  if (!nom) return;
  const ok = await toasts.confirmer(
    'Redémarrer le service du projet « ' + nom + ' » ?\n\n'
    + '(Redémarrage simple : ni le TOPIC_NTFY ni les tokens ne sont modifiés.)',
    { texteConfirmer: 'Redémarrer' });
  if (!ok) return;
  const labelInitial = btn ? btn.textContent : null;
  if (btn) { btn.disabled = true; btn.textContent = 'Redémarrage…'; }
  ccwMessage('ccw-message', 'Redémarrage du service de « ' + nom + ' » sur le PC fixe…', '');
  ccwAfficherSortie('');
  try {
    const j = await api.post('/ccw/redemarrer-projet', { nom: nom }, { silencieux: true });
    ccwAfficherSortie(j.sortie);
    if (j.succes) {
      ccwMessage('ccw-message',
        'Service « ' + (j.service || nom) + ' » redémarré.', 'succes');
    } else {
      ccwMessage('ccw-message', j.erreur || 'Échec du redémarrage.', 'erreur');
    }
    ccwChargerProjets();
  } catch (e) {
    ccwMessage('ccw-message', 'Erreur réseau : ' + e.message, 'erreur');
  } finally {
    if (btn) { btn.disabled = false; if (labelInitial !== null) btn.textContent = labelInitial; }
  }
}

// Démarre le service d'un projet CCW (issue #203) : « nssm start » côté VM,
// contrôle indépendant du redémarrage. Même pattern que ccwRedemarrerProjet.
async function ccwDemarrerProjet(nom, btn) {
  if (!nom) return;
  const labelInitial = btn ? btn.textContent : null;
  if (btn) { btn.disabled = true; btn.textContent = 'Démarrage…'; }
  ccwMessage('ccw-message', 'Démarrage du service de « ' + nom + ' » sur le PC fixe…', '');
  ccwAfficherSortie('');
  try {
    const j = await api.post('/ccw/demarrer-projet', { nom: nom }, { silencieux: true });
    ccwAfficherSortie(j.sortie);
    if (j.succes) {
      ccwMessage('ccw-message',
        'Service « ' + (j.service || nom) + ' » démarré.', 'succes');
    } else {
      ccwMessage('ccw-message', j.erreur || 'Échec du démarrage.', 'erreur');
    }
    ccwChargerProjets();
  } catch (e) {
    ccwMessage('ccw-message', 'Erreur réseau : ' + e.message, 'erreur');
  } finally {
    if (btn) { btn.disabled = false; if (labelInitial !== null) btn.textContent = labelInitial; }
  }
}

// Arrête le service d'un projet CCW (issue #203) : « nssm stop » côté VM, pour
// libérer des ressources sans le relancer aussitôt. Confirmation demandée.
async function ccwArreterProjet(nom, btn) {
  if (!nom) return;
  const ok = await toasts.confirmer(
    'Arrêter le service du projet « ' + nom + ' » ?\n\n'
    + '(Le service restera arrêté jusqu\'à un « Démarrer » ou « Redémarrer ».)',
    { texteConfirmer: 'Arrêter' });
  if (!ok) return;
  const labelInitial = btn ? btn.textContent : null;
  if (btn) { btn.disabled = true; btn.textContent = 'Arrêt…'; }
  ccwMessage('ccw-message', 'Arrêt du service de « ' + nom + ' » sur le PC fixe…', '');
  ccwAfficherSortie('');
  try {
    const j = await api.post('/ccw/arreter-projet', { nom: nom }, { silencieux: true });
    ccwAfficherSortie(j.sortie);
    if (j.succes) {
      ccwMessage('ccw-message',
        'Service « ' + (j.service || nom) + ' » arrêté.', 'succes');
    } else {
      ccwMessage('ccw-message', j.erreur || 'Échec de l\'arrêt.', 'erreur');
    }
    ccwChargerProjets();
  } catch (e) {
    ccwMessage('ccw-message', 'Erreur réseau : ' + e.message, 'erreur');
  } finally {
    if (btn) { btn.disabled = false; if (labelInitial !== null) btn.textContent = labelInitial; }
  }
}

// Nettoie les verrous CCW orphelins d'un projet (issue #431, prévu par #378) :
// arrête le service, supprime tous les .lock de son dossier de verrous, puis
// relance — en un seul appel serveur (/ccw/nettoyer-verrous). Cas d'usage :
// un verrou orphelin bloque le watcher CCW sans issue précise à interrompre
// (à la différence du bouton « Interrompre l'issue », qui exige une issue
// ouverte). Même pattern que ccwRedemarrerProjet/ccwArreterProjet, utilisé
// depuis le panneau latéral (#pl-zone-actions, import direct — voir en-tête) :
// la zone #ccw-message de l'onglet CCW n'y existe pas, ccwMessage()/
// ccwAfficherSortie() y sont donc des no-op silencieux — le retour visuel se
// fait via le libellé du bouton.
export async function ccwNettoyerVerrous(nom, btn) {
  if (!nom) return;
  const ok = await toasts.confirmer(
    'Nettoyer les verrous CCW du projet « ' + nom + ' » ?\n\n'
    + 'Le service sera ARRÊTÉ, tous les fichiers .lock de son dossier de '
    + 'verrous seront supprimés, puis le service sera relancé.',
    { texteConfirmer: 'Nettoyer' });
  if (!ok) return;
  const labelInitial = btn ? btn.textContent : null;
  if (btn) { btn.disabled = true; btn.textContent = 'Nettoyage…'; }
  ccwMessage('ccw-message', 'Nettoyage des verrous de « ' + nom + ' » sur le PC fixe…', '');
  ccwAfficherSortie('');
  try {
    const j = await api.post('/ccw/nettoyer-verrous', { nom: nom }, { silencieux: true });
    ccwAfficherSortie(j.sortie);
    if (j.statut === 'succes') {
      ccwMessage('ccw-message', j.message || 'Verrous nettoyés, service relancé.', 'succes');
      toasts.succes(j.message || 'Verrous nettoyés, service relancé.');
    } else {
      ccwMessage('ccw-message', j.message || 'Échec du nettoyage des verrous.', 'erreur');
      toasts.erreur(j.message || 'Échec du nettoyage des verrous CCW.');
    }
    ccwChargerProjets();
  } catch (e) {
    ccwMessage('ccw-message', 'Erreur réseau : ' + e.message, 'erreur');
    toasts.erreur('Erreur réseau : ' + e.message);
  } finally {
    if (btn) { btn.disabled = false; if (labelInitial !== null) btn.textContent = labelInitial; }
  }
}

async function ccwAjouterProjet() {
  const nom   = document.getElementById('ccw-add-nom').value.trim();
  const depot = document.getElementById('ccw-add-depot').value.trim();
  if (!nom || !depot) {
    ccwMessage('ccw-message', 'Nom du projet et dépôt requis.', 'erreur');
    return;
  }
  ccwOccupe('ccw-btn-ajouter', true, 'Création…');
  ccwMessage('ccw-message', 'Création du projet sur le PC fixe (clone + config + service)…', '');
  ccwAfficherSortie('');
  try {
    const j = await api.post('/ccw/ajouter-projet', { nom: nom, depot: depot }, { silencieux: true });
    ccwAfficherSortie(j.sortie);
    if (j.succes) {
      ccwMessage('ccw-message', 'Projet « ' + nom + ' » ajouté. Finalisez-le ci-dessous (TOPIC_NTFY + tokens).', 'succes');
      ccwChargerProjets();
    } else {
      ccwMessage('ccw-message', j.erreur || 'Échec de la création.', 'erreur');
    }
  } catch (e) {
    ccwMessage('ccw-message', 'Erreur réseau : ' + e.message, 'erreur');
  } finally {
    ccwOccupe('ccw-btn-ajouter', false);
  }
}

async function ccwFinaliserProjet() {
  const nom   = document.getElementById('ccw-fin-nom').value.trim();
  const topic = document.getElementById('ccw-fin-topic').value.trim();
  const gh    = document.getElementById('ccw-fin-gh').value;
  const oauth = document.getElementById('ccw-fin-oauth').value;
  if (!nom) {
    ccwMessage('ccw-message', 'Choisissez un projet dans la liste déroulante.', 'erreur');
    return;
  }
  if (!gh && !oauth) {
    ccwMessage('ccw-message',
      'Au moins un des deux tokens (GH_TOKEN ou CLAUDE_CODE_OAUTH_TOKEN) est requis — '
      + 'laissez l\'autre champ vide pour conserver sa valeur actuelle.', 'erreur');
    return;
  }
  // Issue #743 : un champ laissé vide conserve la valeur actuelle de CE
  // token sur le service (lue côté PC fixe, jamais ici) — message de
  // confirmation adapté selon ce qui est effectivement fourni.
  const quoiToken = (gh && oauth) ? 'les deux tokens'
    : gh ? 'le token GH_TOKEN (CLAUDE_CODE_OAUTH_TOKEN conservé tel quel)'
         : 'le token CLAUDE_CODE_OAUTH_TOKEN (GH_TOKEN conservé tel quel)';
  const ok = await toasts.confirmer(
    'Finaliser « ' + nom + ' » : écrire TOPIC_NTFY et poser ' + quoiToken
    + ' sur le service, puis le redémarrer ?',
    { texteConfirmer: 'Finaliser' });
  if (!ok) return;
  ccwOccupe('ccw-btn-finaliser', true, 'Finalisation…');
  ccwMessage('ccw-message', 'Finalisation en cours (topic + tokens + redémarrage du service)…', '');
  ccwAfficherSortie('');
  try {
    const j = await api.post('/ccw/finaliser-projet',
      { nom: nom, topic: topic, gh_token: gh, oauth_token: oauth }, { silencieux: true });
    ccwAfficherSortie(j.sortie);
    if (j.succes && !j.avertissement) {
      ccwMessage('ccw-message', 'Projet « ' + nom + ' » finalisé : tokens posés, service redémarré.', 'succes');
    } else if (j.avertissement) {
      ccwMessage('ccw-message', j.erreur || 'Appliqué, mais à vérifier.', 'avertissement');
    } else {
      ccwMessage('ccw-message', j.erreur || 'Échec de la finalisation.', 'erreur');
    }
    // Effacer topic + tokens dès la réponse reçue (ne pas les laisser affichés).
    ccwViderChampsFinalisation();
    ccwChargerProjets();
  } catch (e) {
    ccwMessage('ccw-message', 'Erreur réseau : ' + e.message, 'erreur');
    ccwViderChampsFinalisation();
  } finally {
    ccwOccupe('ccw-btn-finaliser', false);
  }
}

// Affiche le résumé par service de « Poser ce jeton Claude sur tous les
// services » (issue #743, point 3) — une ligne par projet, jamais de valeur
// de token (seulement projet/statut/detail, tous non sensibles).
function ccwAfficherResumeTousServices(resultats) {
  const zone = document.getElementById('ccw-tous-resume');
  if (!zone) return;
  if (!resultats.length) { zone.innerHTML = ''; zone.style.display = 'none'; return; }
  const couleur = { OK: '#2e8b57', 'à vérifier': '#e0a800', 'échec': '#c0392b', 'sauté': '#888' };
  const icone   = { OK: '✓', 'à vérifier': '⚠', 'échec': '✗', 'sauté': '⏭' };
  zone.innerHTML = resultats.map(function(r) {
    return '<div style="padding:3px 0;font-size:13px">'
      + '<span style="color:' + (couleur[r.statut] || '#888') + '">'
      + (icone[r.statut] || '?') + ' ' + dom.echapperHtml(r.statut) + '</span>'
      + ' — ' + dom.echapperHtml(r.projet)
      + (r.detail ? ' <span style="color:#999">(' + dom.echapperHtml(r.detail) + ')</span>' : '')
      + '</div>';
  }).join('');
  zone.style.display = 'block';
}

// « Poser ce jeton Claude sur tous les services CCW » (issue #743, point 3) :
// une seule saisie du jeton Claude, appliquée à chaque service CCW-Watcher*
// connu, en conservant le jeton GitHub propre à chacun — en RÉUTILISANT la
// route /ccw/finaliser-projet existante (sans gh_token ni topic, reconduits/
// ignorés côté serveur, voir ccw_finaliser_projet), un appel SÉQUENTIEL par
// service (jamais de redémarrages concurrents sur le PC fixe). Un service
// occupé (point 4 : réutilise resumeProjetMonitoring, déjà en mémoire côté
// app.js — aucun fetch réseau supplémentaire) est sauté et signalé dans le
// résumé, jamais redémarré de force ; si son état n'est pas déterminable,
// une confirmation explicite est demandée avant de le traiter malgré tout.
async function ccwPoserTokenTousLesServices() {
  const champOauth = document.getElementById('ccw-tous-oauth');
  const oauth = champOauth ? champOauth.value : '';
  if (!oauth) {
    ccwMessage('ccw-message', 'Le jeton CLAUDE_CODE_OAUTH_TOKEN est requis.', 'erreur');
    return;
  }
  const projets = obtenirCcwProjetsConnus() || [];
  if (!projets.length) {
    ccwMessage('ccw-message', 'Aucun service CCW connu — rafraîchissez la liste des projets.', 'erreur');
    return;
  }
  const ok = await toasts.confirmer(
    'Poser ce jeton Claude (CLAUDE_CODE_OAUTH_TOKEN) sur les ' + projets.length
    + ' service(s) CCW-Watcher* listé(s) ci-dessus, en conservant le jeton GitHub propre '
    + 'à chacun, et redémarrer chaque service non occupé ?',
    { texteConfirmer: 'Poser sur tous' });
  if (!ok) { if (champOauth) champOauth.value = ''; return; }

  const resumeParProjet = {};
  projets.forEach(function(p) { resumeParProjet[p.projet] = appelerAncien('resumeProjetMonitoring', p.projet); });

  let plan = planifierPoseTokenTous(projets, resumeParProjet, false);
  const indetermines = plan.filter(function(e) { return e.indetermine && e.action === 'sauter'; })
                            .map(function(e) { return e.projet; });
  if (indetermines.length) {
    const continuer = await toasts.confirmer(
      'État « en cours » non déterminable pour : ' + indetermines.join(', ') + '.\n\n'
      + 'Continuer malgré tout avec ce(s) service(s) (redémarrage possible pendant une '
      + 'tâche en cours) ?',
      { texteConfirmer: 'Continuer quand même' });
    plan = planifierPoseTokenTous(projets, resumeParProjet, continuer);
  }

  ccwOccupe('ccw-btn-tous', true, 'Pose en cours…');
  ccwMessage('ccw-message', 'Pose du jeton Claude sur ' + projets.length + ' service(s)…', '');
  ccwAfficherSortie('');
  ccwAfficherResumeTousServices([]);
  const resultats = [];
  for (const etape of plan) {
    if (etape.action === 'sauter') {
      resultats.push({ projet: etape.projet, statut: 'sauté', detail: etape.raison });
      continue;
    }
    try {
      const j = await api.post('/ccw/finaliser-projet',
        { nom: etape.projet, topic: '', oauth_token: oauth }, { silencieux: true });
      if (j.succes && !j.avertissement) {
        resultats.push({ projet: etape.projet, statut: 'OK', detail: '' });
      } else if (j.avertissement) {
        resultats.push({ projet: etape.projet, statut: 'à vérifier', detail: j.erreur || '' });
      } else {
        resultats.push({ projet: etape.projet, statut: 'échec', detail: j.erreur || 'Échec.' });
      }
    } catch (e) {
      resultats.push({ projet: etape.projet, statut: 'échec', detail: 'Erreur réseau : ' + e.message });
    }
  }
  if (champOauth) champOauth.value = '';   // jamais réaffiché, même en cas d'échec partiel.
  ccwOccupe('ccw-btn-tous', false);
  ccwAfficherResumeTousServices(resultats);
  const compte = resumerResultatsPoseTokenTous(resultats);
  ccwMessage('ccw-message',
    'Pose terminée : ' + compte.OK + ' OK, ' + compte['à vérifier'] + ' à vérifier, '
    + compte['échec'] + ' échec(s), ' + compte['sauté'] + ' sauté(s).',
    compte['échec'] ? 'erreur' : (compte['à vérifier'] ? 'avertissement' : 'succes'));
  ccwChargerProjets();
}

// ─── Délégation d'événements (remplace les onclick= inline, §6.7 étape 2) ──
// La ligne (ccw-preselectionner) ignore les clics dont la cible est un
// <button> : ces clics sont déjà pris en charge par la règle du bouton
// concerné — la délégation du socle (un seul écouteur par type d'événement,
// voir socle/dom.js) ne rejoue pas la bulle DOM entre règles, donc
// event.stopPropagation() (utilisé par l'ancien code à onclick= inline) n'a
// ici aucun effet sur les AUTRES règles déjà enregistrées : c'est cette garde
// explicite qui les rend mutuellement exclusives.
function installerDelegationCcw() {
  dom.surAction('[data-action="ccw-rafraichir"]', 'click', () => ccwChargerProjets());
  dom.surAction('[data-action="ccw-ajouter"]', 'click', () => ccwAjouterProjet());
  dom.surAction('[data-action="ccw-finaliser"]', 'click', () => ccwFinaliserProjet());
  dom.surAction('[data-action="ccw-tous"]', 'click', () => ccwPoserTokenTousLesServices());

  dom.surAction('[data-action="ccw-preselectionner"]', 'click', (e, el) => {
    if (e.target.closest('button')) return;
    ccwPreselectionnerProjet(el.dataset.projet);
  });
  // Sélection directe dans le menu déroulant (issue #666) : même remise à
  // zéro que la préselection par clic sur une ligne, ci-dessus.
  dom.surAction('#ccw-fin-nom', 'change', () => ccwViderChampsFinalisation());
  dom.surAction('[data-action="ccw-redemarrer"]', 'click',
    (e, el) => ccwRedemarrerProjet(el.dataset.projet, el));
  dom.surAction('[data-action="ccw-demarrer"]', 'click',
    (e, el) => ccwDemarrerProjet(el.dataset.projet, el));
  dom.surAction('[data-action="ccw-arreter"]', 'click',
    (e, el) => ccwArreterProjet(el.dataset.projet, el));
}

/** Point d'entrée, appelé une fois par index.js. */
export function initialiserCcw() {
  installerDelegationCcw();
  // Globales encore appelées par l'ancien app.js (classique, ne peut pas
  // importer ce module) — voir en-tête pour le détail de chaque appelant.
  window.ccwOuvrirOnglet = ccwOuvrirOnglet;
  window.ccwRedemarrerProjet = ccwRedemarrerProjet;
}
