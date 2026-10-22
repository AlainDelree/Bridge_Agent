// Tests de logique pure du module « case à cocher » (refonte étape 5b, issue #636).
// Aucune dépendance, aucun build, aucun DOM. Lancement (depuis la racine) :
//   node --test static/js/tests/
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  normaliserNumero,
  fusionnerCasesServeur,
  estCocheDansEtat,
  ajouterDansEtat,
  retirerDansEtat,
  decisionModeCopie,
  extraireCasesLegacy,
  premieresParProjet,
  appliquerCaseDecochee,
  ligneIdentite,
  prefixerIdentite,
  texteCopieAvecIdentite,
  fusionnerInventaireFichier,
  construireInventaireCumule,
  texteSectionFichiers,
} from '../resultats_coches.js';

// ─── normaliserNumero ─────────────────────────────────────────────────────────
test('normaliserNumero : chaîne DOM → entier', () => {
  assert.equal(normaliserNumero('636'), 636);
  assert.equal(normaliserNumero(636), 636);
});

// ─── fusionnerCasesServeur ────────────────────────────────────────────────────
test('fusionnerCasesServeur : REMPLACE la liste du projet, dédoublonne, normalise', () => {
  const etat = { alpha: [1, 2] };
  const suivant = fusionnerCasesServeur(etat, 'alpha', ['3', 3, 4]);
  assert.deepEqual(suivant.alpha, [3, 4]);         // remplace (le serveur fait foi), dédoublonné
  assert.notEqual(suivant, etat);                  // immuable
});

test('fusionnerCasesServeur : conserve les AUTRES projets', () => {
  const etat = { alpha: [1], beta: [9] };
  const suivant = fusionnerCasesServeur(etat, 'alpha', [2]);
  assert.deepEqual(suivant.beta, [9]);
  assert.deepEqual(suivant.alpha, [2]);
});

test('fusionnerCasesServeur : liste vide/absente → tableau vide', () => {
  assert.deepEqual(fusionnerCasesServeur({}, 'x', []).x, []);
  assert.deepEqual(fusionnerCasesServeur(undefined, 'x', undefined).x, []);
});

// ─── estCocheDansEtat ─────────────────────────────────────────────────────────
test('estCocheDansEtat : compare en entier (tolère la chaîne DOM)', () => {
  const etat = { alpha: [1, 5] };
  assert.equal(estCocheDansEtat(etat, 'alpha', 5), true);
  assert.equal(estCocheDansEtat(etat, 'alpha', '5'), true);
  assert.equal(estCocheDansEtat(etat, 'alpha', 2), false);
  assert.equal(estCocheDansEtat(etat, 'inconnu', 1), false);
});

// ─── ajouter / retirer (immuables, idempotents) ───────────────────────────────
test('ajouterDansEtat : ajoute, idempotent, immuable', () => {
  const etat = { alpha: [1] };
  const a = ajouterDansEtat(etat, 'alpha', '2');
  assert.deepEqual(a.alpha, [1, 2]);
  assert.notEqual(a, etat);
  assert.equal(ajouterDansEtat(a, 'alpha', 2), a);   // déjà présent → même objet
});

test('ajouterDansEtat : crée le projet absent', () => {
  const a = ajouterDansEtat({}, 'neuf', 7);
  assert.deepEqual(a.neuf, [7]);
});

test('retirerDansEtat : retire, supprime la clé projet vidée, idempotent', () => {
  const etat = { alpha: [1, 2], beta: [9] };
  const r = retirerDansEtat(etat, 'alpha', 1);
  assert.deepEqual(r.alpha, [2]);
  const r2 = retirerDansEtat(r, 'alpha', 2);
  assert.equal('alpha' in r2, false);                // liste vidée → clé supprimée
  assert.deepEqual(r2.beta, [9]);
  assert.equal(retirerDansEtat(r2, 'alpha', 99), r2); // absent → même objet
});

// ─── appliquerCaseDecochee (issue #720, événement SSE `case_decochee`) ───────
test('appliquerCaseDecochee : retire la case indiquée par l\'événement', () => {
  const etat = { bridge_agent: [629, 630] };
  const r = appliquerCaseDecochee(etat, { projet: 'bridge_agent', numero: 629 });
  assert.deepEqual(r.bridge_agent, [630]);
});

test('appliquerCaseDecochee : idempotent — déjà décochée → même objet (pas de re-rendu)', () => {
  const etat = { bridge_agent: [630] };
  const r = appliquerCaseDecochee(etat, { projet: 'bridge_agent', numero: 629 });
  assert.equal(r, etat);
});

