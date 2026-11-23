// Test du correctif de l'issue #943 : « la sélection d'une issue saute à la
// première ligne à chaque rechargement de la liste (zone de détail et
// panneau d'actions qui changent d'issue seuls) ».
//
// CAUSE CONFIRMÉE PAR RELECTURE DU CODE : executerRenduListeIssues(reset)
// (static/js/app.js, corps réel de rendreListeIssues — seul appelant :
// appliquerListeIssues, TOUJOURS avec reset=true, lui-même appelé par
// static/js/resultats.js::rendreListeComplete à chaque rechargement complet
// — ↻, réveil, flux silencieux, et depuis #933 aussi création/début/fin de
// traitement et retour d'onglet) appelait INCONDITIONNELLEMENT
// selectionnerPremiereVisible() quand reset=true, laquelle abandonne la
// sélection courante (projetCourant/numeroCourant) pour la première ligne
// visible — y compris quand l'issue déjà sélectionnée est toujours présente
// et visible. Le panneau d'actions (panneau_lateral.js::rendrePanneauLateralActions,
// via obtenirIssueSelectionnee) suit directement projetCourant/numeroCourant :
// son titre « ACTIONS — <projet> #<numéro> » sautait donc avec la sélection.
//
// CORRECTIF : restaurerSelectionApresRendu() (remplace l'appel inconditionnel
// à selectionnerPremiereVisible) ne retombe sur la première ligne visible que
// si aucune issue n'était sélectionnée, ou si l'issue sélectionnée a disparu
// de la liste ou n'est plus visible. Sinon, elle se contente de remarquer la
// ligne déjà sélectionnée (projetCourant/numeroCourant INCHANGÉS) — sans
// appeler selectionnerLigne/afficherIssue, donc sans toucher la zone de
// détail ni relancer son chargement.
//
// CE QUE CES TESTS VÉRIFIENT (logique pure de décision, chargée depuis le
// VRAI static/js/app.js dans un bac à sable vm, même patron que
// static/js/tests/app_redessin_878.test.js et app_rendu_differe_940.test.js) :
//   - issue sélectionnée toujours présente ET visible → sélection conservée,
//     zone de détail NON touchée, aucun fetch réseau déclenché ;
//   - issue sélectionnée disparue de la nouvelle liste → repli sur la
//     première ligne visible (comportement historique, issue #261) ;
//   - issue sélectionnée toujours dans la liste mais masquée (filtre/quota)
//     → même repli ;
//   - aucune sélection au départ → même repli (non-régression explicite).
//
// CE QUE CES TESTS NE PEUVENT PAS VÉRIFIER (pas de vrai navigateur) : voir
// VERIFICATIONS_MANUELLES.md (issue #943) pour les essais à la main (double-
// clic puis dépôt/fin d'issue, ↻, changement de projet/filtre).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ICI = path.dirname(fileURLToPath(import.meta.url));
const CHEMIN_APP_JS = path.join(ICI, '..', 'app.js');

// ─── Fausse DOM MINIMALE (même patron que app_redessin_878.test.js), étendue
// d'un `style.display` (lu par selectionnerPremiereVisible/appliquerFiltresListe)
// et d'un faux querySelectorAll/querySelector CONSCIENT des deux seuls
// sélecteurs réellement utilisés par la logique testée ici — pas un moteur
// CSS général.
function creerElementFactice() {
  const ecouteurs = {};
  const el = {
    dataset: {},
    style: { display: '' },
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
  };
  return el;
}

function creerDocument(zoneListe, zoneIssue) {
  const lignes = () => zoneListe.children.filter((e) => e.classList.contains('ligne-issue'));
  const correspondre = (sel) => {
    if (sel === '#liste-issues .ligne-issue') return lignes();
    if (sel === '#liste-issues .ligne-issue.selectionnee') {
      return lignes().filter((l) => l.classList.contains('selectionnee'));
    }
    return [];   // tout autre sélecteur (restaurerCasesCocheesResultats, pastilles…) : hors périmètre, stubbé par ailleurs
  };
  return {
    activeElement: null,
    addEventListener: () => {},
    getElementById: (id) => (id === 'liste-issues' ? zoneListe : id === 'zone-issue' ? zoneIssue : null),
    querySelector: (sel) => correspondre(sel)[0] || null,
    querySelectorAll: (sel) => correspondre(sel),
    createElement: () => creerElementFactice(),
    hidden: false,
  };
}

