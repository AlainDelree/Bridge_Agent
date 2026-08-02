# Backlog Bridge_Agent

Idées et pistes non prioritaires, à réaliser éventuellement plus tard.
Alain peut modifier ce fichier directement, sans passer par une issue.

---

##Bouton Interrompre dans l'onglet CCW

Procédure : nssm restart CCW-Watcher, puis supprimer le(s) fichier(s)
  dans C:\CCW\Bridge_Agent\logs\verrous\ :
  Get-ChildItem C:\CCW\Bridge_Agent\logs\verrous\ -Filter "*.lock"
  Remove-Item C:\CCW\Bridge_Agent\logs\verrous\<fichier>.lock

---

## Projet dédié à la communication CCL ↔ CCW

**Contexte** : aujourd'hui les issues Windows passent par le projet
`bridge_agent` avec le label `for-windows`, ce qui est contre-intuitif —
bridge_agent est le projet de l'infrastructure elle-même, pas un relais
CCL↔CCW. Avec le futur setup (ThinkPad Linux + fixe Windows en parallèle),
la communication inter-agents va prendre de l'ampleur et mérite son propre
espace.

**Idée** : créer un projet dédié (ex. `ccw_relay` ou `bridge_ccw`) dont
le seul rôle est de porter les issues `for-windows`. Le watcher CCW
surveillerait ce dépôt au lieu de bridge_agent. Les issues CCW auraient
leur propre historique, leur propre CHANGELOG, leur propre CONTEXTE.md —
sans polluer bridge_agent.

**Points à concevoir** : migration des issues CCW existantes ou simple
bascule à partir d'une date, adaptation du provisioning CCW (clone du
nouveau dépôt, config NSSM), labels à recréer sur le nouveau dépôt.

**Statut** : idée en attente, setup physique (fixe Windows) pas encore
en place. À reprendre quand le nouveau hardware sera opérationnel.

## Calibration automatique du TIMEOUT — trois défauts à corriger

**Contexte** : la formule du §19 est
`TIMEOUT_suggéré = max((duree_typique + k × variabilite) × F × backoff, plancher)`
— EWMA par `projet|TYPE|mode`, demi-vie 15 issues, k=4, plancher 30 s,
facteur d'ambiance `F` de demi-vie 4 h. Cette valeur reste purement
INDICATIVE : le TIMEOUT réellement appliqué est celui de l'en-tête de
l'issue (`extraire_timeout`).

**Trois défauts identifiés le 29/07/2026** :
1. `F` n'est jamais alimenté — `_detecter_tag_reseau()` retourne toujours
   `None`, donc `F_reseau`/`F_local` restent à 1.0 et le facteur
   d'ambiance n'influence rien (déjà listé dans les limitations du §19).
2. Même si le tag existait, `maj_calibration_timeout` retombe toujours sur
   `F_local` par défaut sans le lire — c'est un second bug, distinct du
   premier.
3. La clé `projet|TYPE|mode` mélange des populations incompatibles : une
   édition de doc de 250 s et une refonte de `watcher.py` avec tests de
   1800 s finissent dans la même case. La médiane qui en sort n'a pas de
   sens (observé : 2794 s suggérés pour une issue qui en a pris 351).

**Idée** : séparer explicitement le coût de la TÂCHE et l'état de la
MACHINE (réseau, RAM, congestion) — c'est déjà la structure de la formule,
mais les deux moitiés sont mal alimentées. La composition doit rester un
PRODUIT, pas une somme : un agent enchaîne les allers-retours réseau, donc
une latence dégradée étire la durée proportionnellement au travail au lieu
d'ajouter un forfait fixe. Exemple : wifi à +40 % → une doc passe de 250 à
350 s, une refonte de 1800 à 2520 s ; une somme unique surestimerait la
première et sous-estimerait gravement la seconde.

**Deux signaux à capter, faciles et probablement les plus discriminants** :
- le TIMEOUT déclaré dans l'en-tête, comme proxy de complexité — Claude
  Chat estime déjà la difficulté au moment de rédiger ; segmenter la
  calibration là-dessus séparerait mécaniquement les deux populations,
  sans nouvelle donnée à collecter ;
