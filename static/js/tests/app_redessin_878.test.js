// Test du correctif de l'issue #878 : « case à cocher de copie sans effet,
// juste après le redessin de la liste (fin d'issue en direct) ou après le
// retour d'un long masquage d'onglet (resynchronisation complète, reconnexion
// SSE) ». Charge le VRAI static/js/app.js dans un bac à sable vm (même
// patron que static/js/tests/hashes_commit.test.js) pour appeler les VRAIES
// fonctions coucheResultatEnInteraction / remplacerLigneIssue /
// rendreListeIssues — pas une copie qui dériverait du code réel.
//
// MÉCANISME ÉTABLI PAR RELECTURE DU CODE (pas une simple hypothèse) :
//   remplacerLigneIssue (appelée EN DIRECT depuis l'événement /stream
//   `fin_issue`, via window.__resultatsRemplacerLigne) et rendreListeIssues
//   (appelée à la resynchronisation complète après ≥30s de masquage
//   d'onglet OU après une reconnexion SSE, voir static/js/resultats.js)
//   détruisaient JUSQU'ICI le nœud DOM d'une case SANS AUCUNE garde — alors
//   que restaurerCasesCocheesResultats, elle, protège déjà depuis les
//   issues #462/#463 la case sur laquelle l'utilisateur est EN TRAIN d'agir
//   (focus actif, posé par le navigateur au `mousedown`, AVANT `click`/
//   `change`). Le correctif étend cette MÊME garde à ces deux chemins.
//
// CE QUE CES TESTS VÉRIFIENT, ET CE QU'ILS NE PEUVENT PAS VÉRIFIER
//   Ils prouvent que, sous Node, avec une fausse DOM minimale, ces deux
//   fonctions NE DÉTRUISENT PLUS le nœud tant que `document.activeElement`
//   est sa case, et effectuent la reconstruction différée dès le `focusout`.
//   Ce qu'ils NE PEUVENT PAS prouver (aucun DOM réel, aucune boucle
//   d'événements souris sous Node) : que le `click`/`change` d'un VRAI
//   clic utilisateur n'est effectivement JAMAIS délivré par Firefox à un
//   nœud détruit entre `mousedown` et `mouseup` — c'est un comportement du
//   moteur d'événements du navigateur, pas du code de ce dépôt. Voir
//   VERIFICATIONS_MANUELLES.md (issue #878) pour les deux essais à la main.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ICI = path.dirname(fileURLToPath(import.meta.url));
const CHEMIN_APP_JS = path.join(ICI, '..', 'app.js');

// ─── Fausse DOM MINIMALE ───────────────────────────────────────────────────
// PAS un moteur de sélecteurs CSS : juste ce dont coucheResultatEnInteraction/
// remplacerLigneIssue/rendreListeIssues ont besoin (classList, dataset,
// contains, replaceWith, addEventListener). `_declencher(type)` est une AIDE
// DE TEST (pas une API DOM réelle) qui simule le navigateur déclenchant cet
// événement sur l'élément.
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
  };
  return el;
}

