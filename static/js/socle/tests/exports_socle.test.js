// Garde-fou anti-rupture des briques du socle (issue #653, suite #632/#646).
//
// POURQUOI CE TEST EXISTE
//   L'issue #646 (« balayage final ») a retiré dom.$/$$/creerElement en
//   affirmant un « grep exhaustif » sans appelant — alors que dom.$ était
//   utilisé à 17 endroits dans panneau_lateral.js. Le grep manuel de #646
//   cherchait un style d'appel précis (`dom.$(`) et l'a raté. Ce test
//   automatise la vérification, sur le modèle de pont_globales.test.js
//   (#632) : il scanne tous les static/js/*.js à la recherche de
//   `<brique>.<nom>` et vérifie que chaque nom utilisé est bien exposé par
//   le module correspondant.
//
// LIMITES ASSUMÉES (garde-fou simple, pas un analyseur statique complet) :
//   - dom.js et persistance.js sont toujours importés en espace de noms
//     (`import * as dom …`) : leurs exports top-level (`export function`/
//     `export const`) correspondent 1:1 aux noms utilisables. Cas simple.
//   - api.js et store.js sont importés comme UN SEUL export nommé (`import
//     { api } from …`) qui désigne un objet ; le risque équivalent est
//     qu'une CLÉ de cet objet disparaisse. On extrait ces clés au niveau
//     supérieur de l'objet littéral (une clé par ligne, format déjà en
//     vigueur dans ces fichiers) plutôt que par un vrai parseur JS.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ICI = path.dirname(fileURLToPath(import.meta.url));
const RACINE_JS = path.resolve(ICI, '..', '..');   // static/js
const RACINE_SOCLE = path.resolve(ICI, '..');       // static/js/socle

function listerFichiersJs(dossier) {
  const trouves = [];
  for (const entree of fs.readdirSync(dossier, { withFileTypes: true })) {
    if (entree.name === 'tests') continue;
    const chemin = path.join(dossier, entree.name);
    if (entree.isDirectory()) trouves.push(...listerFichiersJs(chemin));
    else if (entree.name.endsWith('.js')) trouves.push(chemin);
  }
  return trouves;
}

// Retire les lignes d'import (elles contiennent souvent '<brique>.js' dans le
// chemin, ce qui matcherait faussement `<brique>\.(\w+)` -> 'js') ainsi que
// les commentaires (ligne // et bloc /* */), qui mentionnent parfois une
// tranche du store en prose (ex. « store.ongletActif ») sans être du code.
function nettoyerPourScan(texte) {
  return texte
    .split('\n')
    .filter((ligne) => !/^\s*import\b/.test(ligne))
    .join('\n')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\/\/.*$/gm, '');
}

function extraireUsages(texteNettoye, prefixe) {
  const noms = new Set();
  const regex = new RegExp(`\\b${prefixe}\\.([A-Za-z_$][\\w$]*)`, 'g');
  let m;
  while ((m = regex.exec(texteNettoye))) noms.add(m[1]);
  return noms;
}

function exportsSimplesDe(texte) {
  const noms = new Set();
  for (const m of texte.matchAll(/^export function\s+([A-Za-z_$][\w$]*)/gm)) noms.add(m[1]);
  for (const m of texte.matchAll(/^export const\s+([A-Za-z_$][\w$]*)/gm)) noms.add(m[1]);
  for (const m of texte.matchAll(/^export class\s+([A-Za-z_$][\w$]*)/gm)) noms.add(m[1]);
  return noms;
}

// Isole le corps { ... } d'une déclaration d'objet littéral (comptage
// d'accolades pour trouver la fermeture correspondante, même si le corps
// contient des objets imbriqués).
function corpsObjetLitteral(texte, declaration) {
  const debut = texte.indexOf(declaration);
  if (debut === -1) return '';
  const ouvrante = texte.indexOf('{', debut);
  let profondeur = 0;
  let i = ouvrante;
  for (; i < texte.length; i++) {
    if (texte[i] === '{') profondeur++;
    else if (texte[i] === '}') { profondeur--; if (profondeur === 0) break; }
  }
  return texte.slice(ouvrante + 1, i);
}

