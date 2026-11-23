// Test du correctif de l'issue #940 : « la ligne d'une nouvelle issue
// n'apparaît pas tant qu'une case à cocher garde le focus (rendu de la liste
// reporté indéfiniment) ».
//
// RAPPEL DU MÉCANISME (voir static/js/tests/app_redessin_878.test.js) :
//   coucheResultatEnInteraction (issue #878) fait reporter rendreListeIssues/
//   remplacerLigneIssue tant qu'une case '.coche-resultat' a le focus du
//   navigateur — pour ne jamais détruire le nœud d'une case EN PLEIN CLIC.
//   AVANT #940, ce report durait jusqu'au `focusout` de cette case, lequel ne
//   survenait JAMAIS si rien d'autre ne prenait le focus ensuite (une case
//   cochée par un clic le garde indéfiniment) : un rendu demandé pendant ce
//   temps restait donc en attente SANS LIMITE.
//
// CE QUE CE FICHIER VÉRIFIE (logique pure, chargée depuis le VRAI
// static/js/app.js dans un bac à sable vm, même patron que
// app_redessin_878.test.js) :
//   - differerRenduSurCoche exécute `executer` au PLAFOND
//     (DELAI_MAX_REPORT_RENDU_MS) même si `focusout` ne survient jamais ;
//   - il n'exécute `executer` qu'UNE SEULE FOIS, quel que soit celui des deux
//     déclencheurs (focusout ou plafond) qui arrive en premier ;
//   - chaque exécution différée journalise côté serveur (POST
//     /journal-rendu-differe, via window.Bridge.api.post) le type de rendu et
//     la durée réelle du report ;
//   - basculerCocheResultat (onchange de la case) retire le focus de la case
//     une fois son changement relayé — c'est ce qui met fin au geste réel et
//     évite d'attendre le plafond dans le cas normal (clic puis plus rien).
//
// CE QUE CES TESTS NE PEUVENT PAS VÉRIFIER (pas de vrai navigateur) : voir
// VERIFICATIONS_MANUELLES.md (issue #940) pour les essais à la main.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ICI = path.dirname(fileURLToPath(import.meta.url));
const CHEMIN_APP_JS = path.join(ICI, '..', 'app.js');

// ─── Fausse DOM MINIMALE (même patron que app_redessin_878.test.js) ──────────
function creerElementFactice() {
  const ecouteurs = {};
  const el = {
    dataset: {},
    children: [],
    parentNode: null,
    classList: {
      _set: new Set(),
      add(c) { this._set.add(c); },
      remove(c) { this._set.delete(c); },
      contains(c) { return this._set.has(c); },
    },
    _innerHTML: '',
    get innerHTML() { return this._innerHTML; },
    set innerHTML(v) { this._innerHTML = v; },
    appendChild(enfant) { this.children.push(enfant); enfant.parentNode = this; return enfant; },
    replaceWith(nouveau) {
      el._remplacePar = nouveau;
      if (el.parentNode) {
        const i = el.parentNode.children.indexOf(el);
        if (i !== -1) el.parentNode.children[i] = nouveau;
      }
    },
    contains(noeud) {
      if (noeud === el) return true;
      return el.children.some((e) => (e.contains ? e.contains(noeud) : e === noeud));
    },
    addEventListener(type, fn, opts) {
      (ecouteurs[type] || (ecouteurs[type] = [])).push({ fn, once: !!(opts && opts.once) });
    },
    removeEventListener(type, fn) {
      if (ecouteurs[type]) ecouteurs[type] = ecouteurs[type].filter((e) => e.fn !== fn);
    },
    _declencher(type) {
      const liste = ecouteurs[type] || [];
      ecouteurs[type] = [];
      liste.forEach((e) => e.fn());
    },
    _nbEcouteurs(type) { return (ecouteurs[type] || []).length; },
  };
  return el;
}

// Minuteurs CONTRÔLABLES (pas de vraie attente) : setTimeout enregistre juste
// le callback, un test déclenche manuellement son exécution via
// declencherMinuteurs() pour simuler le plafond atteint.
function creerMinuteurs() {
  let compteurId = 0;
  const enAttente = new Map();
  return {
    setTimeout(fn, ms) {
      const id = ++compteurId;
      enAttente.set(id, { fn, ms });
      return id;
    },
    clearTimeout(id) { enAttente.delete(id); },
    declencherTous() {
      const callbacks = [...enAttente.values()].map((t) => t.fn);
      enAttente.clear();
      callbacks.forEach((fn) => fn());
    },
    nbEnAttente() { return enAttente.size; },
  };
}

