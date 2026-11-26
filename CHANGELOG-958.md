## 26 novembre 2026 — issue #958

Convention commune de notes de version pour les builds Windows d'Actualise, Scrabble et Rummikub — décidée par Alain parce que la Release GitHub de ces trois projets était créée sans texte : les `CHANGELOG-<N>.md` existent mais sont techniques, rangés par issue et pas par version, donc impossibles à coller tels quels dans une Release. Documentation uniquement (`BUILD_WINDOWS_CCW.md`), aucun script de build, aucun dépôt d'application, aucun fichier de configuration modifié.

**`BUILD_WINDOWS_CCW.md`** :
- « Comment se passe un build » : le fichier de notes `notes_de_version/v<N>.md` ajouté à la liste des commits attendus à l'issue d'un build de publication réussi, avec rappel qu'il reste dans le dépôt et n'entre jamais dans l'archive.
- « Ce que l'agent vérifie et rapporte » : nouveau point — pour un build de publication, l'agent contrôle que le fichier existe, qu'il porte le bon numéro, et en recopie le contenu dans son rapport.
- « Ce que fait Alain ensuite » (étape 3, Release) : récupération du fichier de notes dans le clone Windows (déjà à jour grâce à la fusion de l'étape 2) et passage à `gh release create --notes-file` ; chemins des trois clones trouvés dans la table des projets actifs de `BRIDGE_AGENT_DOC.md` §2 — `C:\CCW\actualise`, `C:\CCW\rummikub`, `C:\CCW\scrabble` — et rappel qu'une Release déjà créée sans notes se complète avec `gh release edit --notes-file`.
- Nouvelle section « Notes de version » (entre « Le numéro de build et Actualise » et « Fiche par projet ») : principe général, quelles issues résumer (entrées de changelog ajoutées depuis le `version.json` du build précédent, dans `CHANGELOG-<N>.md` non fusionnés ou dans `CHANGELOG.md` déjà fusionné), langue et ton, rubriques (« Nouveautés », « Corrections », « Sécurité et robustesse », « À savoir »), fidélité, et ce qui est interdit (jeton, sujet ntfy, chemin propre aux PC d'Alain, adresse IP — ces notes sont publiques).
- « Fiche par projet » : une ligne ajoutée à chacune des fiches Rummikub, Scrabble et Actualise, renvoyant à cette nouvelle section, avec la mention de vérifier à la première utilisation que `notes_de_version/` n'a pas déjà un autre usage dans le dépôt et que le script de build n'embarque pas la racine du dépôt.
- « Modèle d'issue de build » : nouvelle section « Notes de version » dans le gabarit, contrôle du fichier ajouté à « Vérifier le résultat », fichier ajouté à la liste des fichiers modifiables dans « Contraintes », et mention de son contenu dans « Rapport attendu ».

`BRIDGE_AGENT_DOC.md` non modifié : aucun passage (§16 ou autre) ne résume l'étape Release d'un build, il n'y avait donc rien à y faire renvoyer (vérifié : aucune occurrence de « release » dans ce fichier).

`CONTEXTE.md` non modifié (3995/4000 caractères déjà, consigne de ne pas le grossir respectée) : son index renvoie déjà vers `BUILD_WINDOWS_CCW.md` pour les builds Windows.
