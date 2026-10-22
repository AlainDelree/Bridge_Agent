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

import { resultatsCoches } from '../resultats_coches.js';

const PROJET = 'projet_test_787';

// Reconstruit un environnement minimal « mode moderne » (clipboard.write) à
// chaque test : fetch mocké pour /issue, /diff et /cases-cochees ; ancien code
// (pont) réduit à reponseCompleteCcl/hashesDeCommit/majPastillesFiltres.
function fixerEnvironnement() {
  global.document = { getElementById: () => null, querySelectorAll: () => [] };
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
      return { ok: true, text: async () => JSON.stringify({ diff: 'DIFF-' + hash }) };
    }
    if (url.startsWith('/cases-cochees/')) {
      return { ok: true, text: async () => '' };
    }
    throw new Error('URL non mockée dans ce test : ' + url);
  };
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
