## #688 — suite #686 : `encoding="utf-8", errors="replace"` sur les appels subprocess restants

Inventaire élargi de #686 (grep exhaustif, hors `watcher.py` et tests) :
même défaut latent — `subprocess.run(..., text=True, ...)` sans
`encoding="utf-8"` explicite, qui retombe sur `cp1252` sous Windows et
corrompt les accents dans la sortie de `git`/`gh` — trouvé dans 10
fichiers restés hors périmètre de #686. Notable : `app/ccw.py` et les
deux fichiers `provisioning/windows/` tournent déjà, au moins en partie,
côté Windows.

Ajout de `encoding="utf-8", errors="replace"` (18 sites, même pattern que
#686/`watcher.py`) dans :
- `etat_rate_limit.py` (1) ; `app/interruption.py` (3, label/commentaire gh) ;
- `app/ccw.py` (1, scp — les deux autres appels de ce fichier gardent
  `encoding="cp1252"`, volontaire, sortie console Windows non-UTF-8) ;
- `app/projet_ccw.py` (3, scp clé publique + `gh issue create`/`comment` —
  l'appel `openssl` de ce fichier n'a pas `text=True`, sortie binaire,
  inchangé) ;
- `backfill_historique.py` (1) ; `nouveau_projet.py` (2, `gh`/`git`) ;
- `regenerer_tableaux_projets.py` (1) ;
- `scripts/watcher_issues_inbox.py` (2, `gh issue view`/`edit`) ;
- `provisioning/windows/creer_vm_ccw.py` (3, VBoxManage) ;
- `provisioning/windows/lancer_provisioning.py` (1).

Revérification exhaustive (AST, pas juste grep mono-ligne, pour capter les
appels où `text=True`/`encoding=` sont sur des lignes séparées) sur tout
le dépôt (hors tests) : plus aucun site oublié parmi les fichiers listés
ci-dessus. Deux zones restent volontairement intactes, hors périmètre de
cette issue :
- `watcher.py` — exclu explicitement par l'énoncé de #688 (déjà traité
  antérieurement).
- `app/issues.py` — l'énoncé de #688 le donne pour déjà corrigé par #686 ;
  en réalité la branche `worktree-issue-686` (commit `e6d18d8`) n'est
  **pas encore fusionnée dans `master`**, donc ce worktree (créé depuis
  `master`) ne contient pas ce correctif : `app/issues.py` présente donc
  encore, à ce stade, des appels `subprocess.run(text=True, ...)` sans
  `encoding=`. Point à vérifier par Alain lors de la fusion des deux
  branches (pas de conflit attendu, les fichiers touchés ne se recoupent
  pas) — ne pas considérer le dépôt "propre" sur ce point avant que #686
  soit effectivement mergé dans `master`.

Comportement Linux inchangé (le comportement par défaut de `text=True`
sans `encoding=` y était déjà UTF-8 via la locale du système).
