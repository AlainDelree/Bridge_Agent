## 1 novembre 2026 — issue #841

Met à jour les fiches Scrabble et Actualise de `BUILD_WINDOWS_CCW.md` pour
refléter les harmonisations des scripts de build avec Rummikub (issues
#481 de Scrabble et #75 d'Actualise, fusionnées et poussées).

Fiche Scrabble : la puce « Écart connu du manifeste… Cet écart n'est pas
corrigé » est remplacée par son inverse (le manifeste écrit maintenant le
vrai numéro de build, les archives v13/v14 déjà publiées contiennent
encore `"build": 1`) ; ajout d'une puce sur les autres changements de
#481 (suppression du `reset --hard` obsolète, étape 3 devenue une simple
détection, rappel de fin dans l'ordre du guide, non établi à l'exécution
réelle) ; ajout des valeurs mesurées de l'essai `--build 99` après #481
comme référence secondaire. Les références des builds 13 et 14 ne sont
pas modifiées.

Fiche Actualise : le garde-fou (issue #71) est complété par le refus du
zéro initial ou nul (#75, forme `^[1-9][0-9]*$`) avec les trois essais de
refus ; la puce « Release à deux fichiers » gagne la mention de l'ordre
du guide pour le rappel de fin (non établi à l'exécution réelle) ; les
tailles de référence passent au build 12 publié (build 11 conservé comme
« référence précédente »), avec l'essai `--build 99` après #75 ajouté
comme référence secondaire (tailles et nombre d'entrées de l'archive) ;
la durée de l'issue #75 (977s, `TIMEOUT` 3600s) est notée comme durée de
l'issue complète, pas du script seul.

La phrase sur le nouvel `updater.bat` (v12→v13) n'est pas modifiée — son
exactitude pour le build 12 publié reste à relire.

Seul `BUILD_WINDOWS_CCW.md` est modifié (fiches Rummikub, modèle d'issue
et sections générales inchangés).
