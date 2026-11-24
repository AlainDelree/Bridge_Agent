// Tests de logique pure des actions sur la ligne d'une issue OUVERTE (issue
// #641, refonte web étape 6 ; correctif #642 : ✏️ redevenu informatif, icône
// dédiée d'interruption basée sur l'état TIMEOUT). Aucune dépendance au DOM ni
// au réseau — voir static/js/tests/README.md pour lancer ces tests
// (node --test).
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  prefixeInformatifLigneOuverte,
  boutonsActionLigne,
  mecanismeInterruptionLigne,
  sonIssueDepuisReponse,
  normaliserChoixSonIssue,
  etatsOptionsSonIssue,
  fusionnerSonsProjet,
  sonConnuDansCache,
  cleInterruption,
  demarrerInterruption,
  terminerInterruption,
} from '../actions_ligne.js';

// ─── prefixeInformatifLigneOuverte : quel préfixe afficher selon les labels ─
// (issue #642 : mode_write n'est plus une ACTION — non-régression : le préfixe
// ✏️ redevient purement informatif, mais reste posé dans les mêmes conditions
// qu'avant #641.)

test('prefixeInformatifLigneOuverte : needs-human → "needs-human" (prime sur tout)', () => {
  assert.equal(prefixeInformatifLigneOuverte(['needs-human']), 'needs-human');
  assert.equal(prefixeInformatifLigneOuverte(['mode_write', 'needs-human']), 'needs-human');
});

test('prefixeInformatifLigneOuverte : mode_write seul (sans needs-human) → "mode_write" (informatif, non cliquable)', () => {
  assert.equal(prefixeInformatifLigneOuverte(['mode_write']), 'mode_write');
  assert.equal(prefixeInformatifLigneOuverte(['for-linux', 'mode_write']), 'mode_write');
});

test('prefixeInformatifLigneOuverte : done seul, ou aucun label pertinent → null', () => {
  assert.equal(prefixeInformatifLigneOuverte(['done']), null);
  assert.equal(prefixeInformatifLigneOuverte(['for-linux']), null);
  assert.equal(prefixeInformatifLigneOuverte([]), null);
  assert.equal(prefixeInformatifLigneOuverte(undefined), null);
});

test('prefixeInformatifLigneOuverte : accepte des labels objets {name} comme des chaînes', () => {
  assert.equal(prefixeInformatifLigneOuverte([{ name: 'needs-human' }]), 'needs-human');
  assert.equal(prefixeInformatifLigneOuverte([{ name: 'mode_write' }]), 'mode_write');
});

// ─── boutonsActionLigne : quel(s) bouton(s) afficher selon l'état (issue
// #950, remplace afficherIconeInterruption de l'issue #642) — même état de
// départ pour « en cours » : `timing.debut` (pas le seul label mode_write),
// pour qu'une issue en LECTURE en cours reste interrompable depuis sa ligne.

test('boutonsActionLigne : en file (timing connu, debut absent) → ["annuler"]', () => {
  assert.deepEqual(boutonsActionLigne(['for-linux'], { debut: null }), ['annuler']);
  assert.deepEqual(boutonsActionLigne([], { debut: null }), ['annuler']);
});

test('boutonsActionLigne : en cours en LECTURE (aucun label mode_write) → ["interrompre", "fermer"] (issue #951)', () => {
  assert.deepEqual(boutonsActionLigne(['for-linux'], { debut: '2026-09-26T10:00:00Z' }), ['interrompre', 'fermer']);
  assert.deepEqual(boutonsActionLigne([], { debut: '2026-09-26T10:00:00Z' }), ['interrompre', 'fermer']);
});

test('boutonsActionLigne : en cours en ÉCRITURE (label mode_write) → ["interrompre", "fermer"] (issue #951)', () => {
  assert.deepEqual(boutonsActionLigne(['mode_write'], { debut: '2026-09-26T10:00:00Z' }), ['interrompre', 'fermer']);
});

test('boutonsActionLigne : en cours sans limite (sans_limite, debut posé) → ["interrompre", "fermer"]', () => {
  assert.deepEqual(
    boutonsActionLigne(['mode_write'], { debut: '2026-09-26T10:00:00Z', sans_limite: true }),
    ['interrompre', 'fermer'],
  );
});

test('boutonsActionLigne : en cours INTERACTIVE (mode_interactif, debut posé) → ["interrompre", "fermer"] (issue #951, point 3)', () => {
  assert.deepEqual(
    boutonsActionLigne(['mode_interactif'], { debut: '2026-09-26T10:00:00Z' }),
    ['interrompre', 'fermer'],
  );
});

