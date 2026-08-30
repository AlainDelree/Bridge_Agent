## 30 août 2026 — issue #509

Panneau Infrastructure — bouton « Retirer needs-human » sur l'issue
sélectionnée : demande déjà entièrement couverte par l'issue #460
(commit `8dec213`, fusionné dans `master` avant #509). Vérification faite
que le bouton « 🔄 Relancer » de `#pl-zone-actions`
(`rendrePanneauLateralActions()`, `static/js/app.js`) remplit exactement
le besoin décrit : visible uniquement quand l'issue sélectionnée porte le
label `needs-human` et est ouverte, retire ce label via `gh issue edit
--remove-label` (route `POST /relancer-issue`,
`app/interruption.py::route_relancer`, même mécanisme `--add-label`/
`--remove-label` que `app/issues.py::modifier_label_notif`), ne ferme pas
l'issue, poste un commentaire de trace, puis rafraîchit la liste et le
détail sans rechargement manuel complet. Aucune modification de code
nécessaire.
- `BRIDGE_AGENT_DOC.md` : ajout de la sous-section « Relancer une issue
  bloquée en `needs-human` (issue #460, cf. #509) » (juste après
  « Interrompre une issue bloquée »), qui manquait — seul point réellement
  manquant identifié pour cette issue.
