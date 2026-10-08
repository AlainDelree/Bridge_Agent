# CHANGELOG-734 — à fusionner dans CHANGELOG.md

## 8 octobre 2026 — issue #734

Retrait du code mort des trois valeurs de TYPE `spec_vue`/`spec_metier`/`spec_persistance`, héritées de l'ancien pattern « Chef + Specs MVC » abandonné (doc retirée par #207) — relevées comme code mort par l'audit de la doc #731 : plus aucune consigne `type_spec_*.md`, plus aucune mention dans `BRIDGE_AGENT_DOC.md`, aucun test ne les citait.

- **`watcher.py`** : `TYPES_ISSUE` réduit à `("chef", "ouvrier", "normal")` ; `_classer_valeur_type` perd ses trois branches persistance/métier/vue (et la tolérance aux variantes « vue »/« métier »/« persistance ») ; docstrings de `_classer_valeur_type` et `deduire_type_issue` nettoyées des mentions spec_*. Comportement inchangé pour chef/ouvrier/normal (champ TYPE et préfixe de titre). Un champ TYPE spec_vue/spec_metier/spec_persistance (ou vue/métier/persistance) retombe désormais sur « normal », comme toute valeur inconnue.
- **Historique des durées** (`logs/historique_durees.json`, `logs/etat_timeout.json`) : aucune migration ni réécriture des entrées spec_* existantes — elles restent présentes mais deviennent orphelines (plus aucun type_issue produit ne les cible), sans erreur de lecture (clé de combinaison en simple chaîne, filtrage par égalité stricte dans `app/issues.py::estimer_duree`).
- **`app/issues.py`** : aucun changement — importe `deduire_type_issue` comme une fonction de classification opaque, ne dépend d'aucune des valeurs retirées.
- Tests (`tests/test_retrait_types_spec_mvc_734.py`, 5 scénarios) : TYPE spec_* (et variantes vue/métier/persistance) → normal ; spec_* absents de `TYPES_ISSUE` ; chef/ouvrier toujours reconnus par champ TYPE et par préfixe de titre ; un historique contenant d'anciennes entrées spec_* se filtre sans erreur via `estimer_duree`. Suite rejouée sans régression sur les tests liés (`test_backoff_ancrage_duree_typique_590.py`, `test_ordre_titre_entete_512.py`).
- Doc : aucune modification — `BRIDGE_AGENT_DOC.md` ne mentionnait déjà plus ces valeurs (vérifié, rien à retirer).

Après fusion : relancer les watchers de projet (`watcher.py` modifié), de préférence quand aucune issue en écriture ne tourne, ET redémarrer `new_issue.py` (il importe `watcher.py`).
