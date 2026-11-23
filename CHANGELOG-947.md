## 2026-11-23 — issue #947

Nouvelle route de lecture `GET /issues-en-cours/<nom_projet>`
(`app/watchers.py::issues_en_cours`, même famille que `/watchers` et
`/statut/<nom_projet>`) : donne, pour UN projet et à l'instant précis de
l'appel, les issues réellement en cours de traitement — préparation de
l'étude #939 (avertir avant de fermer proprement une issue si d'autres
issues du même projet tournent encore). Aucun bouton, aucune fenêtre,
aucune interruption ni fermeture n'est modifié par cette issue : seule la
route et sa logique sont ajoutées.

Source UNIQUE : les verrous de traitement, via `tache_en_cours()`
(`app/watchers.py`, donc `watcher.taches_en_cours`, issue #946) — aucun
appel GitHub, aucune lecture de la liste d'issues de l'interface. Une tâche
dont le watcher propriétaire est mort n'est pas comptée : c'est déjà le
comportement de `taches_en_cours` elle-même, non dupliqué ici.

Réponse JSON : `{"watcher_actif": bool, "issues": [{"numero": int|null,
"mode": str}, ...]}` — `numero` vaut `null` pour un verrou ancien sans champ
`numero=` (compté quand même comme tâche en cours), `watcher_actif` reflète
séparément l'état du watcher (fichier PID) sans jamais filtrer la liste.
Projet inconnu → `{"erreur": "Projet introuvable."}`, HTTP 404, comme les
autres routes de cette famille (`/avancement`, `/journal`).

Paramètre de requête optionnel `?exclure=<numero>` : retire de la liste
l'entrée portant ce numéro, pour que la future fenêtre de fermeture propre
obtienne directement « les AUTRES issues en cours ». Un verrou dont le
numéro est inconnu n'est JAMAIS exclu par erreur — seule une égalité
stricte avec un numéro connu exclut une entrée.

Tests ajoutés (`tests/test_issues_en_cours_947.py`, 8 scénarios) : projet
inconnu ; projet sans verrou (liste vide) ; une tâche avec numéro ; une
tâche sans numéro (verrou ancien) ; plusieurs tâches en parallèle ;
exclusion d'un numéro connu ; non-exclusion quand le numéro du verrou est
inconnu ; tâche dont le watcher est mort (verrou réel, PID réellement mort,
sans mock de `taches_en_cours`) — ignorée sans duplication du filtre. Suite
complète (`tests/lancer_tous_les_tests.py`, 134 fichiers) exécutée sans
régression.

`ARCHITECTURE.md` §11.1 mis à jour (nouveau consommateur de
`taches_en_cours`, forme de la réponse, limite héritée du numéro inconnu).
