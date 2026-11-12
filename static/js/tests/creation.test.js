// Tests de la logique PURE de creation.js (issue #652, refonte web §6.7).
//
// creation.js pilote tout le formulaire « Nouvelle issue » ; ses fonctions
// DOM/réseau (collecterFormulaire, envoyerIssue, joindreImage…) sont vérifiées
// manuellement dans le navigateur (voir VERIFICATIONS_MANUELLES.md). Ce fichier
// couvre uniquement les fonctions PURES exportées — détecteurs d'en-tête à
// partir d'un texte et cohérence projet/en-tête — jusqu'ici non testées bien
// qu'elles soient déjà pures (l'occasion de les couvrir, cf. § tâche #652).
//
// Note : importer creation.js exécute son code de tête, qui ne touche NI au DOM
// NI au réseau (l'exposition window.* est gardée par `typeof window`) — l'import
// est donc sûr sous Node, comme onglets.js/panneau_lateral.js.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  zoneEntete,
  lireChampEntete,
  retirerLigneEntete,
  normaliserTexteMode,
  reconnaitreModeTexte,
  reconnaitreComplexiteTexte,
  NIVEAUX_COMPLEXITE,
  timeoutDefautSelonMode,
  detecterIncoherenceProjet,
  decouperCorpsEnBlocs,
  projetEffectifBloc,
  modeEffectifBloc,
  complexiteEffectifBloc,
} from '../creation.js';

// ─── zoneEntete : borne les 25 premières lignes (issue #512) ───────────────
test('zoneEntete : renvoie tout le texte si < 25 lignes', () => {
  const t = 'a\nb\nc';
  assert.equal(zoneEntete(t), t);
});

test('zoneEntete : coupe au bout de 25 lignes', () => {
  const lignes = Array.from({ length: 40 }, (_, i) => 'ligne' + i);
  const texte = lignes.join('\n');
  const zone = zoneEntete(texte);
  // Les 25 premières lignes (indices 0..24) + le saut de ligne final.
  assert.equal(zone, lignes.slice(0, 25).join('\n') + '\n');
});

test('zoneEntete : corps vide/null → chaîne vide', () => {
  assert.equal(zoneEntete(''), '');
  assert.equal(zoneEntete(null), '');
  assert.equal(zoneEntete(undefined), '');
});

// ─── lireChampEntete : lecture d'un « | CHAMP | valeur | » ─────────────────
test('lireChampEntete : lit la valeur nettoyée', () => {
  const corps = '| PROJET | scrabble |\n| TIMEOUT | 1200s |';
  assert.equal(lireChampEntete(corps, 'PROJET'), 'scrabble');
  assert.equal(lireChampEntete(corps, 'TIMEOUT'), '1200s');
});

test('lireChampEntete : insensible à la casse du mot-clé, espaces tolérés', () => {
  assert.equal(lireChampEntete('|projet|  monprojet  |', 'PROJET'), 'monprojet');
  assert.equal(lireChampEntete('\t|  PROJET  |demo|', 'PROJET'), 'demo');
});

test('lireChampEntete : champ absent ou cellule vide → null', () => {
  assert.equal(lireChampEntete('| AUTRE | x |', 'PROJET'), null);
  assert.equal(lireChampEntete('| PROJET |   |', 'PROJET'), null);
});

test('lireChampEntete : ignore une mention hors zone d\'en-tête (issue #512)', () => {
  const bruit = Array.from({ length: 30 }, () => 'texte explicatif').join('\n');
  const corps = bruit + '\n| PROJET | tardif |';
  assert.equal(lireChampEntete(corps, 'PROJET'), null);
});

// ─── retirerLigneEntete : retire la ligne exacte du champ (issue #129) ─────
test('retirerLigneEntete : retire la ligne et son saut de ligne', () => {
  const corps = '| PROJET | scrabble |\nContenu réel';
  assert.equal(retirerLigneEntete(corps, 'PROJET'), 'Contenu réel');
});

test('retirerLigneEntete : cible la ligne exacte au milieu du tableau', () => {
  const corps = '| SOURCE | CC |\n| TIMEOUT | 300 |\n| DEST | CCL |';
  assert.equal(retirerLigneEntete(corps, 'TIMEOUT'),
    '| SOURCE | CC |\n| DEST | CCL |');
});

test('retirerLigneEntete : champ absent → corps inchangé', () => {
  const corps = '| PROJET | x |';
  assert.equal(retirerLigneEntete(corps, 'MODE'), corps);
});

test('retirerLigneEntete : dernière ligne sans \\n final → retire le \\n précédent', () => {
  const corps = 'Contenu\n| MODE | ecriture |';
  assert.equal(retirerLigneEntete(corps, 'MODE'), 'Contenu');
});

// ─── reconnaitreModeTexte / normaliserTexteMode (issue #326) ───────────────
test('normaliserTexteMode : minuscule, trim, sans accents', () => {
  assert.equal(normaliserTexteMode('  ÉCRITURE '), 'ecriture');
  assert.equal(normaliserTexteMode('Lecture Active'), 'lecture active');
});

