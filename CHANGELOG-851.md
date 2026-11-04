## 4 novembre 2026 — issue #851

Doc uniquement (aucun changement de code), suite à une issue `COMPLEXITE |
moyen` non reconnue (repliée sur `normal` + label `sans-complexite`).
Investigation du code (`watcher.py::_complexite_depuis_entete`,
`_complexite_brute_depuis_entete`, et plus généralement tous les
`extraire_*` de l'en-tête bridge, ex. `extraire_mode_entete`,
`extraire_priorite`) : chacun parcourt l'intégralité de `body.splitlines()`
sans aucune rupture sur ligne vide — une ligne vide au milieu de l'en-tête
n'arrête donc PAS la lecture des champs suivants. Confirmé empiriquement :
cette issue #851 elle-même portait volontairement une ligne vide avant
`| COMPLEXITE | normal |` et n'a reçu AUCUN label `sans-complexite`.
L'hypothèse de la ligne vide est donc infirmée ; aucun ajout au §3.3 de
`BRIDGE_AGENT_DOC.md` (prévu seulement si l'hypothèse avait été confirmée).
Reste l'hypothèse de l'avertissement du §6 citant lui-même les mots à
éviter (`moyen`, `léger`, `simple`, `trivial`, `normale`) : cette liste est
retirée du §6 de `BRIDGE_AGENT_DOC.md` (encadré ⚠️ et phrase « y compris
ceux listés ci-dessus » adaptée), la mesure (champ absent dans plus de la
moitié des issues de plusieurs projets) et la règle des quatre valeurs
exactes (`rapide`/`court`/`normal`/`lourd`) étant conservées à l'identique.
