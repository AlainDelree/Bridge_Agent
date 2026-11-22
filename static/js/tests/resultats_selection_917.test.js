// Tests de resultats.rafraichirSelection (issue #917 points 2/3) : le voile
// de veille/réveil et le rafraîchissement périodique du projet sélectionné ne
// doivent JAMAIS toucher aux autres projets (liste ET timing), contrairement
// à chargerTimingTous() (toujours TOUS les projets, réservé au ↻ complet —
// voir resultats_resync_729.test.js, qui ne vérifie que la liste). Même
// patron DOM minimal que ce fichier.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { resultats } from '../resultats.js';

function installerDomMinimal(nomsProjet) {
  global.document = {
    getElementById: (id) => (id === 'projet'
      ? { options: nomsProjet.map((v) => ({ value: v })) }
      : null),
    querySelectorAll: () => [],
    querySelector: () => null,
    createElement: () => ({
      className: '', textContent: '', style: {},
      classList: { add() {}, remove() {} },
      appendChild() {}, addEventListener() {}, setAttribute() {}, remove() {}, select() {},
    }),
    body: { appendChild: () => {}, removeChild: () => {} },
    head: { appendChild: () => {} },
  };
  global.window = globalThis;
  global.requestAnimationFrame = (cb) => cb();
  window.__resultatsListeVide = () => {};
  window.__resultatsMiroirListe = () => {};
  window.__resultatsSetTiming = () => {};
  window.appliquerListeIssues = () => {};
  window.majIndicateurListe = () => {};
  window.limiteIssuesProjet = () => 5;
  window.restaurerCasesCocheesResultats = () => {};
  window.majPastillesFiltres = () => {};
}

function installerFetchMinimal(echecs = new Set()) {
  const appels = [];
  global.fetch = async (url) => {
    appels.push(url);
    for (const e of echecs) {
      if (url.includes(e)) return { ok: false, status: 500, text: async () => '{}' };
    }
    let body = null;
    if (url.includes('/issues-liste/')) body = [];
    else if (url.includes('/issues-en-attente/')) body = [];
    return { ok: true, text: async () => JSON.stringify(body) };
  };
  return appels;
}

test('rafraichirSelection : ne recharge QUE le(s) projet(s) donné(s), ni la liste ni le timing des autres', async () => {
  installerDomMinimal(['a', 'b']);
  const appels = installerFetchMinimal();
  const r = await resultats.rafraichirSelection(['a']);
  assert.equal(r.succes, true);
  assert.ok(appels.some((u) => u.includes('/issues-liste/a')));
  assert.ok(appels.some((u) => u.includes('/issues-en-attente/a')));
  assert.ok(!appels.some((u) => u.includes('/issues-liste/b')), 'projet hors sélection : liste jamais refetchée');
  assert.ok(!appels.some((u) => u.includes('/issues-en-attente/b')), 'projet hors sélection : timing jamais refetché');
});

test('rafraichirSelection : liste vide → aucun appel réseau, succès trivial', async () => {
  installerDomMinimal(['a', 'b']);
  const appels = installerFetchMinimal();
  const r = await resultats.rafraichirSelection([]);
  assert.equal(r.succes, true);
  assert.equal(appels.length, 0);
});

test('rafraichirSelection : échec réseau sur la liste → succes:false', async () => {
  installerDomMinimal(['a']);
  installerFetchMinimal(new Set(['/issues-liste/a']));
  const r = await resultats.rafraichirSelection(['a']);
  assert.equal(r.succes, false);
});

test('rafraichirSelection : échec réseau sur le timing seul → succes:false', async () => {
  installerDomMinimal(['a']);
  installerFetchMinimal(new Set(['/issues-en-attente/a']));
  const r = await resultats.rafraichirSelection(['a']);
  assert.equal(r.succes, false);
});

test('rafraichirSelection : tout réussit → succes:true', async () => {
  installerDomMinimal(['a']);
  installerFetchMinimal();
  const r = await resultats.rafraichirSelection(['a']);
  assert.equal(r.succes, true);
});
