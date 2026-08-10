# Backlog Bridge_Agent

Idées et pistes non prioritaires, à réaliser éventuellement plus tard.
Alain peut modifier ce fichier directement, sans passer par une issue.

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

## Calibration TIMEOUT — v2 (backtest des constantes)

**Contexte** : la formule du §19 est
`TIMEOUT_suggéré = max((duree_typique + k × variabilite) × F × backoff, plancher)`
— EWMA par `projet|TYPE|mode|complexite`, demi-vie 15 issues, k=4,
plancher 30 s, facteur d'ambiance `F` de demi-vie 4 h. Cette valeur reste
purement INDICATIVE : le TIMEOUT réellement appliqué est celui de
l'en-tête de l'issue (`extraire_timeout`).

**Les trois défauts identifiés le 29/07/2026 sont corrigés** :
- Défaut 1+2 : champ `RESEAU` implémenté, `F_reseau`/`F_local` alimentés,
  fallback corrigé dans `lire_timeout_suggere` (#435).
- Défaut 3 : champ `COMPLEXITE` ajouté comme 4e dimension de la clé EWMA
  (#434).

**Ce qui reste** : valider empiriquement les constantes
(`K_VARIABILITE=4`, `DEMI_VIE_ISSUES=15`, `DEMI_VIE_AMBIANCE_HEURES=4`)
par backtest sur `historique_durees.json` une fois ~20 observations
accumulées par clé `projet|TYPE|mode|complexite`.
