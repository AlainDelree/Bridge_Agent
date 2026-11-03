## 3 novembre 2026 — issue #847

Suite de #846 : le commit de sauvegarde fait par le watcher lui-même était
jusqu'ici sauté dès qu'un projet définissait `CMD_BACKUP` dans son `.conf` —
or l'audit des `.conf` réels (fait par CC, hors périmètre de ce worktree)
montre que 12 projets sur 13 ont exactement la même valeur, écrite par
défaut à la création par `nouveau_projet.py` (`GABARIT_CONF`) : un commit
git de tout le dossier avec `--allow-empty` et un message
« avant-<description> ». Seul alchess a une commande personnalisée (un
gestionnaire de sauvegarde Python, sans commit git). En pratique, la
sauvegarde #846 ne s'appliquait donc à AUCUN projet git, y compris
Relecture_Bridge — le projet dont l'oubli de l'agent (incident #121) avait
motivé #846.

**Critère de reconnaissance** (nouvelle fonction `_cmd_backup_est_standard`,
`watcher.py`) : `CMD_BACKUP` est reconnu comme la commande standard si,
après normalisation des espaces (`strip()` + espaces multiples réduits à
un seul), il matche `^git add -A && git commit -m ["'].*?["'] --allow-empty$`
— guillemets simples ou doubles tolérés autour du message (contenu
quelconque, la convention « avant-<description> » n'est PAS vérifiée),
espaces tolérés partout ailleurs. Rien de plus : ordre des éléments et
drapeaux exacts inchangés — une variante qui s'écarte de cette structure
(drapeau manquant, ordre inversé, commande étendue...) n'est PAS reconnue,
par principe de prudence (« dans le doute, ne pas se substituer à
l'agent », demandé par l'issue).

**Comportement** :
- `CMD_BACKUP` vide OU reconnu standard → le watcher committe lui-même
  (comportement #846, désormais étendu à ce second cas) ; l'agent est
  informé que ce commit est déjà fait et ne doit pas en refaire un.
- `CMD_BACKUP` renseigné et NON reconnu (ex. alchess, ou toute variante que
  le critère ne reconnaît pas avec certitude) → comportement #846 inchangé
  à l'identique : le watcher ne committe rien, la commande reste la
  consigne transmise à l'agent, qui l'exécute lui-même.

Le reste du mécanisme #846 (hash dans le rapport de clôture, repli sur
`None` en cas d'échec du commit watcher, absence de second commit aux
tentatives 2/3, séparation propre en cas de RELANCE) ne change pas — seule
la condition qui déclenche `_commit_sauvegarde_watcher` (dans
`_demarrer_traitement`) et celle qui choisit le texte de consigne injecté
dans le prompt (dans `lancer_claude`) ont été élargies de « `CMD_BACKUP`
vide » à « `CMD_BACKUP` vide ou reconnu comme standard ».

**Documentation** : `BRIDGE_AGENT_DOC.md` §5 (mode écriture) — « sauf projet
définissant `CMD_BACKUP` » devient « sauf commande de sauvegarde
personnalisée dans `CMD_BACKUP` », avec le rappel du critère de
reconnaissance.

**Fichiers modifiés** : `watcher.py` (nouvelle fonction
`_cmd_backup_est_standard` + constante `_RE_CMD_BACKUP_STANDARD` ;
condition élargie dans `_demarrer_traitement` et `lancer_claude` ;
docstrings mises à jour) ; `BRIDGE_AGENT_DOC.md` ; `tests/
test_commit_sauvegarde_watcher_846.py` (les deux scénarios « CMD_BACKUP
défini » utilisaient par erreur la valeur STANDARD du gabarit — désormais
devenue reconnue — corrigés pour utiliser une commande réellement
personnalisée, de type alchess) ; nouveau
`tests/test_cmd_backup_standard_847.py` (19 scénarios : 7 variantes de la
commande standard reconnues, dont espacement/guillemets/message
personnalisé, 7 valeurs non reconnues avec certitude — dont alchess,
`--allow-empty` manquant, drapeaux dans un ordre inversé — et 5 tests
bout-en-bout sur dépôts git jetables : commande standard → watcher
committe, variante d'espacement → watcher committe, alchess → watcher ne
committe pas, vide → watcher committe, non reconnue → watcher ne committe
pas). Aucun fichier `.conf` modifié (`configs/` reste hors périmètre et
n'a pas été touché).

**Tests** : `pytest tests/` → 432 passed (413 avant, +19 nouveaux), mêmes
11 erreurs préexistantes et sans rapport
(`tests/test_signature_attente_825.py`, fixture `tmp_dir_factory`
inexistante — non touché par cette issue). `node --test
static/js/tests/ static/js/socle/tests/` → 492 passed, 0 fail, inchangé
(aucun fichier JS modifié). `python3 -m py_compile watcher.py` → OK.