test('reconnaitreModeTexte : reconnaît les trois modes (tolérant)', () => {
  assert.equal(reconnaitreModeTexte('écriture'), 'ecriture');
  assert.equal(reconnaitreModeTexte('mode_write'), 'ecriture');
  assert.equal(reconnaitreModeTexte('lecture active'), 'lecture_active');
  assert.equal(reconnaitreModeTexte('mode_scratch'), 'lecture_active');
  assert.equal(reconnaitreModeTexte('lecture seule'), 'lecture');
  assert.equal(reconnaitreModeTexte('read'), 'lecture');
});

test('reconnaitreModeTexte : « lecture active » n\'est pas absorbé par « lecture »', () => {
  // L'ordre du tableau MODE_SYNONYMES teste lecture_active avant lecture.
  assert.equal(reconnaitreModeTexte('Lecture active (scratch)'), 'lecture_active');
});

test('reconnaitreModeTexte : absent ou non reconnu → lecture (défaut sûr)', () => {
  assert.equal(reconnaitreModeTexte(''), 'lecture');
  assert.equal(reconnaitreModeTexte(null), 'lecture');
  assert.equal(reconnaitreModeTexte('n\'importe quoi'), 'lecture');
});

// ─── timeoutDefautSelonMode : plancher écriture (issue #752) ──────────────
test('timeoutDefautSelonMode : écriture avec un projet à 300s → 900s', () => {
  assert.equal(timeoutDefautSelonMode(300, 'ecriture'), 900);
});

test('timeoutDefautSelonMode : écriture avec un projet à 1200s → 1200s (inchangé)', () => {
  assert.equal(timeoutDefautSelonMode(1200, 'ecriture'), 1200);
});

test('timeoutDefautSelonMode : lecture/lecture active → valeur du projet inchangée', () => {
  assert.equal(timeoutDefautSelonMode(300, 'lecture'), 300);
  assert.equal(timeoutDefautSelonMode(300, 'lecture_active'), 300);
});

// ─── detecterIncoherenceProjet : cohérence projet ⇄ en-tête (issue #44) ────
test('detecterIncoherenceProjet : champ PROJET absent → null (pas de vérif)', () => {
  assert.equal(detecterIncoherenceProjet({ corps: 'rien', projet: 'scrabble' }), null);
});

test('detecterIncoherenceProjet : identique (casse ignorée) → null', () => {
  assert.equal(
    detecterIncoherenceProjet({ corps: '| PROJET | Scrabble |', projet: 'scrabble' }),
    null);
});

test('detecterIncoherenceProjet : divergence → {projetIssue, projetSelectionne}', () => {
  assert.deepEqual(
    detecterIncoherenceProjet({ corps: '| PROJET | autre |', projet: 'scrabble' }),
    { projetIssue: 'autre', projetSelectionne: 'scrabble' });
});

// ─── decouperCorpsEnBlocs : envoi en lot (issue #135) ──────────────────────
test('decouperCorpsEnBlocs : aucun #Titre: → tableau vide (pas de lot)', () => {
  assert.deepEqual(decouperCorpsEnBlocs('un corps sans titre'), []);
});

test('decouperCorpsEnBlocs : un seul bloc', () => {
  assert.deepEqual(
    decouperCorpsEnBlocs('#Titre: A\ncorps de A'),
    [{ titre: 'A', corps: 'corps de A' }]);
});

test('decouperCorpsEnBlocs : plusieurs blocs, casse et corps propres', () => {
  const corps = '#Titre: Premier\nligne 1\n#titre: Second\nligne 2';
  assert.deepEqual(decouperCorpsEnBlocs(corps), [
    { titre: 'Premier', corps: 'ligne 1' },
    { titre: 'Second', corps: 'ligne 2' },
  ]);
});

test('decouperCorpsEnBlocs : titre vide possible (garde-fou à l\'envoi)', () => {
  const corps = '#Titre:\nsans titre\n#Titre: B\nok';
  const blocs = decouperCorpsEnBlocs(corps);
  assert.equal(blocs.length, 2);
  assert.equal(blocs[0].titre, '');
  assert.equal(blocs[1].titre, 'B');
});

// ─── projetEffectifBloc / modeEffectifBloc : repli formulaire (issue #142/#505)
test('projetEffectifBloc : PROJET du bloc prioritaire, sinon repli formulaire', () => {
  assert.equal(projetEffectifBloc({ corps: '| PROJET | jeu |' }, 'form'), 'jeu');
  assert.equal(projetEffectifBloc({ corps: 'rien' }, 'form'), 'form');
});

test('modeEffectifBloc : MODE du bloc reconnu, sinon repli formulaire', () => {
  assert.equal(modeEffectifBloc({ corps: '| MODE | écriture |' }, 'lecture'), 'ecriture');
  assert.equal(modeEffectifBloc({ corps: 'rien' }, 'lecture_active'), 'lecture_active');
});

