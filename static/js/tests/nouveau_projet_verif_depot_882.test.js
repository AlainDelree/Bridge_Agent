// Test du correctif de l'issue #882 : le message sous « Dépôt GitHub »
// (`npVerifier`/`npAfficherEtatDepot`, static/js/app.js) pouvait rester
// affiché pour un nom INTERMÉDIAIRE tapé pendant la frappe (ex.
// « AlainDelree/Bridge ») alors que le champ contenait déjà sa valeur
// finale (« AlainDelree/Bridgebc ») — la réponse réseau de la vérification
// du nom intermédiaire est arrivée APRÈS celle du nom final et l'a
// remplacée à l'écran, sans que rien dans le code ne détecte ce retard.
//
// Charge le VRAI static/js/app.js dans un bac à sable vm (même patron que
// static/js/tests/app_redessin_878.test.js) pour appeler les VRAIES
// fonctions npVerifier/npAfficherEtatDepot/npMajAvertissementPrive — pas une
// copie qui dériverait du code réel.
//
// CE QUE CES TESTS VÉRIFIENT, ET CE QU'ILS NE PEUVENT PAS VÉRIFIER
//   Ils prouvent que, sous Node, avec une fausse DOM minimale et un `fetch`
//   dont on contrôle nous-mêmes l'ordre de résolution des promesses, une
//   réponse en retard sur un nom qui n'est plus celui du champ n'est jamais
//   affichée, et que rien n'est affiché tant que la vérification du nom
//   courant n'est pas arrivée. Ce qu'ils NE PEUVENT PAS prouver (aucun DOM
//   réel) : le rendu visuel effectif dans un navigateur — voir
//   VERIFICATIONS_MANUELLES.md (issue #882) pour l'essai à la main.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ICI = path.dirname(fileURLToPath(import.meta.url));
const CHEMIN_APP_JS = path.join(ICI, '..', 'app.js');

// ─── Fausse DOM MINIMALE ───────────────────────────────────────────────────
// Juste ce dont npVerifier/npAfficherEtatDepot/npMajAvertissementPrive ont
// besoin : value/checked (champs), textContent/style.display (messages).
function creerChampFactice(valeurInitiale) {
  return {
    value: valeurInitiale !== undefined ? valeurInitiale : '',
    checked: false,
    textContent: '',
    style: { display: '' },
  };
}

function creerDomFactice() {
  const elements = new Map([
    ['np-nom', creerChampFactice('')],
    ['np-depot', creerChampFactice('')],
    ['np-nom-msg', creerChampFactice('')],
    ['np-depot-msg', creerChampFactice('')],
    ['np-rep-msg', creerChampFactice('')],
    ['np-rep', creerChampFactice('')],
    ['np-creer-depot-ligne', creerChampFactice('')],
    ['np-public-ligne', creerChampFactice('')],
    ['np-avertissement-prive', creerChampFactice('')],
    ['np-public', creerChampFactice('')],
  ]);
  return {
    elements,
    getElementById(id) { return elements.get(id) || null; },
  };
}

// `fetch` sous contrôle du test UNIQUEMENT pour /nouveau-projet/verifier :
// chaque appel empile un `resolve` que le test déclenche lui-même, dans
// l'ordre qu'il choisit — c'est ce qui permet de simuler une réponse réseau
// arrivant dans le désordre (la requête la plus récente répond AVANT la plus
// ancienne). Tout autre appel (`demarrerCycleVie()` envoie un /heartbeat dès
// le chargement du script, app.js:2924) répond immédiatement, pour ne pas
// décaler les index des appels qu'on veut vraiment contrôler.
function creerFetchControle() {
  const resoluteurs = [];
  function fetchMock(url) {
    if (typeof url === 'string' && url.startsWith('/nouveau-projet/verifier')) {
      return new Promise((resolve) => { resoluteurs.push(resolve); });
    }
    return Promise.resolve({ json: () => Promise.resolve({}) });
  }
  function repondre(indexAppel, donnees) {
    resoluteurs[indexAppel]({ json: () => Promise.resolve(donnees) });
  }
  return { fetchMock, repondre };
}

