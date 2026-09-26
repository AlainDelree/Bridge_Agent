// actions_ligne.js — actions cliquables directement sur la ligne d'une issue
// OUVERTE, onglet Résultats (issue #641, refonte web étape 6 — ARCHITECTURE.md
// §6.7 ; correctif issue #642).
//
// POURQUOI CE MODULE
//   Avant #641, une ligne ouverte affichait un préfixe purement STATIQUE
//   (⚠️ needs-human, ✏️ mode_write, posé par prefixeIssue() dans app.js) : agir
//   dessus obligeait à sélectionner l'issue puis à aller chercher l'action dans
//   le panneau latéral (#628). #641 avait rendu ⚠️ ET ✏️ cliquables — mais ✏️
//   n'existe que sur une issue en ÉCRITURE (label mode_write) : une issue en
//   LECTURE en cours n'avait alors plus AUCUN moyen d'être interrompue depuis
//   sa ligne (régression signalée #642). Ce module distingue désormais deux
//   choses bien séparées :
//     ⚠️ needs-human            → reste cliquable, « retirer needs-human »
//                                 (relancerIssue(), app.js, INCHANGÉE).
//     ✏️ mode_write             → redevient PUREMENT INFORMATIF (#642) : plus
//                                 aucun clic, juste une infobulle « Mode
//                                 écriture en cours ».
//     icône dédiée « interrompre » → NOUVELLE (#642), affichée sur TOUTE issue
//                                 OUVERTE actuellement EN COURS (lecture OU
//                                 écriture, needs-human exclu puisque déjà
//                                 arrêtée) — basée sur le même état (`timing.
//                                 debut`) qui déclenche aujourd'hui le décompte
//                                 TIMEOUT actif dans resultats.js, pas sur le
//                                 seul label mode_write. Carré vert « ✓ » au
//                                 repos, carré rouge « ✕ » au survol (CSS pure,
//                                 aucun état JS intermédiaire) — le clic
//                                 déclenche directement interrompreIssue()
//                                 (app.js, INCHANGÉE), dont le confirm() natif
//                                 reste l'unique confirmation.
//   Aucune route ni confirmation dupliquée : app.js appelle directement ses
//   propres fonctions (mêmes route /interrompre ou /relancer-issue, même
//   confirm(), même modale de résultat détaillée) — ce module ne s'occupe QUE
//   du rendu des badges, pas de la logique métier d'interruption/relance.
//   S'y ajoute un contrôle compact à 3 états pour le son PROPRE à cette issue
//   (issue #630/#637) : déplacé ici depuis la zone Actions du panneau latéral,
//   qui ne le montrait que pour l'issue SÉLECTIONNÉE — logique pure inchangée
//   (sonIssueDepuisReponse/normaliserChoixSonIssue/etatsOptionsSonIssue), juste
//   déplacée de panneau_lateral.js à ce module puisque le panneau ne l'affiche
//   plus (voir panneau_lateral.js).
//
// POURQUOI L'ICÔNE « INTERROMPRE » EST TOUJOURS RENDUE MASQUÉE ICI
//   Au moment où construireLigneIssueDOM (app.js) construit une ligne, l'état
//   `timing` (decompte TIMEOUT, source de vérité dans resultats.js/store) n'est
//   pas forcément encore chargé (ex. tout premier rendu de page). Comme pour
//   .ligne-estimation/.ligne-tempsrestant, l'icône est donc toujours posée dans
//   le DOM mais masquée (display:none) à la construction, puis
//   resultats.js::majBadges() décide de l'afficher ou non à CHAQUE recalcul
//   (rendu complet + tick 1 s), à partir de `afficherIconeInterruption()`
//   ci-dessous (logique pure, exportée pour être appelée depuis resultats.js
//   ET testée sous Node ici). C'est ce qui permet à l'icône d'apparaître dès
//   qu'une issue passe de « en file » à « en cours » (événement debut_issue)
//   sans reconstruire toute la ligne.
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

// Exportée (issue #647) : resultats.js la réutilise pour calculerBadgeSans
// Redacteur() plutôt que de dupliquer cette normalisation objet-ou-chaîne.
export function normaliserNomsLabels(labels) {
  return (labels || []).map((l) => ((l && l.name) || l || '').toLowerCase());
}

