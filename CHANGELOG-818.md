## Issue #818 — Labels GitHub : ne rien créer et n'émettre qu'un seul avertissement quand la liste des labels du dépôt est illisible

Suite de #816 : `creer_labels(depot)` (`labels_github.py`) conservait son
comportement d'origine (pensé pour la création d'un projet) quand
`gh label list` échoue — liste des existants vide, tentative de création
des treize labels quand même. Pour une vérification automatique à chaque
démarrage de watcher, cela produisait treize avertissements trompeurs (un
label peut très bien exister, c'est la lecture qui a échoué) et pouvait
retarder le démarrage jusqu'à quatorze fois le délai de garde de 30s si le
réseau ne répond plus sans refuser.

`labels_github.creer_labels` : si `gh label list` échoue (code de retour
non nul — réseau, droits, dépôt inaccessible, délai dépassé ou `gh`
absent, `_gh` ramenant déjà tous ces cas à un simple `returncode != 0`),
plus aucune création n'est tentée. La fonction renvoie alors une liste à
un seul élément `(None, "illisible", raison)`, distincte des statuts
`"deja"`/`"cree"`/`"echec"` inchangés quand la liste est lue avec succès.

`watcher.verifier_labels_demarrage` : sur une liste illisible, un seul
avertissement est journalisé (« Labels GitHub de '<dépôt>' non vérifiés
(liste illisible : <raison>) — rien n'a été créé. »), plus de ligne par
label. Comportement inchangé quand la liste est lue. Le démarrage du
watcher continue toujours.

`rattraper_labels.py` : affiche « liste illisible : <raison> » pour un
dépôt dont la liste est illisible au lieu de treize lignes en échec, et ne
compte pas ce dépôt dans le total d'échecs ni dans le code de sortie.

`nouveau_projet.py` (`creer_projet`, flux non interactif) : le message de
l'étape « Labels GitHub » reste compréhensible sur liste illisible
(« liste illisible : <raison> — aucune création tentée. ») au lieu
d'afficher « 0 nouveau(x), 0 déjà existant(s) » sans explication. L'étape
interactive `etape_labels` (script CLI) n'est pas concernée par cette
issue.

Tests (`tests/test_labels_auto_watcher_816.py`, complétés) : liste
illisible par code de retour et par délai dépassé (aucune création
tentée) ; un seul avertissement journalisé dans les deux cas, ainsi que
dans le cas déjà couvert d'une exception sous-jacente ; comportement
inchangé quand la liste est lue (labels manquants créés, le reste laissé
intact) ; outil de rattrapage avec un dépôt à liste illisible, non compté
comme échec.
