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

**Statut** : évalué le 2026-08-21 — coût de migration élevé pour un
bénéfice surtout esthétique. Le label `for-windows` sur bridge_agent fait
le travail sans friction. À reconsidérer si des projets exclusivement
Windows voient le jour et justifient un espace dédié.

## Calibration TIMEOUT — v2 (backtest des constantes)

**Statut** : ✅ Réalisé le 2026-08-21 — backtest effectué sur 1070
observations (issues #475). Résultats : K=4 → 97% couverture (ratio
médian 6.63x), K=3 → 96% couverture (ratio médian 5.36x). K passé à 3
(issue #475), `k_utilise` enregistré dans `historique_durees.json` pour
permettre la comparaison a posteriori. `DEMI_VIE_ISSUES=15` validée —
toutes les demi-vies testées donnent 97% globalement. Pas de v2 nécessaire
pour l'instant.
