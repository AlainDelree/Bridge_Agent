// Test du contenu des 3 variantes de copie (case à cocher / badges Diff / All),
// issue #787 : cocher la case copiait le résultat ET le diff, alors qu'elle ne
// doit copier que le résultat seul (comportement voulu depuis l'origine, #636).
//
// CAUSE ÉTABLIE (voir le rapport de clôture de l'issue) : resultats_coches.js
// appelait la MAUVAISE variante dans basculer() — texteAll (résultat + diff)
// au lieu de texteReponse (résultat seul). La variante texteReponse elle-même
// n'a jamais ajouté de diff ; le défaut est resté invisible deux mois car la
// reconnaissance des numéros de commit (issue #784) était cassée, si bien que
// texteAll ne trouvait jamais de diff à ajouter — une fois #784 corrigé,
// texteAll (toujours appelé par erreur par la case) a commencé à en ajouter.
//
// Ce test exerce le VRAI chemin de production (basculer/copierReponseBadge/
// copierAllBadge/copierDiffBadge → lancerCopie → copierModerne → clipboard),
// pour couvrir la connexion entre chaque point d'entrée et sa variante — pas
// seulement les fonctions pures déjà testées dans resultats_coches.test.js.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { resultatsCoches, SEUIL_LIGNES_VOLUMINEUX } from '../resultats_coches.js';

const PROJET = 'projet_test_787';

// Reconstruit un environnement minimal « mode moderne » (clipboard.write) à
// chaque test : fetch mocké pour /issue, /diff et /cases-cochees ; ancien code
// (pont) réduit à reponseCompleteCcl/hashesDeCommit/majPastillesFiltres.
// `diffParHash` (issue #790) : fonction hash → contenu du diff, pour fabriquer
// un diff volumineux (au-delà du seuil) dans les tests de téléchargement.
function fixerEnvironnement(diffParHash) {
  const telechargements = [];
  global.document = {
    getElementById: () => null,
    querySelectorAll: () => [],
    // Mock minimal du lien <a download> (issue #790) : capture href/download
    // au moment du click plutôt que de vraiment manipuler le DOM.
    createElement: (tag) => ({
      tag,
      click() { if (this.tag === 'a') telechargements.push({ nom: this.download, href: this.href }); },
    }),
    body: { appendChild: () => {}, removeChild: () => {} },
    querySelector: () => null,
  };
  global.URL = { createObjectURL: () => 'blob:mock', revokeObjectURL: () => {} };
  global.window = globalThis;
  window.isSecureContext = true;
  window.reponseCompleteCcl = (it) => 'Corps du rapport pour #' + it.number;
  window.hashesDeCommit = () => ['aaa1111', 'bbb2222'];
  window.majPastillesFiltres = () => {};
  global.ClipboardItem = class { constructor(data) { this.data = data; } };
  global.fetch = async (url) => {
    if (url.startsWith('/issue/')) {
      return { ok: true, text: async () => JSON.stringify({ number: 787, title: 'Titre', labels: [] }) };
    }
    if (url.startsWith('/diff/')) {
      const hash = decodeURIComponent(url.slice(url.lastIndexOf('/') + 1));
      const diff = diffParHash ? diffParHash(hash) : 'DIFF-' + hash;
      return { ok: true, text: async () => JSON.stringify({ diff }) };
    }
    if (url.startsWith('/cases-cochees/')) {
      return { ok: true, text: async () => '' };
    }
    throw new Error('URL non mockée dans ce test : ' + url);
  };
  return telechargements;
}

// Arme navigator.clipboard.write pour résoudre dès le PROCHAIN appel — chaque
// test pose sa propre promesse juste avant de déclencher l'action, pas de
// sleep ni de polling.
function attendreProchaineCopie() {
  return new Promise((resolve) => {
    global.navigator = {
      clipboard: {
        write: async (items) => {
          const blob = items[0].data['text/plain'];
          resolve(await blob.text());
        },
      },
    };
  });
}

function evenementCase(numero) {
  return { target: { checked: true, closest: () => null } };
}

function evenementBadge() {
  return { stopPropagation() {}, currentTarget: { textContent: '', title: '' } };
}

