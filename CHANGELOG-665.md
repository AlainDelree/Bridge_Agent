## #665 — docs(bridge_agent_doc): PROJET reste le projet réellement ciblé même quand REDACTEUR=bridge_agent (canal CCW)

`BRIDGE_AGENT_DOC.md` : la règle 2 de « Cohérence `REDACTEUR` / `PROJET` »
(§3.4) — `for-windows` + `REDACTEUR == bridge_agent` valide « quel que soit
le `PROJET` réellement ciblé » — pouvait se lire comme si `PROJET` devait lui
aussi valoir `bridge_agent` sur le canal CCW. Erreur constatée deux fois en
usage réel (#661, #664 : issues de build Actualise routées dans la file de
`bridge_agent`).

- §3.4 : ajout, juste après la règle 2, d'un avertissement explicite
  (« `PROJET` ne devient JAMAIS `bridge_agent` du seul fait qu'une issue passe
  par le canal CCW — seul `REDACTEUR` le devient ») et d'un exemple d'en-tête
  contrastant les deux champs (`PROJET = actualise`, `REDACTEUR =
  bridge_agent`), avec rappel que `PROJET = bridge_agent` passerait la
  validation (règle 1) tout en envoyant l'issue dans la mauvaise file.
- §3.1 (tableau des champs d'en-tête `issues_inbox/`, ligne `REDACTEUR`) et
  §17.3 (tableau des champs d'en-tête, ligne `REDACTEUR`) : même précision
  ajoutée en une phrase, ces deux résumés reprenant la règle du canal CCW
  sans distinguer les deux champs.

Purement documentaire, aucun changement de code.
