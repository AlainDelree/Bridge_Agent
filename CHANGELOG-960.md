## 26 novembre 2026 — issue #960

Ordre incohérent entre écriture et contrôle du fichier de notes de version dans `BUILD_WINDOWS_CCW.md`, introduit par les issues #958 et #959 : le modèle d'issue de build demandait d'écrire `notes_de_version/v<N>.md` « après le build et les vérifications de la section "Vérifier le résultat" qui suit », alors que cette même section contenait le contrôle de ce fichier — impossible à faire avant qu'il existe. Documentation uniquement (`BUILD_WINDOWS_CCW.md`), rien d'autre modifié.

**`BUILD_WINDOWS_CCW.md`** :
- Corps du guide, section « Notes de version » : « après le build et ses vérifications » précisé en « après le build et la vérification de l'archive ».
- Modèle d'issue de build, section « Notes de version » : même précision, et ajout de la mention que le contrôle du fichier de notes (existe, bon numéro) se fait juste après son écriture et son commit — ce contrôle ne pouvant se faire qu'une fois le fichier écrit, il ne fait plus partie de la section « Vérifier le résultat » qui suit.
- Modèle d'issue de build, section « Vérifier le résultat » : le point sur `notes_de_version/v<numéro-de-build>.md` retiré de cette liste (déplacé dans « Notes de version » ci-dessus), qui ne porte donc plus que sur l'archive.

Ordre final décrit par les trois passages : build, vérification de l'archive, écriture du fichier de notes, commit, contrôle du fichier, rapport.

« Ce que l'agent vérifie et rapporte » (corps du guide) non modifié : ce point ne laissait pas entendre un contrôle avant écriture, rien à y corriger.

`CONTEXTE.md` non modifié : aucune règle, convention, architecture ou dépendance touchée par cette tâche.
