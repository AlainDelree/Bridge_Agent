# CHANGELOG-722 — à fusionner dans CHANGELOG.md

## 6 octobre 2026 — issue #722

Documentation uniquement (`BRIDGE_AGENT_DOC.md`) : **le mode lecture ne peut exécuter aucun script, `python3` compris** — ce n'était écrit nulle part clairement, ce qui a conduit un Claude Chat (03/10/2026) à choisir la lecture seule pour une issue qui devait exécuter un script Python de simulation, provoquant un refus systématique des commandes `python3` (bloquées par la demande d'approbation interactive de Claude Code, inatteignable en session non-interactive) — comportement voulu du watcher, pas un bug.

- §5 (« Modes lecture seule / lecture active / écriture »), dans la description de la lecture seule : encadré rappelant qu'en dehors de la courte allowlist (`git fetch`, `git pull --ff-only`, heuristique interne Claude Code), aucune commande n'est exécutée, script ou `python3` compris ; pour exécuter un script d'analyse/simulation/mesure sans toucher au projet → lecture active (`| MODE | lecture active |`) ; pour un script qui doit modifier le projet → écriture (`| MODE | écriture |`) ; précise que ce refus ne concerne pas les issues déjà en écriture.
- §3.3 (« Format attendu du fichier », champ `MODE`) : encadré à l'endroit où Claude Chat choisit le `MODE` en rédigeant une issue — mots déclencheurs à repérer dans la tâche demandée (exécuter, lancer, mesurer, simuler, tester, `python3`, `pytest`, script) : leur présence signale presque toujours que le mode lecture (défaut) est le mauvais choix.

Hors périmètre (rappel de l'issue) : aucun changement de code ni de comportement du watcher ; `python3` non ajouté à `OUTILS_LECTURE_AUTORISES`.