test('case à cocher (basculer) : copie le résultat SEUL, sans diff', async () => {
  fixerEnvironnement();
  const copie = attendreProchaineCopie();
  resultatsCoches.basculer(evenementCase(), PROJET, 101);
  const texte = await copie;
  assert.match(texte, /Issue #787 — projet_test_787 — Titre/);   // ligne d'identité (#723)
  assert.match(texte, /Corps du rapport pour #787/);
  assert.doesNotMatch(texte, /DIFF-/, 'la case ne doit PAS copier le diff (issue #787)');
});

test('badge ✅ (copierReponseBadge) : copie le résultat SEUL, sans diff', async () => {
  fixerEnvironnement();
  const copie = attendreProchaineCopie();
  resultatsCoches.copierReponseBadge(evenementBadge(), PROJET, 102);
  const texte = await copie;
  assert.match(texte, /Corps du rapport pour #787/);
  assert.doesNotMatch(texte, /DIFF-/);
});

test('badge Diff (copierDiffBadge) : copie le diff SEUL, sans le résultat ni identité', async () => {
  fixerEnvironnement();
  const copie = attendreProchaineCopie();
  resultatsCoches.copierDiffBadge(evenementBadge(), PROJET, 103);
  const texte = await copie;
  assert.match(texte, /DIFF-aaa1111/);
  assert.match(texte, /DIFF-bbb2222/);
  assert.doesNotMatch(texte, /Corps du rapport/);
  assert.doesNotMatch(texte, /Issue #787/);   // pas d'identité pour la variante diff (#723)
});

test('badge All (copierAllBadge) : copie le résultat ET le diff', async () => {
  fixerEnvironnement();
  const copie = attendreProchaineCopie();
  resultatsCoches.copierAllBadge(evenementBadge(), PROJET, 104);
  const texte = await copie;
  assert.match(texte, /Issue #787 — projet_test_787 — Titre/);
  assert.match(texte, /Corps du rapport pour #787/);
  assert.match(texte, /DIFF-aaa1111/);
  assert.match(texte, /DIFF-bbb2222/);
});

// ─── Diff/All au-delà du seuil de lignes (issue #790) : fichier, pas de copie ──
const DIFF_VOLUMINEUX = Array(SEUIL_LIGNES_VOLUMINEUX + 10).fill('+ligne').join('\n');

// clipboard.write ne doit JAMAIS être appelé dans ces tests — poser une sentinelle
// qui échoue le test si elle est sollicitée, au lieu d'attendre une résolution
// qui ne viendra jamais.
function interdireCopiePressePapier() {
  global.navigator = {
    clipboard: { write: async () => { throw new Error('clipboard.write ne doit pas être appelé (diff volumineux, #790)'); } },
  };
}

// Attend que le téléchargement (asynchrone : fetch /issue puis /diff) ait eu
// lieu, en laissant la chaîne de promesses internes se dérouler — pas de
// hook exposé par le module pour l'attendre directement.
async function attendreTelechargement(telechargements, tentativesMax = 50) {
  for (let i = 0; i < tentativesMax && telechargements.length === 0; i++) {
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  return telechargements[0];
}

test('badge Diff, diff volumineux (> seuil) : fichier téléchargé, pas de copie', async () => {
  const telechargements = fixerEnvironnement((hash) => (hash === 'aaa1111' ? DIFF_VOLUMINEUX : 'DIFF-' + hash));
  interdireCopiePressePapier();
  resultatsCoches.copierDiffBadge(evenementBadge(), PROJET, 201);
  const fichier = await attendreTelechargement(telechargements);
  assert.ok(fichier, 'le téléchargement attendu n\'a pas eu lieu');
  assert.equal(fichier.nom, PROJET + '-201-diff.txt');
  assert.equal(telechargements.length, 1);
});

test('badge All, texte volumineux (> seuil) : fichier téléchargé, pas de copie', async () => {
  const telechargements = fixerEnvironnement((hash) => (hash === 'aaa1111' ? DIFF_VOLUMINEUX : 'DIFF-' + hash));
  interdireCopiePressePapier();
  resultatsCoches.copierAllBadge(evenementBadge(), PROJET, 202);
  const fichier = await attendreTelechargement(telechargements);
  assert.ok(fichier, 'le téléchargement attendu n\'a pas eu lieu');
  assert.equal(fichier.nom, PROJET + '-202-all.txt');
});

test('badge Diff, diff COURT (sous le seuil) : copie inchangée, aucun téléchargement', async () => {
  const telechargements = fixerEnvironnement();
  const copie = attendreProchaineCopie();
  resultatsCoches.copierDiffBadge(evenementBadge(), PROJET, 203);
  const texte = await copie;
  assert.match(texte, /DIFF-aaa1111/);
  assert.equal(telechargements.length, 0, 'un diff court ne doit générer aucun fichier');
});
