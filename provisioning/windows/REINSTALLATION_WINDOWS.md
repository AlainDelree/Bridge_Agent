# REINSTALLATION_WINDOWS — réinstallation du système Windows lui-même

Procédure **préalable** à `REINSTALLATION_CCW.md` (même dossier), qui ne
couvre que le provisioning logiciel de l'agent CCW (SSH, `provisionner.ps1`,
tokens) et suppose Windows déjà installé et opérationnel. Ce document-ci
couvre l'étape d'avant : remettre Windows lui-même à neuf sur le PC fixe,
depuis la fabrication de la clé USB jusqu'à un Bureau fraîchement installé
avec Windows Update désactivé durablement.

Issue #671, suite de la réinstallation du 27/09/2026 (issue #658) menée via
la fonction de réparation intégrée de Windows faute de clé USB à jour —
voir §3 ci-dessous pour ce cas particulier.

## Procédure

### 1. Fabriquer la clé USB bootable

**Édition** : Windows 11 IoT Enterprise LTSC (évaluation 90 jours) — même
édition que celle déjà en place sur le PC fixe (cf. `REINSTALLATION_CCW.md`
et `eval-expiration.json`).

**Source de l'ISO officielle** :
https://www.microsoft.com/fr-fr/evalcenter/evaluate-windows-11-iot-enterprise-ltsc

**Outil recommandé** : Rufus, en **mode normal** (PAS le mode « écriture en
mode ISO »). La clé USB habituelle utilisée pour ce PC est une clé bootable
classique à **partition unique FAT32** (contenu de l'ISO copié directement
dessus) — **pas** une clé Ventoy (multi-ISO). Vérifié le 28/09/2026 via
`lsblk -f` : une seule partition `vfat`, aucune partition `Ventoy`/`VTOYEFI`
sur la clé habituelle. Rufus en mode normal reproduit ce format ; le mode
« ISO » de Rufus (image montée telle quelle, souvent en NTFS) donnerait un
résultat différent et n'est pas celui utilisé jusqu'ici.

> Note d'incertitude : l'outil exact utilisé pour graver la clé actuelle
> n'est pas certifié à 100 % (pas de trace conservée de l'outil au moment
> de la gravure) — mais le résultat observé (partition unique FAT32,
> contenu ISO à plat) correspond au comportement de Rufus en mode normal,
> d'où la recommandation. Si une clé Ventoy est utilisée à l'avenir par
> commodité, en tenir compte au §2 (ordre de boot) et au §3 (le
> comportement de réparation en place peut différer).

Avant de graver, **ne PAS injecter** de fichier `autounattend.xml` sur la
clé pour un usage physique manuel sur ce PC — `autounattend.xml` (ce
dossier) est prévu pour le provisioning **automatisé de la VM CCW-Build**
(`creer_vm_ccw.py`), pas pour la réinstallation physique du PC fixe décrite
ici. Une installation manuelle classique (écrans OOBE répondus à la main)
est le cas normal pour ce PC.

### 2. Booter depuis la clé USB

Sur ce PC fixe, forcer le boot sur la clé USB via le menu de boot du
BIOS/UEFI (touche d'accès au menu de boot au démarrage, avant le chargement
de Windows — variable selon la carte mère, généralement `F12`, `F11`, `Échap`
ou `Suppr`/`Del` pour entrer dans le setup complet si le menu rapide n'est
pas proposé). Choisir la clé USB dans le mode **UEFI** (pas « Legacy »/CSM)
pour rester cohérent avec le partitionnement GPT attendu par Windows 11.

Si le boot sur clé USB reste inactif malgré le choix dans le menu de boot,
vérifier dans le setup BIOS/UEFI que le « Secure Boot » n'exclut pas un
média externe non signé de la façon attendue, et que l'ordre de boot par
défaut n'est pas restreint au seul disque interne — cas déjà rencontré sur
ce PC par le passé, résolu en repassant temporairement l'ordre de boot en
priorité USB avant redémarrage.

### 3. Installation standard vs réparation en place

