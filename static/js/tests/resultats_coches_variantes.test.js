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

// Inventaire par défaut (issue #788) pour les deux hashes fournis par
// window.hashesDeCommit ci-dessous — un fichier modifié, un fichier ajouté.
const INVENTAIRE_DEFAUT = {
  aaa1111: [{ chemin: 'app/issues.py', statut: 'modifié', ancien_chemin: null, ajoutees: 12, supprimees: 3 }],
  bbb2222: [{ chemin: 'static/js/app.js', statut: 'ajouté', ancien_chemin: null, ajoutees: 5, supprimees: 0 }],
};

// Reconstruit un environnement minimal « mode moderne » (clipboard.write) à
// chaque test : fetch mocké pour /issue, /diff, /inventaire-commit et
// /cases-cochees ; ancien code (pont) réduit à reponseCompleteCcl/
// hashesDeCommit/etatCommitsDeclares/majPastillesFiltres.
// Argument : soit un objet d'options (issue #788), soit directement la fonction
// diffParHash (issue #790) — les deux formes d'appel coexistent dans ce fichier.
//   - etatCommits : simule le retour de etatCommitsDeclares (app.js) — par
//     défaut des hashes exploitables, comme avant l'issue #788.
//   - inventaireParHash : réponse /inventaire-commit par hash (défaut ci-dessus).
//   - inventaireEnEchec : ensemble de hashes pour lesquels /inventaire-commit
//     doit échouer (404), pour vérifier que l'échec est signalé, pas avalé.
//   - diffParHash (issue #790) : fonction hash → contenu du diff, pour fabriquer
//     un diff volumineux (au-delà du seuil) dans les tests de téléchargement.
// Retourne la liste des téléchargements capturés (issue #790).
function fixerEnvironnement(options = {}) {
  const {
    etatCommits = { etat: 'hashes', hashes: ['aaa1111', 'bbb2222'] },
    inventaireParHash = INVENTAIRE_DEFAUT,
    inventaireEnEchec = new Set(),
    diffParHash,
  } = typeof options === 'function' ? { diffParHash: options } : options;
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
  window.hashesDeCommit = () => etatCommits.hashes;
  window.etatCommitsDeclares = () => etatCommits;
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
    if (url.startsWith('/inventaire-commit/')) {
      const hash = decodeURIComponent(url.slice(url.lastIndexOf('/') + 1));
      if (inventaireEnEchec.has(hash)) {
        return { ok: false, status: 404, text: async () => JSON.stringify({ erreur: 'Commit ' + hash + ' introuvable.' }) };
      }
      return { ok: true, text: async () => JSON.stringify({ fichiers: inventaireParHash[hash] || [] }) };
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

test('case à cocher (basculer) : copie le résultat SEUL, sans diff, + inventaire des fichiers (#788)', async () => {
  fixerEnvironnement();
  const copie = attendreProchaineCopie();
  resultatsCoches.basculer(evenementCase(), PROJET, 101);
  const texte = await copie;
  assert.match(texte, /Issue #787 — projet_test_787 — Titre/);   // ligne d'identité (#723)
  assert.match(texte, /Corps du rapport pour #787/);
  assert.doesNotMatch(texte, /DIFF-/, 'la case ne doit PAS copier le diff (issue #787)');
  assert.match(texte, /===== Fichiers modifiés =====/);
  assert.match(texte, /modifié {2}app\/issues\.py {2}\(\+12 -3\)/);
  assert.match(texte, /ajouté {2}static\/js\/app\.js {2}\(\+5 -0\)/);
});

test('badge ✅ (copierReponseBadge) : copie le résultat SEUL, sans diff, + inventaire des fichiers', async () => {
  fixerEnvironnement();
  const copie = attendreProchaineCopie();
  resultatsCoches.copierReponseBadge(evenementBadge(), PROJET, 102);
  const texte = await copie;
  assert.match(texte, /Corps du rapport pour #787/);
  assert.doesNotMatch(texte, /DIFF-/);
  assert.match(texte, /===== Fichiers modifiés =====/);
});

test('badge Diff (copierDiffBadge) : copie le diff SEUL, sans le résultat ni identité ni inventaire', async () => {
  fixerEnvironnement();
  const copie = attendreProchaineCopie();
  resultatsCoches.copierDiffBadge(evenementBadge(), PROJET, 103);
  const texte = await copie;
  assert.match(texte, /DIFF-aaa1111/);
  assert.match(texte, /DIFF-bbb2222/);
  assert.doesNotMatch(texte, /Corps du rapport/);
  assert.doesNotMatch(texte, /Issue #787/);   // pas d'identité pour la variante diff (#723)
  assert.doesNotMatch(texte, /Fichiers modifiés/, 'le bouton Diff ne doit pas changer (issue #788, point 4)');
});

test('badge All (copierAllBadge) : copie le résultat ET le diff, sans inventaire (comportement inchangé)', async () => {
  fixerEnvironnement();
  const copie = attendreProchaineCopie();
  resultatsCoches.copierAllBadge(evenementBadge(), PROJET, 104);
  const texte = await copie;
  assert.match(texte, /Issue #787 — projet_test_787 — Titre/);
  assert.match(texte, /Corps du rapport pour #787/);
  assert.match(texte, /DIFF-aaa1111/);
  assert.match(texte, /DIFF-bbb2222/);
  assert.doesNotMatch(texte, /Fichiers modifiés/, 'le bouton All ne doit pas changer (issue #788, point 4)');
});

// ─── Issue #788 : section « Fichiers modifiés » — les 3 cas à distinguer ─────

test('case à cocher : ligne « Commits » dit « aucun » (lecture seule) → PAS de section, pas d\'alerte', async () => {
  fixerEnvironnement({ etatCommits: { etat: 'aucun', hashes: [] } });
  const copie = attendreProchaineCopie();
  resultatsCoches.basculer(evenementCase(), PROJET, 105);
  const texte = await copie;
  assert.match(texte, /Corps du rapport pour #787/);
  assert.doesNotMatch(texte, /Fichiers modifiés/);
});

test('case à cocher : ligne « Commits » absente/non reconnue → anomalie signalée dans le texte copié', async () => {
  fixerEnvironnement({ etatCommits: { etat: 'absente', hashes: [] } });
  const copie = attendreProchaineCopie();
  resultatsCoches.basculer(evenementCase(), PROJET, 106);
  const texte = await copie;
  assert.match(texte, /===== Fichiers modifiés =====/);
  assert.match(texte, /absente ou non reconnue/);
});

test('case à cocher : commit introuvable côté serveur → échec signalé dans la section, jamais en silence', async () => {
  fixerEnvironnement({ inventaireEnEchec: new Set(['bbb2222']) });
  const copie = attendreProchaineCopie();
  resultatsCoches.basculer(evenementCase(), PROJET, 107);
  const texte = await copie;
  assert.match(texte, /===== Fichiers modifiés =====/);
  assert.match(texte, /modifié {2}app\/issues\.py {2}\(\+12 -3\)/);   // le commit en succès reste listé
  assert.match(texte, /⚠ Commit bbb2222 : inventaire impossible — Commit bbb2222 introuvable\./);
});

test('case à cocher : commit de sauvegarde vide (aucun fichier) → mention explicite, pas de silence', async () => {
  fixerEnvironnement({
    etatCommits: { etat: 'hashes', hashes: ['ccc3333'] },
    inventaireParHash: { ccc3333: [] },
  });
  const copie = attendreProchaineCopie();
  resultatsCoches.basculer(evenementCase(), PROJET, 108);
  const texte = await copie;
  assert.match(texte, /===== Fichiers modifiés =====/);
  assert.match(texte, /aucun fichier/);
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
