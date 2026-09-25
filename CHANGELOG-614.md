## 25 septembre 2026 — issue #614

Réduit la consommation GraphQL du poller de notifications (`app/notifications_poller.py`) :
le filtre `_dans_la_portee()` (diagnostic #613) n'intervenait qu'**après** les
appels `gh issue list`, sur les transitions déjà récupérées — avec 14 projets
configurés, `surveiller_transitions()` interrogeait donc systématiquement les
14 projets à chaque cycle (2 appels gh chacun, 28/cycle) quel que soit
`BRIDGE_NOTIF_SCOPE`, alors que le défaut `for-windows` n'a besoin que des
projets CCW.

- **Nouvelle fonction `_projets_dans_la_portee()`** : filtre la liste retournée
  par `lister_projets()` **avant** la boucle principale de
  `surveiller_transitions()`, sur le champ `LABEL` du `.conf` de chaque projet
  (`cfg.label`) — `SCOPE=for-windows`/`for-linux` ne gardent que les projets au
  label correspondant, `SCOPE=all` garde tout (comportement inchangé),
  `SCOPE=off` reste court-circuité plus haut (aucun changement). Distincte de
  `_dans_la_portee()` (conservée telle quelle), qui filtre les *transitions*
  sur les labels de l'*issue* elle-même — sécurité complémentaire en aval, non
  redondante.
- **Log de chaque appel gh** : `_gh_list()` journalise désormais
  `gh issue list <dépôt> label=<label> state=<état>` avant chaque appel réseau
  (log de `new_issue.py`), pour permettre un diagnostic précis lors d'un futur
  épisode d'épuisement de quota GraphQL.
- **BRIDGE_AGENT_DOC.md §17** mis à jour : décrit le filtrage par SCOPE en
  amont des appels gh et la disponibilité du log par appel.
- Suite de tests existante toujours verte (14 passed).
