## 2 novembre 2026 — issue #843

Consigne : `COMPLEXITE` obligatoire dans toute issue, quatre valeurs exactes.
Correction de `BRIDGE_AGENT_DOC.md` uniquement (aucun fichier de code
touché), suite à une mesure sur ~1500 issues fermées montrant le champ
`COMPLEXITE` absent dans plus de la moitié des issues de plusieurs projets,
et des valeurs hors liste ailleurs (`moyen`, `léger`, `simple`, `trivial`,
`normale`) — silencieusement rangées en `normal` par le code, ce qui
fausse la calibration du `TIMEOUT`.

- §3.3 : table des champs reconnus — `COMPLEXITE` passe d'absent à
  **obligatoire** (comme `PROJET`), quel que soit le `MODE` ; exemple
  canonique d'en-tête complété avec `| COMPLEXITE | normal |`.
- §6 : table des champs spéciaux — reformulation de la ligne `COMPLEXITE`
  (obligatoire, quatre valeurs exactes `rapide`/`court`/`normal`/`lourd`,
  aucun autre mot) ; nouvel encadré détaillant l'interdiction des mots
  déjà rencontrés, un critère de choix par valeur calé sur les durées
  médianes observées (rapide ≈1-2 min, court ≈2-5 min, normal ≈3-15 min,
  lourd ≈10-30 min), la règle du choix de la valeur la plus élevée en cas
  d'hésitation, et le rappel que `absent ou non reconnu = normal` reste un
  repli technique du code, pas un choix de rédaction légitime. Exemple de
  format dans le corps complété avec `| COMPLEXITE | court |`.
- Pied de page (`*Dernière mise à jour*`) mis à jour en conséquence.

Aucun changement de comportement côté code : le repli `normal` du watcher
reste inchangé, seule la consigne lue par Claude Chat avant de rédiger une
issue est corrigée.
