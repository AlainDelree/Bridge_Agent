## 2 novembre 2026 — issue #845

`logs/historique_durees.json` n'enregistrait, jusqu'ici, que des champs
agrégés (projet/type/mode/durée...) — ni le numéro de l'issue, ni la
complexité retenue, ni le TIMEOUT réellement appliqué, ni l'estimation/
TIMEOUT_suggéré affichés au lancement. Il fallait reconstituer ces données
depuis les commentaires GitHub pour vérifier si l'estimation et le TIMEOUT
suggéré collaient à la réalité.

Chaque nouvelle ligne (succès ou tentative expirée) porte désormais, en
plus des champs existants : `numero_issue`, `tentative`, `timeout_applique`,
`complexite`/`complexite_statut` (`valide`/`absente`/`non_reconnue`, avec
`complexite_brute` dans ce dernier cas), `timeout_suggere_lancement` et
`estimation_lancement`. Ces deux dernières valeurs sont figées **une seule
fois, avant la première tentative** (`watcher._demarrer_traitement`) puis
transmises telles quelles à chaque ligne de cette même issue — jamais
recalculées après une éventuelle mise à jour de la calibration par cette
issue elle-même, sinon la mesure de leur fiabilité serait faussée. Une
tentative expirée garde sa sémantique inchangée : `duree` y reste le
plafond TIMEOUT atteint, pas une durée réelle — désormais dit explicitement
dans `BRIDGE_AGENT_DOC.md` §19.1 (nouvelle sous-section, format complet
d'une ligne documenté).

`estimer_duree()`/`_charger_historique()` (badge de fiabilité affiché par
l'interface, issue #108) sont déplacées d'`app/issues.py` vers `watcher.py`
— seule source désormais, réimportée par `app/issues.py` — pour que le
watcher puisse calculer, au lancement, l'EXACTE même estimation que celle
déjà affichée dans l'interface, sans dupliquer ce calcul (endroit le plus
simple compte tenu du sens existant des imports : `app/issues.py` importe
déjà de nombreuses primitives de `watcher.py`, jamais l'inverse).

Aucun changement du calcul de l'estimation, du TIMEOUT suggéré ou de la
calibration elle-même — uniquement ce qui est enregistré. Rétrocompatibilité
totale : les anciennes lignes ne sont pas modifiées, tous les lecteurs
(estimation affichée, `scripts/archiver_historique.py`) tolèrent l'absence
des nouveaux champs ; l'archivage déplace chaque entrée comme un dict entier
et conserve donc automatiquement les nouveaux champs d'une ligne archivée.

12 tests Python ajoutés (`tests/test_contexte_decision_historique_845.py`) :
nouvelle ligne avec tous les champs, ligne sans ces champs (comportement
d'avant l'issue), ancienne ligne lue sans erreur, complexité absente/non
reconnue (valeur brute conservée)/valide, tentative expirée, préservation
par l'archivage, et un scénario bout en bout (`_demarrer_traitement` →
`_finaliser_succes`, réseau GitHub bouché) qui confirme que l'estimation
écrite reste celle d'avant la clôture même si l'historique grandit entre
temps. `tests/test_duree_attente_842.py` adapté (monkeypatch sur
`watcher.FICHIER_HISTORIQUE`/`FICHIER_ETAT_TIMEOUT`, désormais la seule
source, au lieu de `app.issues.FICHIER_HISTORIQUE`/`FICHIER_ETAT_TIMEOUT`
— mécanique, aucun changement d'intention).
