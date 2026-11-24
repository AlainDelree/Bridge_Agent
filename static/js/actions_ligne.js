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
//     ⚠️ needs-human            → cliquable jusqu'à l'issue #950 (« retirer
//                                 needs-human »), désormais PUREMENT
//                                 INFORMATIF comme ✏️ ci-dessous : l'action
//                                 vit dans le bouton explicite « Relancer »
//                                 du groupe décrit plus bas, pour ne pas
//                                 avoir deux façons de faire la même chose.
//     ✏️ mode_write             → redevient PUREMENT INFORMATIF (#642) : plus
//                                 aucun clic, juste une infobulle « Mode
//                                 écriture en cours ».
//     zone d'actions PAR ISSUE  → REFONTE (issue #950, étude #938/#939) :
//                                 l'ancienne icône dédiée carrée verte/rouge
//                                 (#642, appelait /interrompre — tue TOUT le
//                                 watcher du projet) est remplacée par un
//                                 groupe de boutons textuels courts dont la
//                                 composition dépend de l'état de l'issue —
//                                 « Annuler » (en file), « Interrompre » (en
//                                 cours — interruption CIBLÉE #949 pour une
//                                 issue normale, comportement historique
//                                 watcher entier pour une issue interactive),
//                                 « Relancer » + « Fermer » (needs-human),
//                                 rien (terminée). Décision par
//                                 boutonsActionLigne() ci-dessous (logique
//                                 pure, testée) — même patron que l'ancienne
//                                 icône : TOUJOURS posée masquée au rendu,
//                                 révélée par resultats.js::majBadges(). Le
//                                 ⚠️ needs-human devient donc purement
//                                 informatif (l'action « Relancer » vit
//                                 désormais dans ce groupe, pas sur le badge).
//                                 Décision d'Alain (#950) : TOUTES les actions
//                                 par issue vivent sur CETTE ligne, plus
//                                 jamais dans le panneau de détail ni le
//                                 panneau Infrastructure — un bouton de
//                                 panneau peut viser une autre issue que
//                                 celle crue sélectionnée (sélection qui
//                                 « saute », #943), un bouton de LIGNE ne
//                                 peut viser que SA PROPRE issue (nom/numéro
//                                 clos dans son propre onclick, jamais lus
//                                 depuis une sélection courante).
//   Aucune route ni confirmation dupliquée : app.js appelle directement ses
//   propres fonctions (mêmes routes, mêmes confirm(), même modale de résultat
//   détaillée pour l'interruption historique) — ce module ne s'occupe QUE du
//   rendu des boutons/badges, pas de la logique métier.
//   S'y ajoute un contrôle compact à 4 états pour le son PROPRE à cette issue
//   (issue #630/#637, option Silence #699) : déplacé ici depuis la zone Actions
//   du panneau latéral, qui ne le montrait que pour l'issue SÉLECTIONNÉE —
//   logique pure inchangée
//   (sonIssueDepuisReponse/normaliserChoixSonIssue/etatsOptionsSonIssue), juste
//   déplacée de panneau_lateral.js à ce module puisque le panneau ne l'affiche
//   plus (voir panneau_lateral.js).
//
// POURQUOI LES BOUTONS D'ACTION SONT TOUJOURS RENDUS MASQUÉS ICI
//   Au moment où construireLigneIssueDOM (app.js) construit une ligne, l'état
//   `timing` (decompte TIMEOUT, source de vérité dans resultats.js/store) n'est
//   pas forcément encore chargé (ex. tout premier rendu de page). Comme pour
//   .ligne-estimation/.ligne-tempsrestant, les QUATRE boutons possibles sont
//   donc toujours posés dans le DOM mais masqués (display:none) à la
//   construction, puis resultats.js::majBadges() décide à CHAQUE recalcul
//   (rendu complet + tick 1 s) lequel afficher, à partir de
//   `boutonsActionLigne()` ci-dessous (logique pure, exportée pour être
//   appelée depuis resultats.js ET testée sous Node ici). C'est ce qui permet
//   au bon bouton d'apparaître dès qu'une issue change d'état (événement
//   debut_issue/fin_issue) sans reconstruire toute la ligne.
//
// CE QUI N'EST PAS ICI
//   - prefixeIssue() (ligne FERMÉE, ou ○/✅ statique d'une ligne ouverte sans
//     needs-human/mode_write) reste dans app.js, INCHANGÉ.
//   - Les badges ✅/Diff/All d'une ligne FERMÉE+done (resultats_coches.js) sont
//     un mécanisme séparé, non touché par cette étape.
//   - annulerIssue()/interrompreIssue()/relancerIssue()/fermerIssue()
//     (confirmation, route, modale) restent dans app.js — appelées
//     directement par les onclick inline générés ici
//     (annulerDepuisLigne/interrompreDepuisLigne/retirerNeedsHumanDepuisLigne/
//     fermerDepuisLigne, définies dans app.js), pas via ce module.
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

