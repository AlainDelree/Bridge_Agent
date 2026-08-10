# Backlog Bridge_Agent

Idées et pistes non prioritaires, à réaliser éventuellement plus tard.
Alain peut modifier ce fichier directement, sans passer par une issue.

---

## Worktrees en production — points de surveillance

**Contexte** : après correction de #340, deux limites connues restent
sur le mécanisme de parallélisation des issues mode_write via git
worktrees (cf. `WORKTREES.md`) :

- Pas d'alerte sur l'accumulation de worktrees (nettoyage manuel requis).
- `issues_en_cours` sans verrou explicite inter-process.

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
