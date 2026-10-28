## Issue #822 — Onglet En attente : afficher la date du dernier dépôt quand un élément est remplacé

Depuis l'issue #820, remplacer un élément en attente (même `#Titre:` ET
même `PROJET`) restaurait le `mtime` d'origine du fichier après l'avoir
réécrit, pour que sa place dans l'onglet reste inchangée — au prix d'un
défaut signalé par Alain : l'onglet continuait d'afficher la date du
PREMIER dépôt, impossible de voir d'un coup d'œil qu'une correction avait
bien été prise en compte.

Depuis l'issue #819, la place d'un élément est de toute façon mémorisée à
part (ordre manuel persisté dans `en_attente/.ordre/ordre.json`), donc la
date du fichier n'est plus la seule chose qui la fixait — le mtime restauré
par #820 était devenu une béquille superflue pour les éléments déjà connus
de cet ordre, et insuffisante pour ceux qui ne l'étaient pas encore.

`scripts/watcher_issues_inbox.py` :
- `DOSSIER_ORDRE_ATTENTE`/`FICHIER_ORDRE_ATTENTE`/`_chemin_ordre_attente`/
  `_lire_ordre_attente_persiste`/`_ecrire_ordre_attente`/
  `fusionner_ordre_attente` (logique pure de l'issue #819) sont relogées ici
  depuis `app/issues_inbox.py`, qui les réimporte désormais tel quel — le
  watcher doit pouvoir les appeler lui-même avant un remplacement, ce qui
  aurait créé un import circulaire si elles étaient restées côté app
  (`app.issues_inbox` importe déjà plusieurs noms depuis ce module) ;
- nouvelles `_dates_items_en_attente()` (liste légère id/date de
  `en_attente/`) et `_figer_place_avant_remplacement()` : persistent
  l'ordre d'affichage COURANT (ordre mémorisé fusionné aux dates réelles)
  juste AVANT un remplacement — y compris pour un élément jamais encore
  affiché/déplacé dans l'onglet, donc absent jusque-là de l'ordre mémorisé ;
- `_remplacer_item_en_attente()` appelle ce verrou puis laisse le `mtime`
  de l'élément évoluer normalement (plus de restauration manuelle) : la
  date affichée reflète désormais le DERNIER dépôt, la place reste
  garantie par l'ordre figé juste avant.

`app/issues_inbox.py` : la section « Ordre manuel (issue #819) » ne
contient plus que l'import depuis `watcher_issues_inbox` ; comportement et
API (`fusionner_ordre_attente`, etc.) inchangés pour ses appelants.

`tests/test_remplacement_attente_820.py` : les assertions qui vérifiaient
une date/mtime INCHANGÉE après remplacement sont remplacées par des
assertions de date qui AVANCE (reflète le dernier dépôt) + place inchangée
vérifiée via l'ordre persisté (`w._lire_ordre_attente_persiste`) ou la
route `GET /issues-attente` ; les listages de `en_attente/` filtrent
désormais `p.is_file()` (le sous-dossier `.ordre/` y apparaît maintenant
dès le premier remplacement). Le test de non-régression #820 sur la
position dans la liste (`test_position_conservee_dans_la_liste_apres_remplacement`)
couvre explicitement le cas d'un élément jamais encore affiché/déplacé
(aucun ordre mémorisé préexistant dans ce test) et vérifie en plus que sa
date affichée change bien après le remplacement.

`BRIDGE_AGENT_DOC.md` non modifié (hors périmètre de cette tâche).