function chargerAppJs() {
  const code = fs.readFileSync(CHEMIN_APP_JS, 'utf8');
  const zoneListe = creerElementFactice();
  const zoneIssue = creerElementFactice();
  const minuteurs = creerMinuteurs();
  const appelsApiPost = [];
  const sandbox = {
    console,
    sessionStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    fetch: () => Promise.resolve({ ok: false, json: () => Promise.resolve({}) }),
    EventSource: class { addEventListener() {} close() {} },
    setInterval: () => 0,
    setTimeout: minuteurs.setTimeout,
    clearTimeout: minuteurs.clearTimeout,
    document: {
      activeElement: null,
      addEventListener: () => {},
      getElementById: (id) => (id === 'liste-issues' ? zoneListe : id === 'zone-issue' ? zoneIssue : null),
      querySelector: () => null,
      querySelectorAll: () => [],
      createElement: () => creerElementFactice(),
      hidden: false,
    },
  };
  sandbox.window = sandbox;
  sandbox.addEventListener = () => {};
  sandbox.window.Bridge = {
    api: {
      post: (url, corps, opts) => {
        appelsApiPost.push({ url, corps, opts });
        return Promise.resolve({ succes: true });
      },
    },
  };
  vm.createContext(sandbox);
  new vm.Script(code, { filename: CHEMIN_APP_JS }).runInContext(sandbox);
  return { sandbox, zoneListe, zoneIssue, minuteurs, appelsApiPost };
}

// ─── differerRenduSurCoche : plafond atteint, focusout jamais livré ─────────
test('differerRenduSurCoche : n\'exécute PAS executer avant que focusout ou le plafond ne survienne', () => {
  const { sandbox } = chargerAppJs();
  const coche = creerElementFactice();
  let execute = false;

  sandbox.differerRenduSurCoche(coche, 'liste', () => { execute = true; });

  assert.equal(execute, false, 'pas encore exécuté : ni focusout ni plafond ne sont survenus');
});

test('differerRenduSurCoche : le plafond déclenche executer et journalise la durée du report', () => {
  const { sandbox, minuteurs, appelsApiPost } = chargerAppJs();
  const coche = creerElementFactice();
  let execute = false;

  sandbox.differerRenduSurCoche(coche, 'liste', () => { execute = true; });
  minuteurs.declencherTous();   // simule DELAI_MAX_REPORT_RENDU_MS écoulé

  assert.equal(execute, true, 'le plafond doit exécuter le rendu même si le focus n\'a pas bougé');
  assert.equal(appelsApiPost.length, 1);
  assert.equal(appelsApiPost[0].url, '/journal-rendu-differe');
  assert.equal(appelsApiPost[0].corps.type_rendu, 'liste');
  assert.equal(typeof appelsApiPost[0].corps.duree_report_ms, 'number');
  assert.ok(appelsApiPost[0].corps.duree_report_ms >= 0);
  assert.equal(appelsApiPost[0].opts.silencieux, true);
});

test('differerRenduSurCoche : un focusout avant le plafond exécute une seule fois (pas de double exécution au plafond)', () => {
  const { sandbox, minuteurs, appelsApiPost } = chargerAppJs();
  const coche = creerElementFactice();
  let nbExecutions = 0;

  sandbox.differerRenduSurCoche(coche, 'ligne', () => { nbExecutions += 1; });
  coche._declencher('focusout');   // fin du geste normal, bien avant le plafond
  assert.equal(nbExecutions, 1);
  assert.equal(appelsApiPost.length, 1);
  assert.equal(appelsApiPost[0].corps.type_rendu, 'ligne');

  // Le plafond, s'il se déclenche malgré tout (minuteur non annulé par erreur),
  // ne doit JAMAIS ré-exécuter ni journaliser une seconde fois.
  minuteurs.declencherTous();
  assert.equal(nbExecutions, 1, 'aucune seconde exécution après le focusout');
  assert.equal(appelsApiPost.length, 1, 'aucune seconde journalisation après le focusout');
});

test('differerRenduSurCoche : le minuteur plafond est annulé par un focusout précoce (aucun minuteur ne reste en attente)', () => {
  const { sandbox, minuteurs } = chargerAppJs();
  const coche = creerElementFactice();

  sandbox.differerRenduSurCoche(coche, 'liste', () => {});
  assert.equal(minuteurs.nbEnAttente(), 1);
  coche._declencher('focusout');
  assert.equal(minuteurs.nbEnAttente(), 0, 'le minuteur plafond doit être annulé une fois le geste terminé');
});

