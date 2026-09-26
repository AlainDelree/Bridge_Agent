// actions_ligne.js — actions cliquables directement sur la ligne d'une issue
// OUVERTE, onglet Résultats (issue #641, refonte web étape 6 — ARCHITECTURE.md
// §6.7).
//
// POURQUOI CE MODULE
//   Avant cette étape, une ligne ouverte affichait un préfixe purement STATIQUE
//   (⚠️ needs-human, ✏️ mode_write, posé par prefixeIssue() dans app.js) : agir
//   dessus obligeait à sélectionner l'issue puis à aller chercher l'action dans
//   le panneau latéral (#628). Ce module rend ces deux préfixes CLIQUABLES sur
//   la ligne elle-même :
//     ⚠️ needs-human → « retirer needs-human » (relancerIssue(), app.js, INCHANGÉE)
//     ✏️ mode_write   → « interrompre »         (interrompreIssue(), app.js, INCHANGÉE)
//   Aucune route ni confirmation dupliquée : app.js appelle directement ses
//   propres fonctions (mêmes route /interrompre ou /relancer-issue, même
//   confirm(), même modale de résultat détaillée) — ce module ne s'occupe QUE
//   du rendu du badge cliquable, pas de la logique métier d'interruption/relance.
//   S'y ajoute un contrôle compact à 3 états pour le son PROPRE à cette issue
//   (issue #630/#637) : déplacé ici depuis la zone Actions du panneau latéral,
//   qui ne le montrait que pour l'issue SÉLECTIONNÉE — logique pure inchangée
//   (sonIssueDepuisReponse/normaliserChoixSonIssue/etatsOptionsSonIssue), juste
//   déplacée de panneau_lateral.js à ce module puisque le panneau ne l'affiche
//   plus (voir panneau_lateral.js).
//
// CE QUI N'EST PAS ICI
//   - prefixeIssue() (ligne FERMÉE, ou ○/✅ statique d'une ligne ouverte sans
//     needs-human/mode_write) reste dans app.js, INCHANGÉ.
//   - Les badges ✅/Diff/All d'une ligne FERMÉE+done (resultats_coches.js) sont
//     un mécanisme séparé, non touché par cette étape.
//   - interrompreIssue()/relancerIssue() (confirmation, route, modale) restent
//     dans app.js — appelées directement par les onclick inline générés ici
//     (retirerNeedsHumanDepuisLigne/interrompreDepuisLigne, définies dans
//     app.js), pas via ce module.
//
// SON PAR ISSUE — UNE requête GET /son-issue/<projet> par projet connu (issue
// #641, backend étendu dans app/son_issue.py), jamais une par ligne/rendu —
// même stratégie que resultats_coches.js (issue #636, cases « traité/lu »).
// Déclenchée paresseusement au premier rendu d'une ligne de ce projet ; les
// lignes déjà rendues avant la réponse sont repatchées (resyncLignesSon), le
// clic reste sur la route existante POST /son-issue/<projet>/<numero> (#630).

import { api } from './socle/api.js';
import * as dom from './socle/dom.js';

// ─────────────────────────────────────────────────────────────────────────────
// 1. LOGIQUE PURE (testée sous Node — voir static/js/tests/actions_ligne.test.js)
//    Aucune dépendance au DOM ni au réseau.
// ─────────────────────────────────────────────────────────────────────────────

function normaliserNomsLabels(labels) {
  return (labels || []).map((l) => ((l && l.name) || l || '').toLowerCase());
}

// Action à proposer sur une ligne OUVERTE — même priorité que l'ex-prefixeIssue()
// d'app.js : needs-human prime sur mode_write. null pour une ligne done seule
// ou sans label pertinent (○/✅ restent statiques, sans action).
export function actionLigneOuverte(labels) {
  const noms = normaliserNomsLabels(labels);
  if (noms.includes('needs-human')) return 'needs-human';
  if (noms.includes('mode_write'))  return 'interrompre';
  return null;
}

// Normalise la réponse de GET /son-issue/<projet>/<numero> : 'plat'/'cloche' si
// un choix propre existe pour cette issue, sinon null (suit alors l'interrupteur
// global — voir etat_son_issue.py::son_choisi). Déplacée telle quelle depuis
// panneau_lateral.js (issue #637) à l'étape 6 (#641).
export function sonIssueDepuisReponse(donnees) {
  const son = donnees && donnees.son;
  return (son === 'plat' || son === 'cloche') ? son : null;
}

