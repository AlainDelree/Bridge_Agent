## 2 novembre 2026 — issue #844

Label informatif `sans-complexite` + badge dédié (❔, ton sarcelle) sur la
ligne de résultat, même mécanisme que `sans-redacteur` (#647) mais aligné sur
les DEUX chemins de création (fichier déposé dans `issues_inbox/` ET
formulaire web) : posé quand la ligne `COMPLEXITE` est absente ou que sa
valeur n'est pas l'une des quatre reconnues (`rapide`/`court`/`normal`/
`lourd`), jamais un rejet. `watcher.py` factorise désormais la détection
(`NIVEAUX_COMPLEXITE`, `complexite_reconnue()`) à côté d'`extraire_complexite()`
(calibration TIMEOUT, #434) pour que les deux restent strictement alignés —
aucune issue acceptée par la calibration ne reçoit ce label. Déclaré dans
`labels_github.LABELS` (quatorzième label, créé/contrôlé au démarrage de
chaque watcher) et dans la table des labels de `BRIDGE_AGENT_DOC.md` (§4).
13 tests Python + 4 tests JS ajoutés.
