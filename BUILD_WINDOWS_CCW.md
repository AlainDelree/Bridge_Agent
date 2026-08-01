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