// ─── rendreListeIssues/remplacerLigneIssue : plafond respecté de bout en bout ─
test('rendreListeIssues : un rendu différé s\'exécute au plafond même si le focus ne bouge jamais', () => {
  const { sandbox, zoneListe, minuteurs, appelsApiPost } = chargerAppJs();
  zoneListe.innerHTML = 'SENTINELLE-AVANT-RESYNC';
  const coche = creerElementFactice();
  coche.classList.add('coche-resultat');
  zoneListe.appendChild(coche);
  sandbox.document.activeElement = coche;   // focus resté sur la case, AUCUN autre geste

  sandbox.rendreListeIssues(true);
  assert.equal(zoneListe.innerHTML, 'SENTINELLE-AVANT-RESYNC', 'différé tant que le focus est actif');

  minuteurs.declencherTous();   // le focus n'a PAS bougé, mais le plafond, lui, est atteint

  assert.notEqual(zoneListe.innerHTML, 'SENTINELLE-AVANT-RESYNC',
    'le rendu doit s\'exécuter au plafond même si le focus n\'a jamais bougé (issue #940 point 3)');
  assert.equal(appelsApiPost.length, 1);
  assert.equal(appelsApiPost[0].corps.type_rendu, 'liste');
});

test('remplacerLigneIssue : un rendu différé s\'exécute au plafond même si le focus ne bouge jamais', () => {
  const { sandbox, minuteurs, appelsApiPost } = chargerAppJs();
  const ligneAncienne = creerElementFactice();
  ligneAncienne.dataset.projet = 'bridge_agent';
  ligneAncienne.dataset.numero = '940';
  const coche = creerElementFactice();
  coche.classList.add('coche-resultat');
  ligneAncienne.appendChild(coche);
  sandbox.document.activeElement = coche;

  const itFraiche = { projet: 'bridge_agent', number: 940, title: 'neuf', state: 'OPEN' };
  sandbox.window.__resultatsMiroirListe([itFraiche]);
  sandbox.document.querySelectorAll = () => [ligneAncienne];
  const nouvelle = creerElementFactice();
  sandbox.construireLigneIssueDOM = () => nouvelle;
  sandbox.brancherEvenementsLigneIssue = () => {};
  sandbox.appliquerFiltresListe = () => {};
  sandbox.restaurerCasesCocheesResultats = () => {};
  sandbox.majPastillesFiltres = () => {};

  sandbox.remplacerLigneIssue(ligneAncienne, { projet: 'bridge_agent', number: 940, title: 'ancien', state: 'OPEN' });
  assert.equal(ligneAncienne._remplacePar, undefined, 'différé tant que le focus est actif');

  minuteurs.declencherTous();   // focus jamais bougé, plafond atteint

  assert.equal(ligneAncienne._remplacePar, nouvelle,
    'le remplacement doit avoir lieu au plafond même sans focusout (issue #940 point 3)');
  assert.equal(appelsApiPost.length, 1);
  assert.equal(appelsApiPost[0].corps.type_rendu, 'ligne');
});

// ─── basculerCocheResultat : retire le focus après son effet (issue #940 point 2) ─
test('basculerCocheResultat : relaie à resultatsCoches.basculer PUIS retire le focus de la case', () => {
  const { sandbox } = chargerAppJs();
  const appelsBasculer = [];
  sandbox.window.Bridge.resultatsCoches = {
    basculer: (event, projet, numero) => { appelsBasculer.push({ event, projet, numero }); },
  };
  let nbBlur = 0;
  const cb = creerElementFactice();
  cb.classList.add('coche-resultat');
  cb.blur = () => { nbBlur += 1; };
  const event = { target: cb };

  sandbox.basculerCocheResultat(event, 'bridge_agent', '940');

  assert.equal(appelsBasculer.length, 1, 'doit relayer au module dédié');
  assert.deepEqual(
    { projet: appelsBasculer[0].projet, numero: appelsBasculer[0].numero },
    { projet: 'bridge_agent', numero: '940' });
  assert.equal(nbBlur, 1, 'doit retirer le focus de la case une fois son changement relayé');
});

test('basculerCocheResultat : ne plante pas si window.Bridge.resultatsCoches est absent (repli existant)', () => {
  const { sandbox } = chargerAppJs();
  let nbBlur = 0;
  const cb = creerElementFactice();
  cb.blur = () => { nbBlur += 1; };
  assert.doesNotThrow(() => sandbox.basculerCocheResultat({ target: cb }, 'bridge_agent', '940'));
  assert.equal(nbBlur, 1, 'le retrait du focus ne dépend pas de la présence du module');
});
