# BUILD_WINDOWS_CCW — builds Windows par projet (CCW)

Document de référence pour tout ce qui est **spécifique à un projet donné**
dans les builds Windows délégués à CCW (PyInstaller/Inno Setup). Le pattern
général et la procédure d'envoi d'une issue `for-windows` restent dans
`BRIDGE_AGENT_DOC.md` (§16.3) ; ce fichier évite d'y accumuler, projet après
projet, du contenu qui n'intéresse que le projet en question.

Convention d'ajout : une nouvelle checklist par projet buildé, à la suite,
la plus récente en premier. Ne pas renuméroter les entrées existantes.

---

## Pattern général — staging local (issue #297)

Un build PyInstaller/Inno Setup lancé **directement** sur
`\\VBOXSVR\CCW_Share` peut produire des fichiers tronqués/corrompus
(diagnostiqué sur Scrabble, fix #338).

**Contournement standard :** le script de build copie d'abord les sources
vers un répertoire local à la VM (`C:\Temp\<Projet>Build` ou équivalent),
construit **entièrement** là, puis ne recopie vers le partage que
l'artefact final (installeur ou `dist\`).

**Conséquence obligatoire :** ajouter ce chemin local au `PERIMETRE` de
`configs\ccw.conf` (liste séparée par virgules), sans quoi CCW refuse à
juste titre d'en sortir et bloque légitimement le build.

**Rappel :** avant de builder un nouveau projet, vérifier si son script de
build suit déjà ce schéma de staging local et, si oui, étendre le
`PERIMETRE` en conséquence.

---

## Checklist par projet

À remplir pour chaque projet buildé sous Windows :

- **Chemin du clone CCW** : `Z:\CCW\<projet>`
- **Script de build** : nom et emplacement (ex. `build\rebuild_<projet>.bat`)
- **`.spec`** : liste explicite des `datas`, ou `collect_tree` en bloc —
  ⚠️ mise en garde si en bloc : un `collect_tree` mal ciblé peut embarquer
  des ressources volumineuses et non nécessaires dans l'artefact final
  (cf. incident dump wiktionnaire 8,2 Go sur Scrabble, 31/07/2026)
- **TIMEOUT de référence observé**
- **Taille de référence de l'artefact final** (installeur ou `dist\`),
  idéalement avec un hash pour détecter une régression silencieuse

---

## Actualise

- **Chemin du clone CCW** : `Z:\CCW\actualise` (dépôt AlainDelree/Actualise,
  public)
- **Script de build** : `build\rebuild_actualise.bat` (staging local
  `C:\Temp\ActualiseBuild`, PAS d'étape Inno Setup — Actualise se
  distribue en `dist\Actualise\` nu via Release GitHub, pas d'installeur)
- **`.spec`** : `actualise.spec` — `--onedir --noconsole` (invisible
  pendant que l'application cible tourne, logging fichier compense, voir
  `CONCEPTION.md` du projet Actualise) ; `datas=[]` explicite
  (`config.json` est externe, jamais embarqué) ; `hiddenimports=[]`
  (`requests` détecté seul par PyInstaller)
- **TIMEOUT de référence observé** : build réel 90,47 s (marge très
  confortable avec le TIMEOUT de 1800s utilisé)
- **Taille de référence de l'artefact final** : `dist\Actualise\` non
  compressé, 20 970 000 octets environ (20,97 Mo, 29 fichiers) —
  `Actualise.exe` seul : 4 388 786 octets, SHA-256
  `61A3373D6EE2D48A357E34BA9E967236B101F3F580BD98BC20DD667C86772F47`
  (référence du 3 août 2026)
- **Mode `--publier`** (suite #328/#329, demandé par #364, implémenté côté
  CCW via l'issue for-windows #365 — `rebuild_actualise.bat` vit dans le
  dépôt Actualise, hors périmètre CCL) : après un build réussi, construit
  `actualise.zip` (manifeste `{"build": N, "supprimer": []}`), détermine le
  numéro de build (auto = `version.json` existant + 1, ou forcé via
  `--publier --build N`), calcule le SHA-256 du zip, écrit `version.json`
  (`{"build": N, "sha256": "..."}`) et fait un commit local sur le dépôt
  Actualise — jamais de `git push` ni de Release GitHub (restent manuels,
  à la charge d'Alain). Comportement par défaut (sans paramètre) inchangé.

## Rummikub

- **Chemin du clone CCW** : `Z:\CCW\rummikub`
- **Script de build** : `build\rebuild_rummikub.bat` (6 étapes)
- **`.spec`** : `rummikub.spec` — liste explicite des `datas`
  (`src/rummikub/ui/web/`), aucun `collect_tree` en bloc
- **TIMEOUT de référence observé** : 1200s (build réel : ~333s)
- **Deux garde-fous de taille distincts** (issue #57 — dist non compressé
  et installeur compressé sont deux grandeurs différentes) :
  - `dist\Rummikub\` non compressé : 28 712 051 octets (~28,7 Mo),
    fourchette 20-45 Mo
  - `Rummikub-Setup.exe` compressé : 12 778 092 octets (~12,18 Mo),
    fourchette 5-25 Mo

## Scrabble

- **Chemin du clone CCW** : `Z:\CCW\scrabble`
- **Script de build** : `build\rebuild_scrabble.bat` (7 étapes, fix #338)
- **`.spec`** : `scrabble.spec` corrigé en liste explicite des `datas`
  (issue ouverte suite au diagnostic du dump wiktionnaire embarqué en bloc
  par `collect_tree`)
- **TIMEOUT de référence observé** : 1200s
- **Taille de référence de l'artefact final** : installeur, 26 546 846
  octets — SHA256
  `d52e101f8758a1b107011adf0bc1a04102bce48d3283248650019ba101ef3254`
  (référence du 31 juillet 2026)
