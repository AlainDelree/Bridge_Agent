# CHANGELOG-735 — à fusionner dans CHANGELOG.md

## 8 octobre 2026 — issue #735 (2/3)

Nettoyage de `BRIDGE_AGENT_DOC.md`, §10 à §13 : réécriture pour ne garder que ce dont Claude Chat a besoin pour rédiger une issue ou un fichier de dépôt (audit #731, suite de l'issue #733 1/3). Retrait de l'interface, du fonctionnement interne, des procédures d'exploitation et de l'historique d'issues passées ; aucune modification de code.

- **§10** — arborescence du dépôt (périmée, omettait déjà `scripts/` et une grande partie de `app/`) remplacée par un renvoi d'une ligne vers `ARCHITECTURE.md` ; convention `CHANGELOG.md`/pied de page inchangée.
- **§11** — détail du hexdump BOM PowerShell condensé à l'essentiel (règle + raison + exception `autounattend.xml`) ; bullet « Parallélisation mode_write » conservé (recommandation de scope pour Claude Chat) mais le workflow de fusion détaillé d'Alain (déjà entièrement dans `WORKTREES.md`) supprimé au profit d'un renvoi.
- **§12** — paragraphe « Workflow » réaligné sur le flux réel : dépôt `.txt` dans `issues_inbox/` comme méthode normale, formulaire web en secours seulement, Claude Chat ne produit jamais de texte à coller. Mécanique détaillée des actions légitimes d'Alain sur `configs/*.conf` (issue #724) condensée : seule la règle « ne jamais modifier » (déjà énoncée juste au-dessus) reste dans ce document, le mécanisme technique déplacé vers `ARCHITECTURE.md` (absent jusqu'ici). §12.1 condensé au tableau des trois couches de consignes et à l'instruction de consulter `consignes/globales.md` via `curl` ; retrait de l'historique (#209/#211) et du détail d'emplacement/ordre interne dans le prompt.
- **§13** (le plus gros bloc, ~1100 lignes) — retrait quasi complet, contenu d'exploitation/maintenance : bloc de commandes shell (lancer l'interface, mot de passe, watcher manuel) et mesure du quota API GraphQL ; état serveur des cases cochées (backend #629 + interface #636) ; journal des messages éphémères/toasts (#730) et couleur d'accent des projets (#120 et suite), tous deux de l'interface ; cycle de vie des watchers (démarrage/extinction/systemd --user) ; boutons « Interrompre une issue bloquée » et « Relancer en needs-human » ; nettoyage de l'arbre de process (ctypes, Job Objects Windows, diagnostic « CCL ne démarre pas »). Conservé et condensé : commandes de création/suppression de projet (`nouveau_projet.py`/`supprimer_projet.py`), avec correction du texte qui affirmait à tort que la mise à jour de `BRIDGE_AGENT_DOC.md` après création/suppression de projet n'était « jamais poussée » — elle est commitée ET poussée automatiquement depuis l'issue #645 ; détail de l'orchestration déplacé vers `ARCHITECTURE.md` (absent jusqu'ici). Parallélisation mode_write par worktrees condensée à 3 lignes (worktree isolé, fusion manuelle par Alain, réutilisation sur RELANCE, séquentiel pour lecture) avec renvoi vers `WORKTREES.md`.

**Taille** : 4092 → 2784 lignes (sections 10-13 : ~1500 → ~190 lignes, soit environ -1310 lignes).

**Déplacements vers `ARCHITECTURE.md`** (information absente là-bas, reportée de façon concise) :
- nouvelle §2.6 : garde-fou `configs/*.conf` et actions légitimes d'Alain (issue #724) ;
- nouvelle §8 : orchestration `creer_projet()`/`supprimer_projet()`, avec la correction du commit/push automatique de la doc (#645).

Tout le reste du contenu retiré décrit de l'interface, du fonctionnement interne ou des procédures d'exploitation déjà entièrement couvertes par `WORKTREES.md` (parallélisation worktrees) ou sans destination identifiée qui en avait besoin — simplement supprimé.

**Renvois corrigés** (pointaient vers des sous-sections de §13 retirées) : §14 (rallumage automatique du watcher, reformulé sans numéro de section), §16 (service NSSM vs supervision systemd, reformulé), §16.4 (pendant CCL du bouton Interrompre, reformulé sans renvoi), §18.2 (push initial de `nouveau_projet.py`, renvoie désormais vers `ARCHITECTURE.md`).

**Doute signalé** : aucun — les renvois `§3.5`/`§3.8`/`§3.10`/`§3.11`/`§3.12`/`§3.15` laissés en suspens par l'issue #733 (1/3) sont tous situés en §16/§17/§20, hors périmètre de cette issue 2/3 ; à traiter par l'issue 3/3 ou une passe dédiée.

**Suite de tests** : `python3 -m pytest tests/ -q` → 227 passed ; `node --test static/js/tests/ static/js/socle/tests/` → 269 passed. Aucun test ne dépend du texte retiré. `regenerer_tableaux_projets.py` non relancé réellement dans ce worktree (pas de `configs/`, écraserait les tableaux comme noté dans le CHANGELOG de l'issue #733) — ancres `DEBUT:TABLEAU_PROJETS_ACTIFS`/`DEBUT:TABLEAU_PERIMETRE_PROJETS` et tableaux des §2/§7 vérifiés inchangés (non touchés par cette issue), et couverts par les tests pytest existants qui l'exercent via monkeypatch (`test_commit_doc_projet_645.py`, `test_supprimer_projet_587.py`, `test_topic_ntfy_facultatif_667.py`).

Après fusion : rien à relancer (doc seule).