// Quel(s) bouton(s) d'action afficher sur cette ligne OUVERTE ? (issue #950,
// remplace afficherIconeInterruption de l'issue #642 — même état de départ :
// le MÊME `timing.debut` que le décompte TIMEOUT actif de resultats.js, pas
// le seul label mode_write, pour qu'une issue en LECTURE en cours reste
// elle aussi interrompable depuis sa ligne, #642) :
//   - done                              → [] (terminée, aucune action)
//   - needs-human                       → ['relancer', 'fermer']
//     (prime sur tout le reste — priorité identique à prefixeInformatifLigneOuverte)
//   - timing inconnu (pas encore chargé)→ [] (on ne sait pas encore si
//     l'issue est « en file » ou « en cours » — mieux vaut n'afficher ni
//     « Annuler » ni « Interrompre » par erreur que de risquer la mauvaise
//     action ; révisé dès que `timing` arrive, cf. majBadges())
//   - timing.debut absent               → ['annuler']   (en file)
//   - timing.debut posé                 → ['interrompre'] (en cours — même
//     libellé qu'une issue interactive, voir mecanismeInterruptionLigne()
//     ci-dessous pour la DÉCISION DE MÉCANISME, distincte de l'affichage)
export function boutonsActionLigne(labels, timing) {
  const noms = normaliserNomsLabels(labels);
  if (noms.includes('done')) return [];
  if (noms.includes('needs-human')) return ['relancer', 'fermer'];
  if (!timing) return [];
  return timing.debut ? ['interrompre'] : ['annuler'];
}

// Quel MÉCANISME le bouton « Interrompre » doit-il déclencher ? (issue #950,
// point 6) Une issue INTERACTIVE (session tmux, étude #888) ne passe jamais
// par la boucle _attendre_fin_claude : l'interruption CIBLÉE (#949, fichier-
// sentinelle relu par cette boucle) ne peut donc jamais la toucher — seul le
// mécanisme HISTORIQUE (watcher entier du projet, /interrompre) fonctionne
// encore pour elle. Même détection que resultats.js::estIssueInteractive
// (label `mode_interactif`), dupliquée ici en pure logique plutôt
// qu'importée : ce module est importé PAR resultats.js, jamais l'inverse
// (éviterait un cycle d'imports ES).
export function mecanismeInterruptionLigne(labels) {
  return normaliserNomsLabels(labels).includes('mode_interactif') ? 'watcher_complet' : 'ciblee';
}

// ─── Garde anti-double-déclenchement d'une interruption (issue #748) ──────
// L'appel réseau de /interrompre peut durer plusieurs secondes (arbre de
// process + attente de 5s côté serveur) ; sans retour visuel, un second clic
// pendant ce temps relançait un second appel concurrent — vécu sur Scrabble
// #452. Logique pure (app.js applique les décisions ci-dessous au DOM — le
// bouton « Interrompre » de la ligne, qu'il mène au mécanisme CIBLÉ #949 ou
// au mécanisme historique watcher entier #323, + le bouton « Interrompre et
// relancer » du panneau latéral, issue #950) : un ensemble partagé de
// couples (projet, numéro) actuellement en cours d'interruption, commun à
// ces déclencheurs puisqu'ils appellent tous `demarrerInterruption`/
// `terminerInterruption` autour de leur appel réseau respectif.
export function cleInterruption(nom, numero) {
  return nom + '#' + numero;
}

// true si CE couple vient d'être accepté (et enregistré aussitôt comme « en
// cours ») ; false s'il l'était déjà — l'appelant doit alors ignorer le clic.
export function demarrerInterruption(enCours, nom, numero) {
  const cle = cleInterruption(nom, numero);
  if (enCours.has(cle)) return false;
  enCours.add(cle);
  return true;
}

