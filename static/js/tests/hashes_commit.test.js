// Test de hashesDeCommit() (app.js) — bouton de copie du diff, issue #784.
//
// POURQUOI CE TEST EXISTE
//   Le diagnostic #783 a établi que hashesDeCommit() cherchait une ligne
//   « Commits : ... » alors que le gabarit de watcher.py (ligne_commits)
//   écrit depuis le 30/08 un chemin de travail entre « Commits » et « : » —
//   la reconnaissance échouait silencieusement, pour toutes les issues, quel
//   que soit leur mode. Le défaut a survécu à une réécriture ultérieure de
//   cette même ligne faute de tout lien entre le gabarit (watcher.py) et la
//   reconnaissance (app.js).
//
//   Pour rendre ce lien apparent, ce test ne recopie PAS la ligne à la main :
//   il LIT le texte réel de watcher.py (la f-string ligne_commits) et
//   construit les lignes de test à partir de ce texte. Si une future
//   modification du gabarit change sa forme, soit l'extraction ci-dessous ne
//   trouve plus exactement 2 formes (échec explicite et parlant), soit la
//   ligne produite change et hashesDeCommit() ne la reconnaît plus (échec
//   sur les assertions) — dans les deux cas CE test casse, pas le bouton en
//   silence. Voir aussi le commentaire croisé déposé dans watcher.py au-dessus
//   de ligne_commits, et celui au-dessus de hashesDeCommit() dans app.js.
//
//   app.js n'est pas un module ES (script classique hérité, chargé tel quel
//   par le navigateur) : impossible de l'importer directement. On le charge
//   ici dans un bac à sable vm minimal (stubs document/window/fetch/…, juste
//   assez pour que le script se charge sans lever) afin d'appeler la VRAIE
//   fonction hashesDeCommit — pas une copie qui dérperait du code réel.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ICI = path.dirname(fileURLToPath(import.meta.url));
const CHEMIN_APP_JS  = path.join(ICI, '..', 'app.js');
const CHEMIN_WATCHER = path.join(ICI, '..', '..', '..', 'watcher.py');

// Extrait les deux formes du gabarit watcher.py::ligne_commits (écriture /
// lecture seule) depuis la f-string source elle-même.
function gabaritsLigneCommits() {
  const source = fs.readFileSync(CHEMIN_WATCHER, 'utf8');
  const trouves = [...source.matchAll(/ligne_commits = f"([^"]*)"/g)].map(m => m[1]);
  assert.equal(trouves.length, 2,
    `watcher.py : attendu 2 formes de ligne_commits (écriture/lecture seule), `
    + `${trouves.length} trouvée(s) — gabarit modifié, mettre à jour ce test (issue #784).`);
  const [gabaritEcriture, gabaritLectureSeule] = trouves;
  const cwd = '/home/alain/depots/bridge_agent';
  return {
    // Les placeholders [hash backup]/[hash fix] sont remplacés par l'agent
    // dans sa réponse réelle — on simule ce remplacement comme le ferait CCL.
    ecriture: gabaritEcriture.replace('{cwd_effectif}', cwd)
      .replace('[hash backup]', 'abc1234')
      .replace('[hash fix]', 'def5678'),
    lectureSeule: gabaritLectureSeule.replace('{cwd_effectif}', cwd),
  };
}

function chargerHashesDeCommit() {
  const code = fs.readFileSync(CHEMIN_APP_JS, 'utf8');
  const sandbox = {
    console,
    sessionStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    fetch: () => Promise.resolve({ ok: false, json: () => Promise.resolve({}) }),
    EventSource: class { addEventListener() {} close() {} },
    setInterval: () => 0,
    setTimeout: () => 0,
    clearTimeout: () => {},
    document: {
      addEventListener: () => {},
      getElementById: () => null,
      querySelector: () => null,
      querySelectorAll: () => [],
      createElement: () => ({ classList: { add() {}, remove() {} }, style: {}, addEventListener() {} }),
      hidden: false,
    },
  };
  sandbox.window = sandbox;
  sandbox.addEventListener = () => {};
  vm.createContext(sandbox);
  new vm.Script(code, { filename: CHEMIN_APP_JS }).runInContext(sandbox);
  return sandbox.hashesDeCommit;
}

const hashesDeCommitVm = chargerHashesDeCommit();
// hashesDeCommitVm() renvoie un tableau construit dans le réalm vm (Array
// différent du réalm hôte) : assert.deepEqual le jugerait non égal à un
// littéral ['x'] malgré un contenu identique. Array.from() le ramène dans le
// réalm hôte avant comparaison.
const hashesDeCommit = (it) => Array.from(hashesDeCommitVm(it));
const { ecriture, lectureSeule } = gabaritsLigneCommits();

test('hashesDeCommit : reconnaît la ligne réelle du gabarit écriture (chemin intercalé, issue #784)', () => {
  const it = { comments: [{ body: `✅ Tâche terminée — exemple\n${ecriture}\npy_compile : OK` }] };
  assert.deepEqual(hashesDeCommit(it), ['abc1234', 'def5678']);
});

test('hashesDeCommit : forme lecture seule du gabarit (aucun hash) → liste vide', () => {
  const it = { comments: [{ body: `✅ Tâche terminée — rien à faire\n${lectureSeule}\npy_compile : N/A` }] };
  assert.deepEqual(hashesDeCommit(it), []);
});

test('hashesDeCommit : aucun commentaire → liste vide', () => {
  assert.deepEqual(hashesDeCommit({ comments: [] }), []);
  assert.deepEqual(hashesDeCommit({}), []);
});
