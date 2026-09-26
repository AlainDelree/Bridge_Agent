// Tests de logique pure des actions sur la ligne d'une issue OUVERTE (issue
// #641, refonte web étape 6 ; correctif #642 : ✏️ redevenu informatif, icône
// dédiée d'interruption basée sur l'état TIMEOUT). Aucune dépendance au DOM ni
// au réseau — voir static/js/tests/README.md pour lancer ces tests
// (node --test).
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  prefixeInformatifLigneOuverte,
  afficherIconeInterruption,
  sonIssueDepuisReponse,
  normaliserChoixSonIssue,
  etatsOptionsSonIssue,
  fusionnerSonsProjet,
  sonConnuDansCache,
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

// ─── afficherIconeInterruption : quand afficher l'icône dédiée (issue #642) ─
// Correctif de la régression #641 : une issue en LECTURE en cours doit pouvoir
// être interrompue depuis sa ligne — basé sur `timing.debut` (même état que le
// décompte TIMEOUT actif de resultats.js), PAS sur le seul label mode_write.

test('afficherIconeInterruption : en cours en LECTURE (aucun label mode_write) → true', () => {
  assert.equal(afficherIconeInterruption(['for-linux'], { debut: '2026-09-26T10:00:00Z' }), true);
  assert.equal(afficherIconeInterruption([], { debut: '2026-09-26T10:00:00Z' }), true);
});

test('afficherIconeInterruption : en cours en ÉCRITURE (label mode_write) → true', () => {
  assert.equal(afficherIconeInterruption(['mode_write'], { debut: '2026-09-26T10:00:00Z' }), true);
});

test('afficherIconeInterruption : en cours sans limite (sans_limite, debut posé) → true', () => {
  assert.equal(
    afficherIconeInterruption(['mode_write'], { debut: '2026-09-26T10:00:00Z', sans_limite: true }),
    true,
  );
});

test('afficherIconeInterruption : "en file" (timing connu mais debut absent) → false', () => {
  assert.equal(afficherIconeInterruption(['mode_write'], { debut: null }), false);
  assert.equal(afficherIconeInterruption([], { debut: null }), false);
});

test('afficherIconeInterruption : needs-human → false même si debut posé (déjà arrêtée)', () => {
  assert.equal(afficherIconeInterruption(['needs-human'], { debut: '2026-09-26T10:00:00Z' }), false);
  assert.equal(
    afficherIconeInterruption(['mode_write', 'needs-human'], { debut: '2026-09-26T10:00:00Z' }),
    false,
  );
});

test('afficherIconeInterruption : aucun timing connu (issue fermée, ou pas encore chargé) → false', () => {
  assert.equal(afficherIconeInterruption(['mode_write'], undefined), false);
  assert.equal(afficherIconeInterruption(['mode_write'], null), false);
});

test('afficherIconeInterruption : accepte des labels objets {name} comme des chaînes', () => {
  assert.equal(
    afficherIconeInterruption([{ name: 'needs-human' }], { debut: '2026-09-26T10:00:00Z' }),
    false,
  );
  assert.equal(
    afficherIconeInterruption([{ name: 'mode_scratch' }], { debut: '2026-09-26T10:00:00Z' }),
    true,
  );
});

// ─── Son PAR ISSUE (issue #630/#637, réutilisées telles quelles) ──────────

test('sonIssueDepuisReponse : {son: "plat"} → "plat"', () => {
  assert.equal(sonIssueDepuisReponse({ son: 'plat' }), 'plat');
});

test('sonIssueDepuisReponse : {son: "cloche"} → "cloche"', () => {
  assert.equal(sonIssueDepuisReponse({ son: 'cloche' }), 'cloche');
});

test('sonIssueDepuisReponse : réponse absente/vide/valeur inconnue → null', () => {
  assert.equal(sonIssueDepuisReponse(null), null);
  assert.equal(sonIssueDepuisReponse(undefined), null);
  assert.equal(sonIssueDepuisReponse({}), null);
  assert.equal(sonIssueDepuisReponse({ son: 'autre-chose' }), null);
});

test('normaliserChoixSonIssue : "plat"/"cloche" inchangés, "" et valeur inattendue → null', () => {
  assert.equal(normaliserChoixSonIssue('plat'), 'plat');
  assert.equal(normaliserChoixSonIssue('cloche'), 'cloche');
  assert.equal(normaliserChoixSonIssue(''), null);
  assert.equal(normaliserChoixSonIssue('autre-chose'), null);
  assert.equal(normaliserChoixSonIssue(undefined), null);
});

test('etatsOptionsSonIssue : un seul état actif à la fois, "Global" par défaut', () => {
  assert.deepEqual(etatsOptionsSonIssue(null), { global: true, plat: false, cloche: false });
  assert.deepEqual(etatsOptionsSonIssue('plat'), { global: false, plat: true, cloche: false });
  assert.deepEqual(etatsOptionsSonIssue('cloche'), { global: false, plat: false, cloche: true });
});

// ─── Cache du son par projet (GET /son-issue/<projet> en bloc, issue #641) ─

test('fusionnerSonsProjet : ne retient que les valeurs "plat"/"cloche"', () => {
  const cache = fusionnerSonsProjet({}, 'bridge_agent', { 630: 'cloche', 631: 'plat', 632: 'autre', 633: null });
  assert.deepEqual(cache, { bridge_agent: { '630': 'cloche', '631': 'plat' } });
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
