## 23 septembre 2026 — issue #594

Onglet Configuration → Zone dangereuse : ajout d'un rappel « **Projet ciblé : <nom>** » (gras, rouge) juste au-dessus du bouton « 🗑 Supprimer ce projet… » (issue #594) — mis à jour dynamiquement, sans rechargement de page, à chaque changement de la combobox `#projet` en haut de page (`appliquerAccentProjet()` dans `static/js/app.js`, appelée par `onProjetChange()`), pour qu'un utilisateur ne regardant que le bas de la page sache sans ambiguïté quel projet sera supprimé avant de cliquer.
