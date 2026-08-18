## 18 août 2026 — issue #452

CONFIG — `provisioning/windows/eval-expiration.json` mis à jour pour
refléter l'échéance réelle du PC fixe physique (remplaçant l'ancienne VM
VirtualBox, cf. #449/#450), installé le 17 août 2026.
- `date_installation` : `2026-07-19` → `2026-08-17`.
- `date_expiration` : `2026-10-17` → `2026-11-15` (date_installation +
  eval_jours = 90 jours, conforme à la note du fichier).
