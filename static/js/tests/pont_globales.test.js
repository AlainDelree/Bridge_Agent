// Garde-fou anti-rupture du pont (issue #632, raccord vague 1).
//
// POURQUOI CE TEST EXISTE
//   L'issue #632 a constaté qu'une fusion (#626 retirant basculerOnglet) avait
//   silencieusement cassé des appels appelerAncien(...) faits par un autre
//   module (#627/#628) vers des fonctions déjà retirées d'app.js — jusqu'à ce
//   qu'on les cherche à la main. Ce test automatise cette recherche : il
//   collecte tous les noms passés à appelerAncien(...) dans static/js/*.js
//   (littéraux, + ceux construits dynamiquement par initialisationsPour) et
//   vérifie que chacun correspond soit à une fonction déclarée dans app.js,
//   soit à une globale publiée par un module (window.xxx = ...).
//
// LIMITES ASSUMÉES (garde-fou simple, pas un analyseur statique complet) :
//   - une fonction imbriquée dans app.js matchant `function nom(` est comptée
//     comme "connue" même si elle n'est pas réellement globale (faux négatif
//     acceptable : on préfère ne pas bloquer sur un cas rare plutôt que
//     multiplier les faux positifs) ;
//   - seuls les appels appelerAncien('litteral', ...) sont vus statiquement ;
//     le seul appel dynamique connu (onglets.js, boucle sur initialisationsPour)
//     est couvert en appelant cette fonction pour chaque onglet réel (voir
//     templates/fragments/onglets.html).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { initialisationsPour } from '../onglets.js';

const ICI = path.dirname(fileURLToPath(import.meta.url));
const RACINE_JS = path.resolve(ICI, '..');            // static/js
const CHEMIN_APP_JS = path.join(RACINE_JS, 'app.js');

// Onglets réels (voir templates/fragments/onglets.html, data-onglet="…").
const NOMS_ONGLETS = ['resultats', 'attente', 'inbox', 'journal', 'config', 'ccw', 'creation'];

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

function extraireNoms(texte, motif) {
  const noms = new Set();
  const regex = new RegExp(motif, 'g');
  let m;
  while ((m = regex.exec(texte))) noms.add(m[1]);
  return noms;
}

test('appelerAncien : chaque nom appelé existe dans app.js ou est publié par un module', () => {
  const texteAppJs = fs.readFileSync(CHEMIN_APP_JS, 'utf8');
  const globalesAppJs = new Set([
    ...extraireNoms(texteAppJs, String.raw`function\s+([A-Za-z_$][\w$]*)\s*\(`),
    ...extraireNoms(texteAppJs, String.raw`window\.([A-Za-z_$][\w$]*)\s*=`),
  ]);

  const CHEMIN_PONT_JS = path.join(RACINE_JS, 'socle', 'pont.js');
  const fichiersModules = listerFichiersJs(RACINE_JS).filter((f) => f !== CHEMIN_APP_JS);
  const globalesModules = new Set();
  const nomsAppeles = new Set();
  for (const fichier of fichiersModules) {
    const texte = fs.readFileSync(fichier, 'utf8');
    for (const nom of extraireNoms(texte, String.raw`window\.([A-Za-z_$][\w$]*)\s*=`)) {
      globalesModules.add(nom);
    }
    // pont.js définit appelerAncien mais ne l'appelle jamais lui-même — son
    // seul « appelerAncien(...) » est un exemple en commentaire (nomFonction).
    if (fichier === CHEMIN_PONT_JS) continue;
    for (const nom of extraireNoms(texte, String.raw`appelerAncien\(\s*'([^']+)'`)) {
      nomsAppeles.add(nom);
    }
  }
  // Couvre l'unique appel dynamique (onglets.js : appelerAncien(fonction) dans
  // une boucle sur initialisationsPour(nom)).
  for (const onglet of NOMS_ONGLETS) {
    for (const nom of initialisationsPour(onglet)) nomsAppeles.add(nom);
  }

  const connues = new Set([...globalesAppJs, ...globalesModules]);
  const inconnues = [...nomsAppeles].filter((nom) => !connues.has(nom)).sort();

  assert.deepEqual(inconnues, [],
    'noms passés à appelerAncien sans fonction correspondante dans app.js ni publiée '
    + 'par un module — rupture de pont (voir issue #632) : ' + inconnues.join(', '));
});

// Pont dans l'AUTRE sens (issue #652) : depuis la sortie du formulaire « Nouvelle
// issue » dans static/js/creation.js, l'ancien app.js appelle encore certaines de
// ses fonctions PAR LEUR NOM (chargerTemplates au changement de projet ;
// afficherMessage pour les erreurs du bouton watcher) — elles ne sont donc plus
// définies dans app.js et DOIVENT être publiées en globales window.* par un
// module, sinon l'appel bare-name d'app.js lève un ReferenceError silencieux au
// runtime. Ce garde-fou vérifie explicitement cette publication (symétrique du
// test appelerAncien ci-dessus).
test('globales publiées par un module pour l\'ancien app.js (issue #652) : chargerTemplates, afficherMessage', () => {
  const RACINE_JS_2 = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
  const CHEMIN_APP = path.join(RACINE_JS_2, 'app.js');
  const texteApp = fs.readFileSync(CHEMIN_APP, 'utf8');

  const fichiersModules = listerFichiersJs(RACINE_JS_2).filter((f) => f !== CHEMIN_APP);
  const globalesModules = new Set();
  for (const fichier of fichiersModules) {
    for (const nom of extraireNoms(fs.readFileSync(fichier, 'utf8'),
      String.raw`window\.([A-Za-z_$][\w$]*)\s*=`)) {
      globalesModules.add(nom);
    }
  }

  // Fonctions du formulaire sorties d'app.js mais encore appelées par lui.
  const attendues = ['chargerTemplates', 'afficherMessage'];
  for (const nom of attendues) {
    // Le nom est bien appelé quelque part dans app.js…
    assert.ok(new RegExp(String.raw`\b${nom}\s*\(`).test(texteApp),
      `app.js n'appelle plus ${nom}() — mettre à jour ce garde-fou (issue #652).`);
    // …et n'y est plus défini (déplacé dans un module)…
    assert.ok(!new RegExp(String.raw`function\s+${nom}\s*\(`).test(texteApp),
      `${nom} redéfini dans app.js — le pont inverse n'a plus lieu d'être.`);
    // …donc un module DOIT le publier en globale window.*.
    assert.ok(globalesModules.has(nom),
      `${nom} appelé par app.js mais publié par aucun module (window.${nom} = …) `
      + '— rupture de pont inverse (issue #652).');
  }
});
