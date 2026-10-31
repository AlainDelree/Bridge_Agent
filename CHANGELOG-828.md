## Issue #828 — `BUILD_WINDOWS_CCW.md` : mise à jour de la fiche Rummikub (solveur, tailles, script durci)

La fiche Rummikub décrivait encore le jeu d'avant le solveur exact
(gardes de taille 20-45 Mo / 5-25 Mo, tailles de référence d'avant le
solveur présentées sans distinction) et un script d'avant l'issue #218 de
Rummikub. Mise à jour à partir des chiffres de l'issue #218 de Rummikub
(essai `--build 99`, sans `--publier`, commit d7611d2) et de l'issue #208
de Rummikub, sans relecture du script ni du dépôt Rummikub lui-même
(hors périmètre de cette issue).

- **Gardes de taille** : fourchettes remplacées par 20-120 Mo (20 971 520
  à 125 829 120 octets) pour le dossier `dist\` non compressé et 5-50 Mo
  (5 242 880 à 52 428 800 octets) pour l'installeur compressé et pour
  l'archive zip (mêmes bornes que l'installeur) ; « Mo » précisé à
  1 048 576 octets. Noté que ces gardes n'affichent qu'un message
  `[ATTENTION]` sans arrêter le build, que le script annonce ~80 Mo/~30 Mo
  attendus, que l'élargissement vient du solveur exact (issues #206 et
  #208 de Rummikub), et que le script qualifie lui-même ces valeurs de
  provisoires.
- **Tailles de référence** : nouveau paragraphe « Build de référence avec
  solveur » (essai `--build 99` de l'issue #218, octobre 2026, commit
  d7611d2) — dossier 62 571 296 octets, installeur 21 077 072 octets,
  archive 25 962 601 octets, aucun garde déclenché, présenté comme le
  premier build avec solveur (essai non publié). Les trois jeux de
  tailles d'avant le solveur (build 13, essai 99 du 25 octobre 2026, build
  14) sont conservés mais chacun désormais marqué explicitement « avant
  solveur », pour ne plus laisser deux jeux de tailles sans explication.
- **Solveur et autotest** : nouveau paragraphe listant `highspy` 1.15.1 et
  `numpy` 2.5.4 installés depuis `requirements.txt` et collectés par
  PyInstaller, et une « Vérification propre à ce projet » pour l'option
  `--autotest` (issue #208) — succès constaté (code de sortie 0, message
  « backend HIGHS, 6 tuiles posées en 0 ms (optimum prouvé) »), à recopier
  dans « Vérifier le résultat » du modèle d'issue (pas dans
  « Vérifications préalables »). La manière exacte dont elle est lancée
  reste « Non établi ».
- **Script durci (issue #218)** : garde-fou `0bis` complété (refuse
  désormais aussi un numéro avec un zéro initial ou nul — `--build 0`,
  `--build 014`, `--build 05` — code de sortie 1, rien écrit) ; nouveau
  paragraphe sur le remplacement de l'ancien `taskkill` par une simple
  détection d'instance en cours, sans fermeture ni arrêt du build ; la
  puce « Release à deux fichiers » précise que le rappel de fin avec
  `--publier` suit maintenant l'ordre du guide (fusionner sans pousser,
  Release à deux fichiers, pousser master), avec un « Non établi » pour
  le fait que ce rappel n'a pas encore été vu à l'exécution.
- **Durée** : nouvelle puce « Durée de l'issue #218 » — 697 secondes pour
  un `TIMEOUT` de 1800s, pour un build avec solveur et trois refus,
  précisé comme n'étant pas la durée du script seul.

Aucune mention « à confirmer » trouvée dans le guide (l'issue #827 les
avait déjà toutes retirées) ; les fiches Scrabble et Actualise et le
modèle d'issue de build ne sont pas modifiés.