test('boutonsActionLigne : needs-human → ["relancer", "fermer"], prime sur tout le reste', () => {
  assert.deepEqual(boutonsActionLigne(['needs-human'], { debut: '2026-09-26T10:00:00Z' }), ['relancer', 'fermer']);
  assert.deepEqual(boutonsActionLigne(['mode_write', 'needs-human'], { debut: '2026-09-26T10:00:00Z' }),
    ['relancer', 'fermer']);
  // needs-human prime même sans aucun timing connu, ou sur une issue en file.
  assert.deepEqual(boutonsActionLigne(['needs-human'], undefined), ['relancer', 'fermer']);
  assert.deepEqual(boutonsActionLigne(['needs-human'], { debut: null }), ['relancer', 'fermer']);
});

test('boutonsActionLigne : done → [] (terminée, aucune action), prime sur needs-human', () => {
  assert.deepEqual(boutonsActionLigne(['done'], { debut: '2026-09-26T10:00:00Z' }), []);
  assert.deepEqual(boutonsActionLigne(['done', 'needs-human'], { debut: null }), []);
});

test('boutonsActionLigne : aucun timing connu (pas encore chargé) → [] tant qu\'on ne sait pas', () => {
  assert.deepEqual(boutonsActionLigne(['mode_write'], undefined), []);
  assert.deepEqual(boutonsActionLigne(['mode_write'], null), []);
  assert.deepEqual(boutonsActionLigne([], undefined), []);
});

test('boutonsActionLigne : accepte des labels objets {name} comme des chaînes', () => {
  assert.deepEqual(
    boutonsActionLigne([{ name: 'needs-human' }], { debut: '2026-09-26T10:00:00Z' }),
    ['relancer', 'fermer'],
  );
  assert.deepEqual(
    boutonsActionLigne([{ name: 'mode_scratch' }], { debut: '2026-09-26T10:00:00Z' }),
    ['interrompre', 'fermer'],
  );
});

// ─── mecanismeInterruptionLigne : quel mécanisme pour le bouton « Interrompre »
// (issue #950, point 6) — une issue interactive (mode_interactif) n'est jamais
// couverte par #949 (pas de boucle _attendre_fin_claude), le bouton garde donc
// le comportement historique (watcher entier).

test('mecanismeInterruptionLigne : issue interactive → "watcher_complet"', () => {
  assert.equal(mecanismeInterruptionLigne(['mode_interactif']), 'watcher_complet');
  assert.equal(mecanismeInterruptionLigne(['for-linux', 'mode_interactif']), 'watcher_complet');
});

test('mecanismeInterruptionLigne : issue normale (sans mode_interactif) → "ciblee"', () => {
  assert.equal(mecanismeInterruptionLigne(['for-linux', 'mode_write']), 'ciblee');
  assert.equal(mecanismeInterruptionLigne([]), 'ciblee');
  assert.equal(mecanismeInterruptionLigne(undefined), 'ciblee');
});

test('mecanismeInterruptionLigne : accepte des labels objets {name} comme des chaînes', () => {
  assert.equal(mecanismeInterruptionLigne([{ name: 'mode_interactif' }]), 'watcher_complet');
});

// ─── Son PAR ISSUE (issue #630/#637, réutilisées telles quelles) ──────────

test('sonIssueDepuisReponse : {son: "plat"} → "plat"', () => {
  assert.equal(sonIssueDepuisReponse({ son: 'plat' }), 'plat');
});

test('sonIssueDepuisReponse : {son: "cloche"} → "cloche"', () => {
  assert.equal(sonIssueDepuisReponse({ son: 'cloche' }), 'cloche');
});

test('sonIssueDepuisReponse : {son: "silence"} → "silence" (issue #699)', () => {
  assert.equal(sonIssueDepuisReponse({ son: 'silence' }), 'silence');
});

test('sonIssueDepuisReponse : réponse absente/vide/valeur inconnue → null', () => {
  assert.equal(sonIssueDepuisReponse(null), null);
  assert.equal(sonIssueDepuisReponse(undefined), null);
  assert.equal(sonIssueDepuisReponse({}), null);
  assert.equal(sonIssueDepuisReponse({ son: 'autre-chose' }), null);
});

