## #506 — eval-expiration.json : correction date d'installation Windows PC fixe (2026-08-30)

`provisioning/windows/eval-expiration.json` contenait déjà `date_installation:
2026-08-17` / `date_expiration: 2026-11-15` (mis à jour par le fix #452, le
2026-08-18) — pas les valeurs `2026-07-19`/`2026-10-17` que l'issue supposait.
La mesure fraîche du 30 août 2026 fournie dans l'issue (`GracePeriodRemaining`
= 111244 min ≈ 77,25 j restants) recalcule une expiration au **2026-11-15**
et une installation au **2026-08-17** — exactement les valeurs déjà en place.
Aucune modification du JSON n'était donc nécessaire.

En revanche, `BRIDGE_AGENT_DOC.md` §16.1 (tableau « Repères de dates »)
n'avait pas été mis à jour lors du fix #452 et affichait encore les
anciennes dates de la VM. Corrigé :
- « Date d'installation Windows » : 2026-07-19 → **2026-08-17**
- « Expiration éval Windows (90 j) » : 2026-10-17 → **2026-11-15**

Non touché (hors périmètre de l'issue) :
- §16, tableau `provisioning/windows/` (ligne `eval-expiration.json`) :
  mentions 2026-07-19/2026-10-17 explicitement présentées comme historique
  de l'ancienne VM VirtualBox (issue #167), conservées telles quelles.
- §16.1, ligne « Expiration token GitHub » (≈ 2026-10-17) : concerne
  l'expiration d'un token GitHub fine-grained réel, non recalculable depuis
  la mesure Windows fournie — signalé pour vérification manuelle éventuelle,
  non modifié.
