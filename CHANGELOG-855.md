## 4 novembre 2026 — issue #855

Un lot (plusieurs blocs `#Titre:`) déposé **à la main** directement dans
`issues_inbox/en_attente/` (pour reporter son lancement sans jamais passer
par `issues_inbox/`) n'apparaissait que comme **une seule ligne** dans
l'onglet « En attente » — titre du premier bloc, condition « non précisée »
— au lieu d'une ligne par bloc. Contrairement à un lot arrivé par le
circuit normal (champ `ATTENTE`, #713), déjà découpé un bloc par fichier
par le watcher AVANT sa mise en attente, un fichier déposé directement
dans `en_attente/` n'est jamais vu par `traiter_dossier` (qui ne scrute que
`issues_inbox/`, pas son sous-dossier).

Ajout de `scripts/watcher_issues_inbox.py::decouper_fichiers_lot_attente`,
qui découpe un tel fichier en un fichier par bloc avec le même nommage que
le circuit normal (`<stem>__bloc<N><suffixe>`) — appelé en auto-guérison
par `app/issues_inbox.py::_items_attente`/`etat_inbox` à chaque lecture de
l'onglet (même principe que `fusionner_ordre_attente`, #819), sans
dépendre d'un cycle du watcher spool ni de son état démarré/arrêté. Aucun
bloc créé ni perdu (même découpage que `decouper_corps_en_blocs`) ; un
fichier à un seul bloc ou déjà découpé par le watcher n'est jamais touché
(idempotent) ; la règle de remplacement du §3.16/#820 (même `#Titre:` ET
même `PROJET`) continue de fonctionner, la correspondance se faisant sur
le contenu, jamais sur le nom de fichier.

Par la même occasion, le texte affiché pour un bloc sans champ `ATTENTE`
passe de « condition non précisée » à « aucune condition »
(`static/js/attente.js::descriptionLigneAttente`) — un dépôt manuel direct
dans `en_attente/` n'a simplement rien à préciser, ce n'est pas une
donnée manquante.

Fichiers touchés : `scripts/watcher_issues_inbox.py` (nouvelle fonction),
`app/issues_inbox.py` (deux points d'appel + doc), `static/js/attente.js`
+ `static/js/tests/attente.test.js` (texte de repli), `BRIDGE_AGENT_DOC.md`
(§3.16, deux phrases ajoutées). Nouveau test
`tests/test_decoupage_lot_en_attente_855.py` (11 scénarios, dont le cas
réel de l'issue : lot de 7 blocs, 4 sans `ATTENTE` et 3 avec).