function chargerAppJs(fetchMock) {
  const code = fs.readFileSync(CHEMIN_APP_JS, 'utf8');
  const dom = creerDomFactice();
  const sandbox = {
    console,
    sessionStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    fetch: fetchMock,
    EventSource: class { addEventListener() {} close() {} },
    setInterval: () => 0,
    setTimeout: () => 0,
    clearTimeout: () => {},
    document: Object.assign(dom, {
      activeElement: null,
      addEventListener: () => {},
      querySelector: () => null,
      querySelectorAll: () => [],
      createElement: () => creerChampFactice(''),
      hidden: false,
    }),
  };
  sandbox.window = sandbox;
  sandbox.addEventListener = () => {};
  vm.createContext(sandbox);
  new vm.Script(code, { filename: CHEMIN_APP_JS }).runInContext(sandbox);
  return { sandbox, dom };
}

// ─── Reproduction directe de l'issue #882 ──────────────────────────────────
test('npVerifier : une réponse en retard sur un nom intermédiaire ne doit JAMAIS écraser celle du nom final', async () => {
  const { fetchMock, repondre } = creerFetchControle();
  const { sandbox, dom } = chargerAppJs(fetchMock);

  dom.elements.get('np-nom').value = 'bridge_agent';
  dom.elements.get('np-depot').value = 'AlainDelree/Bridge';   // nom intermédiaire, tapé en premier
  const p1 = sandbox.npVerifier();   // 1ère requête (lancée en premier)

  dom.elements.get('np-depot').value = 'AlainDelree/Bridgebc'; // puis corrigé — valeur FINALE du champ
  const p2 = sandbox.npVerifier();   // 2ème requête (lancée après, plus récente)

  // Le réseau répond dans le désordre : la requête la PLUS RÉCENTE (2) répond
  // d'abord ; celle du nom intermédiaire (1), la plus ancienne, répond ENSUITE,
  // en retard — exactement le scénario observé dans l'issue.
  repondre(1, { nom_valide: true, conf_existe: false, nom: 'bridge_agent',
                depot: 'AlainDelree/Bridgebc', depot_existe: false,
                depot_defaut: '', rep_defaut: '', rep_casse_differente: '' });
  await p2;
  assert.equal(dom.elements.get('np-depot-msg').textContent,
    'ℹ AlainDelree/Bridgebc n\'existe pas encore.');

  repondre(0, { nom_valide: true, conf_existe: false, nom: 'bridge_agent',
                depot: 'AlainDelree/Bridge', depot_existe: false,
                depot_defaut: '', rep_defaut: '', rep_casse_differente: '' });
  await p1;

  // La réponse en retard (nom intermédiaire) est ignorée : le message reste
  // celui du nom FINAL, jamais remplacé ni par du vide, ni par « …Bridge ».
  assert.equal(dom.elements.get('np-depot-msg').textContent,
    'ℹ AlainDelree/Bridgebc n\'existe pas encore.');
});

test('npVerifier : une réponse en retard ne doit pas non plus écraser un état "dépôt existant" plus récent', async () => {
  const { fetchMock, repondre } = creerFetchControle();
  const { sandbox, dom } = chargerAppJs(fetchMock);

  dom.elements.get('np-nom').value = 'bridge_agent';
  dom.elements.get('np-depot').value = 'AlainDelree/Bridge';
  const p1 = sandbox.npVerifier();

  dom.elements.get('np-depot').value = 'AlainDelree/Bridgebc';
  const p2 = sandbox.npVerifier();

  // Cette fois le nom final existe déjà sur GitHub.
  repondre(1, { nom_valide: true, conf_existe: false, nom: 'bridge_agent',
                depot: 'AlainDelree/Bridgebc', depot_existe: true,
                depot_defaut: '', rep_defaut: '', rep_casse_differente: '' });
  await p2;
  assert.match(dom.elements.get('np-depot-msg').textContent, /existe déjà/);

  repondre(0, { nom_valide: true, conf_existe: false, nom: 'bridge_agent',
                depot: 'AlainDelree/Bridge', depot_existe: false,
                depot_defaut: '', rep_defaut: '', rep_casse_differente: '' });
  await p1;

  assert.match(dom.elements.get('np-depot-msg').textContent, /existe déjà/);
});

