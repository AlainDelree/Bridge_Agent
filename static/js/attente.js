// attente.js — onglet « En attente » : issues mises de côté par le champ
// d'en-tête ATTENTE avant leur création (issue #713, interface issue #714).
//
// RESPONSABILITÉ
//   Liste des éléments de issues_inbox/en_attente/ (GET /issues-attente),
//   actions « Lancer » (POST /issues-attente/lancer) et « Supprimer » (POST
//   /issues-attente/supprimer, après confirmation — suppression définitive,
//   aucun archivage). Alain seul juge si la CONDITION affichée est remplie :
//   « Lancer » ne vérifie rien (hors périmètre de cette issue, cf. le corps
//   de l'issue #714) ; l'issue lancée rejoint ensuite le circuit normal et
//   apparaît dans Résultats par le chemin habituel (création, événement SSE
//   creation_issue) — pas de changement d'onglet automatique ici.
//
// BADGE — compteur suivant le sondage déjà en place (issue #705 : une mise à
// jour uniquement par événements peut être manquée). static/js/resultats.js
// pousse déjà nb_en_attente (issue #713, GET /issues-inbox/etat) dans
// store.issuesInbox.nbEnAttente à chaque cycle de rafraichirInbox() ; ce
// module s'y abonne pour mettre à jour le badge et, si l'onglet « En attente »
// est actuellement ouvert, recharger la liste dès que ce compteur change —
// aucun polling dédié supplémentaire.
//
// INITIALISATION : initAttente() est appelée une fois par index.js (import
// direct, comme initJournal()/initialiserCcw()) ; elle installe la
// délégation des boutons Lancer/Supprimer et les deux abonnements au store
// (activation de l'onglet, compteur en_attente). Pas d'entrée dans
// onglets.js::initialisationsPour — ce module réagit directement à
// store.ongletActif, comme resultats.js (issue #632).

import { store } from './socle/store.js';
import { api } from './socle/api.js';
import { toasts } from './socle/toasts.js';
import * as dom from './socle/dom.js';
import { appelerAncien } from './socle/pont.js';

// ─────────────────────────────────────────────────────────────────────────────
// LOGIQUE PURE (testée sous Node — voir static/js/tests/attente.test.js)
//    Aucune dépendance au DOM ni au réseau.
// ─────────────────────────────────────────────────────────────────────────────

/** "JJ/MM/AAAA HH:MM" en heure locale, à partir d'un objet Date (pas d'un
 *  epoch — la conversion epoch→Date reste à l'appelant, cf. descriptionLigneAttente
 *  ci-dessous) ; chaîne vide si `dateObj` est absent/falsy. */
export function formaterDateAttente(dateObj) {
  if (!dateObj) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return pad(dateObj.getDate()) + '/' + pad(dateObj.getMonth() + 1) + '/' + dateObj.getFullYear()
       + ' ' + pad(dateObj.getHours()) + ':' + pad(dateObj.getMinutes());
}

// Faut-il afficher le badge « nombre d'éléments en attente » sur l'onglet
// (issue #714, § tâche demandée : visible seulement si > 0, rien d'affiché
// sinon). Logique pure, testée sous Node.
export function decisionBadgeAttente(nb) {
  const n = Number(nb) || 0;
  return n > 0 ? { afficher: true, texte: String(n) } : { afficher: false, texte: '' };
}

// Descriptif d'affichage d'une ligne (titre/projet/date/condition), avec les
// replis explicites demandés par l'issue (titre/condition jamais vides à
// l'écran). `item` = {id, titre, projet, date, condition} tel que renvoyé par
// GET /issues-attente (voir app/issues_inbox.py::_lire_item_attente).
export function descriptionLigneAttente(item) {
  const it = item || {};
  return {
    titre: it.titre || '(sans titre)',
    projet: it.projet || '',
    date: formaterDateAttente(it.date ? new Date(it.date * 1000) : null),
    condition: it.condition || '(condition non précisée)',
  };
}

// Interprète l'échec d'un appel /issues-attente/lancer ou /supprimer : ces
// deux routes renvoient un statut HTTP non-2xx sur erreur (400/404/500, voir
// app/issues_inbox.py), donc api.post() lève une ErreurApi dont `.corps` est
// le texte brut de la réponse (JSON ici) — on y relit le champ `erreur` posé
// par le serveur ; à défaut (corps non-JSON, absent) on retombe sur `repli`.
// Logique pure, testée sous Node.
export function messageEchecAttente(erreurApi, repli) {
  if (erreurApi && erreurApi.corps) {
    try {
      const corps = JSON.parse(erreurApi.corps);
      if (corps && corps.erreur) return corps.erreur;
    } catch (e) { /* corps non-JSON : repli */ }
  }
  return repli;
}

// ─────────────────────────────────────────────────────────────────────────────
// RENDU DOM
// ─────────────────────────────────────────────────────────────────────────────

function zoneListe() {
  return document.getElementById('attente-liste');
}