function chargerAppJs() {
  const code = fs.readFileSync(CHEMIN_APP_JS, 'utf8');
  const zoneListe = creerElementFactice();
  const zoneIssue = creerElementFactice();
  const appelsFetch = [];
  const sandbox = {
    console,
    sessionStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    fetch: (url) => { appelsFetch.push(url); return Promise.resolve({ ok: false, json: () => Promise.resolve({}) }); },
    EventSource: class { addEventListener() {} close() {} },
    setInterval: () => 0,
    setTimeout: () => 0,
    clearTimeout: () => {},
    document: creerDocument(zoneListe, zoneIssue),
    // Pont vers panneau_lateral.js (issue #375/#628) : simples globales posées
    // par son propre script au démarrage réel de l'interface — ici de simples
    // bouchons, hors périmètre de cette issue (la DÉCISION de conserver la
    // sélection, pas le rendu du panneau lui-même — déjà couvert par
    // l'assertion sur obtenirIssueSelectionnee ci-dessous).
    rafraichirPanneauLateralResultats: () => {},
    majBoutonTesterSonActif: () => {},
  };
  sandbox.window = sandbox;
  sandbox.addEventListener = () => {};
  vm.createContext(sandbox);
  new vm.Script(code, { filename: CHEMIN_APP_JS }).runInContext(sandbox);

  // Rendu DOM d'une ligne réduit à ce dont la logique de sélection a besoin
  // (dataset.projet/numero, classe .ligne-issue, visibilité) : construireLigneIssueDOM
  // réel est volumineux et déjà exercé par ailleurs (hors périmètre ici, même
  // choix que app_rendu_differe_940.test.js).
  sandbox.construireLigneIssueDOM = (it) => {
    const ligne = creerElementFactice();
    ligne.classList.add('ligne-issue');
    ligne.dataset.projet = it.projet;
    ligne.dataset.numero = String(it.number);
    return ligne;
  };
  sandbox.brancherEvenementsLigneIssue = () => {};
  sandbox.appliquerFiltresListe = () => {};
  sandbox.restaurerCasesCocheesResultats = () => {};
  sandbox.majPastillesFiltres = () => {};

  return { sandbox, zoneListe, zoneIssue, appelsFetch };
}

function ligneParNumero(zoneListe, numero) {
  return zoneListe.children.find((l) => l.dataset.numero === String(numero));
}

// ─── Issue sélectionnée toujours présente ET visible → sélection conservée ──
test('executerRenduListeIssues : conserve la sélection si l\'issue sélectionnée est toujours dans la liste', () => {
  const { sandbox, zoneListe, zoneIssue, appelsFetch } = chargerAppJs();
  sandbox.window.__resultatsMiroirListe([
    { projet: 'bridge_agent', number: 940, title: 'autre issue', state: 'OPEN' },
    { projet: 'bridge_agent', number: 943, title: 'celle déjà ouverte', state: 'OPEN' },
  ]);

  // Simule la sélection déjà faite par Alain (double-clic) AVANT ce rechargement.
  sandbox.selectionnerLigne('bridge_agent', '943');
  zoneIssue.innerHTML = 'SENTINELLE-DETAIL-943-DEJA-OUVERT';

  sandbox.rendreListeIssues(true);   // rechargement complet (↻, debut_issue, fin_issue…)

  const l943 = ligneParNumero(zoneListe, 943);
  const l940 = ligneParNumero(zoneListe, 940);
  assert.ok(l943.classList.contains('selectionnee'), 'la ligne #943, déjà sélectionnée, doit le rester');
  assert.equal(l940.classList.contains('selectionnee'), false, 'aucune autre ligne ne doit devenir sélectionnée');
  // JSON.stringify plutôt que assert.deepEqual : l'objet `issue` provient du
  // bac à sable vm (autre « royaume » JS, prototype Object distinct de celui
  // de ce fichier de test) — deepStrictEqual (assert/strict) le comparerait
  // à tort comme différent à cause du seul prototype.
  assert.equal(
    JSON.stringify(sandbox.obtenirIssueSelectionnee()),
    JSON.stringify({ projet: 'bridge_agent', numero: '943', issue: { projet: 'bridge_agent', number: 943, title: 'celle déjà ouverte', state: 'OPEN' } }),
    'projetCourant/numeroCourant ne doivent pas avoir bougé (panneau Infrastructure correct)');
  assert.equal(zoneIssue.innerHTML, 'SENTINELLE-DETAIL-943-DEJA-OUVERT',
    'la zone de détail ne doit pas être réinitialisée ni rechargée');
  // Seul /issue/... (afficherIssue) recharge le détail — /heartbeat part déjà
  // au chargement du script lui-même (demarrerCycleVie), sans rapport avec
  // la sélection : on ne vérifie donc l'ABSENCE que de l'appel de détail.
  assert.ok(appelsFetch.every((u) => !u.startsWith('/issue/')),
    'aucun fetch de détail ne doit être déclenché par un simple rechargement de liste');
});

