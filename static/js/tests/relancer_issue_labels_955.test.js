// Test de non-régression — issue #955 : le bouton « Relancer » d'une ligne
// (retirerNeedsHumanDepuisLigne → relancerIssue(), static/js/app.js) envoyait
// à /relancer-issue des labels lus via labelsIssueDepuisCache() — un cache
// localStorage alimenté UNIQUEMENT quand le détail de CETTE issue a déjà été
// ouvert (double-clic, afficherIssue()). Cliqué directement depuis sa ligne
// (sans jamais avoir ouvert son détail — cas réel constaté le 25/11/2026 sur
// testvibe, juste après « Arrêter »), le cache est vide : le label for-linux
// manque alors des labels transmis, et app.interruption.route_relancer() ne
// redémarre JAMAIS le watcher CCL éteint (garde `"for-linux" in labels`,
// issue #574), silencieusement.
//
// Fix : relancerIssue() lit désormais labelsIssueCourante() (déjà utilisée
// par fermerDepuisLigne()/interrompreDepuisLigne() pour la même raison, issue
// #951), qui regarde en PRIORITÉ le store du socle — alimenté par
// /issues-liste pour TOUTES les issues ouvertes connues, jamais seulement
// celles dont le détail a été affiché — avec repli sur l'ancien cache
// seulement si le store est muet.
//
// Charge le VRAI static/js/app.js dans un bac à sable vm (même patron que
// static/js/tests/relance_consigne_896.test.js). Lancement (depuis la
// racine) :  node --test static/js/tests/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ICI = path.dirname(fileURLToPath(import.meta.url));
const CHEMIN_APP_JS = path.join(ICI, '..', 'app.js');

function chargerContexte() {
  const code = fs.readFileSync(CHEMIN_APP_JS, 'utf8');
  const appels = [];
  const sandbox = {
    console,
    confirm: () => true,
    alert: () => {},
    sessionStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    fetch: (url, opts) => {
      appels.push({ url, body: opts && opts.body ? JSON.parse(opts.body) : null });
      // succes:false → relancerIssue() s'arrête juste après (alert + return),
      // sans jamais appeler chargerListeIssues() (défini ailleurs, pas chargé
      // dans ce bac à sable) : inutile de simuler toute la suite.
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ succes: false }) });
    },
    EventSource: class { addEventListener() {} close() {} },
    setInterval: () => 0,
    setTimeout: () => 0,
    clearTimeout: () => {},
    document: {
      activeElement: null,
      addEventListener: () => {},
      getElementById: (id) => (id === 'projet'
        ? { options: [{ value: 'testvibe', textContent: 'testvibe — Owner/testvibe' }] }
        : null),
      querySelector: () => null,
      querySelectorAll: () => [],
      createElement: () => ({}),
      hidden: false,
    },
  };
  sandbox.window = sandbox;
  sandbox.addEventListener = () => {};
  sandbox.window.Bridge = {
    persistance: {
      cleCacheDetail: (nom, numero) => `detail:${nom}:${numero}`,
      // Cache détail ABSENT — l'issue #20 n'a jamais été double-cliquée dans
      // ce scénario, exactement la situation réelle du 25/11/2026.
      lire: () => null,
    },
    store: {
      // Le store, lui, connaît déjà cette issue (alimenté par /issues-liste
      // pour TOUTES les issues ouvertes, pas seulement celles ouvertes en
      // détail) — avec son label for-linux.
      lireIssue: (nom, numero) => ({
        projet: nom,
        number: numero,
        labels: [{ name: 'bridge' }, { name: 'for-linux' }],
      }),
    },
  };
  vm.createContext(sandbox);
  new vm.Script(code, { filename: CHEMIN_APP_JS }).runInContext(sandbox);
  return { ctx: sandbox, appels };
}

test('labelsIssueDepuisCache seul (ancien comportement) est vide quand le détail n\'a jamais été ouvert — cause #955', () => {
  const { ctx } = chargerContexte();
  // Comparaison par longueur, pas deepEqual : le tableau retourné vient du
  // réalme vm (Array sandbox), deepStrictEqual avec un littéral du réalme
  // hôte échoue sur l'identité du constructeur malgré une structure identique.
  assert.equal(ctx.labelsIssueDepuisCache('testvibe', 20).length, 0);
});

test('relancerIssue : les labels postés à /relancer-issue incluent for-linux via le store, même sans cache détail (#955)', async () => {
  const { ctx, appels } = chargerContexte();
  await ctx.relancerIssue('testvibe', 20);
  const appel = appels.find((a) => a.url === '/relancer-issue');
  assert.ok(appel, 'un POST /relancer-issue est attendu');
  assert.ok(Array.isArray(appel.body.labels), 'labels doit être un tableau');
  assert.ok(
    appel.body.labels.map((l) => String(l).toLowerCase()).includes('for-linux'),
    'for-linux doit figurer dans les labels transmis — sinon redemarrer_si_eteint() '
    + "n'est jamais invoqué côté serveur (app.interruption.route_relancer)"
  );
});
