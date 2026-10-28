// Tests de logique pure de l'onglet « En attente » (issue #714, suite #713 ;
// ordre manuel, issue #819). Aucune dépendance au DOM ni au réseau — voir
// static/js/tests/README.md pour lancer ces tests (node --test).
import { test } from 'node:test';
import assert from 'node:assert/strict';

// couleurFondPastilleProjet délègue à l'ancien code via appelerAncien (pont
// socle → app.js, voir socle/pont.js) : window.couleurProjet doit exister
// AVANT l'import du module (comme resultats_activation.test.js).
global.window = globalThis;
window.couleurProjet = (nom) => (nom === 'bridge_agent' ? '#EB0000' : undefined);

import {
  formaterDateAttente,
  decisionBadgeAttente,
  decisionDeplacementAttente,
  descriptionLigneAttente,
  couleurFondPastilleProjet,
  couleurTexteSurFond,
  messageEchecAttente,
  texteACopierAttente,
  fautRechargerAttente,
} from '../attente.js';

// ─── formaterDateAttente ────────────────────────────────────────────────────

test('formaterDateAttente : JJ/MM/AAAA HH:MM, zéro-rembourré', () => {
  assert.equal(formaterDateAttente(new Date(2024, 0, 5, 9, 7)), '05/01/2024 09:07');
});

test('formaterDateAttente : jour/mois/heure/minute à deux chiffres non modifiés', () => {
  assert.equal(formaterDateAttente(new Date(2026, 10, 23, 14, 32)), '23/11/2026 14:32');
});

test('formaterDateAttente : absent → chaîne vide', () => {
  assert.equal(formaterDateAttente(null), '');
  assert.equal(formaterDateAttente(undefined), '');
});

// ─── decisionBadgeAttente ───────────────────────────────────────────────────

test('decisionBadgeAttente : > 0 → affiché avec le compteur en texte', () => {
  assert.deepEqual(decisionBadgeAttente(1), { afficher: true, texte: '1' });
  assert.deepEqual(decisionBadgeAttente(12), { afficher: true, texte: '12' });
});

test('decisionBadgeAttente : 0/absent/null → masqué (rien d\'affiché)', () => {
  assert.deepEqual(decisionBadgeAttente(0), { afficher: false, texte: '' });
  assert.deepEqual(decisionBadgeAttente(undefined), { afficher: false, texte: '' });
  assert.deepEqual(decisionBadgeAttente(null), { afficher: false, texte: '' });
});

// ─── decisionDeplacementAttente (issue #819) ───────────────────────────────

test('decisionDeplacementAttente : premier élément → ne peut pas monter', () => {
  assert.deepEqual(decisionDeplacementAttente(0, 3), { peutMonter: false, peutDescendre: true });
});

test('decisionDeplacementAttente : dernier élément → ne peut pas descendre', () => {
  assert.deepEqual(decisionDeplacementAttente(2, 3), { peutMonter: true, peutDescendre: false });
});

test('decisionDeplacementAttente : élément du milieu → les deux sens possibles', () => {
  assert.deepEqual(decisionDeplacementAttente(1, 3), { peutMonter: true, peutDescendre: true });
});

test('decisionDeplacementAttente : seul élément de la liste → ni l\'un ni l\'autre', () => {
  assert.deepEqual(decisionDeplacementAttente(0, 1), { peutMonter: false, peutDescendre: false });
});

// ─── descriptionLigneAttente ────────────────────────────────────────────────

test('descriptionLigneAttente : reprend titre/projet/condition tels quels', () => {
  const item = { id: 'a.txt', titre: 'Mon titre', projet: 'bridge_agent',
                 date: Math.floor(new Date(2026, 0, 1, 10, 0).getTime() / 1000),
                 condition: 'après la fusion de l\'étape C' };
  const desc = descriptionLigneAttente(item);
  assert.equal(desc.titre, 'Mon titre');
  assert.equal(desc.projet, 'bridge_agent');
  assert.equal(desc.condition, 'après la fusion de l\'étape C');
  assert.equal(desc.date, '01/01/2026 10:00');
});

test('descriptionLigneAttente : titre/condition absents → replis explicites', () => {
  const desc = descriptionLigneAttente({ id: 'a.txt', projet: 'bridge_agent', date: 0 });
  assert.equal(desc.titre, '(sans titre)');
  assert.equal(desc.condition, '(condition non précisée)');
  assert.equal(desc.date, '');
});

test('descriptionLigneAttente : item absent ne lève pas d\'exception', () => {
  const desc = descriptionLigneAttente(null);
  assert.equal(desc.titre, '(sans titre)');
  assert.equal(desc.projet, '');
  assert.equal(desc.projetAffiche, 'projet inconnu');
});

// ─── descriptionLigneAttente : projetAffiche (pastille nominative, #728) ───

test('descriptionLigneAttente : projetAffiche reprend le nom du projet', () => {
  const desc = descriptionLigneAttente({ id: 'a.txt', titre: 'T', projet: 'bridge_agent' });
  assert.equal(desc.projetAffiche, 'bridge_agent');
});

test('descriptionLigneAttente : projetAffiche → « projet inconnu » si projet vide', () => {
  assert.equal(descriptionLigneAttente({ id: 'a.txt', projet: '' }).projetAffiche, 'projet inconnu');
  assert.equal(descriptionLigneAttente({ id: 'a.txt' }).projetAffiche, 'projet inconnu');
});