**Cas normal — installation standard** : depuis l'écran de démarrage du
programme d'installation Windows lancé par la clé USB, choisir une
installation propre (formatage de la partition système), ce qui donne accès
à toutes les options (garder ou non les fichiers/applications, ou tout
effacer). C'est le cas d'usage habituel d'Alain avec ce PC.

**Cas de réparation en place (rencontré le 27/09/2026)** : si la clé USB
disponible au moment de la réinstallation est **antérieure** à la version
de Windows actuellement installée sur le disque (clé fabriquée avant la
dernière mise à jour de fonctionnalité, par exemple), le programme
d'installation refuse de proposer une installation propre classique depuis
ce média et ne propose que la voie de **réparation/mise à niveau en
place** (lancée directement depuis `setup.exe` sur la clé, à l'intérieur
de la session Windows existante, plutôt que depuis un boot USB pur).

**Limite connue de ce cas** : seule l'option « **conserver les fichiers
personnels** » est alors disponible — pas « conserver les applications ».
Concrètement : les documents/fichiers utilisateur survivent, mais **tous
les logiciels installés sont à réinstaller** après coup (dont tout
l'outillage posé par `provisionner.ps1`, cf. `REINSTALLATION_CCW.md`). Ce
n'est donc pas un simple redémarrage propre — préparer la réinstallation
complète du logiciel en aval en conséquence.

Pour éviter de retomber dans ce cas contraint, tenir la clé USB à jour
avec la dernière ISO officielle disponible (§1) avant toute réinstallation
planifiée, plutôt que de réutiliser une clé ancienne.

### 4. Désactiver durablement Windows Update

**Contexte** : la réinstallation du 27/09/2026 (issue #658) a été motivée
par un plantage `ucrtbase.dll` causé par une mise à jour cumulative
Windows. `provisionner.ps1` désactive déjà Windows Update au provisioning
CCW (cf. `REINSTALLATION_CCW.md`, étape 4), mais uniquement dans la mesure
où ce script agit — cette étape-ci vise une désactivation **complète et
durable au niveau de Windows lui-même**, à effectuer une fois juste après
l'installation, en admin (PowerShell) :

**a. Service Windows Update** — désactiver et arrêter le service :

```powershell
Stop-Service -Name wuauserv -Force
Set-Service -Name wuauserv -StartupType Disabled
```

**b. Stratégie de groupe / registre** — désactiver la recherche
automatique de mises à jour au niveau politique, pour empêcher Windows de
réactiver le service tout seul (les éditions IoT Enterprise LTSC n'ont pas
toujours `gpedit.msc` disponible ; la clé de registre équivalente
fonctionne dans tous les cas) :

```powershell
New-Item -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" -Force | Out-Null
Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" -Name "NoAutoUpdate" -Value 1 -Type DWord
```

**c. Tâches planifiées** — Windows Update s'appuie aussi sur des tâches
planifiées indépendantes du service (`UpdateOrchestrator`), qui peuvent
redéclencher une recherche même service arrêté :

```powershell
Get-ScheduledTask -TaskPath "\Microsoft\Windows\UpdateOrchestrator\*" |
    Disable-ScheduledTask
```

**Vérification** : redémarrer le PC, puis confirmer que le service reste
à l'état `Stopped`/`Disabled` (`Get-Service wuauserv`) et qu'aucune tâche
`UpdateOrchestrator` ne repasse à `Ready` (`Get-ScheduledTask -TaskPath
"\Microsoft\Windows\UpdateOrchestrator\*" | Select TaskName, State`).

> Cette désactivation est délibérément agressive (pas de simple report des
> mises à jour) : la cause du plantage du 27/09/2026 était une mise à jour
> cumulative appliquée automatiquement en arrière-plan, sans action de
> l'utilisateur — l'objectif est qu'aucun mécanisme résiduel de Windows ne
> puisse la réappliquer d'ici la prochaine réinstallation planifiée
> (~tous les 3 mois, cf. `eval-expiration.json`).

---

Une fois cette procédure terminée (Windows installé, Windows Update
désactivé), poursuivre avec `REINSTALLATION_CCW.md` pour le provisioning
de l'agent CCW.