// ─── Issue sélectionnée disparue de la nouvelle liste → repli première visible ─
test('executerRenduListeIssues : retombe sur la première ligne visible si l\'issue sélectionnée a disparu', () => {
  const { sandbox, zoneListe, zoneIssue } = chargerAppJs();
  sandbox.window.__resultatsMiroirListe([{ projet: 'bridge_agent', number: 943, title: 'encore là', state: 'OPEN' }]);
  sandbox.selectionnerLigne('bridge_agent', '940');   // sélection d'une issue qui ne sera plus dans la liste
  zoneIssue.innerHTML = 'SENTINELLE-DETAIL-940';

  sandbox.rendreListeIssues(true);

  const l943 = ligneParNumero(zoneListe, 943);
  assert.ok(l943.classList.contains('selectionnee'), 'repli sur la première (et seule) ligne visible');
  assert.deepEqual(sandbox.obtenirIssueSelectionnee().numero, '943');
  assert.notEqual(zoneIssue.innerHTML, 'SENTINELLE-DETAIL-940', 'la zone de détail doit refléter le repli, pas l\'ancienne issue disparue');
});

// ─── Issue sélectionnée toujours dans la liste mais masquée (filtre/quota) ──
test('executerRenduListeIssues : retombe sur la première ligne visible si l\'issue sélectionnée est masquée', () => {
  const { sandbox, zoneListe } = chargerAppJs();
  sandbox.window.__resultatsMiroirListe([
    { projet: 'bridge_agent', number: 943, title: 'masquée par le filtre', state: 'OPEN' },
    { projet: 'bridge_agent', number: 944, title: 'visible', state: 'OPEN' },
  ]);
  sandbox.selectionnerLigne('bridge_agent', '943');

  // appliquerFiltresListe est stubbée (hors périmètre, voir chargerAppJs) :
  // on simule directement SON effet (masquage par display:none) sur la ligne
  // de l'issue sélectionnée, pour isoler la seule décision testée ici.
  const ancienStub = sandbox.appliquerFiltresListe;
  sandbox.appliquerFiltresListe = () => {
    const l = ligneParNumero(zoneListe, 943);
    if (l) l.style.display = 'none';
  };

  sandbox.rendreListeIssues(true);
  sandbox.appliquerFiltresListe = ancienStub;

  const l944 = ligneParNumero(zoneListe, 944);
  assert.ok(l944.classList.contains('selectionnee'), 'repli sur la première ligne encore VISIBLE (#943 est masquée)');
  assert.equal(sandbox.obtenirIssueSelectionnee().numero, '944');
});

// ─── Aucune sélection au départ → comportement historique inchangé ─────────
test('executerRenduListeIssues : sans sélection préalable, sélectionne la première ligne visible (non-régression)', () => {
  const { sandbox, zoneListe } = chargerAppJs();
  sandbox.window.__resultatsMiroirListe([
    { projet: 'bridge_agent', number: 950, title: 'première', state: 'OPEN' },
    { projet: 'bridge_agent', number: 951, title: 'deuxième', state: 'OPEN' },
  ]);

  sandbox.rendreListeIssues(true);   // aucun selectionnerLigne() préalable — comme au chargement initial

  const l950 = ligneParNumero(zoneListe, 950);
  assert.ok(l950.classList.contains('selectionnee'), 'comportement historique préservé : première ligne visible');
  assert.equal(sandbox.obtenirIssueSelectionnee().numero, '950');
});