test('appliquerCaseDecochee : événement malformé (projet/numéro absent) → no-op', () => {
  const etat = { bridge_agent: [629] };
  assert.equal(appliquerCaseDecochee(etat, null), etat);
  assert.equal(appliquerCaseDecochee(etat, {}), etat);
  assert.equal(appliquerCaseDecochee(etat, { projet: 'bridge_agent' }), etat);
  assert.equal(appliquerCaseDecochee(etat, { numero: 629 }), etat);
});

test('appliquerCaseDecochee : ne touche pas aux autres projets', () => {
  const etat = { bridge_agent: [629], autre_projet: [1] };
  const r = appliquerCaseDecochee(etat, { projet: 'bridge_agent', numero: 629 });
  assert.deepEqual(r.autre_projet, [1]);
});

// ─── decisionModeCopie ────────────────────────────────────────────────────────
test('decisionModeCopie : sécurisé + clipboard.write + ClipboardItem → moderne', () => {
  assert.equal(decisionModeCopie(true, { write: () => {} }, true), 'moderne');
});

test('decisionModeCopie : contexte non sécurisé (--lan) → repli', () => {
  assert.equal(decisionModeCopie(false, { write: () => {} }, true), 'repli');
});

test('decisionModeCopie : clipboard absent ou sans write → repli', () => {
  assert.equal(decisionModeCopie(true, null, true), 'repli');
  assert.equal(decisionModeCopie(true, { writeText: () => {} }, true), 'repli');
});

test('decisionModeCopie : ClipboardItem indisponible → repli', () => {
  assert.equal(decisionModeCopie(true, { write: () => {} }, false), 'repli');
});

// ─── extraireCasesLegacy (migration idempotente du localStorage) ──────────────
test('extraireCasesLegacy : ne retient que les clés resultat-coche:* = "1"', () => {
  const entrees = [
    { cle: 'resultat-coche:alpha:12', valeur: '1' },
    { cle: 'resultat-coche:beta:3', valeur: '1' },
    { cle: 'resultat-coche:alpha:99', valeur: '0' },   // valeur ≠ '1' → ignorée
    { cle: 'bridge_limite_issues_projet', valeur: '5' }, // autre clé → ignorée
    { cle: 'resultat-coche:mauvais', valeur: '1' },      // pas de numéro → ignorée
  ];
  const { cases, cles } = extraireCasesLegacy(entrees);
  assert.deepEqual(cases, [
    { projet: 'alpha', numero: 12 },
    { projet: 'beta', numero: 3 },
  ]);
  assert.deepEqual(cles, ['resultat-coche:alpha:12', 'resultat-coche:beta:3']);
});

test('extraireCasesLegacy : nom de projet contenant un « : » (découpe sur le dernier)', () => {
  const { cases } = extraireCasesLegacy([{ cle: 'resultat-coche:a:b:42', valeur: '1' }]);
  assert.deepEqual(cases, [{ projet: 'a:b', numero: 42 }]);
});

test('extraireCasesLegacy : numéro non entier ignoré, entrée vide tolérée', () => {
  const { cases } = extraireCasesLegacy([
    { cle: 'resultat-coche:alpha:abc', valeur: '1' },
    { cle: 'resultat-coche:alpha:', valeur: '1' },
  ]);
  assert.deepEqual(cases, []);
  assert.deepEqual(extraireCasesLegacy(undefined).cases, []);
});

// ─── premieresParProjet (périmètre pastilles = « Cocher tout ») ────────────────
test('premieresParProjet : borne aux N premières par projet (ordre conservé)', () => {
  const issues = [
    { projet: 'a', number: 5 }, { projet: 'b', number: 50 },
    { projet: 'a', number: 4 }, { projet: 'a', number: 3 },
    { projet: 'b', number: 49 },
  ];
  const r = premieresParProjet(issues, 2);
  assert.deepEqual(r.a, [5, 4]);   // 3 hors limite
  assert.deepEqual(r.b, [50, 49]);
});

test('premieresParProjet : limite Infinity → toutes les issues chargées (remise à zéro)', () => {
  const issues = [
    { projet: 'a', number: 1 }, { projet: 'a', number: 2 }, { projet: 'b', number: 3 },
  ];
  const r = premieresParProjet(issues, Infinity);
  assert.deepEqual(r.a, [1, 2]);
  assert.deepEqual(r.b, [3]);
});

