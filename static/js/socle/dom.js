// dom.js — échappement HTML + registre de délégation d'événements (issue #625).
//
// RESPONSABILITÉ
//   Deux choses :
//   1. echapperHtml(texte), pour construire du DOM sans concaténer de HTML brut.
//   2. UN REGISTRE DE DÉLÉGATION D'ÉVÉNEMENTS qui remplace, module par module
//      depuis l'étape 2 (#626) : les gestionnaires inline du HTML (onclick=…)
//      et les gestionnaires générés sous forme de texte dans le JS.
//      Au lieu d'un handler par nœud, on enregistre (une fois) une règle
//      « ce sélecteur, cet événement → cette fonction », et un seul écouteur
//      par type d'événement, posé sur un ancêtre stable, route les événements.
//
// CE QU'IL EXPOSE
//   - echapperHtml(texte)          : (fonction pure, testée sous Node)
//   - surAction(selecteur, type, gestionnaire) : enregistre une règle déléguée.
//   - installerDelegation(racine?) : (ré)installe les écouteurs racine.

/** Échappe les 5 caractères sensibles pour insertion dans du HTML. Pur. */
export function echapperHtml(texte) {
  return String(texte)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ─── Registre de délégation ──────────────────────────────────────────────────
// regles : Map<typeEvenement, Array<{selecteur, gestionnaire}>>
const regles = new Map();
const typesInstalles = new Set();

/**
 * Enregistre une règle déléguée. À l'événement `type`, si la cible (ou un de
 * ses ancêtres) correspond à `selecteur`, `gestionnaire(evenement, element)`
 * est appelé (element = le nœud correspondant, via closest).
 */
export function surAction(selecteur, type, gestionnaire) {
  if (!regles.has(type)) regles.set(type, []);
  regles.get(type).push({ selecteur, gestionnaire });
  installerType(type);
  return () => {
    const liste = regles.get(type) || [];
    const i = liste.findIndex((r) => r.selecteur === selecteur && r.gestionnaire === gestionnaire);
    if (i >= 0) liste.splice(i, 1);
  };
}

function installerType(type, racine) {
  if (typeof document === 'undefined') return;
  if (typesInstalles.has(type)) return;
  typesInstalles.add(type);
  (racine || document).addEventListener(type, (evenement) => {
    const liste = regles.get(type);
    if (!liste) return;
    for (const { selecteur, gestionnaire } of liste) {
      const cible = evenement.target;
      const element = cible && cible.closest ? cible.closest(selecteur) : null;
      if (element) gestionnaire(evenement, element);
    }
  });
}

/** (Ré)installe un écouteur par type d'événement déjà enregistré. */
export function installerDelegation(racine) {
  for (const type of regles.keys()) installerType(type, racine);
}
