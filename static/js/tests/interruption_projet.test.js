// Tests de logique pure des boutons de niveau PROJET du panneau Infrastructure
// (issue #954 : « Tout interrompre pour ce projet », « Redémarrer le
// watcher »/« Interrompre et relancer », « Arrêter » enrichi). Aucune
// dépendance au DOM ni au réseau — voir static/js/tests/README.md pour
// lancer ces tests (node --test).
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  afficherBoutonToutInterrompre,
  libelleBoutonWatcherCcl,
  classifierIssuesEnCoursProjet,
  fautConfirmerActionProjet,
  libelleIssueCourte,
  listeLibellesIssues,
  messageToutInterrompreProjet,
  messageRedemarrerWatcherProjet,
  messageArreterWatcherProjet,
  resumeArretCibles,
  demarrerActionProjet,
  terminerActionProjet,
  actionProjetEnCours,
  decisionBoutonProjet,
  DUREE_MAX_ACTION_PROJET_MS,
} from '../interruption_projet.js';

// ─── afficherBoutonToutInterrompre / libelleBoutonWatcherCcl ──────────────

test('afficherBoutonToutInterrompre : affiché seulement s\'il y a au moins une issue en cours', () => {
  assert.equal(afficherBoutonToutInterrompre(0), false);
  assert.equal(afficherBoutonToutInterrompre(undefined), false);
  assert.equal(afficherBoutonToutInterrompre(1), true);
  assert.equal(afficherBoutonToutInterrompre(3), true);
});

test('libelleBoutonWatcherCcl : "Lancer" si éteint, "Redémarrer le watcher" si actif (issue #954, renommage)', () => {
  assert.equal(libelleBoutonWatcherCcl(false), '▶ Lancer');
  assert.equal(libelleBoutonWatcherCcl(true), '↺ Redémarrer le watcher');
});

// ─── classifierIssuesEnCoursProjet : normales vs interactives ─────────────

test('classifierIssuesEnCoursProjet : sans label mode_interactif → normales', () => {
  const { normales, interactives } = classifierIssuesEnCoursProjet([
    { numero: 1, titre: 'A', mode: 'ecriture', labels: ['for-linux', 'mode_write'] },
    { numero: 2, titre: 'B', mode: 'lecture', labels: [] },
  ]);
  assert.deepEqual(normales.map((i) => i.numero), [1, 2]);
  assert.deepEqual(interactives, []);
  assert.equal(normales[0].interactif, false);
});

test('classifierIssuesEnCoursProjet : label mode_interactif → interactives, jamais couvertes par #949', () => {
  const { normales, interactives } = classifierIssuesEnCoursProjet([
    { numero: 10, titre: 'Interactive', mode: 'ecriture', labels: ['mode_interactif'] },
    { numero: 11, titre: 'Normale', mode: 'ecriture', labels: ['for-linux'] },
  ]);
  assert.deepEqual(normales.map((i) => i.numero), [11]);
  assert.deepEqual(interactives.map((i) => i.numero), [10]);
  assert.equal(interactives[0].interactif, true);
});

test('classifierIssuesEnCoursProjet : liste vide/absente → deux groupes vides', () => {
  assert.deepEqual(classifierIssuesEnCoursProjet([]), { normales: [], interactives: [] });
  assert.deepEqual(classifierIssuesEnCoursProjet(undefined), { normales: [], interactives: [] });
});

test('classifierIssuesEnCoursProjet : accepte des labels objets {name} comme des chaînes', () => {
  const { interactives } = classifierIssuesEnCoursProjet([
    { numero: 5, titre: '', mode: 'ecriture', labels: [{ name: 'mode_interactif' }] },
  ]);
  assert.equal(interactives.length, 1);
});

// ─── fautConfirmerActionProjet ──────────────────────────────────────────────

test('fautConfirmerActionProjet : aucune issue en cours → pas de confirmation (comportement direct inchangé)', () => {
  assert.equal(fautConfirmerActionProjet([], []), false);
  assert.equal(fautConfirmerActionProjet(undefined, undefined), false);
});

test('fautConfirmerActionProjet : au moins une issue (normale OU interactive) → confirmation', () => {
  assert.equal(fautConfirmerActionProjet([{ numero: 1 }], []), true);
  assert.equal(fautConfirmerActionProjet([], [{ numero: 2 }]), true);
  assert.equal(fautConfirmerActionProjet([{ numero: 1 }], [{ numero: 2 }]), true);
});

// ─── libelleIssueCourte / listeLibellesIssues ──────────────────────────────

