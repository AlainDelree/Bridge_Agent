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

import { resultatsCoches, SEUIL_LIGNES_VOLUMINEUX, MESSAGE_PREPARATION_TROP_LONGUE } from '../resultats_coches.js';
import { store } from '../socle/store.js';

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
// Éléments DOM créés durant le test courant (issue #791) : réinitialisé à
// chaque appel de fixerEnvironnement, assez riche pour que toasts.js (toast
// d'échec avec texteSecours, voir définirContenuToast) s'exécute sans lever,
// afin de pouvoir inspecter son contenu (zoneSecoursToast/texteDesToasts).
let elementsCrees = [];

function fixerEnvironnement(options = {}) {
  const {
    etatCommits = { etat: 'hashes', hashes: ['aaa1111', 'bbb2222'] },
    inventaireParHash = INVENTAIRE_DEFAUT,
    inventaireEnEchec = new Set(),
    diffParHash,
  } = typeof options === 'function' ? { diffParHash: options } : options;
  const telechargements = [];
  elementsCrees = [];
  global.document = {
    getElementById: () => null,
    querySelectorAll: () => [],
    // Mock minimal du lien <a download> (issue #790) : capture href/download
    // au moment du click plutôt que de vraiment manipuler le DOM. Assez de
    // DOM (classList/appendChild/addEventListener) pour que toasts.js
    // construise un toast d'échec sans lever (issue #791).
    createElement: (tag) => {
      const el = {
        tag,
        textContent: '',
        className: '',
        classList: { add() {}, remove() {} },
        appendChild() {},
        addEventListener() {},
        setAttribute() {},
        remove() {},
        select() {},
        click() { if (this.tag === 'a') telechargements.push({ nom: this.download, href: this.href }); },
      };
      elementsCrees.push(el);
      return el;
    },
    body: { appendChild: () => {}, removeChild: () => {} },
    querySelector: () => null,
  };
  global.URL = { createObjectURL: () => 'blob:mock', revokeObjectURL: () => {} };
  global.requestAnimationFrame = (cb) => cb();
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

// ─── Issue #808 : état « windows » — inventaire par construction impossible
//     depuis le ThinkPad (commits sur le PC fixe) → texte neutre, AUCUNE
//     requête d'inventaire au serveur.

test('case à cocher : issue Windows (etat « windows », avec hashes) → texte neutre, AUCUNE requête d\'inventaire', async () => {
  fixerEnvironnement({ etatCommits: { etat: 'windows', hashes: ['aaa1111', 'bbb2222'] } });
  let requeteInventaire = false;
  const fetchOriginal = global.fetch;
  global.fetch = async (url, ...reste) => {
    if (url.startsWith('/inventaire-commit/')) requeteInventaire = true;
    return fetchOriginal(url, ...reste);
  };
  const copie = attendreProchaineCopie();
  resultatsCoches.basculer(evenementCase(), PROJET, 109);
  const texte = await copie;
  assert.equal(requeteInventaire, false,
    'aucune requête /inventaire-commit ne doit être faite pour une issue Windows (issue #808)');
  assert.match(texte, /===== Fichiers modifiés =====/);
  assert.match(texte, /ThinkPad/);
  assert.match(texte, /_ccw/);
  assert.doesNotMatch(texte, /⚠/, 'pas un cas d\'anomalie — aucun symbole d\'alerte');
});

test('case à cocher : issue Windows (etat « windows », SANS hashes) → même texte neutre, AUCUNE requête d\'inventaire', async () => {
  fixerEnvironnement({ etatCommits: { etat: 'windows', hashes: [] } });
  let requeteInventaire = false;
  const fetchOriginal = global.fetch;
  global.fetch = async (url, ...reste) => {
    if (url.startsWith('/inventaire-commit/')) requeteInventaire = true;
    return fetchOriginal(url, ...reste);
  };
  const copie = attendreProchaineCopie();
  resultatsCoches.basculer(evenementCase(), PROJET, 110);
  const texte = await copie;
  assert.equal(requeteInventaire, false,
    'aucune requête /inventaire-commit ne doit être faite pour une issue Windows (issue #808)');
  assert.match(texte, /===== Fichiers modifiés =====/);
  assert.doesNotMatch(texte, /⚠/);
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

// Zone <textarea> de secours (texteSecours, issue #782) du dernier toast
// d'échec affiché — voir definirContenuToast dans toasts.js.
function zoneSecoursToast() {
  return elementsCrees.find((e) => e.className === 'socle-toast-secours');
}

// Textes de tous les toasts affichés jusqu'ici (span interne sans classe,
// voir definirContenuToast) — pour vérifier qu'aucun n'annonce un fichier
// téléchargé (issue #791).
function texteDesToasts() {
  return elementsCrees.filter((e) => e.tag === 'span' && e.className === '').map((e) => e.textContent);
}

// Attend l'apparition de la zone de secours d'un toast d'échec (asynchrone,
// comme le téléchargement) — même principe que attendreTelechargement.
async function attendreZoneSecours(tentativesMax = 50) {
  for (let i = 0; i < tentativesMax && !zoneSecoursToast(); i++) {
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  return zoneSecoursToast();
}

// Ligne de détail technique (detailTechnique, issue #824) du dernier toast
// d'échec affiché — voir definirContenuToast dans toasts.js.
function detailToast() {
  return elementsCrees.find((e) => e.className === 'socle-toast-detail');
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

// ─── Échec du téléchargement au-delà du seuil (issue #791) : pas de faux
//     « fichier téléchargé », échec signalé via le mécanisme existant ────────

test('badge Diff, diff volumineux (> seuil) MAIS téléchargement en échec : aucun "fichier téléchargé", échec signalé avec le texte complet', async () => {
  const telechargements = fixerEnvironnement((hash) => (hash === 'aaa1111' ? DIFF_VOLUMINEUX : 'DIFF-' + hash));
  interdireCopiePressePapier();
  // Simule l'échec de la création du lien de téléchargement (ex. Blob/URL
  // indisponible) — declencherTelechargement le capture et renvoie faux.
  global.URL.createObjectURL = () => { throw new Error('échec simulé de URL.createObjectURL'); };
  resultatsCoches.copierDiffBadge(evenementBadge(), PROJET, 301);
  const zone = await attendreZoneSecours();
  assert.equal(telechargements.length, 0, 'aucun téléchargement n\'a réellement eu lieu');
  assert.ok(zone, 'l\'échec doit être signalé via le mécanisme de secours existant (issue #782)');
  assert.match(zone.value, /Diff aaa1111/, 'le texte complet doit rester accessible pour une copie manuelle');
  const messages = texteDesToasts();
  assert.ok(
    !messages.some((m) => /téléchargé/.test(m)),
    'aucun message ne doit annoncer un fichier téléchargé puisque le téléchargement a échoué',
  );
});

test('badge All, texte volumineux (> seuil) MAIS téléchargement en échec : aucun "fichier téléchargé", échec signalé avec le texte complet', async () => {
  const telechargements = fixerEnvironnement((hash) => (hash === 'aaa1111' ? DIFF_VOLUMINEUX : 'DIFF-' + hash));
  interdireCopiePressePapier();
  global.URL.createObjectURL = () => { throw new Error('échec simulé de URL.createObjectURL'); };
  resultatsCoches.copierAllBadge(evenementBadge(), PROJET, 302);
  const zone = await attendreZoneSecours();
  assert.equal(telechargements.length, 0, 'aucun téléchargement n\'a réellement eu lieu');
  assert.ok(zone, 'l\'échec doit être signalé via le mécanisme de secours existant (issue #782)');
  assert.match(zone.value, /Corps du rapport pour #787/, 'le texte complet doit rester accessible pour une copie manuelle');
  const messages = texteDesToasts();
  assert.ok(
    !messages.some((m) => /téléchargé/.test(m)),
    'aucun message ne doit annoncer un fichier téléchargé puisque le téléchargement a échoué',
  );
});

test('badge Diff, diff volumineux (> seuil) ET téléchargement en SUCCÈS : le toast annonce bien un fichier téléchargé (comportement inchangé)', async () => {
  fixerEnvironnement((hash) => (hash === 'aaa1111' ? DIFF_VOLUMINEUX : 'DIFF-' + hash));
  interdireCopiePressePapier();
  resultatsCoches.copierDiffBadge(evenementBadge(), PROJET, 303);
  // Le toast de succès (comme la zone de secours) est posé de façon
  // asynchrone — même attente que pour la zone de secours.
  let messages = texteDesToasts();
  for (let i = 0; i < 50 && !messages.some((m) => /téléchargé/.test(m)); i++) {
    await new Promise((resolve) => setTimeout(resolve, 5));
    messages = texteDesToasts();
  }
  assert.ok(messages.some((m) => /téléchargé/.test(m)), 'le succès du téléchargement doit toujours être annoncé');
  assert.ok(!zoneSecoursToast(), 'aucune zone de secours ne doit apparaître en cas de succès');
});

// ─── Issue #824 : la cause réelle de l'échec de copie atteint l'affichage ────

test('badge ✅, échec RÉEL de navigator.clipboard.write (NotAllowedError) : le toast ET la console reçoivent la cause, la zone de secours reste inchangée, le message principal devient celui du geste expiré (issue #832 point 4b, remplace le message générique de #824)', async () => {
  fixerEnvironnement();
  const avertissements = [];
  const warnOriginal = console.warn;
  console.warn = (...args) => avertissements.push(args.join(' '));
  global.navigator = {
    clipboard: {
      write: async () => {
        throw Object.assign(new Error('The request is not allowed.'), { name: 'NotAllowedError' });
      },
    },
  };
  try {
    resultatsCoches.copierReponseBadge(evenementBadge(), PROJET, 401);
    const zone = await attendreZoneSecours();
    assert.ok(zone, 'le texte complet doit rester accessible (texteSecours, issue #782, inchangé)');
    assert.match(zone.value, /Corps du rapport pour #787/);
    const detail = detailToast();
    assert.ok(detail, 'une ligne de détail technique doit être ajoutée au toast (issue #824)');
    assert.match(detail.textContent, /NotAllowedError/);
    assert.match(detail.textContent, /The request is not allowed\./);
    assert.match(detail.textContent, /mode=moderne/);
    assert.match(detail.textContent, /délai=\d+ ms/);
    assert.ok(
      avertissements.some((a) => a.includes('NotAllowedError') && a.includes('The request is not allowed.')),
      'la cause doit être journalisée par console.warn (jusqu\'ici ignorée, issue #824)',
    );
    const messages = texteDesToasts();
    assert.ok(
      messages.some((m) => m === 'Préparation trop longue pour le presse-papier : copie manuelle ci-dessous '
        + '(Ctrl+C) ; le texte est maintenant prêt, décoche puis recoche la case.'),
      'NotAllowedError est un geste expiré (issue #832 point 4) : le message principal devient actionnable');
  } finally {
    console.warn = warnOriginal;
  }
});

test('badge Diff, téléchargement en échec (echec(undefined, t), sans exception) : détail « (aucune exception) », pas de confusion avec une vraie erreur', async () => {
  const telechargements = fixerEnvironnement((hash) => (hash === 'aaa1111' ? DIFF_VOLUMINEUX : 'DIFF-' + hash));
  interdireCopiePressePapier();
  global.URL.createObjectURL = () => { throw new Error('échec simulé de URL.createObjectURL'); };
  resultatsCoches.copierDiffBadge(evenementBadge(), PROJET, 402);
  await attendreZoneSecours();
  assert.equal(telechargements.length, 0);
  const detail = detailToast();
  assert.ok(detail, 'une ligne de détail doit être ajoutée même sans exception (issue #824)');
  assert.match(detail.textContent, /\(aucune exception\)/);
  assert.doesNotMatch(detail.textContent, /undefined/);
  assert.match(detail.textContent, /mode=moderne/);
});

// ─── Issue #832 : préparation à l'avance en mode moderne ─────────────────────
// (expiration du geste dans Firefox — voir le rapport de l'issue). Intercepte
// /issue pour contrôler, par numéro, le moment où le fetch de préparation
// résout — permet de simuler une préparation LENTE encore en vol.
function intercepterFetchIssue(numeroLent) {
  const fetchOriginal = global.fetch;
  const comptes = {};
  let resolveur;
  global.fetch = async (url, ...reste) => {
    if (url.startsWith('/issue/')) {
      const numero = Number(decodeURIComponent(url.slice(url.lastIndexOf('/') + 1)));
      comptes[numero] = (comptes[numero] || 0) + 1;
      if (numero === numeroLent) {
        return new Promise((resolve) => { resolveur = () => resolve(fetchOriginal(url, ...reste)); });
      }
    }
    return fetchOriginal(url, ...reste);
  };
  return { comptes, debloquer: () => resolveur() };
}

async function attendreQue(predicat, tentativesMax = 100) {
  for (let i = 0; i < tentativesMax && !predicat(); i++) {
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  return predicat();
}

test('chemin rapide (issue #832 pt.2) : un texte déjà préparé et valide est écrit sans attendre la préparation lente d\'une AUTRE copie en cours', async () => {
  fixerEnvironnement({ etatCommits: { etat: 'aucun', hashes: [] } });
  const NUMERO_LENT = 501001;
  const NUMERO_RAPIDE = 501002;
  const { comptes, debloquer } = intercepterFetchIssue(NUMERO_LENT);

  const ecritures = [];
  global.navigator = {
    clipboard: {
      write: async (items) => { ecritures.push(await items[0].data['text/plain'].text()); },
    },
  };

  // Préchargement en tâche de fond de NUMERO_RAPIDE (variante 'reponse').
  store.remplacerIssues([
    { projet: PROJET, number: NUMERO_RAPIDE, title: 'Rapide', createdAt: '2026-01-01T00:00:00Z', state: 'OPEN', labels: [] },
  ]);
  resultatsCoches.precharderVisibles();
  assert.ok(await attendreQue(() => comptes[NUMERO_RAPIDE] === 1), 'le préchargement de NUMERO_RAPIDE doit avoir fetché /issue');
  await new Promise((resolve) => setTimeout(resolve, 20));   // laisse memoriserTextePrepare s'exécuter

  // Lance une copie LENTE (préparation en vol, fetch bloqué), PUIS une copie
  // RAPIDE (texte déjà préparé) : la seconde ne doit pas attendre la première.
  resultatsCoches.copierReponseBadge(evenementBadge(), PROJET, NUMERO_LENT);
  resultatsCoches.copierReponseBadge(evenementBadge(), PROJET, NUMERO_RAPIDE);

  assert.ok(await attendreQue(() => ecritures.length >= 1), 'la copie du texte déjà prêt ne doit pas attendre');
  assert.equal(ecritures.length, 1, 'une seule écriture à ce stade : NUMERO_LENT est toujours en préparation');

  debloquer();
  assert.ok(await attendreQue(() => ecritures.length >= 2), 'la copie lente doit finir par aboutir une fois débloquée');
});

test('chemin lent, écriture refusée pour geste expiré (NotAllowedError) : texte conservé dans le cache (point 4a), message du point 4b, détail technique conservé — le clic suivant aboutit sans nouvelle requête', async () => {
  fixerEnvironnement({ etatCommits: { etat: 'aucun', hashes: [] } });
  const NUMERO = 502001;
  const { comptes } = intercepterFetchIssue(-1);   // aucun numéro bloqué : tout résout immédiatement

  let premierAppel = true;
  global.navigator = {
    clipboard: {
      write: async (items) => {
        if (premierAppel) {
          premierAppel = false;
          throw Object.assign(new Error('The request is not allowed.'), { name: 'NotAllowedError' });
        }
        return items[0].data['text/plain'].text();
      },
    },
  };

  resultatsCoches.copierReponseBadge(evenementBadge(), PROJET, NUMERO);
  const zone = await attendreZoneSecours();
  assert.ok(zone, 'le texte complet doit rester accessible (texteSecours, issue #782, inchangé)');
  const detail = detailToast();
  assert.ok(detail, 'la ligne de détail technique (issue #824) doit rester présente');
  assert.match(detail.textContent, /NotAllowedError/);
  const messages = texteDesToasts();
  assert.ok(messages.some((m) => m === MESSAGE_PREPARATION_TROP_LONGUE),
    'le message principal doit devenir celui du point 4b');

  const comptesAvant = comptes[NUMERO];
  const copieSuivante = attendreProchaineCopie();
  resultatsCoches.copierReponseBadge(evenementBadge(), PROJET, NUMERO);
  const texteEcrit = await copieSuivante;
  assert.match(texteEcrit, /Corps du rapport pour #787/);
  assert.equal(comptes[NUMERO], comptesAvant,
    'le second clic doit utiliser le texte mis en cache (point 4a), sans nouvelle requête /issue');
});

test('autre erreur (ni NotAllowedError, ni préparation lente) : le message principal reste inchangé', async () => {
  fixerEnvironnement({ etatCommits: { etat: 'aucun', hashes: [] } });
  global.navigator = {
    clipboard: { write: async () => { throw new Error('Erreur inattendue du presse-papier.'); } },
  };
  resultatsCoches.copierReponseBadge(evenementBadge(), PROJET, 503001);
  await attendreZoneSecours();
  const messages = texteDesToasts();
  assert.ok(messages.some((m) => m === 'Copie impossible — le presse-papier n\'a pas pu être écrit.'));
  assert.ok(!messages.some((m) => m === MESSAGE_PREPARATION_TROP_LONGUE),
    'une erreur générique ne doit jamais prendre le message du point 4b');
});

test('mode repli : la variante « reponse » (celle que la case copie, #787) est préchargée dès le début — écart comblé, auparavant seul « all » l\'était', async () => {
  fixerEnvironnement({ etatCommits: { etat: 'aucun', hashes: [] } });
  window.isSecureContext = false;
  global.navigator = {};
  global.ClipboardItem = undefined;
  const NUMERO = 504001;
  const { comptes } = intercepterFetchIssue(-1);

  store.remplacerIssues([
    { projet: PROJET, number: NUMERO, title: 'Repli', createdAt: '2026-01-01T00:00:00Z', state: 'OPEN', labels: [] },
  ]);
  resultatsCoches.precharderVisibles();
  assert.ok(await attendreQue(() => comptes[NUMERO] === 1), 'le préchargement doit avoir fetché /issue');
  await new Promise((resolve) => setTimeout(resolve, 20));   // laisse memoriserTextePrepare s'exécuter ('reponse' puis 'all')

  resultatsCoches.basculer(evenementCase(), PROJET, NUMERO);
  const messages = texteDesToasts();
  assert.ok(
    !messages.some((m) => /en préparation|en cours/.test(m)),
    'la case ne doit plus répondre « en préparation » au premier clic : « reponse » est déjà préchargée');
});

test('precharderVisibles : ne lance rien quand la page est cachée (document.hidden)', async () => {
  fixerEnvironnement({ etatCommits: { etat: 'aucun', hashes: [] } });
  const { comptes } = intercepterFetchIssue(-1);
  document.hidden = true;
  try {
    store.remplacerIssues([
      { projet: PROJET, number: 505001, title: 'Caché', createdAt: '2026-01-01T00:00:00Z', state: 'OPEN', labels: [] },
    ]);
    resultatsCoches.precharderVisibles();
    await new Promise((resolve) => setTimeout(resolve, 30));
    assert.equal(comptes[505001], undefined, 'aucune préparation ne doit démarrer quand document.hidden est vrai');
  } finally {
    document.hidden = false;
  }
});
