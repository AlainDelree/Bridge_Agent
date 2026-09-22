## 22 septembre 2026 — issue #589

Repli silencieux sur REP_TRAVAIL quand la création du worktree échoue
(chemin ou branche déjà pris) — rendu visible sans changer le comportement
du repli lui-même, qui reste volontaire et propre (cf. BRIDGE_AGENT_DOC.md).
Scénario déclencheur : une tentative interrompue (TIMEOUT trop court)
laisse un worktree orphelin ; la relance échoue à recréer un worktree au
même chemin/branche et retombe sur REP_TRAVAIL sans aucun signal — découvert
seulement en tentant un nettoyage manuel plus tard.

- `watcher.py` :
  - `_creer_worktree` retourne désormais `(chemin, raison_deja_pris)` au lieu
    de `chemin` seul. `raison_deja_pris` n'est renseignée QUE quand l'échec
    est attribuable à un chemin ou une branche déjà pris (les deux
    vérifications sont faites AVANT l'appel à `git worktree add`, pas par
    reconnaissance de mots-clés dans le message d'erreur git — localisé,
    donc peu fiable) ; reste `None` pour une erreur git générique, afin de ne
    pas présumer une cause qu'on n'a pas vérifiée. Nouvelle vérification de
    la branche (`git rev-parse --verify`) en plus de celle déjà existante sur
    le chemin. Dans les deux cas « déjà pris », un `log.warning` explicite
    mentionne désormais le chemin concerné et la cause précise, distinct du
    `log.warning` générique pour les autres échecs.
  - `_traiter_issue_synchrone` : nouveau paramètre `echec_worktree_deja_pris`
    — quand renseigné, un avertissement (`avertissement_worktree_deja_pris`)
    est injecté en tête du compte-rendu de clôture posté sur l'issue (succès
    comme échec final), avant le corps du résultat, sur le même principe que
    `avertissement_conflit` déjà en place.
  - `traiter_issue` : les deux points d'appel de `_creer_worktree` (chemin
    parallélisé et chemin séquentiel MAX_WRITE_PARALLELE<=1, issue #577)
    transmettent désormais `raison_deja_pris` à `_traiter_issue_synchrone`.
- `tests/test_worktree_parallelisation_337.py` :
  - `scenario_creer_worktree_succes_et_repli` : adapté à la nouvelle
    signature tuple, vérifie que `raison` est `None` au succès et renseignée
    (avec le chemin) pour le repli « chemin déjà pris ».
  - `scenario_max_1_repli_si_worktree_echoue` : étendu pour vérifier les deux
    volets de #589 — un `log.warning` explicite (chemin + « déjà pris »),
    capturé via le nouvel utilitaire `_capturer_logs_watcher`, et la présence
    de la mention dans le compte-rendu réellement posté sur l'issue (corps
    capturé par le faux `gh` de test, `corps-<numero>.md`).

Hors scope, comme demandé : aucune suppression automatique du worktree
orphelin — le nettoyage reste toujours manuel (`git worktree remove` jamais
appelé automatiquement), y compris dans ce chemin.

Vérifié : `py_compile` sur les deux fichiers touchés, les 9 scénarios de
`tests/test_worktree_parallelisation_337.py` passent (dont les deux
nouvelles assertions #589), ainsi que l'intégralité des 16 autres suites de
tests existantes (aucune régression).
