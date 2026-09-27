# CHANGELOG-662 — à fusionner dans CHANGELOG.md

## 27 septembre 2026 — issue #662

Purge automatique des sidecars `.motifs` orphelins de `issues_inbox/rejected/` : quand un fichier rejeté est retiré manuellement (explorateur de fichiers, hors de tout mécanisme applicatif), son sidecar `rejected/.motifs/<nom>.motif` (issue #631) restait indéfiniment sur le disque sans jamais gêner le fonctionnement, mais polluant le dossier avec le temps.

- `scripts/watcher_issues_inbox.py::purger_motifs_orphelins()` : nouvelle fonction, appelée à chaque cycle de `boucle()` juste après `traiter_dossier()` — compare `rejected/.motifs/` à `rejected/` et supprime tout sidecar dont le fichier rejeté associé n'existe plus. Purge silencieuse (aucun log, aucune notification) : sans effet sur le comportement observable de l'application (`/issues-inbox/etat`, rejets normaux inchangés).

Tests : `tests/test_purge_motifs_orphelins_662.py` (5 scénarios pytest) — sidecar orphelin supprimé, sidecar avec fichier rejeté toujours présent conservé, dossier `.motifs` absent ou vide sans plantage, mélange orphelin/conservé.
