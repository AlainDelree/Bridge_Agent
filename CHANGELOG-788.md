## 22 octobre 2026 — issue #788

La case à cocher de l'onglet Résultats copiait jusqu'ici uniquement le
commentaire de clôture de l'agent : Claude Chat ne voyait pas ce qui avait
réellement changé et devait croire le rapport, alors que des rapports
d'agent se sont déjà révélés inexacts ou incomplets (ex. un fichier réécrit
en entier avec perte de tous les accents, sans rien dans le rapport).

- **Nouvelle route `GET /inventaire-commit/<projet>/<hash>`**
  (`app/issues.py::inventaire_commit`) : pour un commit, renvoie la liste de
  ses fichiers — statut (ajouté/modifié/supprimé/renommé/copié) et lignes
  ajoutées/supprimées — **sans le contenu du patch**. Repart de
  `git show --name-status`/`--numstat`, chacun en mode `-z` (séparateurs
  NUL, parsing sans ambiguïté) et `--find-renames` : contrairement au
  `--stat` de la route `/diff` existante (bouton Diff, inchangée), les
  suppressions et renommages sont explicitement distingués (chemin d'origine
  conservé). Même contrat d'erreur que `diff_commit` (hash invalide,
  projet/dépôt introuvable, commit introuvable, timeout, git absent).
- **`static/js/app.js`** : nouvelle fonction `etatCommitsDeclares(it)`,
  à côté de `hashesDeCommit`, qui classe la ligne « Commits … » du dernier
  commentaire en trois cas — `'hashes'` (commits exploitables), `'aucun'`
  (ligne lecture seule, cas normal) ou `'absente'` (ligne absente ou non
  reconnue : une anomalie, à ne jamais confondre avec `'aucun'` — un bug de
  reconnaissance des commits est déjà resté invisible deux mois, issue
  #784). `hashesDeCommit` et `etatCommitsDeclares` partagent désormais la
  détection de la ligne (`ligneCommitsDeclares`), pour ne jamais diverger.
- **`static/js/resultats_coches.js`** : `texteReponse` (producteur de la
  variante copiée par la case et par le badge ✅ — voir #787) ajoute
  désormais, quand la réponse n'est pas vide, une section
  `===== Fichiers modifiés =====` construite à partir de l'inventaire
  cumulé (tous les commits de l'issue, lignes +/- sommées, statut du commit
  le plus récent) :
  - ligne « Commits » = `aucun` → **aucune section, aucune alerte** (cas
    normal en lecture seule) ;
  - ligne absente/non reconnue, ou un commit en échec (introuvable, git en
    panne, timeout…) → la section le **dit explicitement**, jamais en
    silence (contrairement au bouton Diff, qui ignore un diff en échec) ;
  - un commit vide (sauvegarde `--allow-empty`) ne contribue simplement
    aucun fichier — mention « aucun fichier » si c'est le seul commit.
  - Les boutons **Diff** et **All** (`texteDiff`/`texteAll`) sont
    **inchangés** : l'inventaire n'est ajouté qu'à la variante « réponse ».
  - Moteur de copie (#636/#782) non touché : la section est assemblée dans
    le texte AVANT la demande d'écriture presse-papier, comme le reste du
    corps — aucun changement au séquencement ni à la sérialisation des
    copies rapprochées.
- **Tests** :
  - `tests/test_inventaire_fichiers_788.py` (7 tests, dépôts git jetables
    réels) — route `/inventaire-commit` : ajout/modification/suppression/
    renommage (y compris vers un sous-dossier)/fichier binaire/commit vide/
    erreurs (hash invalide, projet et dépôt introuvables, commit
    introuvable).
  - `static/js/tests/resultats_coches.test.js` : nouveaux tests de
    `fusionnerInventaireFichier`/`construireInventaireCumule`/
    `texteSectionFichiers` (logique pure).
  - `static/js/tests/hashes_commit.test.js` : nouveaux tests de
    `etatCommitsDeclares` sur les gabarits réels de `watcher.py::ligne_commits`
    (même technique que les tests existants de `hashesDeCommit`, issue
    #784).
  - `static/js/tests/resultats_coches_variantes.test.js` : les tests
    existants (case/badges) vérifient désormais aussi la présence/absence de
    la section ; 3 nouveaux tests couvrent « aucun », « absente » et un
    commit en échec signalé dans le texte copié.
