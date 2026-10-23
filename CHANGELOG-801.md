## Issue #801 — retrait des scripts et de la documentation de l'ancienne VM CCW-Build

Suppression des quatre fichiers qui ne servaient qu'à la VM VirtualBox `CCW-Build` (supprimée par Alain) : `provisioning/windows/creer_vm_ccw.py`, `provisioning/windows/lancer_provisioning.py`, `provisioning/windows/demarrer_ccw.sh`, `provisioning/windows/autounattend.xml`. Aucun appel depuis `app/*.py`, `watcher.py` ou les tests ; seuls des documents et `provisionner.ps1` (traité par une autre issue) les citaient.

`BUILD_WINDOWS_CCW.md` : retrait de la mention du chemin VirtualBox `\\VBOXSVR\CCW_Share`, remplacée par une description générique d'un build lancé directement sur un dossier réseau partagé, et précision que les builds s'exécutent dans le dossier du projet sous `C:\CCW` (clone GitHub local), `C:\CCW_Share` restant le dossier partagé du PC fixe. Reste de la section et checklists par projet (Actualise, Rummikub, Scrabble) inchangés.

`provisioning/windows/REINSTALLATION_CCW.md` : retrait du paragraphe sur `autounattend.xml`/VM `CCW-Build`, remplacé par deux phrases sur la conséquence de l'expiration de la licence d'évaluation Windows (redémarrages horaires, service `CCW-Watcher` cassé, échéance suivie dans l'annuaire AnnuaireToken, réinstaller avant l'échéance).

`provisioning/windows/REINSTALLATION_WINDOWS.md` : retrait du paragraphe « ne PAS injecter de fichier `autounattend.xml` » (provisioning automatisé de la VM), reste de l'étape 1 inchangé.

`BRIDGE_AGENT_DOC.md` §11 : retrait de la précision « `autounattend.xml` n'est pas concerné » dans la règle du BOM UTF-8 PowerShell (le fichier n'existe plus). Dernière ligne du document mise à jour (23 octobre 2026).

`VERIFICATIONS_MANUELLES.md` : retrait de la puce de contrôle de l'absence d'une ligne « VM » dans le panneau de monitoring (devenue sans objet, la VM n'existant plus du tout).

Recherche des références restantes aux quatre fichiers supprimés dans tout le dépôt (hors `CHANGELOG.md` et `.git`) : seules restent `.gitignore` (lignes sur `autounattend.local.xml`, volontairement conservées — un fichier local peut exister sur le poste d'Alain) et la nouvelle dernière ligne de `BRIDGE_AGENT_DOC.md` elle-même (qui documente la suppression). Aucune autre occurrence, y compris en dehors des fichiers Markdown.

Volontairement non modifié : `.gitignore`, `CHANGELOG.md`, le code Python, les scripts PowerShell, le JavaScript — tous hors périmètre de cette issue. Le contournement de « staging local » (`BUILD_WINDOWS_CCW.md` §Pattern général, et mentionné dans `BRIDGE_AGENT_DOC.md` §16 ainsi que dans les consignes globales injectées) n'a pas été modifié ni déclaré obsolète : son utilité dépend des scripts de build propres à chaque dépôt projet, hors constat établi par cette issue.
