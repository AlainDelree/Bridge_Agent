## 25 septembre 2026 — issue #619

Diagnostic #579 (bas niveau, point 2) : `_traiter_issue_synchrone` (watcher.py)
faisait ~610 lignes et empilait séquentiellement plusieurs responsabilités
distinctes (guards, bootstrap CCW, résolution de périmètre, verrou, lecture
active, boucle de tentatives, succès/échec, nettoyage) — correcte mais
difficile à naviguer. Découpée en 12 sous-fonctions privées nommées d'après
les blocs commentés déjà présents, comportement strictement identique :

- `_guards_precoces_et_bootstrap` — déjà en cours / déjà en échec définitif /
  déjà traitée / bootstrap CCW (issue #556).
- `_deduire_mode_et_logguer` — priorité/critique/timeout/modèle/mode +
  avertissements de log associés.
- `_resoudre_contexte_execution` (+ dataclass `ContexteExecution`) —
  périmètre effectif (worktree isolé #337, REPO_CIBLE #125, SOUS_DOSSIER
  #550), avec repli sur `CFG.perimetre`/`CFG.rep_travail`.
- `_acquerir_verrou_pour_issue` — verrou anti-collision inter-process (#189).
- `_preparer_lecture_active` — dossier scratch + empreinte REP_TRAVAIL (#327).
- `_demarrer_traitement` — détection RELANCE, ACK, chrono, pre-flight token,
  empreinte configs/*.conf.
- `_executer_une_tentative` — appel `lancer_claude` + garde-fou de format
  (#581) + restauration configs modifiés.
- `_verifier_violation_scratch` — garde-fou niveau 2 lecture active (#327).
- `_finaliser_succes` — commentaire de résultat, fermeture, historique des
  durées, calibration TIMEOUT (#221/#222), notification.
- `_tracer_tentative_expiree` — trace timeout dans l'historique des durées
  (#220) + calibration backoff.
- `_gerer_abandon_max_essais` — retry infini si critique, sinon diagnostic +
  needs-human + notification.
- `_nettoyer_apres_traitement` — libération verrou, nettoyage scratch, log
  fin de worktree (bloc `finally`).

`_traiter_issue_synchrone` devient un orchestrateur de 93 lignes qui
enchaîne ces appels avec les mêmes retours anticipés qu'avant. Point
d'attention préservé : `_preparer_lecture_active` retourne `chemin_scratch`
même en cas d'abandon (échec du `mkdir` après résolution du chemin), pour
que le nettoyage dans `finally` reste identique au comportement historique.

Vérification : suite de tests existante (21 fichiers) verte sans
modification, `py_compile` OK, plus 3 scénarios manuels bout-en-bout
(succès dry-run, abandon après max_essais, guard needs-human) exerçant
l'orchestration réelle en mockant les I/O réseau — aucune régression
observée. Pas de lancement d'issue réelle CCL de bout en bout dans cette
tâche (limitation d'environnement, aucun accès à une vraie issue GitHub
depuis ce worktree) ; les scénarios manuels ci-dessus couvrent le même
enchaînement de fonctions.
