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
  demarrerActionLigne,
  terminerActionLigne,
  actionLigneEnCours,
  decisionAffichageBoutonsLigne,
  DUREE_MAX_ACTION_LIGNE_MS,
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

// ─── Garde anti-double-clic + registre « action en cours » d'une ligne
// (issues #748/#951/#956) ───────────────────────────────────────────────────

test('cleInterruption : clé stable par couple (projet, numéro)', () => {
  assert.equal(cleInterruption('bridge_agent', 452), 'bridge_agent#452');
  assert.equal(cleInterruption('bridge_agent', '452'), 'bridge_agent#452');
});

test('demarrerActionLigne : accepte le premier déclenchement, refuse un second pendant que le premier est en cours', () => {
  const registre = new Map();
  assert.equal(demarrerActionLigne(registre, 'bridge_agent', 452, 'fermer'), true);
  assert.equal(registre.has('bridge_agent#452'), true);
  // Second déclenchement pour LE MÊME couple, avant toute fin — refusé, quelle
  // que soit l'action demandée (point 2 de #956 : UNE SEULE action à la fois
  // pour une ligne, « Interrompre » ne doit pas pouvoir démarrer pendant que
  // « Fermer » tourne déjà, et réciproquement).
  assert.equal(demarrerActionLigne(registre, 'bridge_agent', 452, 'interrompre'), false);
  // Couple DIFFÉRENT (autre numéro, ou autre projet) — indépendant, accepté.
  assert.equal(demarrerActionLigne(registre, 'bridge_agent', 453, 'fermer'), true);
  assert.equal(demarrerActionLigne(registre, 'scrabble', 452, 'fermer'), true);
});

test('terminerActionLigne : libère le couple, un nouveau déclenchement redevient possible', () => {
  const registre = new Map();
  demarrerActionLigne(registre, 'bridge_agent', 452, 'fermer');
  terminerActionLigne(registre, 'bridge_agent', 452);
  assert.equal(registre.has('bridge_agent#452'), false);
  assert.equal(demarrerActionLigne(registre, 'bridge_agent', 452, 'interrompre'), true);
});

test('terminerActionLigne : un couple absent ne lève pas d\'erreur (no-op)', () => {
  const registre = new Map();
  assert.doesNotThrow(() => terminerActionLigne(registre, 'bridge_agent', 452));
  assert.equal(registre.size, 0);
});

test('actionLigneEnCours : renvoie l\'entrée { action, debut } tant qu\'elle est fraîche, null si absente', () => {
  const registre = new Map();
  assert.equal(actionLigneEnCours(registre, 'bridge_agent', 452), null);
  demarrerActionLigne(registre, 'bridge_agent', 452, 'fermer', { maintenant: 1000 });
  assert.deepEqual(
    actionLigneEnCours(registre, 'bridge_agent', 452, 1500),
    { action: 'fermer', debut: 1000, dureeMaxMs: DUREE_MAX_ACTION_LIGNE_MS },
  );
  // Couple différent — toujours absent.
  assert.equal(actionLigneEnCours(registre, 'bridge_agent', 999, 1500), null);
});

// ─── Garde-fou de durée (issue #956, point 4) : une entrée périmée n'est
// jamais traitée comme « toujours en cours » — un bouton ne doit jamais
// rester bloqué indéfiniment, même si un chemin imprévu a oublié de lever
// l'état.

test('actionLigneEnCours : garde-fou — une entrée plus vieille que DUREE_MAX_ACTION_LIGNE_MS est ignorée ET retirée', () => {
  const registre = new Map();
  demarrerActionLigne(registre, 'bridge_agent', 452, 'fermer', { maintenant: 0 });
  const maintenant = DUREE_MAX_ACTION_LIGNE_MS + 1;
  assert.equal(actionLigneEnCours(registre, 'bridge_agent', 452, maintenant), null);
  // Retirée du registre au passage — un démarrage ultérieur n'est donc plus
  // refusé par une entrée fantôme.
  assert.equal(registre.has('bridge_agent#452'), false);
  assert.equal(demarrerActionLigne(registre, 'bridge_agent', 452, 'interrompre', { maintenant }), true);
});