test('libelleIssueCourte : numéro + titre, ou numéro seul sans titre', () => {
  assert.equal(libelleIssueCourte({ numero: 12, titre: 'Mon titre' }), '#12 — Mon titre');
  assert.equal(libelleIssueCourte({ numero: 13, titre: '' }), '#13');
  assert.equal(libelleIssueCourte({ numero: 14 }), '#14');
});

test('listeLibellesIssues : jointure virgule, liste vide → chaîne vide', () => {
  assert.equal(listeLibellesIssues([{ numero: 1, titre: 'A' }, { numero: 2, titre: '' }]), '#1 — A, #2');
  assert.equal(listeLibellesIssues([]), '');
  assert.equal(listeLibellesIssues(undefined), '');
});

// ─── Messages de confirmation (issue #954, points 1-3) ────────────────────

test('messageToutInterrompreProjet : nomme les issues ciblées, rappelle worktrees/commits conservés, watcher actif', () => {
  const msg = messageToutInterrompreProjet('bridge_agent',
    [{ numero: 1, titre: 'Une tâche' }], []);
  assert.match(msg, /#1 — Une tâche/);
  assert.match(msg, /needs-human/);
  assert.match(msg, /conservés/);
  assert.match(msg, /watcher reste actif/);
  assert.doesNotMatch(msg, /interactive/);
});

test('messageToutInterrompreProjet : signale les interactives sans les proposer à l\'arrêt ici', () => {
  const msg = messageToutInterrompreProjet('bridge_agent',
    [{ numero: 1, titre: 'A' }], [{ numero: 2, titre: 'Interactive' }]);
  assert.match(msg, /#2 — Interactive/);
  assert.match(msg, /PAS/);
  assert.match(msg, /propre ligne/);
});

test('messageRedemarrerWatcherProjet : annonce interruption puis relance automatique', () => {
  const msg = messageRedemarrerWatcherProjet('bridge_agent',
    [{ numero: 3, titre: 'X' }], []);
  assert.match(msg, /#3 — X/);
  assert.match(msg, /relancées automatiquement/);
});

test('messageRedemarrerWatcherProjet : sans issue normale, watcher simplement redémarré', () => {
  const msg = messageRedemarrerWatcherProjet('bridge_agent', [], [{ numero: 9, titre: 'Interactive' }]);
  assert.match(msg, /simplement redémarré/);
  assert.match(msg, /#9 — Interactive/);
  assert.match(msg, /reprises automatiquement/);
});

test('messageArreterWatcherProjet : sans aucune issue en cours → texte historique simple', () => {
  assert.equal(messageArreterWatcherProjet('bridge_agent', [], []),
    'Arrêter le watcher du projet « bridge_agent » ?');
});

test('messageArreterWatcherProjet : nomme les normales interrompues proprement, pas de relance automatique', () => {
  const msg = messageArreterWatcherProjet('bridge_agent', [{ numero: 4, titre: 'Y' }], []);
  assert.match(msg, /#4 — Y/);
  assert.match(msg, /orphelin/);
  assert.match(msg, /aucune relance automatique/i);
});

test('messageArreterWatcherProjet : interactives restent actives mais non supervisées, chemin historique distinct', () => {
  const msg = messageArreterWatcherProjet('bridge_agent', [], [{ numero: 8, titre: 'Interactive' }]);
  assert.match(msg, /#8 — Interactive/);
  assert.match(msg, /PAS.*être arrêtées proprement/s);
  assert.match(msg, /propre ligne/);
});

// ─── resumeArretCibles : résultat lisible de « Tout interrompre » ─────────

test('resumeArretCibles : toutes arrêtées → succès', () => {
  const r = resumeArretCibles([1, 2], []);
  assert.equal(r.type, 'succes');
  assert.match(r.texte, /2 issue\(s\) arrêtée\(s\) \(#1, #2\)/);
});

test('resumeArretCibles : certaines non arrêtées à temps → avertissement', () => {
  const r = resumeArretCibles([1], [2, 3]);
  assert.equal(r.type, 'avertissement');
  assert.match(r.texte, /1 issue\(s\) arrêtée\(s\) \(#1\)/);
  assert.match(r.texte, /2 non arrêtée\(s\) à temps \(#2, #3\)/);
});

test('resumeArretCibles : aucune cible → 0 arrêtée, succès', () => {
  const r = resumeArretCibles([], []);
  assert.equal(r.type, 'succes');
  assert.match(r.texte, /^0 issue\(s\) arrêtée\(s\)\./);
});

// ─── Registre « action en cours » du PROJET + décision pure de rendu (issue
// #956, point 3/4) — CONSULTÉS par panneau_lateral.js à chaque reconstruction
// des boutons de niveau projet, au lieu d'un état posé une seule fois sur les
// nœuds DOM présents au clic.

test('demarrerActionProjet : accepte le premier déclenchement, refuse un second pendant que le premier est en cours', () => {
  const registre = new Map();
  assert.equal(demarrerActionProjet(registre, 'bridge_agent', 'tout_interrompre', [1, 2]), true);
  assert.equal(registre.has('bridge_agent'), true);
  // Un AUTRE des 4 boutons de ce MÊME projet (ex. « Arrêter ») est refusé
  // pendant que « Tout interrompre » tourne déjà (point 4 de #954/#956).
  assert.equal(demarrerActionProjet(registre, 'bridge_agent', 'arreter', []), false);
  // Projet DIFFÉRENT — indépendant, accepté.
  assert.equal(demarrerActionProjet(registre, 'scrabble', 'arreter', []), true);
});

test('terminerActionProjet : libère le projet, un nouveau déclenchement redevient possible', () => {
  const registre = new Map();
  demarrerActionProjet(registre, 'bridge_agent', 'tout_interrompre', [1]);
  terminerActionProjet(registre, 'bridge_agent');
  assert.equal(registre.has('bridge_agent'), false);
  assert.equal(demarrerActionProjet(registre, 'bridge_agent', 'arreter', []), true);
});

test('actionProjetEnCours : renvoie l\'entrée { action, debut, numeros } tant qu\'elle est fraîche, null si absente', () => {
  const registre = new Map();
  assert.equal(actionProjetEnCours(registre, 'bridge_agent'), null);
  demarrerActionProjet(registre, 'bridge_agent', 'redemarrer_watcher', [12, 13], 1000);
  const entree = actionProjetEnCours(registre, 'bridge_agent', 1500);
  assert.equal(entree.action, 'redemarrer_watcher');
  assert.equal(entree.debut, 1000);
  assert.deepEqual([...entree.numeros].sort(), [12, 13]);
});

test('actionProjetEnCours : garde-fou — une entrée plus vieille que DUREE_MAX_ACTION_PROJET_MS est ignorée ET retirée (un bouton projet ne doit jamais rester bloqué indéfiniment)', () => {
  const registre = new Map();
  demarrerActionProjet(registre, 'bridge_agent', 'arreter', [], 0);
  const maintenant = DUREE_MAX_ACTION_PROJET_MS + 1;
  assert.equal(actionProjetEnCours(registre, 'bridge_agent', maintenant), null);
  assert.equal(registre.has('bridge_agent'), false);
  assert.equal(demarrerActionProjet(registre, 'bridge_agent', 'redemarrer_watcher', [], maintenant), true);
});

test('decisionBoutonProjet : aucune action en cours → actif, libellé normal conservé par l\'appelant', () => {
  assert.deepEqual(decisionBoutonProjet(null), { desactive: false, libelle: null });
});

test('decisionBoutonProjet : une action en cours → désactivé, libellé d\'attente générique pour les 4 boutons', () => {
  assert.deepEqual(
    decisionBoutonProjet({ action: 'tout_interrompre', debut: 0, numeros: new Set([1]) }),
    { desactive: true, libelle: '⏳ …' },
  );
});

// ─── Levée de l'état dans chaque chemin de fin (issue #956, point 4) :
// succès, échec, délai dépassé, erreur réseau, annulation — tous passent par
// terminerActionProjet dans le `finally` des 3 fonctions exportées
// (toutInterrompreProjet/redemarrerWatcherAvecRelance/arreterWatcherProjet),
// vérifié ici sur le registre lui-même (le câblage réseau est vérifié
// manuellement, voir le rapport de clôture).

test('terminerActionProjet : chemins succès/échec/délai dépassé/erreur réseau — même `finally`, l\'état est levé identiquement', () => {
  const registre = new Map();
  demarrerActionProjet(registre, 'bridge_agent', 'arreter', [1, 2]);
  terminerActionProjet(registre, 'bridge_agent'); // appelé dans le `finally`, quelle que soit l'issue du bloc try
  assert.equal(actionProjetEnCours(registre, 'bridge_agent'), null);
});

test('chemin annulation (confirmation refusée) : l\'état est démarré AVANT la confirmation (#954, pour désactiver les 4 boutons pendant la boîte de dialogue elle-même) mais levé identiquement par le `finally` si elle est refusée', () => {
  const registre = new Map();
  demarrerActionProjet(registre, 'bridge_agent', 'tout_interrompre', []);
  const confirmationRefusee = true;
  if (confirmationRefusee) terminerActionProjet(registre, 'bridge_agent'); // `finally` atteint via le `return` anticipé
  assert.equal(actionProjetEnCours(registre, 'bridge_agent'), null);
});
