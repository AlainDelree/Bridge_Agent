## #684 — docs(bridge_agent_doc): exception REDACTEUR=bridge_agent limitée aux projets sans service CCW dédié

`BRIDGE_AGENT_DOC.md` : la règle 2 de « Cohérence `REDACTEUR` / `PROJET` »
(§3.4) justifiait l'exception `for-windows` + `REDACTEUR == bridge_agent`
par « CCW passe toujours par le canal central `bridge_agent`, quel que soit
le `PROJET` » — formulation antérieure au modèle multi-projets CCW
(services NSSM dédiés `CCW-Watcher-<Projet>`, issue #170) qui pouvait
laisser croire que l'exception vaut pour tout `for-windows`, indistinctement
du projet. Cas réel constaté le 28/09/2026 : une issue `for-windows` pour
Rummikub rédigée avec `REDACTEUR: bridge_agent` alors que Rummikub venait de
recevoir son propre service `CCW-Watcher-Rummikub` — l'exception ne
s'applique plus à lui, `REDACTEUR` aurait dû valoir `rummikub` (règle 1).

- §3.4, règle 2 : ajout de la condition explicite — l'exception ne vaut que
  si le projet visé par `PROJET` n'a **pas** (encore) son propre service CCW
  dédié (dépendant du canal central partagé `bridge_agent` faute de service
  propre) ; dès qu'il en a un, c'est le cas `REDACTEUR == PROJET` (règle 1)
  qui s'applique. Exemple Rummikub ajouté à titre d'illustration.
- Tableau des champs spéciaux (« ## 6. Champs spéciaux dans le corps de
  l'issue », ligne `REDACTEUR` — déjà retouché par #665, visé par l'issue
  #684 sous la référence historique « §17.3 ») : même précision ajoutée,
  condition « projet n'ayant pas encore son propre service CCW dédié »
  explicitée.

Purement documentaire, aucun changement de code.