test('npVerifier : rien n\'est affiché tant que la vérification du nom courant n\'est pas arrivée', async () => {
  const { fetchMock, repondre } = creerFetchControle();
  const { sandbox, dom } = chargerAppJs(fetchMock);

  dom.elements.get('np-nom').value = 'bridge_agent';
  dom.elements.get('np-depot').value = 'AlainDelree/Bridge';
  const p1 = sandbox.npVerifier();
  repondre(0, { nom_valide: true, conf_existe: false, nom: 'bridge_agent',
                depot: 'AlainDelree/Bridge', depot_existe: false,
                depot_defaut: '', rep_defaut: '', rep_casse_differente: '' });
  await p1;
  assert.notEqual(dom.elements.get('np-depot-msg').textContent, '');

  // Nouvelle saisie : une nouvelle vérification démarre, sa réponse n'est pas
  // encore arrivée — le message de l'ancienne valeur ne doit plus être visible.
  dom.elements.get('np-depot').value = 'AlainDelree/Bridgebc';
  const p2 = sandbox.npVerifier();
  assert.equal(dom.elements.get('np-depot-msg').textContent, '',
    'aucun message ne doit rester affiché pendant que la vérification du nom courant est en vol');

  repondre(1, { nom_valide: true, conf_existe: false, nom: 'bridge_agent',
                depot: 'AlainDelree/Bridgebc', depot_existe: false,
                depot_defaut: '', rep_defaut: '', rep_casse_differente: '' });
  await p2;
  assert.equal(dom.elements.get('np-depot-msg').textContent,
    'ℹ AlainDelree/Bridgebc n\'existe pas encore.');
});

// ─── npMajAvertissementPrive : condition GH_TOKEN (issue #882) ────────────
test('npMajAvertissementPrive : dépôt privé + GH_TOKEN présent → avertissement affiché (installation d\'Alain)', () => {
  const { sandbox, dom } = chargerAppJs(() => Promise.reject(new Error('fetch non utilisé dans ce test')));
  sandbox.window.GH_TOKEN_ENV_PRESENT = true;
  dom.elements.get('np-public').checked = false;   // dépôt privé

  sandbox.npMajAvertissementPrive();

  assert.equal(dom.elements.get('np-avertissement-prive').style.display, 'block');
});

test('npMajAvertissementPrive : dépôt privé + GH_TOKEN absent (fait serveur) → avertissement masqué', () => {
  const { sandbox, dom } = chargerAppJs(() => Promise.reject(new Error('fetch non utilisé dans ce test')));
  sandbox.window.GH_TOKEN_ENV_PRESENT = false;
  dom.elements.get('np-public').checked = false;   // dépôt privé

  sandbox.npMajAvertissementPrive();

  assert.equal(dom.elements.get('np-avertissement-prive').style.display, 'none');
});

test('npMajAvertissementPrive : réglage indéterminé (ni true ni false) → avertissement gardé par prudence', () => {
  const { sandbox, dom } = chargerAppJs(() => Promise.reject(new Error('fetch non utilisé dans ce test')));
  sandbox.window.GH_TOKEN_ENV_PRESENT = undefined;
  dom.elements.get('np-public').checked = false;

  sandbox.npMajAvertissementPrive();

  assert.equal(dom.elements.get('np-avertissement-prive').style.display, 'block');
});

test('npMajAvertissementPrive : dépôt public → jamais affiché, quelle que soit la présence de GH_TOKEN', () => {
  const { sandbox, dom } = chargerAppJs(() => Promise.reject(new Error('fetch non utilisé dans ce test')));
  sandbox.window.GH_TOKEN_ENV_PRESENT = true;
  dom.elements.get('np-public').checked = true;   // dépôt public

  sandbox.npMajAvertissementPrive();

  assert.equal(dom.elements.get('np-avertissement-prive').style.display, 'none');
});
