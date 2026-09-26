// Tests de logique pure des lignes « fichier reçu / refusé » (issue #639 —
// fusion de l'ancien onglet « Résultats inbox » dans la liste Résultats).
// Aucune dépendance, aucun build, aucun DOM. Lancement (depuis la racine) :
//   node --test static/js/tests/
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  appliquerFichierRecu,
  appliquerCreationFichier,
  appliquerFichierRefuse,
  reconcilierRejetes,
  descriptionLigneFichier,
  MOTIF_INDISPONIBLE,
} from '../resultats.js';

// ─── fichier_recu : insertion en tête, idempotente ──────────────────────────
test('fichier_recu : insère une ligne « reçu » en tête', () => {
  const r = appliquerFichierRecu([], 'tache.md');
  assert.deepEqual(r, [{ fichier: 'tache.md', statut: 'recu', source: 'sse' }]);
});

test('fichier_recu : idempotent (pas de doublon pour le même fichier)', () => {
  const r1 = appliquerFichierRecu([], 'a.md');
  const r2 = appliquerFichierRecu(r1, 'a.md');
  assert.equal(r2.filter(l => l.fichier === 'a.md' && l.statut === 'recu').length, 1);
});

test('fichier_recu : fichier vide → inchangé', () => {
  assert.deepEqual(appliquerFichierRecu([{ fichier: 'x', statut: 'recu' }], ''),
                   [{ fichier: 'x', statut: 'recu' }]);
});

// ─── creation_issue : remplace la ligne « reçu » (1re création seulement) ────
test('creation_issue : la 1re création retire la ligne « reçu » du fichier', () => {
  const lignes = appliquerFichierRecu([], 'multi.md');
  const apres = appliquerCreationFichier(lignes, 'multi.md');
  assert.deepEqual(apres, []);
});

test('creation_issue : multi-issues — les créations suivantes ne retirent rien', () => {
  let lignes = appliquerFichierRecu([], 'multi.md');
  lignes = appliquerCreationFichier(lignes, 'multi.md');   // 1re création → retire « reçu »
  const avant = lignes.slice();
  lignes = appliquerCreationFichier(lignes, 'multi.md');   // 2e création → rien à retirer
  assert.deepEqual(lignes, avant);
});

test('creation_issue : sans fichier (formulaire) → aucune ligne touchée', () => {
  const lignes = appliquerFichierRecu([], 'a.md');
  assert.deepEqual(appliquerCreationFichier(lignes, null), lignes);
  assert.deepEqual(appliquerCreationFichier(lignes, undefined), lignes);
});

// ─── fichier_refuse : transformation / insertion ─────────────────────────────
test('fichier_refuse : transforme la ligne « reçu » en rouge, MÊME position', () => {
  let lignes = [{ fichier: 'autre.md', statut: 'recu', source: 'sse' }];
  lignes = appliquerFichierRecu(lignes, 'ko.md');          // « ko.md » en tête
  lignes = appliquerFichierRefuse(lignes, 'ko.md', 'Titre', 'mode inconnu');
  assert.equal(lignes.length, 2);
  assert.deepEqual(lignes[0], { fichier: 'ko.md', statut: 'refuse',
    motif: 'mode inconnu', titre: 'Titre', source: 'sse' });
  assert.equal(lignes[1].fichier, 'autre.md');   // l'autre ligne intacte
});

test('fichier_refuse : sans ligne « reçu » → insère une ligne rouge en tête', () => {
  const lignes = appliquerFichierRefuse([], 'seul.md', null, 'corps vide');
  assert.deepEqual(lignes, [{ fichier: 'seul.md', statut: 'refuse',
    motif: 'corps vide', titre: null, source: 'sse' }]);
});

test('fichier_refuse : motif absent → repli « refusé, motif indisponible »', () => {
  const lignes = appliquerFichierRefuse([], 'x.md', null, null);
  assert.equal(lignes[0].motif, MOTIF_INDISPONIBLE);
});

