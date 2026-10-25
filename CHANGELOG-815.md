## Issue #815 — Documentation : fiche Scrabble du guide de build mise à jour pour la nouvelle syntaxe du script (issue #472 de Scrabble)

`BUILD_WINDOWS_CCW.md` (58 insertions, 16 suppressions) : la fiche
Scrabble est réécrite sur le modèle de la fiche Actualise (issue #814) —
commande exacte `build\rebuild_scrabble.bat --publier [--build N]`
(l'ancienne forme `--publier <N>` n'est plus acceptée), numéro par défaut
(build de `version.json` + 1, dans tous les modes), garde-fou et refus
(issue #472 de Scrabble), dix étapes numérotées de 0 à 9 (contre neuf
auparavant), artefacts et copie systématique vers
`C:\CCW_Share\_derniers_builds\scrabble\` dans tous les modes avec
affichage des noms et tailles par le script lui-même, Release à deux
fichiers, essais avec un numéro fictif et nettoyage à la main. Référence
de l'essai avec le numéro fictif 99 (installeur 12 905 773 octets, archive
13 355 850 octets, durée 113 secondes), fournie par le Chat Scrabble et
marquée « à confirmer par le build 14 ». Le build de référence 13 (283
secondes, archive 13 275 222 octets, installeur 12 843 901 octets, 77
fichiers), le `.spec` à liste explicite de `datas` et la vérification de
l'absence de dictionnaire dans l'archive sont conservés, en précisant que
le build 13 date de l'ancienne syntaxe. La fiche Rummikub n'est pas
modifiée.

Dans la fiche Actualise, la phrase sur le nombre d'étapes est corrigée :
Rummikub en annonce neuf (0 à 8), Scrabble désormais dix (0 à 9) comme
Actualise — elle affirmait à tort que Scrabble n'en avait aussi que neuf.

Les trois passages qui décrivaient la récupération des fichiers produits
dans `installeur\output` du worktree comme une règle unique (« Comment se
passe un build », « Ce que fait Alain ensuite » étapes 1 et 6, et le
modèle d'issue — « Rapport attendu ») sont reformulés pour dépendre de la
fiche du projet : si le script copie aussi dans le dossier fixe
`C:\CCW_Share\_derniers_builds\<projet>\` (Actualise et Scrabble à ce
jour), la consigne devient de vérifier la présence des deux fichiers dans
ce dossier avant de supprimer le worktree ; sinon (Rummikub pour
l'instant), de les récupérer dans `installeur\output` du worktree.

Suite de tests Python complète (`tests/lancer_tous_les_tests.py`) :
82 fichiers exécutés, 82 réussis, 0 échec — inchangée par cette
modification purement documentaire.
