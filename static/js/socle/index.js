// index.js — point d'entrée du socle, chargé comme MODULE (issue #625, étape 1).
//
// Ce fichier est le seul <script type="module"> de la page. Il assemble les
// briques partagées, installe le pont de transition, et initialise les modules
// de fonctionnalité déjà sortis d'app.js (onglets.js, issue #626). Il est
// chargé À CÔTÉ de l'ancien static/js/app.js (script classique), sans le
// remplacer ni l'importer.
//
// ⚠️ LE SOCLE NE REMPLACE PAS TOUT ENCORE ⚠️
//   - sse.connecter() n'est PAS appelé : l'ancien app.js gère /stream et /events
//     (interdiction de double connexion, cf. sse.js et issue #625).
//   - seule la règle de délégation de la barre d'onglets est enregistrée
//     (onglets.js, issue #626) ; le reste de dom.installerDelegation() reste
//     inerte tant que les étapes suivantes n'ajoutent pas leurs propres règles.
//   - le store ne pilote encore aucun rendu (hors classes actif/inactif des
//     onglets) ; les autres tranches sont simplement disponibles et testées.
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
import { initialiserOnglets } from '../onglets.js';

// Délégation : inerte tant qu'aucune règle n'est enregistrée (étapes suivantes).
dom.installerDelegation();

// Pont de transition : unique point de contact avec l'ancien code, à retirer à
// la dernière étape de la refonte.
installerPont({ store, api, toasts, dom, sse, persistance });

// Mécanique des onglets (issue #626, étape 2) : premier module de
// fonctionnalité sorti d'app.js, voir ARCHITECTURE.md §6.7.
initialiserOnglets();

// Trace discrète en console — aucun effet visible dans l'interface.
console.debug('[socle] briques chargées et inertes (issue #625, étape 1).');
console.debug('[socle] onglets initialisés (issue #626, étape 2).');