test('fichier_refuse : lot multi-blocs — chaque bloc refusé a sa propre ligne', () => {
  // reçu → bloc 1 refusé (transforme le « reçu ») → bloc 2 refusé (nouvelle ligne)
  let lignes = appliquerFichierRecu([], 'lot.md');
  lignes = appliquerFichierRefuse(lignes, 'lot.md', 'Bloc A', 'motif A');
  lignes = appliquerFichierRefuse(lignes, 'lot.md', 'Bloc B', 'motif B');
  const refus = lignes.filter(l => l.fichier === 'lot.md' && l.statut === 'refuse');
  assert.equal(refus.length, 2);
  assert.deepEqual(refus.map(l => l.motif).sort(), ['motif A', 'motif B']);
});

test('lot mixte : un bloc crée une issue, un autre est refusé — lignes distinctes', () => {
  let lignes = appliquerFichierRecu([], 'mix.md');
  lignes = appliquerCreationFichier(lignes, 'mix.md');     // bloc 1 → issue (retire « reçu »)
  lignes = appliquerFichierRefuse(lignes, 'mix.md', 'Bloc 2', 'motif 2');  // bloc 2 → rouge
  // La ligne « reçu » a disparu ; il reste UNE ligne rouge, distincte de
  // l'issue (qui, elle, vit dans store.issues, pas ici).
  assert.deepEqual(lignes, [{ fichier: 'mix.md', statut: 'refuse',
    motif: 'motif 2', titre: 'Bloc 2', source: 'sse' }]);
});

// ─── reconcilierRejetes : reconstruction + purge depuis /issues-inbox/etat ───
test('reconcilierRejetes : reconstruit une ligne rouge par fichier rejeté', () => {
  const lignes = reconcilierRejetes([], [
    { nom: 'r1.md', date: 2, motif: 'motif 1' },
    { nom: 'r2.md', date: 1, motif: null },
  ]);
  assert.equal(lignes.length, 2);
  assert.equal(lignes[0].source, 'etat');
  assert.equal(lignes[0].motif, 'motif 1');
  assert.equal(lignes[1].motif, MOTIF_INDISPONIBLE);
});

test('reconcilierRejetes : purge les lignes « etat » des fichiers plus rejetés', () => {
  let lignes = reconcilierRejetes([], [{ nom: 'a.md', date: 1, motif: 'm' }]);
  assert.equal(lignes.length, 1);
  lignes = reconcilierRejetes(lignes, []);   // a.md nettoyé manuellement
  assert.deepEqual(lignes, []);
});

test('reconcilierRejetes : ne double pas une ligne SSE déjà présente', () => {
  const sse = appliquerFichierRefuse([], 'live.md', 'T', 'motif live');
  const lignes = reconcilierRejetes(sse, [{ nom: 'live.md', date: 1, motif: 'via disque' }]);
  assert.equal(lignes.filter(l => l.fichier === 'live.md').length, 1);
  assert.equal(lignes[0].source, 'sse');     // la ligne SSE est conservée telle quelle
});

test('reconcilierRejetes : conserve les lignes SSE, ne purge que les « etat »', () => {
  const sse = appliquerFichierRecu([], 'encours.md');   // ligne « reçu » vivante
  const lignes = reconcilierRejetes(sse, []);
  assert.deepEqual(lignes, sse);   // rien à reconstruire, ligne SSE intacte
});

// ─── descriptionLigneFichier : contrat d'EXCLUSION (classe + texte) ──────────
test('descriptionLigneFichier : classe « ligne-fichier », jamais « ligne-issue »', () => {
  const recu = descriptionLigneFichier({ fichier: 'a.md', statut: 'recu' });
  const refuse = descriptionLigneFichier({ fichier: 'b.md', statut: 'refuse', motif: 'x' });
  for (const d of [recu, refuse]) {
    assert.match(d.classe, /^ligne-fichier/);
    assert.doesNotMatch(d.classe, /ligne-issue/);  // exclue des filtres/pastilles/case à cocher
  }
});

test('descriptionLigneFichier : textes attendus (reçu / refusé + motif)', () => {
  assert.equal(descriptionLigneFichier({ fichier: 'a.md', statut: 'recu' }).texte,
               '📥 fichier reçu : a.md');
  assert.equal(descriptionLigneFichier({ fichier: 'b.md', statut: 'refuse', motif: 'mode inconnu' }).texte,
               '✕ fichier refusé : b.md — mode inconnu');
  assert.equal(descriptionLigneFichier({ fichier: 'c.md', statut: 'refuse' }).texte,
               '✕ fichier refusé : c.md — ' + MOTIF_INDISPONIBLE);
});
