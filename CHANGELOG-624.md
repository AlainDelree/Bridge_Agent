## 25 septembre 2026 — issue #624

Remplace #623 (fermée après 3 dépassements de TIMEOUT, conception laissée
ouverte). Corrige la régression diagnostiquée en #621 : depuis #614,
`_projets_dans_la_portee()` (`app/notifications_poller.py`) filtrait les
projets interrogés par `gh` sur le champ `LABEL` de leur `.conf` — un
**défaut** de projet, pas la vérité, puisque c'est le label `for-windows`/
`for-linux` posé sur **chaque issue** (exclusifs, §16) qui dit si elle
concerne CCW. Aucun `.conf` CCL ne portant `LABEL=for-windows`, le poller
n'interrogeait plus aucun projet et ne détectait plus aucune transition
d'issue CCW sur le ThinkPad — seul chemin de notification pour CCW, le
watcher Windows postant ses signaux SSE vers `localhost:5100`, sa propre
machine, jamais atteinte depuis le ThinkPad.

Le poller surveille désormais une **liste d'issues** (`depot`, `numéro`),
pas des projets : `app.notifications_poller._ISSUES_SURVEILLEES`, remplie
par un balayage unique de toutes les issues ouvertes `for-windows` sur tous
les projets configurés au démarrage de `new_issue.py`
(`_balayage_initial()`), et tenue à jour en direct à chaque création ou
relance d'une telle issue depuis le ThinkPad — formulaire web
(`app.issues.envoyer`), bouton « Relancer » de l'onglet Résultats
(`app.interruption.route_relancer`), et `scripts/watcher_issues_inbox.py`
via la nouvelle route `POST /notifier-issue-a-surveiller` (ce dernier tourne
dans un process séparé, incapable de muter directement la liste du process
`new_issue.py`). Liste vide → aucun appel `gh` à ce cycle (cas courant, CCW
n'étant utilisé qu'une ou deux fois par semaine).

À chaque cycle, pour chaque issue de la liste : détection de la prise en
charge (commentaire ACK), en réutilisant `app.issues._debut_traitement`/
`_commentaires_issue` (logique de `/issues-en-attente`) plutôt que de la
dupliquer, avec poussée d'un événement SSE `debut_issue` sur `/stream` ;
détection des transitions terminales (`done`/`needs-human`), notifiées comme
avant (bip/bulle/ntfy selon les labels `notif_*`) plus, désormais, un
événement SSE `fin_issue` sur `/stream` — décorrélé des labels `notif_*`,
comme `watcher.py::notifier_fin_sse` pour CCL. Une issue est retirée de la
liste dès sa transition terminale ; une relance réussie l'y réinjecte.
Garde-fous conservés : anti-spam au démarrage (aucune notification pour une
ACK/transition déjà présente à l'amorçage), filtre de récence, lecture des
labels `notif_*` courants au moment de la détection.

Limite documentée, non traitée : une issue `for-windows` créée directement
sur GitHub ou par un chef n'est ajoutée à la liste surveillée qu'au prochain
démarrage de `new_issue.py` (rattrapée par `_balayage_initial()`).

Tests (`tests/test_poller_issues_ccw_624.py`) : remplissage de la liste
(balayage initial multi-projets, ajout direct filtré par
`BRIDGE_NOTIF_SCOPE`), retrait après transition terminale (avec/sans
amorçage, filtre de récence), détection de l'ACK réutilisant réellement
`_debut_traitement`, et liste vide → aucun appel `gh`. Aucun appel `gh` réel
dans ces tests : `_gh_list`/`_gh_view_issue`/`_commentaires_issue` sont
monkeypatchés.

Doc : BRIDGE_AGENT_DOC.md §17 (poller), §17.1 (mécanisme SSE désormais
décorrélé des labels `notif_*` côté CCW aussi), §17.2 (correction de la
période de polling indiquée — 20 s dans la doc, 60 s dans le code depuis
#188), §17.3 (nouvelle route `/notifier-issue-a-surveiller`).

Fichiers modifiés : `app/notifications_poller.py` (remplacement du
balayage par projet par la liste surveillée, nouvelle route Flask),
`app/__init__.py` (enregistrement de la route), `app/issues.py`
(`numero_depuis_url`, hook dans `envoyer()`), `app/interruption.py` (hook
dans `route_relancer()`), `scripts/watcher_issues_inbox.py` (hooks dans
`_traiter_bloc`/`_traiter_relance`, POST best-effort vers la nouvelle
route), `tests/test_poller_issues_ccw_624.py` (nouveau),
`BRIDGE_AGENT_DOC.md`.
