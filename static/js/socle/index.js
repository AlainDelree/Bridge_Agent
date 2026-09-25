// index.js — point d'entrée du socle, chargé comme MODULE (issue #625, étape 1).
//
// Ce fichier est le seul <script type="module"> de la page. Il assemble les
// briques partagées et installe le pont de transition. Il est chargé À CÔTÉ de
// l'ancien static/js/app.js (script classique), sans le remplacer ni l'importer.
//
// ⚠️ LE SOCLE NE REMPLACE RIEN À CETTE ÉTAPE ⚠️
//   - sse.connecter() n'est PAS appelé : l'ancien app.js gère /stream et /events
//     (interdiction de double connexion, cf. sse.js et issue #625).
//   - aucune règle de délégation n'est enregistrée : dom.installerDelegation()
//     est donc inerte.
//   - le store ne pilote aucun rendu ; il est simplement disponible et testé.
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

// Délégation : inerte tant qu'aucune règle n'est enregistrée (étapes suivantes).
dom.installerDelegation();

// Pont de transition : unique point de contact avec l'ancien code, à retirer à
// la dernière étape de la refonte.
installerPont({ store, api, toasts, dom, sse, persistance });

// Trace discrète en console — aucun effet visible dans l'interface.
console.debug('[socle] briques chargées et inertes (issue #625, étape 1).');