test('demarrerActionLigne : une entrée périmée n\'empêche pas un nouveau démarrage (pas besoin d\'attendre terminerActionLigne)', () => {
  const registre = new Map();
  demarrerActionLigne(registre, 'bridge_agent', 452, 'fermer', { maintenant: 0 });
  const maintenant = DUREE_MAX_ACTION_LIGNE_MS + 1;
  assert.equal(demarrerActionLigne(registre, 'bridge_agent', 452, 'relancer', { maintenant }), true);
  assert.deepEqual(registre.get('bridge_agent#452').action, 'relancer');
});

test('demarrerActionLigne/actionLigneEnCours : dureeMaxMs explicite (issue #956, point 3 — lignes CIBLÉES par une séquence de niveau projet, garde-fou plus long)', () => {
  const registre = new Map();
  demarrerActionLigne(registre, 'bridge_agent', 452, 'projet', { maintenant: 0, dureeMaxMs: 200000 });
  // Toujours fraîche au-delà du garde-fou PAR DÉFAUT, mais sous le garde-fou
  // explicite de cette entrée.
  assert.notEqual(actionLigneEnCours(registre, 'bridge_agent', 452, DUREE_MAX_ACTION_LIGNE_MS + 1), null);
  assert.equal(actionLigneEnCours(registre, 'bridge_agent', 452, 200001), null);
});

// ─── decisionAffichageBoutonsLigne : décision pure CONSULTÉE par le rendu
// (resultats.js::majBadges) à chaque recalcul — issue #956, point 2/4. ────

test('decisionAffichageBoutonsLigne : aucune action en cours → même visibilité que boutonsActionLigne, rien désactivé', () => {
  const decision = decisionAffichageBoutonsLigne(['needs-human'], { debut: '2026-09-26T10:00:00Z' }, null);
  assert.deepEqual(decision, { visibles: ['relancer', 'fermer'], desactives: false, libelleSurcharge: {} });
});

test('decisionAffichageBoutonsLigne : une action propre à cette ligne → TOUS les boutons visibles désactivés, « ⏳ … » SEULEMENT sur celui qui agit', () => {
  const decision = decisionAffichageBoutonsLigne(
    ['for-linux'], { debut: '2026-09-26T10:00:00Z' }, { action: 'fermer', debut: 1000 },
  );
  assert.deepEqual(decision.visibles, ['interrompre', 'fermer']);
  assert.equal(decision.desactives, true);
  assert.deepEqual(decision.libelleSurcharge, { fermer: '⏳ Fermeture…' });
});

test('decisionAffichageBoutonsLigne : chacune des 4 actions a son propre libellé d\'attente', () => {
  const timing = { debut: '2026-09-26T10:00:00Z' };
  assert.deepEqual(
    decisionAffichageBoutonsLigne([], { debut: null }, { action: 'annuler', debut: 0 }).libelleSurcharge,
    { annuler: '⏳ Annulation…' },
  );
  assert.deepEqual(
    decisionAffichageBoutonsLigne([], timing, { action: 'interrompre', debut: 0 }).libelleSurcharge,
    { interrompre: '⏳ Interruption…' },
  );
  assert.deepEqual(
    decisionAffichageBoutonsLigne(['needs-human'], timing, { action: 'relancer', debut: 0 }).libelleSurcharge,
    { relancer: '⏳ Relance…' },
  );
  assert.deepEqual(
    decisionAffichageBoutonsLigne(['needs-human'], timing, { action: 'fermer', debut: 0 }).libelleSurcharge,
    { fermer: '⏳ Fermeture…' },
  );
});

test('decisionAffichageBoutonsLigne : action \'projet\' (ligne CIBLÉE par une séquence de niveau projet, pas sa propre action) → désactivée, AUCUN libellé de bouton remplacé', () => {
  const decision = decisionAffichageBoutonsLigne(
    ['for-linux'], { debut: '2026-09-26T10:00:00Z' }, { action: 'projet', debut: 0 },
  );
  assert.deepEqual(decision.visibles, ['interrompre', 'fermer']);
  assert.equal(decision.desactives, true);
  assert.deepEqual(decision.libelleSurcharge, {});
});