// ─── ligneIdentite / prefixerIdentite / texteCopieAvecIdentite (issue #723) ───
test('ligneIdentite : « Issue #N — projet — titre »', () => {
  const it = { number: 723, title: 'Ajouter l\'identité' };
  assert.equal(ligneIdentite(it, 'bridge_agent'), 'Issue #723 — bridge_agent — Ajouter l\'identité');
});

test('ligneIdentite : détail d\'issue sans titre → pas de « — » final orphelin', () => {
  assert.equal(ligneIdentite({ number: 723 }, 'bridge_agent'), 'Issue #723 — bridge_agent');
  assert.equal(ligneIdentite({ number: 723, title: '' }, 'bridge_agent'), 'Issue #723 — bridge_agent');
});

test('ligneIdentite : titre multiligne ou très long → aplati sur une seule ligne', () => {
  const multiligne = { number: 1, title: 'Première ligne\nDeuxième ligne\r\nTroisième' };
  const r = multiligne && ligneIdentite(multiligne, 'p');
  assert.equal(r.includes('\n'), false);
  assert.equal(r, 'Issue #1 — p — Première ligne Deuxième ligne Troisième');

  const long = 'x'.repeat(5000);
  const rLong = ligneIdentite({ number: 2, title: long }, 'p');
  assert.equal(rLong.includes('\n'), false);
  assert.equal(rLong, 'Issue #2 — p — ' + long);
});

test('prefixerIdentite : texte non vide → ligne d\'identité + ligne vide + texte', () => {
  const it = { number: 5, title: 'Titre' };
  assert.equal(prefixerIdentite(it, 'p', 'Corps du rapport'),
    'Issue #5 — p — Titre\n\nCorps du rapport');
});

test('prefixerIdentite : texte vide ou blanc → inchangé (pas de ligne orpheline)', () => {
  const it = { number: 5, title: 'Titre' };
  assert.equal(prefixerIdentite(it, 'p', ''), '');
  assert.equal(prefixerIdentite(it, 'p', '   '), '   ');
  assert.equal(prefixerIdentite(it, 'p', undefined), undefined);
});

test('texteCopieAvecIdentite : « reponse » et « all » → identité présente', () => {
  const it = { number: 9, title: 'T' };
  assert.equal(texteCopieAvecIdentite('reponse', it, 'p', 'corps').startsWith('Issue #9 — p — T\n\n'), true);
  assert.equal(texteCopieAvecIdentite('all', it, 'p', 'corps').startsWith('Issue #9 — p — T\n\n'), true);
});

test('texteCopieAvecIdentite : « diff » → identité ABSENTE, texte brut inchangé', () => {
  const it = { number: 9, title: 'T' };
  const diffBrut = '===== Diff abc1234 =====\n\n+ligne ajoutée';
  assert.equal(texteCopieAvecIdentite('diff', it, 'p', diffBrut), diffBrut);
});

// ─── fusionnerInventaireFichier / construireInventaireCumule / texteSectionFichiers (issue #788) ──

test('fusionnerInventaireFichier : premier passage — reprend tel quel les compteurs du fichier', () => {
  const acc = fusionnerInventaireFichier({}, { chemin: 'a.py', statut: 'modifié', ancien_chemin: null, ajoutees: 3, supprimees: 1 });
  assert.deepEqual(acc, { 'a.py': { statut: 'modifié', ancienChemin: null, ajoutees: 3, supprimees: 1 } });
});

test('fusionnerInventaireFichier : second passage sur le même chemin — somme les compteurs, garde le DERNIER statut', () => {
  let acc = fusionnerInventaireFichier({}, { chemin: 'a.py', statut: 'ajouté', ancien_chemin: null, ajoutees: 10, supprimees: 0 });
  acc = fusionnerInventaireFichier(acc, { chemin: 'a.py', statut: 'modifié', ancien_chemin: null, ajoutees: 2, supprimees: 1 });
  assert.deepEqual(acc, { 'a.py': { statut: 'modifié', ancienChemin: null, ajoutees: 12, supprimees: 1 } });
});

test('fusionnerInventaireFichier : compteur binaire (null) d\'un côté → somme null, jamais un faux total', () => {
  let acc = fusionnerInventaireFichier({}, { chemin: 'img.png', statut: 'ajouté', ancien_chemin: null, ajoutees: null, supprimees: null });
  acc = fusionnerInventaireFichier(acc, { chemin: 'img.png', statut: 'modifié', ancien_chemin: null, ajoutees: 4, supprimees: 2 });
  assert.equal(acc['img.png'].ajoutees, null);
  assert.equal(acc['img.png'].supprimees, null);
});

