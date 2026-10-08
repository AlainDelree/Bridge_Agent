# CHANGELOG-733 — à fusionner dans CHANGELOG.md

## 8 octobre 2026 — issue #733 (1/3)

Nettoyage de `BRIDGE_AGENT_DOC.md`, §1 à §9 : réécriture pour ne garder que ce dont Claude Chat a besoin pour rédiger une issue ou un fichier de dépôt (audit #731). Retrait de l'interface, du fonctionnement interne, des procédures d'exploitation et de l'historique d'issues passées ; aucune modification de code.

- **§1** — détail du `git pull --ff-only` condensé à quelques lignes ; ajout du choix CCL (`for-linux`)/CCW (`for-windows`) et du rôle de chacun, absent jusqu'ici de cette section.
- **§2** — tableau inchangé (ancre `regenerer_tableaux_projets.py`) ; retrait de la description de la colonne couleur (pastilles/badges, interface).
- **§3** — retrait de la journalisation interne (3.5), de la config optionnelle du watcher (3.7), du suivi dans l'onglet Résultats (3.8), du pilotage/cycle de vie depuis le panneau Infrastructure et `new_issue.py` (3.10 à 3.12), des événements SSE (3.15), et des mécaniques d'interface de `RELANCE`/`ATTENTE` (décoche de case, bouton, pastilles, routes, références à des fichiers de tests). Conservé et condensé : format du fichier (exemple canonique ajouté : `#Titre:`, en-tête, `## Contexte`/`## Tâche demandée`/`## Résultat attendu`), tableau des champs d'en-tête (une phrase par champ), `ATTENTE`, `RELANCE` (avec le modèle de texte libre recommandé), le dépôt de plusieurs blocs. Règle `REDACTEUR` (§3.4) reformulée en quelques phrases : cas normal `REDACTEUR == PROJET` y compris pour les projets à service CCW dédié (Scrabble, Rummikub, Actualise) ; possibilité supplémentaire, valable pour n'importe quel projet, `REDACTEUR=bridge_agent` + label `for-windows` pour le canal CCW central (réserver `SOUS_DOSSIER`), à réserver à un besoin exceptionnel — l'ancienne condition « seulement si pas de service dédié » abandonnée (jamais appliquée par le code, vérifié dans `valider_redacteur()`).
- **§4** — liste des labels corrigée d'après `nouveau_projet.py::LABELS` : ajout de `for-windows` (absent de la doc) ; précision que `mode_scratch` n'est pas provisionné automatiquement.
- **§5** — retrait de la liste détaillée des outils autorisés en lecture, de la note `cwd_effectif` et de l'incident Scrabble ; défense en profondeur de `mode_scratch` condensée à quelques phrases ; conservé le rappel clair du choix de mode pour exécuter un script (issue #722).
- **§6** — `MODELE` : exemple `claude-opus-4-5` (inexistant) remplacé par `claude-opus-4-8` partout, valeurs reconnues listées d'après `app/projets.py::MODELES_VALIDES` ; retrait de la mention d'une détection côté `new_issue.py` pour `MODE` ; `TYPE` précise que les valeurs `spec_*` ne sont pas documentées (traitées à part par Alain) ; renvoi à la règle `REDACTEUR` du §3.4.
- **§7** — tableau inchangé (même ancre) ; texte d'intro conservé tel quel (déjà concis).
- **§8** — condensé à une phrase : seul un auteur autorisé peut faire traiter une issue, quel que soit le label ; retrait de la mécanique du mot de passe et du gitignore.
- **§9** — retrait du tunnel Cloudflare et du mode `--lan` ; conservé uniquement l'accès à la doc par `curl` avec `?nocache=$(date +%s)`.

**Taille** : 4972 → 4092 lignes (sections 1-9 : 1271 → 391 lignes, soit -880 lignes).

**Déplacements** : aucun — tout le contenu retiré décrit de l'interface, du fonctionnement interne ou des procédures d'exploitation déjà hors du périmètre « ce dont Claude Chat a besoin », donc simplement supprimé (pas de destination identifiée qui en avait besoin).

**Doute signalé** : des renvois `§3.5`/`§3.8`/`§3.10`/`§3.11`/`§3.12`/`§3.15` subsistent plus loin dans le fichier (§16, §17, §20 — hors périmètre de cette issue 1/3) et pointent désormais vers des sous-sections retirées ; à corriger lors du nettoyage de ces sections (issues 2/3 ou 3/3 de la série, ou une passe dédiée).

**Suite de tests** : `python3 -m pytest tests/ -q` → 227 passed ; `node --test` (`static/js/tests/` + `static/js/socle/tests/`) → 269 passed. Aucun test ne dépend du texte retiré (les tests citant `BRIDGE_AGENT_DOC.md` par chemin utilisent des fichiers synthétiques, jamais le vrai fichier). `regenerer_tableaux_projets.py` testé manuellement : ses ancres et tableaux sont inchangés (⚠️ ce script écrase le contenu des tableaux si `configs/*.conf` est absent — sans effet ici car ce worktree n'a pas de `configs/`, mais à ne jamais relancer dans ce worktree sans l'avoir restauré, voir le commit de fix).

Après fusion : rien à relancer (doc seule).