// Retire ce couple de l'ensemble « en cours » — appelé après un échec (réseau
// ou réponse succes=false) pour réactiver les déclencheurs ; un succès
// recharge la liste/le panneau, qui les reconstruisent déjà non bloqués, mais
// l'appel reste nécessaire pour vider l'ensemble partagé.
export function terminerInterruption(enCours, nom, numero) {
  enCours.delete(cleInterruption(nom, numero));
}

// Normalise la réponse de GET /son-issue/<projet>/<numero> : 'plat'/'cloche' si
// un choix propre existe pour cette issue, sinon null (suit alors l'interrupteur
// global — voir etat_son_issue.py::son_choisi). Déplacée telle quelle depuis
// panneau_lateral.js (issue #637) à l'étape 6 (#641).
export function sonIssueDepuisReponse(donnees) {
  const son = donnees && donnees.son;
  return (son === 'plat' || son === 'cloche' || son === 'silence') ? son : null;
}

// Normalise la valeur data-valeur d'un bouton du contrôle ('', 'plat',
// 'cloche' ou 'silence') vers ce qui doit être envoyé à POST /son-issue :
// null retire le choix propre à l'issue (elle retombe alors sur
// l'interrupteur global).
export function normaliserChoixSonIssue(valeurBrute) {
  return (valeurBrute === 'plat' || valeurBrute === 'cloche' || valeurBrute === 'silence')
    ? valeurBrute : null;
}

// État actif de chacune des 4 options, pour le rendu — mutuellement exclusif
// (issue #699 : ajout de "silence", coupe le bip pour cette issue seule).
export function etatsOptionsSonIssue(sonChoisi) {
  return {
    global: sonChoisi !== 'plat' && sonChoisi !== 'cloche' && sonChoisi !== 'silence',
    plat: sonChoisi === 'plat',
    cloche: sonChoisi === 'cloche',
    silence: sonChoisi === 'silence',
  };
}

// Fusionne la réponse groupée GET /son-issue/<projet> (issue #641) dans le
// cache local { projet: { numeroStr: 'plat'|'cloche' } } — REMPLACE les
// entrées du projet concerné, conserve les autres (même patron que
// resultats_coches.js::fusionnerCasesServeur). Ignore les valeurs invalides.
export function fusionnerSonsProjet(cache, projet, sonsBruts) {
  const propres = {};
  Object.entries(sonsBruts || {}).forEach(([numero, son]) => {
    if (son === 'plat' || son === 'cloche' || son === 'silence') propres[String(numero)] = son;
  });
  return { ...(cache || {}), [projet]: propres };
}

