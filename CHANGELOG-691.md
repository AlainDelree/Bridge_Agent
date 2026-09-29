## #691 — Idempotence règle pare-feu de `provisionner_new_issue_local.ps1`

- Correction : `Get-NetFirewallRule` (vérification) et `New-NetFirewallRule`
  (création) utilisaient deux noms différents (`-Name` interne vs
  `-DisplayName` réel), rendant la vérification d'idempotence inopérante.
  Unifié sur un seul nom (`Bridge Agent new_issue.py ($Port/tcp)`), vérifié
  et créé via `-DisplayName` dans les deux cas.
- Le nettoyage des deux règles en doublon existantes sur CCW (`Bridge Agent
  - new_issue.py` et `Bridge Agent new_issue.py (5100/tcp)`) ne peut pas être
  fait depuis ce worktree Linux (aucun accès à la machine Windows physique) —
  délégué via une issue `for-windows`.
