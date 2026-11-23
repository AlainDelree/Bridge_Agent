# Issue #945 — Watchers : tracer la cause d'un arrêt, signaler un arrêt non propre au démarrage suivant, et alerter dans l'interface quand une issue attend alors que le watcher du projet est éteint

Suite de l'étude #938 : le 23/11/2026, le watcher du projet `bridge_agent` a
disparu brutalement à 17:45:44 (aucun signal tracé, aucune exception, aucune
auto-extinction, aucune requête d'arrêt avant 17:49) — cause probable un
signal non interceptable (SIGKILL, OOM killer). L'issue suivante (#937,
17:48:46) est restée en file sans que rien ne le signale dans l'interface,
et le watcher ne s'est pas relancé automatiquement malgré `redemarrer_si_eteint`
(aucune supervision ne relance un watcher qui plante depuis #682).

## 1. Trace de la cause d'un arrêt (`watcher.py`)

Un gestionnaire `signal.signal(signal.SIGTERM, _gestionnaire_signal_arret)`
est désormais posé dans `main()`, juste après `acquerir_verrou_processus`
(#908) — SIGTERM était jusqu'ici le seul signal de terminaison qui tuait le
process immédiatement et silencieusement (SIGINT lève déjà
`KeyboardInterrupt`, déjà géré). `_gestionnaire_signal_arret` journalise le
nom du signal puis reproduit EXACTEMENT le même arrêt propre que
`KeyboardInterrupt`/l'auto-extinction (retrait du fichier PID, `sys.exit(0)`)
— le comportement d'arrêt ne change pas, seule la trace est ajoutée. Le
message de `KeyboardInterrupt` nomme désormais lui aussi explicitement
SIGINT, pour rester cohérent. `if __name__ == "__main__":` journalise en
plus (`log.critical`) toute exception qui échapperait à `main()` sans passer
par un de ces chemins déjà tracés, avant de se propager normalement. Un
signal non interceptable (SIGKILL, OOM killer) ne laisse par construction
toujours rien — c'est le point 2 qui le détecte après coup.

## 2. Détection d'un arrêt non propre au démarrage suivant (`watcher.py`)

`detecter_arret_non_propre(cfg)`, appelée dans `main()` juste après le verrou
d'instance et AVANT que le fichier PID ne soit réécrit : si
`logs/watcher-<nom>.pid` existe encore et que son PID n'est plus vivant
(`_pid_vivant`), journalise un `log.warning` net
(`formuler_avertissement_arret_non_propre`, logique pure) citant ce PID et
la dernière ligne du journal lue AVANT ce démarrage
(`_derniere_ligne_journal`, lecture best-effort des derniers 8 Kio). Vérifié
que les trois sorties propres existantes (auto-extinction,
`KeyboardInterrupt`, et le nouveau `_gestionnaire_signal_arret`) retirent
toutes ce fichier avant de sortir — aucune correction nécessaire, elles le
faisaient déjà (sauf `_gestionnaire_signal_arret`, nouveau, qui le fait dès
sa création).

## 3. Alerte « en file, watcher éteint » dans l'interface

`evaluerAlertesWatchers(watchersMap)` (`static/js/panneau_lateral.js`),
appelée à chaque lecture de `/watchers` (tourne en continu dès le chargement
de la page, panneau Infrastructure ouvert ou non) : croise, pour chaque
projet, `resumeProjetMonitoring(nom).enFile` et `watchersMap[nom].actif` —
données déjà en mémoire, aucun appel GitHub ni réseau supplémentaire. Délai
de grâce de 60s (`DELAI_GRACE_ALERTE_WATCHER_MS`) avant d'alerter, un point
de départ par projet réarmé dès que la condition cesse d'être réunie — évite
une fausse alerte pendant la fenêtre où `redemarrer_si_eteint` vient de
relancer le watcher au dépôt d'une issue mais n'a pas encore publié son
fichier PID. Un seul toast par épisode (`doitNotifierAlerteWatcher`).
Résultat écrit dans `store.alertesWatchers`, lu à deux endroits sans second
calcul : la ligne du panneau Infrastructure (`.pl-alerte-watcher`, sous le
résumé « en cours/en file » existant) et le badge du filtre projet de la
liste des résultats (`static/js/app.js::majAlertesBadgesProjets`, classe
`.filtre-projet.alerte-watcher` + `title`). L'alerte disparaît d'elle-même
dès que le watcher redevient actif ou que plus aucune issue n'attend — aucun
redémarrage automatique du watcher n'est déclenché. Logique pure testée sans
DOM : `enAttenteWatcherEteint`, `fautAlerterWatcherEteint`,
`doitNotifierAlerteWatcher`, `texteAlerteWatcher`
(`static/js/tests/panneau_lateral.test.js`).

## 4. Lancement automatique au dépôt d'une issue — constat (sans correctif)

Deux composants lancent le watcher local à la demande, tous deux via
`app/watchers.py::redemarrer_si_eteint(cfg)` → `demarrer_watcher(cfg,
forcer=False)` (PAS `demarrer_watcher_ou_differer`, réservé au bouton manuel
« Enregistrer et relancer ») : `app/issues.py::envoyer()` (formulaire web) et
`scripts/watcher_issues_inbox.py::_traiter_bloc` (spool `issues_inbox/`,
chemin probable d'une issue déposée par CC). `demarrer_watcher(forcer=False)`
ne relance que si `watcher_actif(cfg)` répond `False` (lecture du fichier
PID puis `_pid_vivant`).

Hypothèse retenue pour l'incident du 23/11/2026, à confirmer par Alain sur
le déploiement réel : l'asymétrie VOLONTAIRE de `_pid_vivant` (« PID trouvé
vivant, sonde en échec ⇒ `True` par prudence — un PID mort peut avoir été
recyclé par l'OS ») s'applique ici SANS le filet du verrou OS
`acquerir_verrou_processus` (#908), qui protège uniquement contre un SECOND
watcher lancé par erreur et n'intervient pas dans
`watcher_actif()`/`redemarrer_si_eteint`. Si le PID resté dans
`logs/watcher-<nom>.pid` après le crash a été recyclé par l'OS pour un autre
process avant 17:48:46, `watcher_actif()` répond (à tort) `actif=True` et
rien n'est relancé — sans la moindre trace, cohérent avec le constat de
#938. L'hypothèse zombie est écartée : `_pid_vivant` détecte déjà ce cas
spécifiquement (aurait correctement permis la relance).

**Non vérifié avec les journaux réels de l'incident** (`logs/issues_inbox.log`,
`logs/new_issue.log`) : ces fichiers n'existent pas dans le worktree isolé où
cette tâche a été traitée (gitignorés, propres au déploiement réel) — à
confirmer par Alain. Correctif le plus simple si confirmé : ne plus se fier
à la seule liveness du PID dans `watcher_actif()`/`redemarrer_si_eteint`
pour un fichier PID plus ancien qu'une durée de vie de process plausible, ou
faire porter à ce fichier une empreinte supplémentaire (heure de démarrage
du process lue sur `/proc/<pid>/stat`) pour distinguer un PID recyclé — non
implémenté ici (pas « quelques lignes » évidentes, et nécessite une
vérification sur le déploiement réel avant tout correctif).

## Tests

- `tests/test_arret_non_propre_945.py` : `formuler_avertissement_arret_non_propre`
  (PID connu/inconnu), `_derniere_ligne_journal` (dernière ligne non vide,
  fichier absent), `detecter_arret_non_propre` (aucun fichier PID → silence,
  PID mort → avertissement, PID vivant → silence, PID illisible →
  avertissement quand même), `_nom_signal`, `_gestionnaire_signal_arret`
  (log + nettoyage + sortie 0).
- `static/js/tests/panneau_lateral.test.js` : `enAttenteWatcherEteint`,
  `fautAlerterWatcherEteint` (délai de grâce, seuil personnalisé),
  `doitNotifierAlerteWatcher` (transition, épisode déjà signalé),
  `texteAlerteWatcher`.
- Suite complète rejouée sans régression : `python3 tests/test_auto_extinction_217.py`,
  `python3 tests/test_verrou_processus_unique_908.py`,
  `node --test static/js/socle/tests/ static/js/tests/` (648 tests, 0 échec).

Reste à vérifier à la main (voir `VERIFICATIONS_MANUELLES.md`, nouvelle
section) : envoi réel de SIGTERM/SIGKILL à un watcher, dépôt d'une issue
pendant le délai de grâce, auto-extinction sans fausse alerte, et la lecture
des journaux réels de l'incident (hors périmètre de ce worktree).

## Documentation

`ARCHITECTURE.md` (nouveau §16), `docs/contexte/interface_rafraichissement.md`
(nouveau §10), `VERIFICATIONS_MANUELLES.md` (nouvelle section), ce fichier.
`CONTEXTE.md` non modifié (aucune nouvelle règle/convention/dépendance,
seulement un comportement nouveau déjà documenté ci-dessus).