test('normaliserChoixSonIssue : "plat"/"cloche"/"silence" inchangés, "" et valeur inattendue → null', () => {
  assert.equal(normaliserChoixSonIssue('plat'), 'plat');
  assert.equal(normaliserChoixSonIssue('cloche'), 'cloche');
  assert.equal(normaliserChoixSonIssue('silence'), 'silence');
  assert.equal(normaliserChoixSonIssue(''), null);
  assert.equal(normaliserChoixSonIssue('autre-chose'), null);
  assert.equal(normaliserChoixSonIssue(undefined), null);
});

test('etatsOptionsSonIssue : un seul état actif à la fois, "Global" par défaut (issue #699 : 4e état "silence")', () => {
  assert.deepEqual(etatsOptionsSonIssue(null), { global: true, plat: false, cloche: false, silence: false });
  assert.deepEqual(etatsOptionsSonIssue('plat'), { global: false, plat: true, cloche: false, silence: false });
  assert.deepEqual(etatsOptionsSonIssue('cloche'), { global: false, plat: false, cloche: true, silence: false });
  assert.deepEqual(etatsOptionsSonIssue('silence'), { global: false, plat: false, cloche: false, silence: true });
});

// ─── Cache du son par projet (GET /son-issue/<projet> en bloc, issue #641) ─

test('fusionnerSonsProjet : ne retient que les valeurs "plat"/"cloche"/"silence"', () => {
  const cache = fusionnerSonsProjet({}, 'bridge_agent',
    { 630: 'cloche', 631: 'plat', 632: 'autre', 633: null, 634: 'silence' });
  assert.deepEqual(cache, { bridge_agent: { '630': 'cloche', '631': 'plat', '634': 'silence' } });
});

test('fusionnerSonsProjet : REMPLACE le projet concerné, conserve les autres', () => {
  const avant = { proj_a: { '1': 'cloche' }, proj_b: { '2': 'plat' } };
  const apres = fusionnerSonsProjet(avant, 'proj_a', { 1: 'plat', 3: 'cloche' });
  assert.deepEqual(apres, { proj_a: { '1': 'plat', '3': 'cloche' }, proj_b: { '2': 'plat' } });
});

test('sonConnuDansCache : lit un choix connu ou retombe sur null (suit le global)', () => {
  const cache = { bridge_agent: { '630': 'cloche' } };
  assert.equal(sonConnuDansCache(cache, 'bridge_agent', 630), 'cloche');
  assert.equal(sonConnuDansCache(cache, 'bridge_agent', '630'), 'cloche');
  assert.equal(sonConnuDansCache(cache, 'bridge_agent', 631), null);
  assert.equal(sonConnuDansCache(cache, 'autre_projet', 630), null);
  assert.equal(sonConnuDansCache(null, 'bridge_agent', 630), null);
});

// ─── Garde anti-double-déclenchement d'une interruption (issue #748) ──────

test('cleInterruption : clé stable par couple (projet, numéro)', () => {
  assert.equal(cleInterruption('bridge_agent', 452), 'bridge_agent#452');
  assert.equal(cleInterruption('bridge_agent', '452'), 'bridge_agent#452');
});

test('demarrerInterruption : accepte le premier déclenchement, refuse un second pendant que le premier est en cours', () => {
  const enCours = new Set();
  assert.equal(demarrerInterruption(enCours, 'bridge_agent', 452), true);
  assert.equal(enCours.has('bridge_agent#452'), true);
  // Second déclenchement pour LE MÊME couple, avant toute fin — refusé.
  assert.equal(demarrerInterruption(enCours, 'bridge_agent', 452), false);
  // Couple DIFFÉRENT (autre numéro, ou autre projet) — indépendant, accepté.
  assert.equal(demarrerInterruption(enCours, 'bridge_agent', 453), true);
  assert.equal(demarrerInterruption(enCours, 'scrabble', 452), true);
});

test('terminerInterruption : libère le couple, un nouveau déclenchement redevient possible', () => {
  const enCours = new Set();
  demarrerInterruption(enCours, 'bridge_agent', 452);
  terminerInterruption(enCours, 'bridge_agent', 452);
  assert.equal(enCours.has('bridge_agent#452'), false);
  assert.equal(demarrerInterruption(enCours, 'bridge_agent', 452), true);
});

test('terminerInterruption : un couple absent ne lève pas d\'erreur (no-op)', () => {
  const enCours = new Set();
  assert.doesNotThrow(() => terminerInterruption(enCours, 'bridge_agent', 452));
  assert.equal(enCours.size, 0);
});
