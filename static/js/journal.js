// journal.js — onglet Journal watcher, sorti d'app.js (issue #650, refonte web
// étape 11).
//
// RESPONSABILITÉ
//   Connexion SSE /journal/<projet> (une seule à la fois — sourceJournal ferme
//   la précédente avant d'en ouvrir une nouvelle), affichage coloré des lignes
//   dans #terminal (plus récentes en tête) et bouton « Vider l'affichage ».
//
// BRANCHEMENT (issue #650) : démarrerJournal() est appelé PAR IMPORT DIRECT
// depuis static/js/onglets.js (activerOnglet), plus via le pont — sourceJournal
// n'est donc plus une globale implicite de script classique : seule ce module
// la lit/l'écrit. initJournal() (délégation du bouton Vider) est appelée une
// fois par index.js, comme les autres modules par fonctionnalité.
import { surAction } from './socle/dom.js';

let sourceJournal = null;

// ─── Logique pure (testée sous Node — voir static/js/tests/journal.test.js) ──
// Code couleur d'une ligne de log selon son contenu, indépendant du DOM.
export function classeLigneJournal(texte) {
  const t = String(texte);
  if (t.includes('[WARNING]') || t.includes('⚠')) return 'log-warn';
  if (t.includes('[ERROR]')) return 'log-err';
  if (t.includes('✓') || t.includes('succès')) return 'log-ok';
  return 'log-info';
}

function ajouterLigneTerminal(texte, classe) {
  const term = document.getElementById('terminal');
  const div = document.createElement('div');
  div.className = classe;
  div.textContent = texte;
  // Les lignes les plus récentes s'affichent en haut.
  term.insertBefore(div, term.firstChild);
  term.scrollTop = 0;
}

/** (Ré)ouvre la connexion SSE du journal pour le projet actuellement
 *  sélectionné — ferme la précédente si déjà ouverte (changement de projet ou
 *  ré-entrée dans l'onglet). */
export function demarrerJournal() {
  if (sourceJournal) { sourceJournal.close(); sourceJournal = null; }
  const nom = document.getElementById('projet').value;
  document.getElementById('label-journal').textContent = 'logs/watcher-' + nom + '.log';
  document.getElementById('terminal').innerHTML = '';
  sourceJournal = new EventSource('/journal/' + encodeURIComponent(nom));
  sourceJournal.onmessage = function(e) {
    ajouterLigneTerminal(e.data, classeLigneJournal(e.data));
  };
  sourceJournal.onerror = function() {
    ajouterLigneTerminal('— connexion perdue, tentative de reconnexion…', 'log-warn');
  };
}

export function viderTerminal() {
  document.getElementById('terminal').innerHTML = '';
}

/** Branche la délégation de clic du bouton « Vider l'affichage » — appelé une
 *  seule fois par index.js au chargement de la page. */
export function initJournal() {
  surAction('[data-action="journal-vider"]', 'click', () => viderTerminal());
}