// Normalise la valeur data-valeur d'un bouton du contrôle ('', 'plat' ou
// 'cloche') vers ce qui doit être envoyé à POST /son-issue : null retire le
// choix propre à l'issue (elle retombe alors sur l'interrupteur global).
export function normaliserChoixSonIssue(valeurBrute) {
  return (valeurBrute === 'plat' || valeurBrute === 'cloche') ? valeurBrute : null;
}

// État actif de chacune des 3 options, pour le rendu — mutuellement exclusif.
export function etatsOptionsSonIssue(sonChoisi) {
  return {
    global: sonChoisi !== 'plat' && sonChoisi !== 'cloche',
    plat: sonChoisi === 'plat',
    cloche: sonChoisi === 'cloche',
  };
}

// Fusionne la réponse groupée GET /son-issue/<projet> (issue #641) dans le
// cache local { projet: { numeroStr: 'plat'|'cloche' } } — REMPLACE les
// entrées du projet concerné, conserve les autres (même patron que
// resultats_coches.js::fusionnerCasesServeur). Ignore les valeurs invalides.
export function fusionnerSonsProjet(cache, projet, sonsBruts) {
  const propres = {};
  Object.entries(sonsBruts || {}).forEach(([numero, son]) => {
    if (son === 'plat' || son === 'cloche') propres[String(numero)] = son;
  });
  return { ...(cache || {}), [projet]: propres };
}

