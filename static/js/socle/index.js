// index.js — point d'entrée du socle, chargé comme MODULE (issue #625, étape 1).
//
// Ce fichier est le seul <script type="module"> de la page. Il assemble les
// briques partagées, installe le pont de transition, et initialise les modules
// de fonctionnalité déjà sortis d'app.js (onglets.js, issue #626). Il est
// chargé À CÔTÉ de l'ancien static/js/app.js (script classique), sans le
// remplacer ni l'importer.
//
// CE QUI RESTE À L'ANCIEN app.js (refonte terminée, #625→#645, voir
// ARCHITECTURE.md §6) :
//   - `/events` (cycle de vie serveur : heartbeat, shutdown) — `/stream`, lui,
//     est ouvert et piloté par static/js/resultats.js (issue #627).
//   - la liste des issues, le détail, les filtres, la recherche et les onglets
//     Nouvelle issue/Journal/Configuration/CCW (pas encore sortis d'app.js).
//
// Ordre de chargement (voir templates/fragments/scripts.html) :
//   1. <script> Jinja : window.COULEURS_PERSISTEES / window.MIMES_IMAGE_ACCEPTES
//   2. <script src=app.js> (classique, s'exécute au parsing)
//   3. ce module (type=module → différé, s'exécute APRÈS app.js)
//   → quand ce code tourne, l'ancien app.js et les variables Jinja sont prêts.

import { store } from './store.js';
import { api } from './api.js';
import { toasts } from './toasts.js';
import * as dom from './dom.js';
import { sse } from './sse.js';
import * as persistance from './persistance.js';
import { installerPont } from './pont.js';
import { initialiserOnglets, activerOngletParDefaut } from '../onglets.js';
// Module par fonctionnalité — onglet Résultats (refonte étape 3, issue #627).
import { resultats } from '../resultats.js';
// Module par fonctionnalité — panneau latéral (refonte étape 4, issue #628).
import { initPanneauLateral } from '../panneau_lateral.js';
// Module par fonctionnalité — case « traité/lu » à état serveur + copie fiable
// (refonte étape 5b, issue #636).
import { resultatsCoches } from '../resultats_coches.js';
// Module par fonctionnalité — actions cliquables sur la ligne d'une issue
// ouverte + son par issue (refonte étape 6, issue #641).
import { actionsLigne } from '../actions_ligne.js';

// Délégation : les modules par fonctionnalité (onglets.js, panneau_lateral.js)
// enregistrent leurs propres règles via dom.surAction(...) ; ceci (ré)installe
// les écouteurs racine correspondants.
dom.installerDelegation();

// Pont de transition : unique point de contact avec l'ancien code, à retirer à
// la dernière étape de la refonte. `resultats` y est publié pour qu'app.js pilote
// l'onglet Résultats (activation, ↻, badges) pendant la transition (issue #627).
installerPont({ store, api, toasts, dom, sse, persistance, resultats, resultatsCoches, actionsLigne });

// Onglet Résultats (issue #627) : ouvre l'UNIQUE connexion /stream et s'abonne
// aux transitions d'issue ET à store.ongletActif (issue #632). Le chargement
// initial de la liste, lui, reste paresseux (première activation de l'onglet)
// — voir resultats.onActiverOnglet.
resultats.initialiser();

// Mécanique des onglets (issue #626, étape 2) : premier module de
// fonctionnalité sorti d'app.js, voir ARCHITECTURE.md §6.7. N'active PAS
// encore l'onglet par défaut (voir activerOngletParDefaut plus bas).
initialiserOnglets();

// Panneau latéral de l'onglet Résultats (issue #628, refonte web étape 4) —
// premier module par fonctionnalité à piloter réellement une zone de l'écran
// (voir ARCHITECTURE.md §6.7). S'abonne aussi à store.ongletActif (#632).
initPanneauLateral();

// Case « traité/lu » à état serveur + copie fiable (issue #636, refonte web
// étape 5b) : migre le localStorage hérité (idempotent), charge l'état serveur
// des cases (un GET par projet) et resynchronise le DOM. Lancé AVANT l'activation
// de l'onglet par défaut ; son travail réseau étant asynchrone, la resync du DOM
// se fait dès la réponse serveur (la liste, elle, se rend indépendamment).
resultatsCoches.initialiser();

// Activation de l'onglet par défaut (Résultats) — APPELÉE EN DERNIER,
// volontairement : resultats.js et panneau_lateral.js se sont abonnés à
// store.ongletActif juste au-dessus, et store.set() notifie toujours ses
// abonnés (même à valeur inchangée) — cet ordre garantit que la liste se
// charge et que le panneau démarre dès le premier affichage, quel que soit
// l'ordre des imports en tête de ce fichier (issue #632 : avant ce correctif,
// l'activation par défaut passait par le pont vers des fonctions d'app.js déjà
// retirées, et ne déclenchait donc plus rien).
activerOngletParDefaut();

// Trace discrète en console — aucun effet visible dans l'interface.
console.debug('[socle] briques chargées (issue #625, étape 1).');
console.debug('[socle] onglets initialisés (issue #626, étape 2).');
console.debug('[socle] Résultats piloté par le store (issue #627).');
console.debug('[socle] panneau latéral actif (issue #628).');
console.debug('[socle] Résultats + panneau latéral raccordés au store (issue #632).');
console.debug('[socle] cases « traité/lu » à état serveur + copie fiable (issue #636).');
console.debug('[socle] actions sur la ligne (needs-human/interrompre/son) actives (issue #641).');
