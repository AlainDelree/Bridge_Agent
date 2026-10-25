## Issue #816 — Labels GitHub : créer automatiquement les labels manquants au démarrage des watchers et rattraper les dépôts existants

`LABELS`/`creer_labels` (treize labels, §4 de `BRIDGE_AGENT_DOC.md`)
n'étaient appliqués qu'à la création d'un projet (`nouveau_projet.py`) :
tout label ajouté au code restait absent de chaque dépôt déjà provisionné
jusqu'à un `gh label create` manuel — quatre incidents (`sans-redacteur`
#647/#648, `agent-claude`/`agent-vibe` #768, `mode_scratch` #785), du rejet
d'une création d'issue à une issue de lecture active exécutée en lecture
seule sans la moindre erreur.

`labels_github.py` (nouveau module, 106 lignes) : extrait `LABELS` et
`creer_labels(depot)` de `nouveau_projet.py` plutôt qu'un import direct
depuis `watcher.py`, qui aurait fermé un cycle (`nouveau_projet` →
`regenerer_tableaux_projets` → `from watcher import lire_conf`). Zéro
dépendance externe, importable sans effet de bord des deux côtés et depuis
`rattraper_labels.py`. `creer_labels` reste idempotent à l'identique
(jamais de modification/suppression d'un label existant, comparaison
insensible à la casse) ; son appel `gh` interne reçoit désormais un délai
de garde de 30s (`TIMEOUT_GH_S`, identique à celui déjà utilisé par
`watcher.gh()` ailleurs) pour qu'un appelant automatique ne bloque jamais
indéfiniment sur un réseau indisponible — sans incidence sur l'usage
interactif, ce délai n'étant jamais atteint en pratique. `nouveau_projet.py`
importe et ré-exporte `LABELS`/`creer_labels` depuis ce module
(`nouveau_projet.LABELS`/`nouveau_projet.creer_labels` restent valables,
comportement de création de projet inchangé).

`watcher.py` : nouvelle fonction `verifier_labels_demarrage(cfg)`, appelée
une seule fois dans `main()`, juste après le bandeau de démarrage (CFG
chargé, logs configurés) et avant le premier appel à `lister_issues()` —
pour qu'un label manquant soit rattrapé avant le traitement de la moindre
issue. Elle journalise une ligne de résumé (présents/créés/en échec) puis
une ligne par label créé (`log.info`) ou en échec (`log.warning`, avec
détail). Jamais bloquant : toute exception de l'appel sous-jacent (réseau,
`gh` absent, droits, dépôt inaccessible) est rattrapée et journalisée en
avertissement précis (dépôt, raison) — le watcher démarre normalement dans
tous les cas. Un seul et même `watcher.py` tournant sur CCL et CCW, les
watchers Windows bénéficient de la même vérification sans code spécifique
à la plateforme.

`rattraper_labels.py` (nouvel outil CLI, lancé à la main) : parcourt
`configs/*.conf` (hors `ccw.conf`, canal technique for-windows sans projet
propre, et tout fichier sans champ `DEPOT`, ex. `ccw_ssh.conf`) et applique
`creer_labels` à chaque dépôt déclaré, en affichant un tableau par projet
(labels présents/créés/en échec, avec détail). Ne modifie aucun `.conf`.

`BRIDGE_AGENT_DOC.md` §4 : le commentaire périmé « Les 12 labels » (en
réalité treize depuis #785) est corrigé dans `labels_github.py` ; la note
sur `agent-claude`/`agent-vibe` qui recommandait un `gh label create`
manuel sur les dépôts existants est mise à jour, et un nouveau paragraphe
« Ajouter un label » explique la marche à suivre désormais automatique
(ajout à `LABELS`, création par chaque watcher à son prochain démarrage ou
immédiatement par `rattraper_labels.py`).

`tests/test_labels_auto_watcher_816.py` (nouveau, 8 scénarios, sans aucun
appel réseau — `labels_github._gh`/`watcher._creer_labels_gh`/
`rattraper_labels.creer_labels` monkeypatchés à la main) : tous les labels
déjà présents (rien n'est créé), certains manquants (seuls ceux-là sont
créés), comparaison insensible à la casse, liste illisible côté `gh` et
création en échec (statut détaillé, aucune exception),
`verifier_labels_demarrage` résumé/détail journalisés et jamais bloquant
sur exception, `rattraper_labels` filtre `ccw.conf`/fichiers sans `DEPOT`
et traite plusieurs projets sans toucher à leurs `.conf`.

Non traité : l'éventuelle duplication de cette même logique dans
`nouveau_projet.etape_labels` (version interactive avec `print()`, qui
continue d'appeler le `gh()` propre à `nouveau_projet.py`) n'a pas été
unifiée avec `creer_labels`, pour ne pas changer le comportement/les
messages de la création de projet — hors périmètre de cette issue. La
confirmation que les watchers Windows (CCW) utilisent cette vérification
sans modification supplémentaire n'a pas pu être établie depuis ce
worktree Linux (pas d'environnement CCW disponible ici) ; le code ajouté
n'utilise toutefois que `subprocess`/`gh`, déjà portable ailleurs dans
`watcher.py`.