function construireLigneDOM(item) {
  const desc = descriptionLigneAttente(item);
  const couleur = appelerAncien('couleurProjet', item.projet) || '#888';
  const div = document.createElement('div');
  div.className = 'ligne-attente';
  div.dataset.id = item.id;
  div.innerHTML =
    '<div class="attente-entete">'
    + '<span class="pastille-ligne" style="background:' + couleur + '"></span>'
    + '<span class="attente-titre"></span>'
    + '<span class="attente-projet"></span>'
    + '<span class="attente-date"></span>'
    + '</div>'
    + '<div class="attente-condition"></div>'
    + '<div class="attente-actions">'
    + '<button class="primaire" data-action="attente-lancer">Lancer</button>'
    + '<button class="danger" data-action="attente-supprimer">Supprimer</button>'
    + '</div>';
  // Texte posé via textContent (jamais innerHTML) : titre/projet/condition
  // viennent du contenu d'un fichier déposé dans issues_inbox/, jamais fiable
  // à injecter tel quel — même précaution que resultats.js (lignes fichier).
  div.querySelector('.attente-titre').textContent = desc.titre;
  div.querySelector('.attente-projet').textContent = desc.projet;
  div.querySelector('.attente-date').textContent = desc.date;
  div.querySelector('.attente-condition').textContent = '⏳ Condition : ' + desc.condition;
  return div;
}

function rendreListe(items) {
  const zone = zoneListe();
  if (!zone) return;
  zone.innerHTML = '';
  if (!items || !items.length) {
    const vide = document.createElement('div');
    vide.className = 'issue-vide';
    vide.textContent = 'Aucune issue en attente';
    zone.appendChild(vide);
    return;
  }
  for (const item of items) zone.appendChild(construireLigneDOM(item));
}

// ─── Chargement de la liste (ouverture d'onglet / après chaque action / ─────
//     compteur du badge changé pendant que l'onglet est ouvert) ────────────
let chargementEnCours = false;
export async function chargerListeAttente() {
  if (chargementEnCours) return;
  chargementEnCours = true;
  try {
    const rep = await api.get('/issues-attente', { silencieux: true });
    rendreListe(rep && rep.items);
  } catch (e) {
    toasts.erreur('En attente — échec du chargement : ' + e.message);
  } finally {
    chargementEnCours = false;
  }
}

// ─── Actions ────────────────────────────────────────────────────────────────
function basculerBoutons(ligneEl, desactives) {
  ligneEl.querySelectorAll('button').forEach((b) => { b.disabled = desactives; });
}

async function lancer(id, ligneEl) {
  basculerBoutons(ligneEl, true);
  try {
    const rep = await api.post('/issues-attente/lancer', { id }, { silencieux: true });
    toasts.succes('Issue lancée' + (rep && rep.fichier ? ' (' + rep.fichier + ')' : '')
                 + ' — elle apparaîtra dans Résultats.');
    ligneEl.remove();
    if (!zoneListe().children.length) rendreListe([]);
  } catch (e) {
    toasts.erreur(messageEchecAttente(e, 'Échec du lancement.'));
    basculerBoutons(ligneEl, false);
  }
}

async function supprimer(id, ligneEl) {
  const ok = await toasts.confirmer(
    'Supprimer définitivement cette issue en attente ?\n\n'
    + 'Aucun archivage : le texte d\'origine sera perdu.',
    { texteConfirmer: 'Supprimer' });
  if (!ok) return;
  basculerBoutons(ligneEl, true);
  try {
    await api.post('/issues-attente/supprimer', { id }, { silencieux: true });
    toasts.succes('Issue en attente supprimée.');
    ligneEl.remove();
    if (!zoneListe().children.length) rendreListe([]);
  } catch (e) {
    toasts.erreur(messageEchecAttente(e, 'Échec de la suppression.'));
    basculerBoutons(ligneEl, false);
  }
}

function installerDelegation() {
  dom.surAction('[data-action="attente-lancer"]', 'click', (evenement, element) => {
    const ligne = element.closest('.ligne-attente');
    if (ligne) lancer(ligne.dataset.id, ligne);
  });
  dom.surAction('[data-action="attente-supprimer"]', 'click', (evenement, element) => {
    const ligne = element.closest('.ligne-attente');
    if (ligne) supprimer(ligne.dataset.id, ligne);
  });
}

// ─── Badge (suit le sondage /issues-inbox/etat déjà en place, voir en-tête) ──
function majBadge(nb) {
  const badge = document.getElementById('badge-attente');
  if (!badge) return;
  const decision = decisionBadgeAttente(nb);
  badge.style.display = decision.afficher ? '' : 'none';
  badge.textContent = decision.texte;
}

let ongletActifAttente = false;
let dernierNbConnu = null;

function surChangementInbox(val) {
  const nb = val && val.nbEnAttente;
  majBadge(nb);
  if (ongletActifAttente && nb !== dernierNbConnu) chargerListeAttente();
  dernierNbConnu = nb;
}

function surChangementOnglet(nom) {
  ongletActifAttente = nom === 'attente';
  if (ongletActifAttente) chargerListeAttente();
}

/** Point d'entrée, appelé une fois par index.js. */
export function initAttente() {
  installerDelegation();
  store.abonnerCle('ongletActif', surChangementOnglet);
  store.abonnerCle('issuesInbox', surChangementInbox);
}
