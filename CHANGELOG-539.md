## 13 septembre 2026 — issue #539

Suite retour d'usage sur #535 : 3 paires de couleurs de projet restaient
visuellement trop proches malgré une distance CIE76 au-dessus du seuil de
garde de 15 posé en #535 — `alchess`/`rummikub`, `ecole`/`chesscoach`,
`actualise`/`gestionmail`.

**Diagnostic (point 1 de l'issue)** : les couleurs réellement en usage pour
`alchess`/`rummikub` et `ecole`/`chesscoach` ont une distance CIE76 de 56 et
52 — largement AU-DESSUS du seuil de 15, pas « de justesse » comme supposé.
La vraie cause : leur écart d'angle de teinte dans le plan Lab a\*/b\* n'est
que de 1,6° et 0,4° — ces couleurs ne diffèrent quasiment qu'en clarté/chroma,
pas en teinte. CIE76 (distance euclidienne L/a\*/b\*) traite cet écart comme
n'importe quel autre, alors que l'œil, sur une petite pastille, identifie
d'abord la teinte : deux nuances d'une même teinte se lisent comme UNE seule
couleur, pas deux. `actualise`/`gestionmail` n'a pas pu être mesurée sur la
couleur réelle (gestionmail est un projet créé après #535, sa couleur ne vit
que dans `configs/gestionmail.conf`, hors périmètre de ce worktree et de
toute façon jamais modifiable par CCL/CCW) — mais le même mécanisme est en
cause : `actualise` (ancienne valeur, teinte Lab ≈292°) se trouvait dans la
même zone bleu-violet que `ff_galerie` (285,5°), `gestionmail` (candidat le
plus proche de la palette de l'époque : `#9191FF`, ≈296°) et `chesscoach`
(318,3°).

**Correction (points 2 et 3)** : `nouveau_projet.py` — ajout d'un second seuil
de garde `SEUIL_ECART_TEINTE_MIN` (15°, écart minimal d'angle de teinte Lab
entre deux couleurs de la palette), complémentaire de `SEUIL_DISTANCE_MIN`
(remonté 15→20, défense en profondeur mais insuffisant seul ici : 56 et 52
sont déjà loin au-dessus). `generer_palette()` vérifie désormais les deux
seuils, par construction (filtrage des candidats) ET par assertion finale.
Correction ciblée de 4 couleurs seulement dans `COULEURS_PROJETS_EXISTANTS`
(les 7 autres restent inchangées, même esprit que la correction #534
ecole/ff_galerie) :
- `alchess` `#00FF00`→`#00D68F` (pas de champ COULEUR persisté en `.conf`,
  contrairement à `rummikub` → conservée)
- `ecole` `#DE85FF`→`#CC7400` (pas de champ COULEUR persisté, contrairement à
  `chesscoach` → conservée ; nouvelle teinte ambre/moutarde, clin d'œil à la
  couleur qu'ecole portait déjà entre #534 et #535)
- `actualise` `#086BFF`→`#009DD6` (seul levier disponible côté code puisque
  gestionmail — l'autre membre de la paire — n'est pas modifiable ; nouvelle
  teinte délibérément écartée de toute la zone bleu-violet 197°-320°)
- `bloc_score` `#FFB0AB`→`#FF8595` : 4e paire découverte en appliquant le
  nouveau seuil (non signalée dans l'issue) avec `bridge_agent` (écart de
  teinte 13,2°, sous le nouveau plancher de 15°) — `bridge_agent` non
  retouché, nouvelle teinte toujours rose/saumon pâle.

Toutes les paires (11 couleurs figées + palette régénérée) validées sans
violation par script (120 paires testées, contraste texte noir >= 4,5:1
conservé partout). `static/js/app.js` (`COULEURS_PROJET`) mis à jour en
synchro.

**Mécanisme de sélection pour les futurs projets (point 4)** :
`generer_palette()` accepte désormais un paramètre `couleurs_a_eviter`
(passé avec `COULEURS_PROJETS_EXISTANTS`) et l'utilise comme réservation
initiale de l'algorithme glouton — pas seulement en post-filtrage comme le
faisait déjà `couleurs_utilisees()`. Sans ce paramètre, la garantie de
distance/teinte ne portait que sur les couleurs générées ENTRE ELLES, jamais
sur les 11 couleurs gelées en dur : c'est exactement ce trou qui avait laissé
passer la collision `actualise`/`gestionmail` (gestionmail avait pris une
couleur de la palette, valide par rapport aux autres couleurs générées, mais
jamais vérifiée par rapport à `actualise`). Avec ce paramètre, toute couleur
encore proposée à un futur projet est garantie distincte de TOUS les projets
existants. Conséquence attendue : `NB_COULEURS_PALETTE` (30 demandées) ne
produit plus que 5 couleurs effectivement disponibles au-delà des 11
historiques (contre 40 avant #539) — la combinaison seuil de distance +
seuil de teinte limite mécaniquement le nombre de couleurs vraiment
distinctes sur le cercle chromatique ; à surveiller si de nombreux nouveaux
projets sont créés.

**Point d'attention laissé à Alain** : la couleur réelle de
`configs/gestionmail.conf` n'a pas pu être lue (hors périmètre du worktree
`/home/alain/bridge_agent-issue539`, et modification de `configs/*.conf`
interdite à CCL/CCW dans tous les cas) ni donc revérifiée contre la nouvelle
valeur d'`actualise`. À vérifier manuellement ; si elle s'avère encore trop
proche d'une des 11 couleurs figées (ou d'une future couleur de
`PALETTE_COULEURS`), seule une modification manuelle du `.conf` par Alain
peut la corriger.