// Clés déclarées au niveau supérieur d'un objet littéral (une par ligne,
// `nom: valeur,` ou `nom,` en raccourci, ou `nom(...) { ... }` en méthode) —
// ne descend pas dans les objets/fonctions imbriqués car la capture exige
// que le nom commence la ligne (après espaces).
function clesDeNiveauSuperieur(corps) {
  const noms = new Set();
  for (const m of corps.matchAll(/^\s*([A-Za-z_$][\w$]*)\s*[:,(]/gm)) noms.add(m[1]);
  return noms;
}

const FICHIERS = listerFichiersJs(RACINE_JS);
const TEXTES_NETTOYES = FICHIERS.map((f) => nettoyerPourScan(fs.readFileSync(f, 'utf8')));

function nomsUtilisesPartout(prefixe) {
  const noms = new Set();
  for (const texte of TEXTES_NETTOYES) {
    for (const nom of extraireUsages(texte, prefixe)) noms.add(nom);
  }
  return noms;
}

function verifierExpose(prefixe, exposes) {
  const utilises = nomsUtilisesPartout(prefixe);
  const inconnus = [...utilises].filter((nom) => !exposes.has(nom)).sort();
  assert.deepEqual(inconnus, [],
    `noms utilisés via ${prefixe}.<nom> sans correspondre à un export de ${prefixe}.js — `
    + 'rupture de type dom.$ (voir issue #653) : ' + inconnus.join(', '));
}

test('dom.<nom> : chaque nom utilisé est exporté par socle/dom.js', () => {
  const texteDom = fs.readFileSync(path.join(RACINE_SOCLE, 'dom.js'), 'utf8');
  verifierExpose('dom', exportsSimplesDe(texteDom));
});

test('persistance.<nom> : chaque nom utilisé est exporté par socle/persistance.js', () => {
  const textePersistance = fs.readFileSync(path.join(RACINE_SOCLE, 'persistance.js'), 'utf8');
  verifierExpose('persistance', exportsSimplesDe(textePersistance));
});

test('api.<nom> : chaque nom utilisé est une clé de l\'objet exporté par socle/api.js', () => {
  const texteApi = fs.readFileSync(path.join(RACINE_SOCLE, 'api.js'), 'utf8');
  const corps = corpsObjetLitteral(texteApi, 'export const api = {');
  verifierExpose('api', clesDeNiveauSuperieur(corps));
});

test('store.<nom> : chaque nom utilisé est une clé de l\'objet exporté par socle/store.js', () => {
  const texteStore = fs.readFileSync(path.join(RACINE_SOCLE, 'store.js'), 'utf8');
  const retourCreerStore = texteStore.match(/return\s*{\s*([^}]+)}\s*;/);
  const clesCreerStore = new Set(
    (retourCreerStore ? retourCreerStore[1] : '').split(',').map((s) => s.trim()).filter(Boolean));
  const corpsAidesIssues = corpsObjetLitteral(texteStore, 'const aidesIssues = {');
  const clesAidesIssues = clesDeNiveauSuperieur(corpsAidesIssues);
  verifierExpose('store', new Set([...clesCreerStore, ...clesAidesIssues]));
});

// Cas explicite issue #653 : panneau_lateral.js utilise bien dom.$, et dom.js
// l'exporte bien — la régression #646 aurait été attrapée par ce seul test.
test('cas explicite #653 : panneau_lateral.js utilise dom.$, dom.js l\'exporte', () => {
  const textePanneau = fs.readFileSync(path.join(RACINE_JS, 'panneau_lateral.js'), 'utf8');
  assert.ok(/\bdom\.\$\(/.test(textePanneau),
    'panneau_lateral.js ne semble plus appeler dom.$ — ce test doit être mis à jour '
    + 'si cet usage a été délibérément retiré');
  const texteDom = fs.readFileSync(path.join(RACINE_SOCLE, 'dom.js'), 'utf8');
  assert.ok(exportsSimplesDe(texteDom).has('$'), 'dom.js n\'exporte plus $');
});