// ─── reconnaitreComplexiteTexte : reconnaissance STRICTE (issue #884) ──────
// Contrairement à reconnaitreModeTexte, AUCUN synonyme toléré et AUCUN repli
// implicite : seuls les quatre mots exacts de NIVEAUX_COMPLEXITE (insensible
// à la casse/espaces) sont reconnus, tout le reste renvoie null — l'appelant
// (detecterComplexiteDansCorps / complexiteEffectifBloc) décide du repli.
test('reconnaitreComplexiteTexte : reconnaît les quatre niveaux exacts, insensible à la casse', () => {
  for (const niveau of NIVEAUX_COMPLEXITE) {
    assert.equal(reconnaitreComplexiteTexte(niveau), niveau);
    assert.equal(reconnaitreComplexiteTexte('  ' + niveau.toUpperCase() + '  '), niveau);
  }
});

test('reconnaitreComplexiteTexte : valeur inconnue → null (pas de repli)', () => {
  assert.equal(reconnaitreComplexiteTexte('rapidos'), null);
  assert.equal(reconnaitreComplexiteTexte('moyen'), null);
});

test('reconnaitreComplexiteTexte : absent (vide/null) → null', () => {
  assert.equal(reconnaitreComplexiteTexte(''), null);
  assert.equal(reconnaitreComplexiteTexte(null), null);
});

// ─── lireChampEntete/retirerLigneEntete appliqués à COMPLEXITE/REDACTEUR/
//     ATTENTE (issue #884) — ces fonctions sont déjà génériques (champ passé
//     en paramètre), ces tests documentent simplement leur usage sur les
//     nouveaux champs traités par le formulaire. ───────────────────────────
test('lireChampEntete : lit COMPLEXITE et REDACTEUR comme tout autre champ', () => {
  const corps = '| PROJET     | gestionstock |\n'
              + '| REDACTEUR  | gestionstock |\n'
              + '| MODE       | écriture     |\n'
              + '| COMPLEXITE | rapide       |\n'
              + '| TIMEOUT    | 900s         |';
  assert.equal(lireChampEntete(corps, 'REDACTEUR'), 'gestionstock');
  assert.equal(lireChampEntete(corps, 'COMPLEXITE'), 'rapide');
});

test('retirerLigneEntete : retire REDACTEUR sans toucher aux lignes voisines', () => {
  const corps = '| PROJET    | gestionstock |\n| REDACTEUR | gestionstock |\n| MODE | écriture |';
  assert.equal(retirerLigneEntete(corps, 'REDACTEUR'),
    '| PROJET    | gestionstock |\n| MODE | écriture |');
});

test('retirerLigneEntete : COMPLEXITE non reconnue est quand même retirable (l\'appelant décide, pas la regex)', () => {
  const corps = '| COMPLEXITE | rapidos |\nContenu';
  assert.equal(retirerLigneEntete(corps, 'COMPLEXITE'), 'Contenu');
});

test('lireChampEntete : ATTENTE lue mais retirerLigneEntete n\'est volontairement PAS appelée dessus '
    + 'par detecterAttenteDansCorps (vérifié manuellement, non testable hors DOM)', () => {
  const corps = '| ATTENTE | après la release 2.0 |\nReste du corps';
  assert.equal(lireChampEntete(corps, 'ATTENTE'), 'après la release 2.0');
  // Le corps n'est PAS muté par ce test : on vérifie juste que la ligne
  // RESTE lisible/intacte, comme le fait le détecteur (il ne retire rien).
  assert.equal(corps.includes('| ATTENTE | après la release 2.0 |'), true);
});

// ─── complexiteEffectifBloc : repli formulaire, lot multi-issues (#884) ────
test('complexiteEffectifBloc : COMPLEXITE du bloc prioritaire si reconnue, sinon repli formulaire', () => {
  assert.equal(complexiteEffectifBloc({ corps: '| COMPLEXITE | lourd |' }, 'normal'), 'lourd');
  assert.equal(complexiteEffectifBloc({ corps: 'rien' }, 'court'), 'court');
});

test('complexiteEffectifBloc : valeur non reconnue → repli formulaire (comme absente)', () => {
  assert.equal(complexiteEffectifBloc({ corps: '| COMPLEXITE | rapidos |' }, 'normal'), 'normal');
});

test('complexiteEffectifBloc : lot de plusieurs issues, une COMPLEXITE par bloc', () => {
  const corps = '#Titre: Un\n| COMPLEXITE | rapide |\ncorps un'
              + '\n#Titre: Deux\n| COMPLEXITE | rapidos |\ncorps deux'
              + '\n#Titre: Trois\ncorps trois, sans COMPLEXITE';
  const blocs = decouperCorpsEnBlocs(corps);
  assert.equal(blocs.length, 3);
  assert.equal(complexiteEffectifBloc(blocs[0], 'normal'), 'rapide');   // reconnue
  assert.equal(complexiteEffectifBloc(blocs[1], 'normal'), 'normal');  // non reconnue → repli
  assert.equal(complexiteEffectifBloc(blocs[2], 'normal'), 'normal');  // absente → repli
});