// ─── texteACopierAttente (bouton « copier » du titre, issue #823) ─────────

test('texteACopierAttente : reprend le titre exact tel qu\'écrit dans le fichier', () => {
  assert.equal(texteACopierAttente({ titre: 'Mon titre' }), 'Mon titre');
});

test('texteACopierAttente : titre absent/vide → null, jamais le repli « (sans titre) »', () => {
  assert.equal(texteACopierAttente({ id: 'a.txt' }), null);
  assert.equal(texteACopierAttente({ titre: '' }), null);
  assert.equal(texteACopierAttente({ titre: '   ' }), null);
});

test('texteACopierAttente : item absent ne lève pas d\'exception', () => {
  assert.equal(texteACopierAttente(null), null);
  assert.equal(texteACopierAttente(undefined), null);
});

test('texteACopierAttente : ne modifie pas le titre (espaces internes préservés)', () => {
  assert.equal(texteACopierAttente({ titre: '  Titre avec espaces  ' }), '  Titre avec espaces  ');
});

// ─── couleurFondPastilleProjet ──────────────────────────────────────────────

test('couleurFondPastilleProjet : délègue à couleurProjet (ancien code) si projet non vide', () => {
  assert.equal(couleurFondPastilleProjet('bridge_agent'), '#EB0000');
});

test('couleurFondPastilleProjet : gris neutre si projet vide/absent — jamais rien', () => {
  assert.equal(couleurFondPastilleProjet(''), '#888');
  assert.equal(couleurFondPastilleProjet(undefined), '#888');
});

// ─── couleurTexteSurFond : noir ou blanc selon le meilleur contraste ───────

test('couleurTexteSurFond : fond noir → texte blanc', () => {
  assert.equal(couleurTexteSurFond('#000000'), '#fff');
});

test('couleurTexteSurFond : fond blanc → texte noir', () => {
  assert.equal(couleurTexteSurFond('#ffffff'), '#000');
});

test('couleurTexteSurFond : gris de repli « projet inconnu » (#888) → texte noir', () => {
  assert.equal(couleurTexteSurFond('#888'), '#000');
});

test('couleurTexteSurFond : hex court (#RGB) et hsl() tous deux reconnus', () => {
  assert.equal(couleurTexteSurFond('#000'), '#fff');
  assert.equal(couleurTexteSurFond('hsl(210, 100%, 10%)'), '#fff');
  assert.equal(couleurTexteSurFond('hsl(60, 100%, 90%)'), '#000');
});

test('couleurTexteSurFond : couleur non reconnue → noir par défaut (pas de régression)', () => {
  assert.equal(couleurTexteSurFond('rebeccapurple'), '#000');
  assert.equal(couleurTexteSurFond(''), '#000');
});

// ─── messageEchecAttente ────────────────────────────────────────────────────

test('messageEchecAttente : corps JSON avec champ erreur → message serveur', () => {
  const erreur = { corps: '{"succes":false,"erreur":"identifiant invalide."}' };
  assert.equal(messageEchecAttente(erreur, 'repli'), 'identifiant invalide.');
});

test('messageEchecAttente : corps non-JSON → repli', () => {
  assert.equal(messageEchecAttente({ corps: 'Internal Server Error' }, 'repli'), 'repli');
});

test('messageEchecAttente : corps JSON sans champ erreur → repli', () => {
  assert.equal(messageEchecAttente({ corps: '{"succes":false}' }, 'repli'), 'repli');
});

test('messageEchecAttente : erreur absente/sans corps → repli', () => {
  assert.equal(messageEchecAttente(null, 'repli'), 'repli');
  assert.equal(messageEchecAttente({}, 'repli'), 'repli');
});

// ─── fautRechargerAttente (issue #825) ─────────────────────────────────────
// Déclenchement du rechargement pendant que l'onglet est ouvert : sur
// changement du nombre (#713, inchangé par cette issue) OU de la signature
// de contenu (#825 — un fichier remplacé sous le même nom, même nombre).

test('fautRechargerAttente : nombre et signature identiques → pas de rechargement', () => {
  assert.equal(
    fautRechargerAttente({ nb: 2, signature: 'a.txt:1:10|b.txt:2:20' },
                          { nb: 2, signature: 'a.txt:1:10|b.txt:2:20' }),
    false);
});

test('fautRechargerAttente : signature changée à nombre égal → rechargement '
   + '(fichier remplacé sous le même nom, issue #825)', () => {
  assert.equal(
    fautRechargerAttente({ nb: 1, signature: 'mono.txt:1000:50' },
                          { nb: 1, signature: 'mono.txt:2000:63' }),
    true);
});

test('fautRechargerAttente : nombre changé, signature inchangée (cas théorique) '
   + '→ rechargement', () => {
  assert.equal(
    fautRechargerAttente({ nb: 1, signature: 'x' }, { nb: 2, signature: 'x' }),
    true);
});

test('fautRechargerAttente : nombre changé → rechargement (comportement #713 inchangé)', () => {
  assert.equal(
    fautRechargerAttente({ nb: 1, signature: 'a.txt:1:10' },
                          { nb: 2, signature: 'a.txt:1:10|b.txt:2:20' }),
    true);
});

test('fautRechargerAttente : état précédent absent (premier appel) → rechargement', () => {
  assert.equal(fautRechargerAttente(null, { nb: 1, signature: 'a.txt:1:10' }), true);
});
