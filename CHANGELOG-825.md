## Issue #825 — Onglet En attente : recharger la liste quand le contenu d'un fichier change, pas seulement quand leur nombre change

Quand Alain écrasait un fichier de `en_attente/` par une version modifiée
de la MÊME issue (même nom, cf. `_remplacer_item_en_attente`, issue #820),
le nombre d'éléments ne changeait pas : le seul déclencheur de
rechargement de l'onglet ouvert (`nb !== dernierNbConnu` dans
`static/js/attente.js`, issue #713/#705) ne se déclenchait jamais — titre,
projet, date et condition affichés restaient périmés jusqu'à un
rechargement manuel (F5), alors que la date renvoyée par
`_lire_item_attente` (le `mtime` du fichier) était, elle, déjà correcte.

`app/issues_inbox.py` :
- nouvelle `_signature_attente(cfg)` — signature du CONTENU de
  `en_attente/`, construite à partir du nom, du `mtime` et de la taille de
  chaque fichier (même parcours que `_nb_en_attente`, un `stat()` de plus
  par fichier, déjà fait par ailleurs dans `_lire_item_attente` : coût
  négligeable). Change si un fichier est ajouté, retiré, OU remplacé sous
  le même nom — ce que `nb_en_attente` seul ne détecte pas. Ignore le
  sous-dossier `.ordre` (`DOSSIER_ORDRE_ATTENTE`, issue #819) via le même
  `chemin.is_file()` que `_nb_en_attente` : un déplacement manuel ne
  déclenche donc pas, à lui seul, de rechargement ;
- `GET /issues-inbox/etat` expose cette signature (`signature_attente`),
  au même titre que `nb_en_attente`.

`static/js/resultats.js` : `rafraichirInbox()` pousse `signature_attente`
dans `store.issuesInbox.signatureAttente`, au même cycle que
`nbEnAttente` (aucun polling supplémentaire — même sondage `/issues-inbox/
etat`, toutes les `POLL_INBOX_MS` = 7000 ms).

`static/js/attente.js` :
- nouvelle `fautRechargerAttente(precedent, nouveau)` — logique pure :
  recharge si le nombre OU la signature a changé depuis le dernier état
  connu ;
- `surChangementInbox` compare désormais `{nb, signature}` via cette
  fonction, au lieu du seul `nb`. Badge inchangé (toujours fondé
  uniquement sur `nbEnAttente`).

Ordre manuel, actions (lancer/supprimer/déplacer), calcul de la date et
affichage d'une ligne : inchangés.

Tests : `tests/test_signature_attente_825.py` (dossier absent/vide,
stabilité sans changement, changement sur ajout/retrait/remplacement sous
le même nom, exclusion de `.ordre`, exposition par la route, non-régression
sur un simple déplacement) et `static/js/tests/attente.test.js::
fautRechargerAttente` (signature changée à nombre égal → rechargement ;
identiques → aucun ; changement de nombre → comportement #713 inchangé).