// Choix connu pour une issue précise dans le cache — null si absente (suit
// alors le réglage global).
export function sonConnuDansCache(cache, projet, numero) {
  const parProjet = (cache && cache[projet]) || {};
  const valeur = parProjet[String(numero)];
  return (valeur === 'plat' || valeur === 'cloche' || valeur === 'silence') ? valeur : null;
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. RENDU (appelé par app.js::construireLigneIssueDOM via window.Bridge.actionsLigne)
// ─────────────────────────────────────────────────────────────────────────────

// Préfixe de gauche d'une ligne OUVERTE — PUREMENT INFORMATIF depuis l'issue
// #950 (plus aucun onclick, y compris ⚠️ needs-human : l'action de relance
// vit désormais dans le bouton explicite « Relancer » du groupe d'actions
// ci-dessous, pour ne pas avoir deux façons de faire la même chose sur la
// même ligne). ○/✅ restent des caractères statiques, exactement comme
// l'ex-prefixeIssue().
export function rendrePrefixeLigneOuverte(labels) {
  const noms = normaliserNomsLabels(labels);
  const prefixe = prefixeInformatifLigneOuverte(labels);
  if (prefixe === 'needs-human') {
    return '<span class="badge-mode-ecriture" title="Échec — intervention humaine requise (voir Relancer/Fermer ci-contre)">⚠️</span>';
  }
  if (prefixe === 'mode_write') {
    return '<span class="badge-mode-ecriture" title="Mode écriture en cours">✏️</span>';
  }
  return noms.includes('done') ? '✅' : '○';
}

// Définition des QUATRE boutons d'action possibles sur une ligne (issue
// #950) — ordre d'affichage fixe, visibilité décidée par boutonsActionLigne()
// ci-dessus (resultats.js::majBadges()). `gestionnaire` : fonction globale
// définie dans app.js, appelée par l'onclick inline généré ci-dessous (même
// patron que les autres actions de ligne — retirerNeedsHumanDepuisLigne,
// choisirSonIssueDepuisLigne…).
const DEFS_BOUTONS_ACTION_LIGNE = [
  { action: 'annuler', classe: 'btn-annuler-ligne', gestionnaire: 'annulerDepuisLigne',
    libelle: 'Annuler', titre: "Annuler cette issue (elle n'a pas encore démarré)" },
  { action: 'interrompre', classe: 'btn-interrompre-ligne', gestionnaire: 'interrompreDepuisLigne',
    libelle: 'Interrompre', titre: 'Interrompre cette issue' },
  { action: 'relancer', classe: 'btn-relancer-ligne', gestionnaire: 'retirerNeedsHumanDepuisLigne',
    libelle: 'Relancer', titre: 'Retirer needs-human et relancer' },
  { action: 'fermer', classe: 'btn-fermer-ligne', gestionnaire: 'fermerDepuisLigne',
    libelle: 'Fermer', titre: "Fermer définitivement cette issue" },
];

// Groupe des quatre boutons d'action PAR ISSUE (issue #950), TOUJOURS posés
// dans le DOM d'une ligne OUVERTE mais masqués à la construction (voir
// docstring d'en-tête) — resultats.js::majBadges() révèle le bon sous-
// ensemble via boutonsActionLigne(). `titre` (titre de l'issue, texte
// libre) est porté en attribut `data-titre` plutôt qu'injecté comme argument
// littéral dans l'onclick= : un titre d'issue contient très souvent des
// apostrophes (« l'issue », « n'est »...) qui casseraient la chaîne JS d'un
// onclick inline, même après échappement HTML (echapperHtml échappe pour du
// HTML, pas pour une chaîne JS imbriquée dans un attribut HTML) —
// interrompreDepuisLigne (app.js) le relit directement sur le bouton cliqué
// (event.currentTarget.dataset.titre), jamais depuis un cache ou la
// sélection courante (point 8 de l'issue #950 : lu dans la ligne elle-même,
// au moment du clic).
export function rendreZoneActionsLigne(nom, numero, titre) {
  const boutons = DEFS_BOUTONS_ACTION_LIGNE.map((def) => {
    const attrTitreIssue = def.action === 'interrompre'
      ? ' data-titre="' + dom.echapperHtml(titre || '') + '"' : '';
    return '<button type="button" class="btn-action-ligne ' + def.classe + '"'
      + ' data-action-ligne="' + def.action + '" style="display:none"'
      + attrTitreIssue
      + ' onclick="' + def.gestionnaire + '(event, \'' + dom.echapperHtml(nom) + '\', '
      + Number(numero) + ')" title="' + dom.echapperHtml(def.titre) + '">'
      + def.libelle + '</button>';
  }).join('');
  return '<span class="zone-actions-ligne">' + boutons + '</span>';
}

// Contrôle compact à 4 états (mini-segmenté, lettres + infobulle — largeur de
// ligne contrainte, issue #633) : G(lobal) / P(lat) / C(loche) / S(ilence,
// issue #699). Remplace le contrôle textuel (« Global »/« Plat »/« Cloche »)
// du panneau, retiré de là.
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
       + boutonSonLigne(etats.cloche, 'cloche', 'C', 'Son de cette issue : Cloche — clic pour changer', nom, numero)
       + boutonSonLigne(etats.silence, 'silence', 'S', 'Son de cette issue : Silence — clic pour changer', nom, numero);
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
// rend préfixe informatif ⚠️/✏️/○/✅ + groupe de boutons d'action PAR ISSUE
// (masqués, révélés par resultats.js::majBadges()) + contrôle de son. `titre`
// (issue #950) : titre de l'issue, pour le rappeler dans la confirmation du
// bouton « Interrompre » — voir rendreZoneActionsLigne().
export function rendreActionsLigneOuverte(nom, numero, labels, titre) {
  assurerSonsProjetCharges(nom);
  return rendrePrefixeLigneOuverte(labels)
       + rendreZoneActionsLigne(nom, numero, titre)
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
  demarrerInterruption,
  terminerInterruption,
  mecanismeInterruptionLigne,
};
