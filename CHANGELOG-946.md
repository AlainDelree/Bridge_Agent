# Issue #946 — Verrous de traitement : y inscrire le numéro de l'issue en cours, pour pouvoir relier chaque verrou à une issue précise

Première brique de l'étude #939 (interrompre UNE issue sans toucher aux
autres) : chaque verrou de traitement (`logs/verrous/*.lock`) consigne
désormais un champ `numero=<N>` à côté des champs existants
(`pid=`/`projet=`/`mode=`/`rep=`), identifiant l'issue réellement en cours de
traitement sous ce verrou — dans les trois modes (écriture, lecture active,
lecture simple), un seul point d'écriture (`watcher.acquerir_verrou`, appelé
par `_acquerir_verrou_pour_issue`, qui connaît déjà le numéro). Placé AVANT
`rep=`, comme les autres champs simples, pour ne jamais dépendre du chemin
(seule valeur pouvant contenir un espace).

Compatibilité stricte avec l'existant : un verrou posé avant cette issue
(champ `numero=` absent) ou une valeur corrompue/vide est lu exactement comme
avant — reprise d'un verrou périmé, nettoyage au démarrage de l'interface,
liste des tâches en cours — le numéro devenant simplement `None` (inconnu),
jamais une erreur. `watcher.taches_en_cours()` expose ce numéro dans chaque
entrée (`{"rep", "mode", "numero"}`) sans changer la façon dont une tâche est
jugée « en cours » (toujours fondée sur `pid=` seul). `app/watchers.py` (route
`/watchers`, panneau Infrastructure) construit ses propres champs booléens à
partir de cette liste par accès par clé — tolère le champ supplémentaire sans
modification de code ; docstring mise à jour. Aucun autre comportement
changé : noms de fichiers verrous, péremption, nettoyage, interruption,
boutons.

Tests ajoutés (`tests/test_numero_verrou_946.py`, 5 scénarios) : écriture du
champ dans les trois modes ; lecture d'un verrou ancien sans `numero=`
(numéro inconnu, comportement inchangé) ; lecture d'un verrou avec `numero=`
et un dossier de travail contenant des espaces ; valeur `numero=` invalide
ignorée sans erreur ; liste des tâches en cours avec et sans numéro.

`ARCHITECTURE.md` §11.1 mis à jour en place (nouveau champ, placement avant
`rep=`, compatibilité avec les anciens verrous).
