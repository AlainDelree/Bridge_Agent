# Backlog Bridge_Agent

Idées et pistes non prioritaires, à réaliser éventuellement plus tard.
Alain peut modifier ce fichier directement, sans passer par une issue.

---

## Concurrence limitée aux issues mode_lecture

**Contexte** : `watcher.py` est aujourd'hui strictement séquentiel (une issue à
la fois, tous modes confondus, cf. §3 de BRIDGE_AGENT_DOC.md). Pour des tâches
en `mode_lecture` (ex. plusieurs audits Python/JS/CSS sur un même projet), ce
séquentiel n'est pas motivé par un risque réel : sans écriture disque, plusieurs
CCL peuvent lire le même dépôt simultanément sans conflit.

**Idée** : permettre à `watcher.py` de traiter plusieurs issues en **parallèle**
uniquement si elles sont **toutes** en `mode_lecture` — garde-fou strict
interdisant toute concurrence dès qu'une issue `mode_write` est impliquée (là,
le risque de conflit d'accès fichier reste réel).

**Points à concevoir avant implémentation** :
- Limites de débit API (Claude, GitHub) si plusieurs CCL appellent en même temps.
- Charge CPU/RAM du ThinkPad avec plusieurs CCL simultanés.
- Entremêlement des logs (un fichier de log par issue en cours ?).
- Détection fiable que TOUTES les issues d'un lot sont bien en mode_lecture avant
  d'autoriser le parallélisme (une seule mode_write dans le lot → tout repasse en
  séquentiel).

**Statut** : idée en attente, pas de développement lancé. Discuté le 24/07/2026,
suite à un timeout sur un audit Scrabble.

---

## Parallélisation en mode_write via git worktrees

**Contexte** : contrairement au cas précédent, paralléliser des tâches
`mode_write` sur un même dépôt pose un vrai risque de conflit d'accès fichier
si plusieurs CCL écrivent en même temps dans le même répertoire de travail.

**Idée** : utiliser les *git worktrees* — un dépôt git peut avoir plusieurs
répertoires de travail simultanés, chacun sur sa propre branche, tous rattachés
au même `.git` (pas de duplication lourde comme un clone complet) :

```bash
git worktree add ../Projet-tache1 -b tache-1-issue-XXX
git worktree add ../Projet-tache2 -b tache-2-issue-YYY
```

Chaque tâche parallèle travaille dans son propre dossier physique, sur sa
propre branche → zéro conflit d'accès fichier pendant l'exécution. Le risque
est déplacé au moment du **merge**, où git gère nativement les conflits
(visibles, résolubles), plutôt que de risquer une corruption silencieuse
pendant l'exécution.

**Ce qu'il faudrait construire** :
- Un champ dans l'en-tête d'issue (ex. `WORKTREE`, ou dérivé automatiquement du
  numéro d'issue) pour que le watcher sache dans quel worktree travailler,
  plutôt que dans le `REP_TRAVAIL` fixe du projet.
- Une étape de création/nettoyage des worktrees (`git worktree add` au
  démarrage, `git worktree remove` + `git branch -d` après merge — sinon ils
  s'accumulent).
- Rien à inventer côté verrouillage/détection de conflit : c'est le travail
  natif de git.

**Ce qu'il ne faut PAS automatiser** : le merge lui-même doit rester une étape
manuelle (ou explicitement validée par Alain), cohérente avec la règle actuelle
de vérification avant push — un merge automatique sans supervision humaine est
le genre d'endroit où l'autonomie de CCL doit rester limitée.

**Piste de test avant d'investir dans l'intégration native** : créer les
worktrees manuellement pour deux issues connues indépendantes, pointer les
`REP_TRAVAIL`/`PERIMETRE` de deux `.conf` temporaires vers ces deux worktrees,
et lancer deux watchers en parallèle sur ces configs — sans aucun changement
de code, pour valider le concept avant d'écrire le champ `WORKTREE` natif.

**Statut** : idée en attente, pas de développement lancé. Discuté le 24/07/2026.
