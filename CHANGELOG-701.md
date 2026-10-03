## #701 — « Interrompre » un watcher Windows natif via le Job Object persistant (suite #695)

- #695 avait livré le côté producteur (`watcher.py`, déjà en master) : création
  d'un Job Object **persistant et nommé** (`nom_job_watcher_windows`) au
  démarrage du watcher sous Windows, auto-assignation du watcher (toute sa
  descendance en hérite automatiquement, claude compris). #701 livre le côté
  consommateur, dans `app/interruption.py` uniquement.
- `interrompre_linux` (nom historique — gère en réalité le watcher **local**,
  quel que soit son OS ; `interrompre_windows` reste le chemin **délégué**
  par SSH vers le PC fixe CCW, pour les issues `for-windows`, inchangé)
  bascule désormais sur une branche `os.name == "nt"` pour reconstruire/
  arrêter l'arbre de process : `/proc` (PPID) sous Linux, appartenance au Job
  Object persistant sous Windows (pas de `CreateToolhelp32Snapshot`, pas de
  dépendance externe).
- Nouvelles fonctions Windows (`app/interruption.py`) :
  - `_cmdline_windows(pid)` : nom de l'image du process (`QueryFullProcessImageNameW`,
    droits minimaux) pour l'affichage — pas de ligne de commande complète
    (demanderait une énumération de processus séparée, hors de portée de
    ctypes seul ; solution la plus simple retenue, comme demandé).
  - `_arreter_arbre_windows(cfg)` : rouvre le Job **par nom**
    (`OpenJobObjectW`, droits minimaux QUERY+TERMINATE), liste ses PID
    membres (`QueryInformationJobObject`/`JobObjectBasicProcessIdList`) pour
    l'affichage, tue tout via `TerminateJobObject`, ferme le handle dans tous
    les cas. Renvoie les mêmes noms d'étape que la branche Linux
    (`arreter_arbre_watcher`/`attente_fin_process`), même contrat à trois
    statuts (succes/rien_a_faire/echec).
- Cas limites gérés : Job introuvable (watcher déjà mort, ou lancé avant
  #695 sans job persistant) → `rien_a_faire`, jamais `echec` ; liste de PID
  tronquée (plus de membres que `_CAPACITE_PID_JOB_PERSISTANT`) → signalée
  dans le message, mais `TerminateJobObject` agit quand même sur tout le job
  (il n'a pas besoin de connaître les PID un par un, à la différence de
  l'énumération d'affichage) ; échec de `TerminateJobObject` → `echec` sur
  les deux étapes, handle quand même fermé (pas de fuite) ; process encore
  listé comme vivant après la fenêtre d'attente de 5s → `echec`, verrou NON
  nettoyé (même garde-fou que côté Linux).
- Comportement Linux strictement inchangé (code Windows entièrement derrière
  `os.name == "nt"`, aucune modification du bloc `/proc` existant — juste
  réindenté sous un `else`). `watcher.py` non modifié (côté producteur #695
  déjà en place, aucun bug constaté en le relisant).
- Tests : `tests/test_interruption_windows_701.py` — mock de `ctypes.windll`
  (`create=True`) + `os.name` forcé à `"nt"`, même pattern que
  `tests/test_nettoyage_arbre_windows_249.py` : job introuvable, succès
  (liste + terminaison), liste tronquée, échec de `TerminateJobObject`,
  process survivant après la fenêtre d'attente, et aiguillage par OS de
  `interrompre_linux` (monkeypatch, sans exécuter de vrai code ctypes
  Windows). Ces tests vérifient les appels ctypes, pas le comportement réel
  de Windows — à valider à la main sur CCW (procédure ci-dessous).

**Procédure de test manuel sur CCW** (à faire à la main, aucun test
automatisé ne peut la remplacer depuis Linux) :
1. Sur le PC fixe Windows, démarrer un watcher local pour un projet (pas via
   la délégation CCW habituelle) — vérifier dans ses logs qu'il journalise
   bien la création du Job persistant (`_preparer_job_persistant_windows`).
2. Depuis `new_issue.py` tournant sur ce même PC, envoyer une issue qui
   déclenche une tâche longue (ex. `sleep`/boucle) pour ce projet.
3. Une fois la tâche en cours, cliquer « Interrompre » sur l'issue dans
   l'onglet Résultats.
4. Vérifier : la réponse liste bien les PID (watcher + claude + descendance)
   avec leur image ; dans le Gestionnaire des tâches, **tout l'arbre**
   disparaît (watcher compris) ; aucun process résiduel ne reste accroché
   après quelques secondes.
5. Relancer le même scénario avec un watcher démarré **avant** le déploiement
   de #695 (pas de Job persistant) pour confirmer le repli en `rien_a_faire`
   (pas de plantage, pas de `echec` trompeur).
