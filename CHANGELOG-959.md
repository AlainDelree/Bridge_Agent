## 26 novembre 2026 — issue #959

Trois retouches sur la convention de notes de version pour les builds Windows, ajoutée par l'issue #958 — relecture du diff du commit 604315e ayant révélé trois points imprécis. Documentation uniquement (`BUILD_WINDOWS_CCW.md`), rien d'autre modifié.

**`BUILD_WINDOWS_CCW.md`** :
- « Ce que fait Alain ensuite » (étape 3, Release) : l'exemple `gh release create` précise désormais depuis quel dossier la commande se lance (le clone Windows du projet, où se trouve le fichier de notes en chemin relatif) et d'où viennent l'installeur et l'archive (`C:\CCW_Share\_derniers_builds\<projet>\`, en chemin complet), au lieu de noms de fichiers relatifs inutilisables tels quels.
- « Comment se passe un build » et « Notes de version » (corps du guide) : « il n'entre jamais dans l'archive » remplacé par « il ne doit pas entrer dans l'archive », formulation plus prudente, en gardant le renvoi à la vérification des dossiers de premier niveau de l'archive qui permet de le détecter. Les mentions « vérifier à la première utilisation » des fiches de projet ne sont pas concernées.
- « Notes de version » (modèle d'issue de build) et corps du guide : précision explicite que l'agent commite le fichier de notes dans la branche du worktree (sans ce commit, Alain ne le fusionnerait pas et il serait absent du clone Windows à l'étape Release), et qu'il l'écrit après le build et ses vérifications, pour qu'il ne puisse pas être embarqué par le script.