- une mesure de latence réseau au démarrage du traitement, pour alimenter
  enfin `tag_reseau` et corriger du même coup le défaut 2.

**Statut** : diagnostic établi le 29/07/2026, aucune implémentation
lancée. À reprendre à froid — le sujet touche des EWMA et des choix de
modélisation qu'on prendrait mal à la légère.

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

---

## Mode mode_tmp_write — écriture scratch limitée pour outillage d'audit

**Contexte** : certains outils d'analyse (eslint flat config pour les
versions ≥ 9, linters divers) exigent un vrai fichier de config sur disque,
pas seulement une commande inline. Le mode_lecture actuel interdit toute
écriture, y compris hors dépôt — ce qui bloque ces outils. Note : ce n'est
PAS ce qui causait les timeouts observés sur Scrabble (#235 vs #238,
réglé par une consigne d'abandon immédiat au refus de permission) — c'est
un besoin distinct et réel, pour les cas où l'outil a effectivement besoin
d'un fichier de config.

**Proposition** (reçue via rapport d'audit Scrabble) : un troisième mode,
`mode_tmp_write`, avec :
- Écriture autorisée uniquement dans un chemin scratch bien défini et
  validé strictement côté watcher (ex. `/tmp/bridge_scratch_<projet>/`),
  jamais dans `REP_TRAVAIL` du projet. Validation stricte du chemin pour
  empêcher tout `../` ou équivalent remontant vers le dépôt.
- Toujours interdit, comme en lecture seule : `git commit`, `git push`,
  toute commande destructrice, toute écriture hors du chemin scratch.
- Nettoyage attendu en fin de tâche par CCL, idéalement complété par un
  nettoyage automatique du dossier scratch par le watcher en fin de
  traitement — pour ne pas reposer uniquement sur la consigne donnée à CCL.
- Conceptuellement plus proche du mode lecture seule que du mode écriture :
  pas de garde-fou "backup avant modification" nécessaire (aucun fichier du
  projet n'est jamais en jeu).

**Point de vigilance** : la garantie ne tient que si la validation du
chemin scratch est réellement stricte côté `watcher.py` — à concevoir avec
soin, pas seulement en confiance sur la consigne donnée à CCL.

**Statut** : idée en attente, pas de développement lancé. Reçue via rapport
d'audit Scrabble le 24/07/2026.

---

## Garde-fou technique sur la modification de PERIMETRE

**Contexte** : PERIMETRE (`configs/*.conf`, ex. `ccw.conf`) est un simple
champ texte lu par `watcher.py` et injecté tel quel dans le prompt de
CCL/CCW. Aucun garde-fou technique n'existe sur sa modification — une
issue pourrait l'élargir ou le restreindre silencieusement (ex. à `C:\`
entier, ou en retirant le partage lui-même), sans que rien ne le
signale comme un événement particulier. Le 31/07/2026, le périmètre
CCW a dû être élargi manuellement (via notepad) pour débloquer un
build légitime — l'usage de PERIMETRE lui-même n'est pas en cause. Le
risque identifié porte sur l'absence de contrôle quand une modification
de cette valeur survient via une issue plutôt qu'à la main.

À noter : le respect du périmètre par CCL/CCW pendant l'exécution est
déjà appliqué uniquement par consigne textuelle du prompt (non
déterministe, cf. issues #290/#291 qui l'ont franchi vs #292 qui s'est
arrêtée). La modification de la valeur elle-même est un problème
distinct et actuellement sans aucun garde-fou, pas même textuel.

**Idée** : avant toute action qui écrirait une nouvelle valeur de
PERIMETRE dans `configs/*.conf`, `watcher.py` devrait détecter le
changement (comparaison ancienne/nouvelle valeur) et refuser
l'application automatique — exiger une confirmation manuelle explicite
(ex. fichier de confirmation posé à la main, ou variable
d'environnement) plutôt que de laisser une issue modifier
silencieusement son propre périmètre d'exécution.

**Statut** : idée en attente, pas de développement lancé. Diagnostic
établi le 31/07/2026 (issue #298).
