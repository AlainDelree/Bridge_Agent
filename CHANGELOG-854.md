## 4 novembre 2026 — issue #854

Correction (`scripts/watcher_issues_inbox.py`) : dans un lot multi-issues
(§3.13), deux blocs portant chacun un champ `ATTENTE` (§3.16) et partageant
exactement le même `#Titre:` ET le même `PROJET` fusionnaient en une seule
ligne dans l'onglet « En attente » — le second bloc était pris, à tort,
pour une correspondance de remplacement (§3.16/#820) avec le fichier que le
PREMIER bloc venait juste d'écrire dans `en_attente/`, pendant la même
boucle de traitement du lot. `traiter_fichier` prend désormais un instantané
des éléments déjà présents dans `en_attente/` AVANT de parcourir les blocs
du lot, et n'autorise un remplacement que contre cet instantané : un bloc
frère écrit pendant le traitement du même lot n'est plus jamais une cible de
remplacement valide, et devient donc sa propre ligne, identifiée par son
propre titre, son propre projet et sa propre condition — comme les autres
blocs du lot. Le remplacement d'un élément RÉELLEMENT déjà présent (dépôt
antérieur) reste inchangé.

Doc (`BRIDGE_AGENT_DOC.md` §3.16) : deux phrases ajoutées précisant ce
comportement (une ligne par bloc même à titres/projets identiques dans un
même lot ; le remplacement ne vise jamais un bloc frère du même lot).

Tests (`tests/test_remplacement_attente_820.py`) : nouveau scénario de
non-régression — lot de trois blocs ATTENTE au même `#Titre:`/`PROJET`,
vérifié de bout en bout (watcher puis route `GET /issues-attente`) : trois
fichiers dans `en_attente/`, trois éléments renvoyés par la route, chacun
avec sa propre condition.
