## 23 septembre 2026 — issue #593

Retrait de `testrelectureprojet` de `BRIDGE_AGENT_DOC.md` : projet test
supprimé, qui avait été ajouté manuellement (hors création standard
Bridge_Agent) pour apparaître dans Relecture_Bridge.

- `BRIDGE_AGENT_DOC.md` :
  - Ligne 85 (tableau §2, projets actifs) : suppression de la ligne
    `| testrelectureprojet | AlainDelree/Testrelectureprojet | ~/Testrelectureprojet | (conf local) |`.
  - Ligne 723 (tableau §7, REP_TRAVAIL par projet) : suppression de la ligne
    `| testrelectureprojet | /home/alain/Testrelectureprojet |`.
  - Vérifié : `grep -i "testrelectureprojet" BRIDGE_AGENT_DOC.md` ne retourne
    plus aucun résultat.
