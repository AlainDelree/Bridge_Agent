# CHANGELOG-774 — à fusionner dans CHANGELOG.md

## 18 octobre 2026 — issue #774

Onglet Configuration : le champ « Modèle Claude Code » (`#conf-MODELE_CCL`) ne
concerne que l'agent historique (`claude`) — il est désormais **masqué**
quand l'agent sélectionné dans la liste « Agent d'exécution » n'est pas celui-
ci, remplacé par une mention courte nommant l'agent en cours et son propre
onglet (ex. « Le modèle de l'agent Vibe se règle dans son propre onglet «
Agent Vibe ». »). Le lien agent ↔ champ se déduit de `cfg.agent_defaut_global`
(reflet de `watcher.AGENT_PAR_DEFAUT`, déjà transmis par le serveur) plutôt
que d'un nom écrit en dur côté JS : un agent ajouté plus tard à
`AGENTS_CONNUS`, par définition non historique, ne fait jamais réapparaître ce
champ (`champModeleCCLConcerne()`, `static/js/config.js`). Le masquage suit la
**sélection en cours** dans la liste déroulante (écouteur `change` sur
`#conf-AGENT`), pas seulement la valeur enregistrée : changer d'agent
affiche/masque le champ immédiatement, sans attendre l'enregistrement. Pur
affichage (`style.display`), la valeur du `<select>` MODELE_CCL n'est jamais
effacée et part toujours dans `sauvegarderConfig()` — le réglage se retrouve
intact si le projet repasse sur l'agent historique.

Avertissement sur le redémarrage du watcher (sous le sélecteur d'agent,
ajouté par #771) raccourci à l'information utile : « Ne prend effet qu'au
redémarrage du watcher de ce projet. » — l'explication sur la différence avec
le modèle et le rappel du bouton (déjà visible juste en dessous) retirés.

`watcher.py` et l'onglet Résultats non touchés. Tests : 5 nouveaux cas dans
`static/js/tests/config.test.js` pour `champModeleCCLConcerne()`/
`texteModeleAutreAgent()` (301 tests JS passent au total, `node --test
static/js/tests/*.test.js`).
