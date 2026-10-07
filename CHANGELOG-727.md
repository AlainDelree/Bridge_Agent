# CHANGELOG-727 — à fusionner dans CHANGELOG.md

## 8 octobre 2026 — issue #727

Documentation uniquement, aucune modification de code : deux informations d'exploitation utilisées en pratique mais absentes du dépôt sont désormais écrites.

- `WORKTREES.md`, §3 (« Workflow normal d'Alain ») : nouvelle table « Après la fusion : quoi relancer » juste après l'étape de nettoyage — `watcher.py` modifié → relancer les watchers de projet (de préférence sans issue en écriture en cours) ; `app/*.py`/templates/modules importés par `new_issue.py` → redémarrer `new_issue.py` ; `scripts/watcher_issues_inbox.py` → relancer le Watcher spool (indépendant des watchers de projet) ; JS/CSS seul → Ctrl+Maj+R navigateur ; doc/tests seuls → rien à relancer. Rappel du principe : un processus lancé avant la fusion garde l'ancien code jusqu'à son redémarrage, même s'il a été lancé le même jour.
- `BRIDGE_AGENT_DOC.md`, §3.14 (champ `RELANCE`) uniquement : modèle recommandé pour le texte libre d'un fichier RELANCE — cause de l'échec puis correction apportée (ex. nouveau `TIMEOUT`), et après un dépassement de délai une phrase de reprise facultative (« Un travail partiel existe peut-être déjà dans le worktree... ») — facultative car le prompt de CCL rappelle déjà l'équivalent quand le worktree est repris sur relance (issue #725), mais la répéter renforce le message.

Aucun renvoi ajouté en §12 de `BRIDGE_AGENT_DOC.md` vers `WORKTREES.md` : un renvoi existait déjà pour la routine de fusion. Suite de tests complète relancée (206 passed) : aucun test de structure de la doc cassé.
