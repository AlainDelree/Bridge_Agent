## 25 septembre 2026 — issue #631

Refonte de l'interface web, **étape 9a/n : événements `issues_inbox` et
création d'issue (backend seul)**. Prépare la fusion de l'onglet « Résultats
inbox » dans Résultats (étape 9b, décision d'Alain) : un fichier déposé dans
`issues_inbox/` doit y apparaître aussitôt comme une ligne « fichier reçu »,
qui se transforme au fil du traitement en ligne d'issue (succès) ou ligne
rouge avec motif (bloc refusé). **Aucun changement visible tant que l'étape
9b n'est pas faite** — le code actuel de l'onglet Résultats ignore les
événements qu'il ne connaît pas.

### 1. Trois nouveaux événements SSE sur `/stream`

Même famille que `/notifier-fin-issue`/`/notifier-debut-issue` (`app/fin_issue.py`,
issue #350/#515) : POST best-effort, timeout court, échec silencieux si
`new_issue.py` n'est pas lancé, pas de `login_requis` (appelées par un script
local).

- **`fichier_recu`** (`POST /notifier-fichier-recu`) — émis par
  `scripts/watcher_issues_inbox.py::traiter_fichier()` dès la prise en charge
  d'un fichier, avant tout parsing. `{"fichier": <nom>}`.
- **`creation_issue`** (`POST /notifier-creation-issue`) — émis après chaque
  création RÉUSSIE d'une issue (jamais pour un bloc `RELANCE`, qui n'en crée
  aucune) : par `watcher_issues_inbox.py` (POST, process séparé) et par
  `app.issues.envoyer()` (formulaire web, appel direct à la nouvelle
  `app.fin_issue.emettre_creation_issue()`, même process → pas de HTTP).
  `{"projet", "numero", "titre", "fichier"}` — `fichier` absent (`null`) pour
  une création via le formulaire.
- **`fichier_refuse`** (`POST /notifier-fichier-refuse`) — émis pour chaque
  bloc refusé (fichier mono-issue entier, ou un bloc d'un lot multi-issues,
  §3.13) : un événement par bloc, dans l'ordre de traitement, jamais groupé.
  `{"fichier", "titre", "motif"}`.

`app/fin_issue.py` factorise la diffusion SSE elle-même (`_diffuser()`),
désormais partagée entre les événements historiques (`fin_issue`/`debut_issue`)
et les trois nouveaux.

### 2. Motif de refus exposé dans `/issues-inbox/etat`

`_deplacer_vers_rejected()` (`scripts/watcher_issues_inbox.py`) écrit
désormais, en plus du renommage habituel du fichier, un sidecar
`issues_inbox/rejected/.motifs/<nom-du-fichier-rejeté>.motif` contenant le
motif de refus **en texte intégral** (le nom du fichier lui-même ne porte
qu'un slug tronqué à 40 caractères, sans accents). `GET /issues-inbox/etat`
(`app/issues_inbox.py`) lit ce sidecar et ajoute un champ `motif` à chaque
entrée de `rejetes` — simple lecture disque, donc consultable après coup, y
compris après un redémarrage de `new_issue.py` ; `None` pour un rejet
antérieur à cette fonctionnalité (rétrocompatibilité). Sous-dossier `.motifs/`
dédié (plutôt qu'un `<nom>.motif` posé directement dans `rejected/`) : un tel
nom aurait aussi matché tout code énumérant `rejected/` par motif de nom (ex.
un glob `*REJETE*`, comme dans `tests/test_champ_redacteur_599.py` — bug
attrapé en cours de développement et corrigé par l'isolation dans ce
sous-dossier).

### 3. Tests et documentation

`tests/test_evenements_issues_inbox_631.py` (15 scénarios pytest, collectés
par `pytest tests/`) : construction et validation des trois routes POST,
appel direct de `emettre_creation_issue()`, ORDRE des événements best-effort
pour un fichier mono-bloc (succès/rejet) et pour un lot de 4 blocs (succès,
rejet, RELANCE-sans-événement, succès), absence de doublon quand tous les
blocs d'un lot échouent, exposition/rétrocompatibilité du motif dans
`etat_inbox()`. Aucun appel réseau ni `gh` réel (`_poster_best_effort` et
`_traiter_bloc` substitués). Suite complète (29 tests pytest + 22 scripts
autonomes) vérifiée verte après ce changement.

Documentation : nouveau §3.15 (contenu et ordre des trois événements) et
mise à jour de §3.2 (sidecar `.motifs/`) et §17.3 (mention des trois
nouvelles routes) dans `BRIDGE_AGENT_DOC.md`.

### Fichiers touchés

`app/fin_issue.py`, `app/__init__.py`, `app/issues.py`, `app/issues_inbox.py`,
`scripts/watcher_issues_inbox.py`, `tests/test_evenements_issues_inbox_631.py`
(nouveau), `BRIDGE_AGENT_DOC.md`.