test('fusionnerInventaireFichier : immuable — ne modifie pas l\'accumulateur reçu', () => {
  const acc = { 'a.py': { statut: 'modifié', ancienChemin: null, ajoutees: 1, supprimees: 0 } };
  fusionnerInventaireFichier(acc, { chemin: 'b.py', statut: 'ajouté', ancien_chemin: null, ajoutees: 5, supprimees: 0 });
  assert.deepEqual(Object.keys(acc), ['a.py']);
});

test('construireInventaireCumule : agrège les fichiers de plusieurs commits réussis', () => {
  const { fichiers, erreurs } = construireInventaireCumule([
    { hash: 'aaa', fichiers: [{ chemin: 'a.py', statut: 'modifié', ancien_chemin: null, ajoutees: 1, supprimees: 0 }] },
    { hash: 'bbb', fichiers: [{ chemin: 'b.py', statut: 'ajouté', ancien_chemin: null, ajoutees: 2, supprimees: 0 }] },
  ]);
  assert.deepEqual(Object.keys(fichiers).sort(), ['a.py', 'b.py']);
  assert.deepEqual(erreurs, []);
});

test('construireInventaireCumule : un commit en échec est reporté dans erreurs, n\'empêche pas les autres', () => {
  const { fichiers, erreurs } = construireInventaireCumule([
    { hash: 'aaa', fichiers: [{ chemin: 'a.py', statut: 'modifié', ancien_chemin: null, ajoutees: 1, supprimees: 0 }] },
    { hash: 'bbb', erreur: 'Commit bbb introuvable.' },
  ]);
  assert.deepEqual(Object.keys(fichiers), ['a.py']);
  assert.deepEqual(erreurs, [{ hash: 'bbb', message: 'Commit bbb introuvable.' }]);
});

test('texteSectionFichiers : etat « aucun » → chaîne vide (pas de section, pas d\'alerte)', () => {
  assert.equal(texteSectionFichiers('aucun', [{ hash: 'aaa', fichiers: [] }]), '');
});

test('texteSectionFichiers : etat « absente » → anomalie signalée, jamais en silence', () => {
  const texte = texteSectionFichiers('absente', []);
  assert.match(texte, /===== Fichiers modifiés =====/);
  assert.match(texte, /absente ou non reconnue/);
});

test('texteSectionFichiers : etat « hashes » avec renommage → ancien → nouveau explicite', () => {
  const texte = texteSectionFichiers('hashes', [
    { hash: 'aaa', fichiers: [{ chemin: 'nouveau.py', statut: 'renommé', ancien_chemin: 'ancien.py', ajoutees: 0, supprimees: 0 }] },
  ]);
  assert.match(texte, /renommé {2}ancien\.py → nouveau\.py {2}\(\+0 -0\)/);
});

test('texteSectionFichiers : etat « hashes » avec suppression → visible avec son statut', () => {
  const texte = texteSectionFichiers('hashes', [
    { hash: 'aaa', fichiers: [{ chemin: 'mort.py', statut: 'supprimé', ancien_chemin: null, ajoutees: 0, supprimees: 8 }] },
  ]);
  assert.match(texte, /supprimé {2}mort\.py {2}\(\+0 -8\)/);
});

test('texteSectionFichiers : fichier binaire → « (binaire) » plutôt qu\'un compte inventé', () => {
  const texte = texteSectionFichiers('hashes', [
    { hash: 'aaa', fichiers: [{ chemin: 'img.png', statut: 'ajouté', ancien_chemin: null, ajoutees: null, supprimees: null }] },
  ]);
  assert.match(texte, /ajouté {2}img\.png {2}\(binaire\)/);
});

test('texteSectionFichiers : aucun fichier et aucune erreur (commit(s) vide(s)) → mention explicite', () => {
  const texte = texteSectionFichiers('hashes', [{ hash: 'aaa', fichiers: [] }]);
  assert.match(texte, /aucun fichier/);
});

test('texteSectionFichiers : échec de commit → signalé, jamais avalé en silence (constat issue #788)', () => {
  const texte = texteSectionFichiers('hashes', [{ hash: 'aaa', erreur: 'Timeout (git n\'a pas répondu en 30s).' }]);
  assert.match(texte, /⚠ Commit aaa : inventaire impossible — Timeout/);
});
