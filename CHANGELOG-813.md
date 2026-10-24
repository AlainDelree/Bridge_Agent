## Issue #813 — Réinstallation du PC fixe : fichiers locaux non versionnés des clones (configurations, exclusions) et mise à jour de l'étape 3 (SSH)

`provisioning/windows/REINSTALLATION_CCW.md` (86 insertions, 20
suppressions) : correction de l'étape 7, qui affirmait à tort que les
fichiers `configs\<projet>-ccw.conf` « survivent » à la réinstallation
(ils ne sont pas versionnés et vivent dans le clone dédié de chaque
projet, pas dans celui de Bridge_Agent — une réinstallation propre les
perd) ; ajout d'un paragraphe « Avant de réinstaller » en tête de l'étape
1 (noter la liste des projets CCW actifs et leur dépôt — lignes `<nom>_ccw`
du tableau §2 de `BRIDGE_AGENT_DOC.md` — et la valeur du `TOPIC_NTFY` de
chacun, copier les `*-ccw.conf` et `ccw.conf` hors du disque qui sera
effacé) ; étape 7 complétée par un repli (`creer_projet_ccw_complet.ps1`
par projet si aucun fichier n'a été restauré) et par l'usage de
`-SeulementProjets` avec la liste des projets actifs, pour ne pas
recréer les services de projets dont CCW n'a plus besoin (`alchess`,
`Relecture_Bridge`) ; mention des exclusions locales `.git\info\exclude`
comme second fichier non versionné du clone, recréé par
`ajouter_projet_ccw.ps1`. Étape 3 : tableau de diagnostic enrichi de
`Network is unreachable` / `Could not resolve hostname` sur la ligne « PC
éteint ou adresse introuvable » (les quatre libellés restent inchangés) ;
bloc « Symptôme à connaître » mis à jour (le message trompeur ne
s'affiche plus que pour cette catégorie ou en repli, `relecture_web`
affichant désormais la cause identifiée avec la commande `ssh-keygen -R`
pour une clé d'hôte modifiée) ; précision près de cette commande sur la
confirmation d'empreinte (`yes`) attendue au test manuel, et sur
l'enregistrement automatique de la nouvelle clé par Bridge_Agent et
`relecture_web` (`StrictHostKeyChecking=accept-new`) ; ajout d'une phrase
sur le message générique + première ligne d'erreur SSH affichés par
`relecture_web` pour une cause non reconnue.

`provisioning/windows/reinstaller_projets_ccw.ps1` (47 insertions, 22
suppressions) : énumère désormais `C:\CCW\*\configs\*-ccw.conf` (racine
des clones CCW, dérivée du chemin du script, paramètre `-RepCCW`
surchargeable) au lieu du seul dossier `configs\` de Bridge_Agent, qui ne
contient que le canal unifié `ccw.conf` — l'ancienne énumération n'y
aurait jamais rien trouvé, même sans réinstallation. Quand aucun fichier
n'est trouvé, affiche un message explicite (fichiers non versionnés,
perdus par une réinstallation propre, deux solutions : restaurer la
copie ou appeler `creer_projet_ccw_complet.ps1` par projet) et termine
avec le code de sortie 1 au lieu de 0.

`provisioning/windows/ajouter_projet_ccw.ps1` (41 insertions, 5
suppressions) : après le clonage ou la mise à jour du dépôt, complète
`.git\info\exclude` du clone avec les lignes `configs/` et `logs/`
(réglage local au clone, jamais versionné) si elles manquent, sans
doublon ni écrasement du contenu existant — en leur absence,
`relecture_web` signalait des modifications non committées sur ces
dossiers et refusait la fusion (constaté le 24/10/2026 sur
`C:\CCW\rummikub` et `C:\CCW\scrabble`). Étapes du script renumérotées
en conséquence (1 à 5).

Aucun autre fichier touché. Scripts PowerShell non exécutés
(remplacements ciblés uniquement, BOM UTF-8 et fins de ligne LF vérifiés
avant/après).