function chargerAppJs() {
  const code = fs.readFileSync(CHEMIN_APP_JS, 'utf8');
  const zoneListe = creerElementFactice();
  const zoneIssue = creerElementFactice();
  const sandbox = {
    console,
    sessionStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    fetch: () => Promise.resolve({ ok: false, json: () => Promise.resolve({}) }),
    EventSource: class { addEventListener() {} close() {} },
    setInterval: () => 0,
    setTimeout: () => 0,
    clearTimeout: () => {},
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
  vm.createContext(sandbox);
  new vm.Script(code, { filename: CHEMIN_APP_JS }).runInContext(sandbox);
  return { sandbox, zoneListe, zoneIssue };
}

// ─── coucheResultatEnInteraction (garde extraite, issue #878) ─────────────────
test('coucheResultatEnInteraction : aucun élément actif → null', () => {
  const { sandbox } = chargerAppJs();
  sandbox.document.activeElement = null;
  assert.equal(sandbox.coucheResultatEnInteraction(creerElementFactice()), null);
});

test('coucheResultatEnInteraction : élément actif sans la classe coche-resultat → null', () => {
  const { sandbox } = chargerAppJs();
  const actif = creerElementFactice();
  const racine = creerElementFactice();
  racine.appendChild(actif);
  sandbox.document.activeElement = actif;
  assert.equal(sandbox.coucheResultatEnInteraction(racine), null);
});

test('coucheResultatEnInteraction : case active mais HORS de la racine → null', () => {
  const { sandbox } = chargerAppJs();
  const actif = creerElementFactice();
  actif.classList.add('coche-resultat');
  const racine = creerElementFactice();   // actif n'y est PAS ajouté
  sandbox.document.activeElement = actif;
  assert.equal(sandbox.coucheResultatEnInteraction(racine), null);
});

test('coucheResultatEnInteraction : case active ET dans la racine → la renvoie', () => {
  const { sandbox } = chargerAppJs();
  const actif = creerElementFactice();
  actif.classList.add('coche-resultat');
  const racine = creerElementFactice();
  racine.appendChild(actif);
  sandbox.document.activeElement = actif;
  assert.equal(sandbox.coucheResultatEnInteraction(racine), actif);
});

// ─── remplacerLigneIssue : situation 1 de l'issue #878 — clic PENDANT le
//     redessin d'une ligne déclenché par `fin_issue` ──────────────────────────
test('remplacerLigneIssue : NE remplace PAS la ligne tant que sa case a le focus (clic en cours)', () => {
  const { sandbox } = chargerAppJs();
  const ligneAncienne = creerElementFactice();
  ligneAncienne.dataset.projet = 'bridge_agent';
  ligneAncienne.dataset.numero = '878';
  const coche = creerElementFactice();
  coche.classList.add('coche-resultat');
  ligneAncienne.appendChild(coche);
  sandbox.document.activeElement = coche;   // mousedown déjà reçu, change pas encore livré

  sandbox.remplacerLigneIssue(ligneAncienne, { projet: 'bridge_agent', number: 878, title: 'neuf', state: 'CLOSED' });

  assert.equal(ligneAncienne._remplacePar, undefined,
    'la ligne ne doit pas être détruite tant que sa case est le focus actif');
});

test('remplacerLigneIssue : reconstruit la ligne au focusout, une fois le clic terminé', () => {
  const { sandbox } = chargerAppJs();
  const ligneAncienne = creerElementFactice();
  ligneAncienne.dataset.projet = 'bridge_agent';
  ligneAncienne.dataset.numero = '878';
  const coche = creerElementFactice();
  coche.classList.add('coche-resultat');
  ligneAncienne.appendChild(coche);
  sandbox.document.activeElement = coche;

  const itFraiche = { projet: 'bridge_agent', number: 878, title: 'neuf', state: 'CLOSED' };
  sandbox.window.__resultatsMiroirListe([itFraiche]);
  // trouverLigneIssue (appelé par le focusout différé) interroge
  // '#liste-issues .ligne-issue' : on y fait répondre notre seule ligne.
  sandbox.document.querySelectorAll = () => [ligneAncienne];
  // Isole la garde de la reconstruction réelle (hors périmètre de cette
  // issue) : construireLigneIssueDOM est une fonction volumineuse qui
  // dépend de nombreux autres utilitaires de rendu, pas de la garde testée ici.
  const nouvelle = creerElementFactice();
  sandbox.construireLigneIssueDOM = () => nouvelle;
  sandbox.brancherEvenementsLigneIssue = () => {};
  sandbox.appliquerFiltresListe = () => {};
  sandbox.restaurerCasesCocheesResultats = () => {};
  sandbox.majPastillesFiltres = () => {};

  sandbox.remplacerLigneIssue(ligneAncienne, { projet: 'bridge_agent', number: 878, title: 'ancien', state: 'OPEN' });
  assert.equal(ligneAncienne._remplacePar, undefined, 'différée tant que le focus est actif');

  // Le focus quitte la case (comme au clic réel : activeElement change AVANT
  // que `focusout` ne se déclenche), PUIS le navigateur livre `focusout`.
  sandbox.document.activeElement = null;
  coche._declencher('focusout');

  assert.equal(ligneAncienne._remplacePar, nouvelle,
    'la reconstruction, différée, doit avoir eu lieu après le focusout');
});

// ─── rendreListeIssues : situation 2 de l'issue #878 — clic juste après un
//     long retour d'onglet/une reconnexion SSE (resynchronisation complète) ──
test('rendreListeIssues : NE détruit PAS la liste tant qu\'une case y a le focus (retour d\'onglet simulé)', () => {
  const { sandbox, zoneListe } = chargerAppJs();
  zoneListe.innerHTML = 'SENTINELLE-AVANT-RESYNC';
  const coche = creerElementFactice();
  coche.classList.add('coche-resultat');
  zoneListe.appendChild(coche);   // la case cliquée est dans la liste
  sandbox.document.activeElement = coche;

  sandbox.rendreListeIssues(true);

  assert.equal(zoneListe.innerHTML, 'SENTINELLE-AVANT-RESYNC',
    'la resynchronisation ne doit pas reconstruire la liste tant que l\'utilisateur clique dans son focus');
});

test('rendreListeIssues : reconstruit la liste au focusout de la case (resynchronisation terminée)', () => {
  const { sandbox, zoneListe, zoneIssue } = chargerAppJs();
  zoneListe.innerHTML = 'SENTINELLE-AVANT-RESYNC';
  const coche = creerElementFactice();
  coche.classList.add('coche-resultat');
  zoneListe.appendChild(coche);
  sandbox.document.activeElement = coche;

  sandbox.rendreListeIssues(true);
  assert.equal(zoneListe.innerHTML, 'SENTINELLE-AVANT-RESYNC', 'différée tant que le focus est actif');

  sandbox.document.activeElement = null;
  coche._declencher('focusout');

  // Liste vide (listeIssuesResultats par défaut) → chemin « Aucune issue » :
  // suffit à prouver que la VRAIE reconstruction a eu lieu après le focusout.
  assert.notEqual(zoneListe.innerHTML, 'SENTINELLE-AVANT-RESYNC');
  assert.match(zoneIssue.innerHTML, /Aucune issue/);
});