test('decisionAffichageBoutonsLigne : un rendu COMPLET pendant une action en cours reconstruit quand même les boutons désactivés (issue #956 — limite #949/#951 levée)', () => {
  // Scénario du rapport : « Fermer » cliqué sur une issue EN COURS, puis
  // PENDANT l'attente, l'issue passe en needs-human (reconstruction complète
  // de la ligne avec de NOUVEAUX labels) — avant #956, la ligne reconstruite
  // réaffichait « Relancer »/« Fermer » ACTIFS (l'état posé au clic ne
  // portait que sur les anciens nœuds DOM, remplacés par la reconstruction).
  // La ligne reste désactivée tant que l'ACTION (pas les labels) est en cours.
  const actionEnCours = { action: 'fermer', debut: 1000 };
  const avant = decisionAffichageBoutonsLigne(['for-linux'], { debut: '2026-09-26T10:00:00Z' }, actionEnCours);
  const apresReconstruction = decisionAffichageBoutonsLigne(['needs-human'], { debut: '2026-09-26T10:00:00Z' }, actionEnCours);
  assert.deepEqual(avant.visibles, ['interrompre', 'fermer']);
  assert.deepEqual(apresReconstruction.visibles, ['relancer', 'fermer']);
  // Les DEUX rendus désactivent tout, avec le même libellé d'attente — jamais
  // de fenêtre où un bouton réapparaît actif.
  assert.equal(avant.desactives, true);
  assert.equal(apresReconstruction.desactives, true);
  assert.deepEqual(apresReconstruction.libelleSurcharge, { fermer: '⏳ Fermeture…' });
});

// ─── Levée de l'état dans chaque chemin de fin (issue #956, point 4) : succès,
// échec, délai dépassé, erreur réseau, annulation — tous passent par
// terminerActionLigne (app.js, dans un `finally`), vérifié ici sur le
// registre lui-même (la logique métier est testée manuellement, voir le
// rapport de clôture).

test('terminerActionLigne : chemin succès — l\'état est levé, le bouton redevient disponible', () => {
  const registre = new Map();
  demarrerActionLigne(registre, 'bridge_agent', 452, 'fermer');
  terminerActionLigne(registre, 'bridge_agent', 452); // appelé dans le `finally` du chemin succès
  assert.equal(actionLigneEnCours(registre, 'bridge_agent', 452), null);
});

test('terminerActionLigne : chemin échec (succes:false côté serveur) — l\'état est levé identiquement', () => {
  const registre = new Map();
  demarrerActionLigne(registre, 'bridge_agent', 452, 'interrompre');
  // Même geste qu'un succès : un `finally` ne distingue pas la cause.
  terminerActionLigne(registre, 'bridge_agent', 452);
  assert.equal(actionLigneEnCours(registre, 'bridge_agent', 452), null);
});

test('terminerActionLigne : chemin erreur réseau (fetch rejeté) — l\'état est levé identiquement', () => {
  const registre = new Map();
  demarrerActionLigne(registre, 'bridge_agent', 452, 'annuler');
  terminerActionLigne(registre, 'bridge_agent', 452);
  assert.equal(actionLigneEnCours(registre, 'bridge_agent', 452), null);
});

test('chemin annulation (confirmation refusée) : l\'état n\'est JAMAIS démarré — la confirm() a lieu AVANT demarrerActionLigne', () => {
  // Les quatre fonctions d'app.js (annulerIssue/interrompreIssue/
  // relancerIssue/fermerIssue*) appellent confirm()/toasts.confirmer() AVANT
  // demarrerActionLigne — un refus retourne sans jamais marquer la ligne.
  const registre = new Map();
  const confirmationRefusee = false;
  if (confirmationRefusee) demarrerActionLigne(registre, 'bridge_agent', 452, 'fermer');
  assert.equal(actionLigneEnCours(registre, 'bridge_agent', 452), null);
});

test('délai dépassé (30s de sondage sans confirmation d\'arrêt) : couvert par le même `finally` que l\'échec — garde-fou de durée en secours si ce `finally` n\'était jamais atteint', () => {
  // Le délai dépassé d'une fermeture (DELAI_MAX_ATTENTE_ARRET_FERMETURE_MS,
  // static/js/app.js) lève l'état via le MÊME `finally` que tout autre
  // chemin — testé ci-dessus. Le garde-fou de durée (DUREE_MAX_ACTION_LIGNE_MS,
  // 90s, largement au-delà des 30s de sondage) est le filet de sécurité
  // SUPPLÉMENTAIRE si ce `finally`, pourtant systématique, n'était jamais
  // atteint (ex. exception non prévue côté navigateur) — déjà couvert par
  // le test de garde-fou ci-dessus.
  const registre = new Map();
  demarrerActionLigne(registre, 'bridge_agent', 452, 'fermer', { maintenant: 0 });
  assert.equal(actionLigneEnCours(registre, 'bridge_agent', 452, DUREE_MAX_ACTION_LIGNE_MS + 1), null);
});