// Choix connu pour une issue précise dans le cache — null si absente (suit
// alors le réglage global).
export function sonConnuDansCache(cache, projet, numero) {
  const parProjet = (cache && cache[projet]) || {};
  const valeur = parProjet[String(numero)];
  return (valeur === 'plat' || valeur === 'cloche') ? valeur : null;
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. RENDU (appelé par app.js::construireLigneIssueDOM via window.Bridge.actionsLigne)
// ─────────────────────────────────────────────────────────────────────────────

// Badge cliquable remplaçant ⚠️/✏️ statiques (ligne OUVERTE uniquement) — ○/✅
// restent des caractères statiques, sans action, exactement comme rendus par
// l'ex-prefixeIssue() pour ces cas. stopPropagation() (dans les fonctions
// app.js appelées) empêche la sélection de la ligne au clic sur le badge.
export function rendreBadgeActionLigne(nom, numero, labels) {
  const noms = normaliserNomsLabels(labels);
  const action = actionLigneOuverte(labels);
  if (action === 'needs-human') {
    return '<span class="badge-action-ligne" onclick="retirerNeedsHumanDepuisLigne(event, \''
      + dom.echapperHtml(nom) + '\', ' + Number(numero) + ')"'
      + ' title="Retirer needs-human et relancer">⚠️</span>';
  }
  if (action === 'interrompre') {
    return '<span class="badge-action-ligne" onclick="interrompreDepuisLigne(event, \''
      + dom.echapperHtml(nom) + '\', ' + Number(numero) + ')"'
      + ' title="Interrompre cette issue">✏️</span>';
  }
  return noms.includes('done') ? '✅' : '○';
}

// Contrôle compact à 3 états (mini-segmenté, lettres + infobulle — largeur de
// ligne contrainte, issue #633) : G(lobal) / P(lat) / C(loche). Remplace le
// contrôle textuel (« Global »/« Plat »/« Cloche ») du panneau, retiré de là.
function boutonSonLigne(actif, valeur, lettre, titre, nom, numero) {
  return '<button type="button" class="ligne-son-opt' + (actif ? ' actif' : '') + '"'
    + ' onclick="choisirSonIssueDepuisLigne(event, \'' + dom.echapperHtml(nom) + '\', '
    + Number(numero) + ', \'' + valeur + '\')"'
    + ' title="' + dom.echapperHtml(titre) + '">' + lettre + '</button>';
}

function boutonsSonLigne(nom, numero, sonChoisi) {
  const etats = etatsOptionsSonIssue(sonChoisi);
  return boutonSonLigne(etats.global, '', 'G', 'Son de cette issue : suit le réglage global — clic pour changer', nom, numero)
       + boutonSonLigne(etats.plat, 'plat', 'P', 'Son de cette issue : Plat — clic pour changer', nom, numero)
       + boutonSonLigne(etats.cloche, 'cloche', 'C', 'Son de cette issue : Cloche — clic pour changer', nom, numero);
}

export function rendreControleSonLigne(nom, numero, sonChoisi) {
  return '<span class="ligne-son-segmente">' + boutonsSonLigne(nom, numero, sonChoisi) + '</span>';
}

// ─────────────────────────────────────────────────────────────────────────────
// 3. CACHE + RÉSEAU (un GET par projet, jamais par ligne)
// ─────────────────────────────────────────────────────────────────────────────

let sonsParProjet = {};             // { projet: { numeroStr: 'plat'|'cloche' } }
const projetsSonsCharges = new Set(); // évite de relancer un GET déjà en cours/fait

async function chargerSonsProjet(nom) {
  try {
    const rep = await api.get('/son-issue/' + encodeURIComponent(nom), { silencieux: true });
    sonsParProjet = fusionnerSonsProjet(sonsParProjet, nom, (rep && rep.sons) || {});
  } catch (e) {
    projetsSonsCharges.delete(nom); // best-effort : réessaiera au prochain rendu de ce projet
    return;
  }
  resyncLignesSon();
}

function assurerSonsProjetCharges(nom) {
  if (!nom || projetsSonsCharges.has(nom)) return;
  projetsSonsCharges.add(nom);
  chargerSonsProjet(nom); // fire-and-forget, resync au retour (resyncLignesSon)
}

// Repatche le contrôle de son des lignes déjà rendues quand la réponse groupée
// arrive après le premier rendu (course bénigne, même principe que
// resultats_coches.js::resyncDom).
function resyncLignesSon() {
  if (typeof document === 'undefined') return;
  document.querySelectorAll('#liste-issues .ligne-issue').forEach((ligne) => {
    const seg = ligne.querySelector('.ligne-son-segmente');
    if (!seg) return;
    const nom = ligne.dataset.projet;
    const numero = ligne.dataset.numero;
    seg.outerHTML = rendreControleSonLigne(nom, numero, sonConnuDansCache(sonsParProjet, nom, numero));
  });
}

// Point d'entrée unique appelé par construireLigneIssueDOM (app.js) pour une
// ligne OUVERTE : déclenche le chargement du son de son projet si besoin, puis
// rend badge d'action + contrôle de son.
export function rendreActionsLigneOuverte(nom, numero, labels) {
  assurerSonsProjetCharges(nom);
  return rendreBadgeActionLigne(nom, numero, labels)
       + rendreControleSonLigne(nom, numero, sonConnuDansCache(sonsParProjet, nom, numero));
}

// Bascule optimiste (avant réponse serveur) du contrôle d'UNE ligne, sans
// reconstruire toute la ligne — appelée par choisirSonIssueDepuisLigne (app.js).
export async function choisirSonIssueLigne(element, nom, numero, valeurBrute) {
  const valeur = normaliserChoixSonIssue(valeurBrute);
  const seg = element && element.closest ? element.closest('.ligne-son-segmente') : null;
  if (seg) seg.innerHTML = boutonsSonLigne(nom, numero, valeur);
  sonsParProjet = fusionnerSonsProjet(sonsParProjet, nom,
    { ...((sonsParProjet && sonsParProjet[nom]) || {}), [String(numero)]: valeur });
  try {
    await api.post('/son-issue/' + encodeURIComponent(nom) + '/' + encodeURIComponent(numero), { son: valeur });
  } catch (e) { /* déjà signalé par api.post (toast) — pas de resync ligne par ligne */ }
}

// Objet publié sous window.Bridge.actionsLigne (via installerPont dans
// index.js) : consommé par app.js (construireLigneIssueDOM et les fonctions
// retirerNeedsHumanDepuisLigne/interrompreDepuisLigne/choisirSonIssueDepuisLigne
// appelées par les onclick inline générés ci-dessus).
export const actionsLigne = {
  rendreActionsLigneOuverte,
  choisirSonIssueLigne,
};
