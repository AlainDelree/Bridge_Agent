## #693 — Portée de `surveiller_transitions()` alignée sur `_lister_issues_labels()` (SSE, auto-refresh)

- Constat : le poller de notifications (`app/notifications_poller.py`)
  limitait la LISTE des issues surveillées (et donc le SSE `fin_issue`/
  `debut_issue` qui déclenche le rafraîchissement automatique de l'onglet
  Résultats) à un seul label (`BRIDGE_NOTIF_SCOPE`, `for-windows` par
  défaut) — alors que le chargement manuel de la même liste
  (`app.issues._lister_issues_labels()`, issue #479/#183) fusionne
  volontairement les deux labels (`for-linux` ET `for-windows`). Une issue
  #692 (`for-windows`) créée directement par `gh issue create` n'avait donc
  déclenché aucun rafraîchissement automatique sur l'instance Linux, alors
  qu'elle apparaît normalement dans la liste après un rafraîchissement
  manuel.
- Correction : `_balayage_initial()` (via la nouvelle `_labels_scope()`) et
  `ajouter_issue_surveillee()` (via `_dans_la_portee()`) surveillent
  désormais TOUJOURS les deux labels bridge, pour chaque projet configuré —
  seul `BRIDGE_NOTIF_SCOPE=off` coupe entièrement la surveillance.
- `BRIDGE_NOTIF_SCOPE` ne restreint plus que le BIP/bulle/ntfy réellement
  émis par ce poller (nouvelle `_bip_dans_la_portee()`, appelée dans
  `_traiter_transition`) — anti-doublon avec le watcher local (issue #187,
  point 4) conservé à l'identique : le SSE peut désormais se déclencher une
  seconde fois, silencieusement, pour une issue déjà notifiée par le
  watcher local, sans bip supplémentaire.
- Paramètres `BRIDGE_NOTIF_INTERVALLE`/`_RECENCE_MIN`/`_ESPACEMENT` vérifiés :
  aucun n'a été calibré en supposant un seul label (ils opèrent par issue
  déjà surveillée, pas par label), donc aucun ajustement nécessaire — le
  volume d'issues CCW/CCL simultanément surveillées reste faible en
  pratique.
- Tests : `tests/test_poller_issues_ccw_624.py` mis à jour (3 scénarios
  adaptés à la nouvelle portée toujours-deux-labels + 1 nouveau scénario
  couvrant directement le fix : SSE déclenché pour une issue hors
  `BRIDGE_NOTIF_SCOPE`, bip filtré) — 11 scénarios, tous verts.
