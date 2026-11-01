## 1 novembre 2026 — issue #842

Onglet « En attente » : chaque ligne affiche désormais une pastille
indicative « ≈ 12min · max 30min » (durée typique connue), « max 30min »
seule (sinon), ou « durée inconnue » si rien n'est disponible. `max` est le
`TIMEOUT` d'une tentative multiplié par `MAX_ESSAIS` du projet ; pour une
issue critique (priorité `haute`/`critique`), `max` devient le mot
**« infini »** en rouge (gras, lisible sans la couleur). La durée typique
réutilise exactement la même source que la pastille « ≈ … » des issues en
cours de l'onglet Résultats (`app.issues.estimer_duree`), pour la
combinaison projet + type + mode + complexité déclarés dans l'en-tête de
l'issue — lecture best-effort, sans verrou ni écriture.

Serveur (`app/issues_inbox.py::_lire_item_attente`) : sept champs ajoutés
(`timeout_s`, `max_essais`, `critique`, `duree_max_s`, `mode`, `complexite`,
`duree_typique_s`), anciens champs inchangés. Page (`static/js/attente.js::
descriptionPastilleDureeAttente`, `static/css/attente.css`) : réutilise
`formaterDuree` de `resultats.js`, jamais reproduit. Aucun changement du
lancement d'une issue, de l'ordre manuel (#819), de la condition d'attente,
de la signature de rechargement de #825, de l'onglet Résultats ni des
calculs de calibration du watcher.

Tests : `tests/test_duree_attente_842.py` (12 scénarios : TIMEOUT/COMPLEXITE
déclarés, défaut du mode, calibration simulée connue/absente/illisible,
priorités normale/haute/critique, MAX_ESSAIS variable/projet introuvable,
anciens champs inchangés, lecture seule) ; `static/js/tests/attente.test.js`
(7 scénarios ajoutés : formatage de la pastille dans les cas prévus, marquage
du mot « infini »).

Non traité : aucune somme des durées de l'onglet (le parallélisme des
issues en écriture la rendrait trompeuse) — piste possible, hors périmètre
de cette issue.
