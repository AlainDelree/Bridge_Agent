// dom.js — utilitaires DOM + registre de délégation d'événements (issue #625).
//
// RESPONSABILITÉ
//   Deux choses :
//   1. Des utilitaires de sélection / création d'éléments et d'échappement
//      (échapperHtml), pour construire du DOM sans concaténer de HTML à la main.
//   2. UN REGISTRE DE DÉLÉGATION D'ÉVÉNEMENTS destiné à remplacer, à terme :
//      - les gestionnaires inline du HTML (onclick=… , >70 aujourd'hui) ;
//      - les gestionnaires générés sous forme de texte dans le JS.
//      Au lieu d'un handler par nœud, on enregistre (une fois) une règle
//      « ce sélecteur, cet événement → cette fonction », et un seul écouteur
//      par type d'événement, posé sur un ancêtre stable, route les événements.
//
// CE QU'IL EXPOSE
//   - $  (sel, racine?)            : querySelector.
//   - $$ (sel, racine?)            : querySelectorAll -> Array.
//   - creerElement(tag, attrs, enfants)
//   - echapperHtml(texte)          : (fonction pure, testée sous Node)
//   - surAction(selecteur, type, gestionnaire) : enregistre une règle déléguée.
//   - installerDelegation(racine?) : (ré)installe les écouteurs racine.
//
// NON-BUT À CETTE ÉTAPE
//   Aucune règle n'est enregistrée par le socle : installerDelegation() est donc
//   inerte. Les étapes suivantes appelleront surAction(...) en sortant chaque
//   fonctionnalité de l'ancien HTML/JS. Accès DOM paresseux → import sûr Node.

export function $(selecteur, racine) {
  return (racine || document).querySelector(selecteur);
}

export function $$(selecteur, racine) {
  return Array.from((racine || document).querySelectorAll(selecteur));
}

/** Échappe les 5 caractères sensibles pour insertion dans du HTML. Pur. */
export function echapperHtml(texte) {
  return String(texte)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Crée un élément avec attributs et enfants.
 * @param {string} tag
 * @param {object} [attrs]   { class, id, textContent, dataset:{}, ...attributs }
 * @param {Array<Node|string>} [enfants]
 */
export function creerElement(tag, attrs = {}, enfants = []) {
  const el = document.createElement(tag);
  for (const [cle, valeur] of Object.entries(attrs)) {
    if (cle === 'class' || cle === 'className') el.className = valeur;
    else if (cle === 'textContent') el.textContent = valeur;
    else if (cle === 'dataset') Object.assign(el.dataset, valeur);
    else if (cle in el && cle !== 'list') { try { el[cle] = valeur; } catch { el.setAttribute(cle, valeur); } }
    else el.setAttribute(cle, valeur);
  }
  for (const enfant of [].concat(enfants)) {
    if (enfant == null) continue;
    el.appendChild(typeof enfant === 'string' ? document.createTextNode(enfant) : enfant);
  }
  return el;
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

/** (Ré)installe un écouteur par type d'événement déjà enregistré. Inerte si
 *  aucune règle n'a encore été posée (cas de l'étape 1). */
export function installerDelegation(racine) {
  for (const type of regles.keys()) installerType(type, racine);
}
