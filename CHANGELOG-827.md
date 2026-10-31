## Issue #827 — `BUILD_WINDOWS_CCW.md` : valeurs mesurées des builds 14, règle d'extraction d'archive, `git pull` du watcher

Les fiches Rummikub (issue #179 du dépôt Rummikub) et Scrabble (issue #474
du dépôt Scrabble) portaient encore des valeurs d'essai marquées « à
confirmer par le build 14 ». Les deux builds 14 ont réussi avec la chaîne
complète (script durci, copie vers le dossier fixe, Release à deux
fichiers, mise à jour par Actualise) : les fiches sont remplacées par les
valeurs mesurées.

- **Rummikub** : nouveau paragraphe « Build de référence du script durci »
  (build 14, commande `--publier --build 14`, code de sortie 0, mode
  `--publier` validé — somme SHA-256 recalculée identique, manifeste sans
  BOM, tailles et durée mesurées). L'essai au numéro fictif 99 est gardé en
  une phrase secondaire, sans « à confirmer » ; le build 13 reste la
  référence de l'ancien script.
- **Scrabble** : même traitement pour le build 14 (tailles, durée,
  comparaison au build 13), plus un nouveau constat : le manifeste de
  l'archive porte un numéro de build fixe égal à 1 (écrit en dur par le
  script), dans la v13 comme dans la v14 — écart sans conséquence
  fonctionnelle puisque le client Actualise ne lit que le champ
  `supprimer`, explicitement noté comme non corrigé.
- **Inspection d'une archive** : nouvelle règle, dans « Ce que l'agent ne
  fait jamais » et dans la section « Ne pas publier » du modèle d'issue —
  lister une archive sans l'extraire, ou l'extraire seulement dans un
  sous-dossier temporaire du worktree (non suivi par git, supprimé
  ensuite), jamais dans un dossier système ou temporaire hors du worktree.
  Deux agents avaient par le passé extrait une archive hors périmètre
  (`C:\WINDOWS\TEMP`, `/tmp`) pour l'inspecter.
- **`git pull` du watcher** : nouveau paragraphe dans « Comment se passe un
  build » expliquant que le watcher rafraîchit le clone de travail du
  projet par `git pull --ff-only` au début de chaque cycle (issue #185),
  avant de créer le worktree — ce `pull` « au mieux » est ignoré si le
  clone a des commits locaux non poussés ou sans réseau, ce qui motive la
  vérification « le commit à construire est un ancêtre de `HEAD` » et la
  consigne de pousser juste après une fusion.

Fichier modifié : `BUILD_WINDOWS_CCW.md` uniquement (+59/-22 lignes). Fin
de ligne LF et accents préservés ; plus aucune occurrence de « à confirmer
par le build 14 » ni « à confirmer » dans le fichier. Suite de tests
Python complète (`tests/lancer_tous_les_tests.py`) : 86/86 fichiers
réussis, 0 échec — non affectée par ce changement (fichier Markdown).
