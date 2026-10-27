## Issue #820 — Champ ATTENTE : un fichier de même titre et même projet remplace l'issue en attente

Jusqu'ici, corriger une issue déjà mise de côté (`issues_inbox/en_attente/`,
champ `ATTENTE`, #713) imposait de la supprimer dans l'onglet « En attente »
puis de redéposer le fichier corrigé, qui se retrouvait en bout de file.
Décision de conception (actée avec Alain, pas de nouveau champ de type MOD) :
la règle de remplacement est implicite — même `#Titre:` ET même `PROJET`.

`scripts/watcher_issues_inbox.py` : avant toute autre validation d'un bloc
(mono-issue ou bloc d'un lot), `_item_en_attente_correspondant()` cherche,
dans `en_attente/` uniquement (l'anti-doublon GitHub reste inchangé), un
élément dont le titre ET le projet correspondent exactement — le premier de
la liste (le plus ancien) en cas de plusieurs correspondances. Si trouvé :

- le nouveau bloc porte encore un `ATTENTE` non vide → `_remplacer_item_en_attente()`
  réécrit le contenu de l'élément (écriture atomique, tempfile + `os.replace`)
  et restaure son `mtime` d'origine, pour que sa place dans la liste de
  l'onglet (triée par date de dépôt) reste inchangée ;
- sinon → le bloc suit le circuit normal de création, et l'ancien élément
  n'est supprimé (`_supprimer_item_en_attente_remplace()`) qu'après un succès
  **réel** (`resultat_gh` non vide, jamais pour une simple `RELANCE`) — un
  fichier rejeté laisse l'ancien élément intact.

`_traiter_lot()` prend maintenant des tuples `(bloc, item_a_remplacer)` pour
porter cette information jusqu'à la suppression après succès, bloc par bloc
— les autres blocs d'un lot suivent leur circuit habituel. Chaque
remplacement est tracé dans `logs/issues_inbox.log` sous un statut distinct
`REMPLACE` (jamais confondu avec `EN_ATTENTE`), et dans les logs applicatifs.

`tests/test_remplacement_attente_820.py` (12 scénarios) : correspondance
titre+projet stricte (vide, différent, plusieurs candidats), remplacement
avec `ATTENTE` (contenu remplacé, place conservée), remplacement sans
`ATTENTE` (création puis suppression de l'ancien), fichier rejeté (ancien
conservé), projet différent (aucun remplacement), lot mixte, position
conservée côté `GET /issues-attente`, écriture atomique (aucun `.tmp`
résiduel).

`BRIDGE_AGENT_DOC.md` §3.16 : paragraphe dédié pour les Chats de projet —
même titre au caractère près obligatoire (un titre modifié crée un second
élément sans avertissement), prévenir Alain si le titre doit changer
(suppression manuelle requise), et signaler dans la réponse qu'un fichier de
remplacement est produit.
