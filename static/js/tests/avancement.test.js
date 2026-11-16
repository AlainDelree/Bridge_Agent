// Tests de logique pure du bouton « Avancement » d'une issue en cours (issue
// #887) : rendu de la modale à partir de la réponse JSON de GET /avancement/
// <projet>/<numero> — aucune dépendance au DOM ni au réseau (voir
// panneau_lateral.js, section « Bouton Avancement »). Lancement (depuis la
// racine) :  node --test static/js/tests/
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  formaterHorodatageAvancement,
  ligneFichierAvancement,
  rendreCorpsAvancement,
} from '../panneau_lateral.js';

// ─── formaterHorodatageAvancement ───────────────────────────────────────────
test('formaterHorodatageAvancement : absent/0/null → tiret', () => {
  assert.equal(formaterHorodatageAvancement(0), '—');
  assert.equal(formaterHorodatageAvancement(null), '—');
  assert.equal(formaterHorodatageAvancement(undefined), '—');
});

test('formaterHorodatageAvancement : horodatage valide → chaîne non vide, pas de tiret', () => {
  const texte = formaterHorodatageAvancement(1700000000);
  assert.ok(texte && texte !== '—');
});

// ─── ligneFichierAvancement ─────────────────────────────────────────────────
test('ligneFichierAvancement : fichier modifié normal', () => {
  const html = ligneFichierAvancement({ chemin: 'a.txt', ancien_chemin: null, statut: 'modifié', ajoutees: 3, supprimees: 1 });
  assert.match(html, /a\.txt/);
  assert.match(html, /\+3/);
  assert.match(html, /-1/);
  assert.match(html, /modifié/);
});

test('ligneFichierAvancement : fichier binaire (compteurs absents) → "?" plutôt que 0', () => {
  const html = ligneFichierAvancement({ chemin: 'img.bin', ancien_chemin: null, statut: 'ajouté', ajoutees: null, supprimees: null });
  assert.match(html, /\+\?/);
  assert.match(html, /-\?/);
});

test('ligneFichierAvancement : renommage → "ancien → nouveau"', () => {
  const html = ligneFichierAvancement({ chemin: 'c.txt', ancien_chemin: 'b.txt', statut: 'renommé', ajoutees: 0, supprimees: 0 });
  assert.match(html, /b\.txt.*→.*c\.txt/);
});

test('ligneFichierAvancement : chemin échappé (pas d\'injection HTML)', () => {
  const html = ligneFichierAvancement({ chemin: '<script>.txt', ancien_chemin: null, statut: 'ajouté', ajoutees: 1, supprimees: 0 });
  assert.ok(!html.includes('<script>'));
});

// ─── rendreCorpsAvancement : cas dégradés (issue #887, point 4) ────────────
test('rendreCorpsAvancement : réponse vide → message, jamais d\'exception', () => {
  const html = rendreCorpsAvancement(null);
  assert.match(html, /vide/);
});

test('rendreCorpsAvancement : lecture seule → message serveur affiché tel quel', () => {
  const html = rendreCorpsAvancement({ disponible: false, raison: 'lecture_seule', message: 'Issue en lecture seule : aucun worktree dédié.' });
  assert.match(html, /lecture seule/);
});

test('rendreCorpsAvancement : issue for-windows (CCW) → message dédié, pas d\'erreur', () => {
  const html = rendreCorpsAvancement({ disponible: false, raison: 'ccw', message: 'Cette issue tourne sur la machine CCW.' });
  assert.match(html, /CCW/);
});

test('rendreCorpsAvancement : worktree introuvable/déjà nettoyé → message dédié', () => {
  const html = rendreCorpsAvancement({ disponible: false, raison: 'worktree_introuvable', message: 'Aucun worktree trouvé pour cette issue.' });
  assert.match(html, /Aucun worktree trouvé/);
});

test('rendreCorpsAvancement : disponible avec commits et fichiers', () => {
  const html = rendreCorpsAvancement({
    disponible: true,
    chemin: '/home/alain/worktrees/projet-issue42',
    branche: 'worktree-issue-42',
    branche_base: 'master',
    derniere_activite: 1700000000,
    commits: [{ hash: 'abc1234', message: 'fix', horodatage: 1700000000 }],
    fichiers_committes: [{ chemin: 'a.txt', ancien_chemin: null, statut: 'modifié', ajoutees: 2, supprimees: 1 }],
    fichiers_non_committes: [{ chemin: 'b.txt', ancien_chemin: null, statut: 'non suivi', ajoutees: 5, supprimees: 0 }],
  });
  assert.match(html, /worktree-issue-42/);
  assert.match(html, /master/);
  assert.match(html, /abc1234/);
  assert.match(html, /a\.txt/);
  assert.match(html, /b\.txt/);
});

test('rendreCorpsAvancement : disponible mais sans commit ni fichier → messages "aucun"', () => {
  const html = rendreCorpsAvancement({
    disponible: true, chemin: '/x', branche: 'worktree-issue-7', branche_base: 'master',
    derniere_activite: null, commits: [], fichiers_committes: [], fichiers_non_committes: [],
  });
  assert.match(html, /Aucun commit depuis la base/);
  assert.match(html, /Working tree propre/);
});