// Préfixe informatif d'une ligne OUVERTE — même priorité que l'ex-prefixeIssue()
// d'app.js : needs-human prime sur mode_write. 'mode_write' n'est plus une
// ACTION depuis #642 (purement informatif, voir rendrePrefixeLigneOuverte) ;
// null pour une ligne done seule ou sans label pertinent (○/✅ restent
// statiques, sans action).
export function prefixeInformatifLigneOuverte(labels) {
  const noms = normaliserNomsLabels(labels);
  if (noms.includes('needs-human')) return 'needs-human';
  if (noms.includes('mode_write'))  return 'mode_write';
  return null;
}

// Faut-il afficher l'icône dédiée « interrompre » sur cette ligne OUVERTE ?
// (issue #642 — correctif de la régression #641 : une issue en LECTURE en
// cours n'avait plus aucun moyen d'être interrompue depuis sa ligne). Basée
// sur le MÊME état que le décompte TIMEOUT actif de resultats.js (`timing.
// debut` non nul = « en cours », peu importe lecture ou écriture) — jamais sur
// le seul label mode_write :
//   - needs-human → false (déjà arrêtée, l'action « retirer needs-human »
//     suffit) ;
//   - aucun timing connu, ou timing.debut absent (« en file », pas encore
//     prise en charge, ou issue fermée dont le timing a été purgé) → false ;
//   - sinon (en cours, lecture ou écriture, avec ou sans limite) → true.
export function afficherIconeInterruption(labels, timing) {
  const noms = normaliserNomsLabels(labels);
  if (noms.includes('needs-human')) return false;
  return !!(timing && timing.debut);
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

// Préfixe de gauche d'une ligne OUVERTE (issue #642, correctif #641) : ⚠️
// needs-human reste la SEULE action cliquable de ce préfixe (retirer
// needs-human) ; ✏️ mode_write est désormais purement informatif (infobulle,
// aucun onclick) — l'interruption est portée par l'icône dédiée ci-dessous,
// quel que soit le mode. ○/✅ restent des caractères statiques, sans action,
// exactement comme l'ex-prefixeIssue(). stopPropagation() (dans
// retirerNeedsHumanDepuisLigne, app.js) empêche la sélection de la ligne au
// clic sur le badge ⚠️.
export function rendrePrefixeLigneOuverte(nom, numero, labels) {
  const noms = normaliserNomsLabels(labels);
  const prefixe = prefixeInformatifLigneOuverte(labels);
  if (prefixe === 'needs-human') {
    return '<span class="badge-action-ligne" onclick="retirerNeedsHumanDepuisLigne(event, \''
      + dom.echapperHtml(nom) + '\', ' + Number(numero) + ')"'
      + ' title="Retirer needs-human et relancer">⚠️</span>';
  }
  if (prefixe === 'mode_write') {
    return '<span class="badge-mode-ecriture" title="Mode écriture en cours">✏️</span>';
  }
  return noms.includes('done') ? '✅' : '○';
}

// Icône dédiée d'interruption (issue #642) : toujours posée dans le DOM d'une
// ligne OUVERTE mais MASQUÉE à la construction (voir docstring d'en-tête) —
// resultats.js::majBadges() décide de l'afficher via afficherIconeInterruption().
// Carré vert « ✓ » au repos, carré rouge « ✕ » au survol (styles resultats.css,
// aucun état JS intermédiaire) ; le clic appelle interrompreDepuisLigne() (app.js,
// INCHANGÉE) — même route/confirmation/modale que interrompreIssue().
export function rendreIconeInterruption(nom, numero) {
  return '<span class="badge-interrompre-ligne" style="display:none"'
    + ' onclick="interrompreDepuisLigne(event, \'' + dom.echapperHtml(nom) + '\', '
    + Number(numero) + ')" title="Interrompre l\'issue">'
    + '<span class="badge-interrompre-ok">✓</span>'
    + '<span class="badge-interrompre-stop">✕</span>'
    + '</span>';
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
// rend préfixe informatif/⚠️ + icône d'interruption (masquée, révélée par
// resultats.js::majBadges()) + contrôle de son.
export function rendreActionsLigneOuverte(nom, numero, labels) {
  assurerSonsProjetCharges(nom);
  return rendrePrefixeLigneOuverte(nom, numero, labels)
       + rendreIconeInterruption(nom, numero)
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
