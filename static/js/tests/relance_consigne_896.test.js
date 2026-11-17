// Test de logique pure du formulaire « Corriger la consigne et relancer »
// de la modale d'interruption (issue #896) — messageNonCommittesRelance()
// construit le texte affiché à partir de la réponse de GET /avancement
// (app/avancement.py), sans DOM ni réseau. Charge le VRAI static/js/app.js
// dans un bac à sable vm (même patron que static/js/tests/app_redessin_878.
// test.js) pour appeler la VRAIE fonction, pas une copie qui dériverait du
// code réel. Lancement (depuis la racine) :  node --test static/js/tests/
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
      getElementById: () => null,
      querySelector: () => null,
      querySelectorAll: () => [],
      createElement: () => ({}),
      hidden: false,
    },
  };
  sandbox.window = sandbox;
  sandbox.addEventListener = () => {};
  vm.createContext(sandbox);
  new vm.Script(code, { filename: CHEMIN_APP_JS }).runInContext(sandbox);
  return sandbox;
}

const ctx = chargerContexte();

test('messageNonCommittesRelance : réponse absente → message neutre, pas d\'avertissement', () => {
  const r = ctx.messageNonCommittesRelance(null);
  assert.equal(r.avertissement, false);
  assert.match(r.texte, /indisponible/);
});

test('messageNonCommittesRelance : disponible:false (lecture seule/CCW/worktree introuvable) → message serveur tel quel', () => {
  const r = ctx.messageNonCommittesRelance({ disponible: false, message: 'Issue en lecture seule : aucun worktree dédié.' });
  assert.equal(r.avertissement, false);
  assert.equal(r.texte, 'Issue en lecture seule : aucun worktree dédié.');
});

test('messageNonCommittesRelance : disponible, aucun fichier non committé → working tree propre, pas d\'avertissement', () => {
  const r = ctx.messageNonCommittesRelance({ disponible: true, fichiers_non_committes: [] });
  assert.equal(r.avertissement, false);
  assert.match(r.texte, /propre/);
});

test('messageNonCommittesRelance : fichiers non committés présents → avertissement listant les chemins', () => {
  const r = ctx.messageNonCommittesRelance({
    disponible: true,
    fichiers_non_committes: [
      { chemin: 'app/foo.py', statut: 'modifié' },
      { chemin: 'bar.txt', statut: 'non suivi' },
    ],
  });
  assert.equal(r.avertissement, true);
  assert.match(r.texte, /NON committé/);
  assert.match(r.texte, /app\/foo\.py/);
  assert.match(r.texte, /bar\.txt/);
});
