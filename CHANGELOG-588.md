## 22 septembre 2026 — issue #588

Correction de `_debut_traitement()` (`app/issues.py`) : affichait à tort
« ⏳ en file » avec une estimation fraîche pour une issue qui venait
d'épuiser ses 3 tentatives, pendant la courte fenêtre où `watcher.py` a déjà
posté le commentaire « Échec après N tentatives » mais pas encore le label
`needs-human` (deux appels `gh` distincts, non atomiques). Le marqueur
« Échec après N tentatives » ne réinitialise plus systématiquement `debut` à
`None` : il ne le fait que s'il n'est **pas** récent (nouvelle constante
`FENETRE_TRANSITOIRE_ECHEC_S = 120`, marge couvrant le pire cas des deux
appels `gh` à 30s de timeout chacun). En-dessous du seuil, `debut` reste
l'ACK du cycle qui vient réellement de tourner plusieurs minutes. Au-dessus,
comportement #525 inchangé (issue relancée après retrait manuel de
`needs-human`, ACK du cycle précédent dans l'historique → « en file »
préservé jusqu'à une nouvelle ACK).

- `app/issues.py` : ajout `FENETRE_TRANSITOIRE_ECHEC_S`, `_echec_recent()`,
  condition ajoutée dans `_debut_traitement()`, docstring mise à jour.
- `tests/test_fenetre_transitoire_echec_588.py` (nouveau) : 6 scénarios
  purs (aucun accès réseau) — échec récent → `debut` conservé, échec juste
  sous le seuil, non-régression #525 (échec ancien → « en file », nouvelle
  ACK après relance fait foi), aucun commentaire, ACK simple sans échec.
