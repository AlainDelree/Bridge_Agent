# REINSTALLATION_CCW — réinstallation du PC fixe CCW

Procédure complète pour réinstaller de A à Z le PC fixe Windows dédié à
l'agent **CCW** (Windows 11 IoT Enterprise LTSC, évaluation 90 jours), sans
avoir à reconstruire la démarche de mémoire. Les scripts référencés vivent
tous dans ce même dossier (`provisioning/windows/`). Pour le contexte
général de l'agent CCW (rôle, architecture, onglet de pilotage), voir
`BRIDGE_AGENT_DOC.md` §16.

**Rappel important — clé SSH CCL→CCW.** La clé **privée** (`~/.ssh/ccl_ccw`
sur le ThinkPad, côté CCL) **reste en place** d'une réinstallation à
l'autre : elle n'a jamais besoin d'être régénérée ni retouchée. Seule sa
**clé publique** (`~/.ssh/ccl_ccw.pub`) doit être réinstallée sur le
Windows fraîchement réinstallé (étape 2 ci-dessous), puisque c'est
`authorized_keys` côté Windows qui est reconstruit à zéro par la
réinstallation, pas la paire de clés côté CCL.

## Procédure

### 1. Réinstallation Windows

> **Avant de réinstaller.** Noter, avant d'effacer le disque : la liste des
> projets CCW actifs et leur dépôt GitHub (lignes `<nom>_ccw` du tableau §2
> de `BRIDGE_AGENT_DOC.md`), et la valeur du `TOPIC_NTFY` de chacun (dans
> `configs\<nom>-ccw.conf`, pour chaque projet dédié, et dans `configs\
> ccw.conf` pour le canal unifié). Puis copier ces fichiers `*-ccw.conf` et
> `ccw.conf` **hors du disque qui sera effacé** (par exemple sur le
> ThinkPad). Aucun de ces fichiers n'est versionné (voir l'étape 7
> ci-dessous) : sans cette copie, seul le repli de l'étape 7 (recréation via
> `creer_projet_ccw_complet.ps1`) permet de reconstituer les projets, sans
> retrouver le `TOPIC_NTFY` déjà choisi pour chacun. Ne pas recopier le
> contenu de ces fichiers dans cette documentation.

**Voir `REINSTALLATION_WINDOWS.md` (ce dossier)** pour la procédure complète
en amont de cette étape : fabrication de la clé USB bootable (source de
l'ISO, outil recommandé), boot BIOS/UEFI sur ce PC fixe, cas standard vs
réparation en place (limite « conserver les fichiers personnels »
seulement), et désactivation complète et durable de Windows Update au
niveau système (service + stratégie/registre + tâches planifiées) — à ne
pas confondre avec la désactivation faite par `provisionner.ps1` à l'étape
4 ci-dessous, qui n'agit qu'au niveau de son propre provisioning.

**Conséquence de l'expiration de la licence d'évaluation (90 jours).** Une
fois cette échéance dépassée, Windows redémarre toutes les heures, ce qui
casse le service `CCW-Watcher`. L'échéance se suit dans l'annuaire (projet
AnnuaireToken) ; réinstaller avant qu'elle n'arrive.

### 2. Configurer l'accès SSH depuis CCL

Une fois Windows installé et une session ouverte, lancer **en admin** (PowerShell) :

```powershell
.\configurer_ssh_ccw.ps1 -ClePub "<contenu de ~/.ssh/ccl_ccw.pub>"
```

Ce script active/configure OpenSSH Server côté Windows et installe la clé
publique fournie dans `authorized_keys` de l'utilisateur SSH (`AlainW`),
pour permettre à CCL de piloter le PC fixe à distance par clé (sans mot de
passe) — voir `BRIDGE_AGENT_DOC.md` §16.2.

Le contenu à passer en `-ClePub` est celui de `~/.ssh/ccl_ccw.pub` **sur
le ThinkPad** (CCL) — la clé publique correspondant à la clé privée
`~/.ssh/ccl_ccw` mentionnée plus haut, qui elle ne bouge pas.

### 3. Vérifier la connexion SSH depuis CCL

Depuis le ThinkPad :

> **Avant ce premier test.** La réinstallation de Windows (étape 1) fait
> générer une nouvelle clé d'hôte au serveur SSH du PC fixe ; le ThinkPad
> refuse alors la connexion tant qu'il se souvient de l'ancienne. Oublier
> l'ancienne clé avant de tester :
> ```bash
> ssh-keygen -R <ip>
> ```
> (même `<ip>` que celle utilisée ci-dessous.) Ceci vaut aussi bien pour
> Bridge_Agent (onglet **CCW**, démarrage automatique des services) que pour
> `relecture_web` : les deux partagent le même fichier `~/.ssh/known_hosts`
> sur le ThinkPad.
>
> Après ce `ssh-keygen -R`, le test manuel ci-dessous (`ssh -i …`)
> redemandera de confirmer l'empreinte du PC fixe (répondre `yes`) — normal,
> puisque la clé d'hôte est effectivement nouvelle. Bridge_Agent et
> `relecture_web`, eux, n'ont besoin d'aucune connexion manuelle préalable :
> les deux utilisent `StrictHostKeyChecking=accept-new`, qui accepte et
> enregistre seul un hôte encore inconnu dès leur toute première connexion.

```bash
ssh -i ~/.ssh/ccl_ccw AlainW@<ip>
```

(`<ip>` = adresse IP locale du PC fixe.) La connexion doit s'établir sans
demande de mot de passe. En cas d'échec, revérifier l'étape 2 (OpenSSH
Server actif, clé bien copiée dans `authorized_keys`) avant de poursuivre.

**Adresse du PC fixe.** Elle est réservée sur la box pour la carte réseau du
PC fixe : `<ip>` reste donc identique après une réinstallation, tant que la
carte réseau elle-même ne change pas. Si elle change malgré tout, mettre à
jour l'adresse à deux endroits : la configuration SSH de Bridge_Agent
(`configs/ccw_ssh.conf`, clé `HOTE`, ou variable d'environnement
`CCW_SSH_HOTE` — voir `app/ccw.py`) et le fichier personnel `ccw_host.conf`
de `relecture_web` (hors dépôt, projet Relecture_Bridge ; modèle versionné :
`ccw_host.conf.example`).

**Diagnostic d'un échec.** Le message affiché par `ssh` indique la cause :

| Cause                              | Message                        | Cause probable                                             | Vérification |
|-------------------------------------|---------------------------------|--------------------------------------------------------------|---------------|
| clé d'hôte modifiée                | `Host key verification failed` | Clé d'hôte modifiée par la réinstallation                     | Voir l'encadré ci-dessus (`ssh-keygen -R <ip>`) |
| clé refusée                        | `Permission denied (publickey)`| Clé publique absente ou mal copiée dans `authorized_keys`    | Revoir l'étape 2 |
| connexion refusée                  | `Connection refused`           | Le serveur SSH du PC fixe n'écoute pas                        | Vérifier que le service OpenSSH est démarré sur le PC fixe |
| PC éteint ou adresse introuvable   | Délai dépassé (`Connection timed out` ou `No route to host`), ou `Network is unreachable` / `Could not resolve hostname` | Adresse incorrecte, ou PC fixe éteint ou injoignable | Vérifier `<ip>` et le réseau |

Ces quatre libellés de cause (« clé d'hôte modifiée », « clé refusée »,
« connexion refusée », « PC éteint ou adresse introuvable ») sont repris
tels quels par `relecture_web` (projet Relecture_Bridge) : ne pas les
renommer sans prévenir ce projet. Pour une cause qui ne correspond à aucune
de ces quatre lignes, `relecture_web` affiche un message générique suivi de
la première ligne du message d'erreur de SSH.

> **Remarque sur la langue.** Les messages de connexion de SSH restent en
> anglais même dans une session système en français : constaté sur le
> ThinkPad (`fr_FR.UTF-8`) pour le message `Connection refused`, avec ou
> sans `LC_ALL=C` devant la commande. Les libellés du tableau ci-dessus
> reprennent donc le texte anglais tel qu'il s'affiche ; les autres
> messages du tableau n'ont pas été testés sur ce point.

> ⚠️ **Symptôme à connaître.** Quand la clé d'hôte est la cause (premier cas
> ci-dessus), `relecture_web` affiche désormais la cause identifiée (« clé
> d'hôte modifiée ») avec la commande `ssh-keygen -R` à exécuter — le
> message « PC fixe éteint ou injoignable » ne s'affiche plus que pour la
> catégorie « PC éteint ou adresse introuvable », ou en repli pour une cause
> non reconnue. Côté Bridge_Agent, rien ne change : l'onglet **CCW** échoue
> de la même façon, et le démarrage automatique des services à la création
> d'une issue `for-windows` échoue aussi, **sans aucun message**.

### 4. Provisionner le logiciel

Toujours en admin sur le PC fixe (ou via la session SSH ouverte à l'étape
précédente) :

```powershell
.\provisionner.ps1
```

**winget n'est PAS un prérequis** (depuis l'issue #658, réinstallation réelle
du 27/09/2026 menée avec Alain). Sur l'édition Windows 11 IoT Enterprise LTSC
du PC fixe CCW, le bootstrap de winget (App Installer) échoue systématiquement
dès sa toute première étape : le paquet dépend du framework
`Microsoft.VCLibs.140.00` (sans le suffixe `.UWPDesktop`), pour lequel aucune
source de téléchargement autonome fiable n'a été trouvée. `provisionner.ps1`
installe donc désormais Git, GitHub CLI et Python 3.12 par **téléchargement
direct des installeurs officiels de chaque éditeur** (Git : dernier
`git-for-windows/git` GitHub Releases ; GitHub CLI : dernier `.msi` `cli/cli` ;
Python : installeur `python.org`), NSSM par archive `.zip` autonome
(`nssm.cc`), et OpenSSL par un installeur autonome équivalent au paquet winget
précédemment utilisé (Shining Light Productions) — winget reste utilisable
pour OpenSSL en repli optionnel (`-TenterWinget`), mais aucune étape
obligatoire n'en dépend plus. Le script installe aussi PyInstaller (pip) et
Claude Code (installeur natif), désactive Windows Update (décision du
27/09/2026, suite à un plantage `ucrtbase.dll` causé par une mise à jour
cumulative), clone `Bridge_Agent` en lecture seule dans
`C:\CCW\Bridge_Agent`, génère la paire de clés de bootstrap « Projet CCW »
(voir étape 8 ci-dessous), écrit `configs\ccw.conf` (avec un placeholder
`TOPIC_NTFY`) et enregistre le service Windows `CCW-Watcher` via NSSM — avec
son `PATH` complet posé dans `AppEnvironmentExtra` (machine + `.local\bin` du
compte de service + `WindowsApps`), sans quoi le service ne verrait ni
`claude.exe` ni les autres exécutables installés en per-user.

Un mode `-DryRun` (alias `-WhatIf`) affiche toutes les actions prévues sans
rien exécuter — utile pour relire le script avant la prochaine vraie
réinstallation (~tous les 3 mois) : `.\provisionner.ps1 -DryRun`.

Le script demande le mot de passe du compte de service en saisie masquée
(`Read-Host -AsSecureString`) : cela fonctionne aussi bien en session
interactive locale qu'**en session SSH** — contrairement à l'ancienne
implémentation (`Get-Credential`), qui ouvrait une fenêtre graphique
invisible et bloquait le script silencieusement, sans erreur visible, quand
il était lancé depuis SSH (constaté le 27/09/2026).

À la fin de son exécution, le script termine par un résumé complet
(logiciels installés + versions, service créé, `PATH` posé, étapes
manuelles restantes) et un **rappel explicite** : un compte déjà ouvert
avant cette installation ne voit pas le nouveau `PATH` avant reconnexion —
fermer/rouvrir la session (ou, mieux, redémarrer la machine) avant de
considérer le provisioning terminé.

> ⚠️ **Collage de scripts multi-lignes via SSH.** Coller un long bloc
> PowerShell multi-lignes directement dans une session SSH mélange parfois
> l'ordre des lignes (constaté à plusieurs reprises le 27/09/2026). Pour tout
> script de dépannage improvisé pendant une réinstallation, préférer
> l'écrire dans un fichier `.ps1` via `Set-Content` puis l'exécuter avec
> `-File`, plutôt que de coller un bloc multi-lignes directement dans le
> prompt.

### 5. Renseigner le topic ntfy et poser les tokens

Éditer `TOPIC_NTFY` dans `configs\ccw.conf` (remplacer le placeholder par
le topic réel), puis lancer :

```powershell
.\mettre_a_jour_tokens_ccw.ps1
```

Le script demande `GH_TOKEN` puis `CLAUDE_CODE_OAUTH_TOKEN` en saisie
masquée, reconstruit **aussi** la ligne `PATH` (issue #658 — sans elle, le
`nssm set … AppEnvironmentExtra` de ce script écraserait celle posée par
`provisionner.ps1`, privant à nouveau le service de `claude.exe`), applique
les trois lignes au service, et redémarre `CCW-Watcher`.

> **Renouveler un seul jeton (issue #743).** À une saisie interactive comme
> au mode `-FichierTokens` (utilisé par l'onglet **CCW** de l'interface
> web), laisser une valeur vide conserve le jeton ACTUELLEMENT posé sur le
> service (lu via `nssm get <service> AppEnvironmentExtra`, jamais affiché)
> au lieu de l'effacer — au moins un des deux jetons reste requis ; si la
> valeur actuelle du jeton omis est introuvable (service neuf), le script
> abandonne SANS rien modifier et demande les deux jetons. Depuis l'onglet
> CCW, l'action **« Poser ce jeton Claude sur tous les services CCW »**
> applique une seule saisie de `CLAUDE_CODE_OAUTH_TOKEN` à tous les services
> `CCW-Watcher*` listés en une fois, en conservant le `GH_TOKEN` propre à
> chacun (résumé par service ; un service avec une issue en cours est sauté,
> jamais redémarré de force) — voir `ARCHITECTURE.md` §10.
>
> **Particularité nssm — sortie non propre (issue #744).** Un essai réel
> (service CCW-Watcher-Scrabble) a montré que la sortie de `nssm get
> <service> AppEnvironmentExtra` n'est PAS du texte propre dans PowerShell :
> nssm écrit en UTF-16, et la console le redécode parfois comme du texte 8
> bits (le décodage peut différer entre session interactive et lancement à
> distance par SSH) — d'où un caractère NUL après chaque caractère de la
> ligne, et des lignes parasites d'un seul NUL entre variables. Le script
> nettoie désormais TOUS les NUL avant de redécouper en lignes, et refuse de
> reconduire un jeton si sa valeur reste douteuse après nettoyage (vide,
> caractère de contrôle résiduel, variable en double ou absente) — abandon
> sans aucune modification dans ce cas, message clair. Un jeton reconduit
> subit aussi un contrôle de longueur plausible avant écriture, et un
> contrôle de longueur après écriture/redémarrage (relecture, comparaison —
> jamais la valeur elle-même) : tout écart est signalé « à vérifier » dans
> le résumé final. Voir `ARCHITECTURE.md` §10.1.

### 6. Vérifier que le service tourne

Confirmer que `CCW-Watcher` est bien à l'état `running`, soit localement
(`nssm status CCW-Watcher` ou services.msc sur le PC fixe), soit depuis
CCL via l'onglet **CCW** de l'interface web (`new_issue.py`) — voir
`BRIDGE_AGENT_DOC.md` §16.2.

### 7. Recréer les services multi-projets dédiés

Les étapes 1 à 6 ne remettent en place que le service de **base**
`CCW-Watcher` (canal `for-windows` de Bridge_Agent) — celui-ci reste
**toujours actif** (voir encadré ci-dessous), contrairement aux services
dédiés recréés par cette étape 7. En production, un par projet du modèle
multi-projets actif (issue #170, cf. `BRIDGE_AGENT_DOC.md` §16) s'ajoute à
ce service de base — eux aussi recréés à zéro par la réinstallation, puisque
le service NSSM et ses tokens ne survivent pas.

> **Modèle « à la demande » (retrofit #712).** Les services dédiés recréés
> ici par `ajouter_projet_ccw.ps1` (via `creer_projet_ccw_complet.ps1`) ne
> tournent **pas en permanence** : chacun s'éteint seul après 20 min
> d'inactivité (`AppExit 42 Exit`) et est rallumé à la demande par
> `new_issue.py` (formulaire web, `issues_inbox/`, relance) via SSH — détail
> complet dans `BRIDGE_AGENT_DOC.md` §16. Deux cas n'en bénéficient pas :
> une issue `for-windows` créée par `gh issue create` direct (hors
> `new_issue.py`), et `new_issue.py` natif sous Windows (pas d'hôte SSH
> configuré pour se joindre lui-même) — dans ces cas, démarrer le service à
> la main (`nssm start <service>` ou bouton **Démarrer** de l'onglet CCW).
> `CCW-Watcher` (service de base, étapes 1-6) reste lui **toujours actif** —
> aucun réglage à reproduire pour lui. Retour arrière pour un service donné :
> `nssm set <service> AppExit 42 Restart`.

**Attention — ces fichiers ne survivent PAS à une réinstallation propre.**
Les fichiers `.conf` de chaque projet (ex. `configs\alchess-ccw.conf`) ne
sont **pas versionnés** (`.gitignore`) et vivent dans le clone **dédié** du
projet (`C:\CCW\<Projet>\configs\<nom>-ccw.conf`), pas dans celui de
Bridge_Agent. Une réinstallation propre efface `C:\CCW` et refait chaque
clone par `git clone`, qui ne ramène aucun fichier non versionné : sans la
copie faite à l'étape 1 (« Avant de réinstaller »), ils sont donc perdus —
voir le repli plus bas si cette copie est absente ou incomplète. La
recréation du service NSSM et la resaisie des deux tokens (GitHub dédié +
Claude Code) par projet restent de toute façon nécessaires, copie ou pas.

**Autre fichier local non versionné du clone : les exclusions `.git/info/
exclude`.** Chaque clone dédié a aussi un réglage local non versionné, qui
masque `configs/` et `logs/` (fichiers du service CCW) pour éviter que
`relecture_web` (projet Relecture_Bridge) ne signale « modifications non
committées » et ne refuse la fusion sur ce clone. Comme les fichiers
`.conf` ci-dessus, ces lignes ne survivent pas à une réinstallation propre ;
`ajouter_projet_ccw.ps1` (appelé par `creer_projet_ccw_complet.ps1`, donc
par ce script) les recrée après le clonage — rien à faire manuellement de
ce côté.

**Liste non codée en dur (issue #597, suite de #552/#571)** : contrairement
à l'ancienne version de ce script, `reinstaller_projets_ccw.ps1` (ce
dossier) ne maintient plus de tableau `$Projets` figé. Il énumère
DYNAMIQUEMENT, à chaque exécution, les fichiers `configs\*-ccw.conf`
présents sous la racine des clones CCW (`C:\CCW\*\configs\`, et non plus le
seul `configs\` de Bridge_Agent — correction #813, ce dernier ne contenant
que le canal unifié `ccw.conf`) — un fichier par projet dédié, créé par
`ajouter_projet_ccw.ps1` à la création du projet et jamais retiré
automatiquement à sa suppression. Chaque fichier fournit à la
fois le nom du projet (préfixe avant `-ccw.conf`) et son dépôt GitHub (clé
`DEPOT=`). Le canal unifié `for-windows` (`configs\ccw.conf`, sans suffixe
projet) est explicitement exclu de cette énumération — il est déjà couvert
par les étapes 1 à 6 ci-dessus, pas par ce script.

Conséquence pratique : la liste des services dédiés recréés par l'étape 7
reflète toujours fidèlement les fichiers `configs\*-ccw.conf` réellement
présents au moment de la réinstallation — plus de risque de recréer un
projet décommissionné (fichier `.conf` absent → non recréé) ni d'oublier un
projet ajouté hors du flux CREATION standard (fichier `.conf` présent →
recréé). Ce mécanisme remplace le tableau `$Projets` qui faisait foi
jusqu'ici (issue #552) et rend caduque la distinction documentée en #571
avec `regenerer_tableaux_projets.py` (celui-ci régénère §2/§7 de
`BRIDGE_AGENT_DOC.md` depuis les `.conf`, mais dans un sous-ensemble
manuellement choisi — ici, la source de vérité est directement le disque).

Toujours en admin sur le PC fixe, depuis `C:\CCW\Bridge_Agent`, en limitant
la recréation aux projets qui ont aujourd'hui une ligne `<nom>_ccw` dans le
tableau §2 de `BRIDGE_AGENT_DOC.md` (sans le suffixe `_ccw` — à ce jour :
`actualise`, `rummikub`, `scrabble`) :

```powershell
.\provisioning\windows\reinstaller_projets_ccw.ps1 -SeulementProjets actualise,rummikub,scrabble
```

Préciser `-SeulementProjets` évite de recréer le service d'un projet dont
CCW n'a plus besoin aujourd'hui (ex. `alchess`, `Relecture_Bridge`) même si
son fichier `.conf` est présent ou restauré sur le disque : un fichier
`.conf` n'est **jamais retiré automatiquement** à la décommission d'un
projet (voir ci-dessus, « Liste non codée en dur »). Un projet ainsi
écarté peut être recréé plus tard à la demande, avec
`creer_projet_ccw_complet.ps1` (repli ci-dessous).

**Repli — si aucun fichier `*-ccw.conf` n'a été restauré** (copie de
l'étape 1 absente ou incomplète) : `reinstaller_projets_ccw.ps1` ne trouve
alors rien à recréer et se termine en erreur avec un message explicite.
Dans ce cas, appeler `creer_projet_ccw_complet.ps1` directement pour chaque
projet de la liste, avec son dépôt — il recrée le clone, le service **et**
le fichier de configuration :

```powershell
.\creer_projet_ccw_complet.ps1 -NomProjet actualise -Depot AlainDelree/Actualise
.\creer_projet_ccw_complet.ps1 -NomProjet rummikub -Depot AlainDelree/Rummikub
.\creer_projet_ccw_complet.ps1 -NomProjet scrabble -Depot AlainDelree/Scrabble
```

`reinstaller_projets_ccw.ps1` séquence l'appel à `creer_projet_ccw_complet.ps1`
(racine du dépôt, §16.5 de `BRIDGE_AGENT_DOC.md`) pour chacun des projets
détectés — évitant de devoir taper une commande par projet de mémoire (cas
normal, fichiers `.conf` restaurés ; le repli ci-dessus appelle le même
script directement, projet par projet). Les deux tokens
restent demandés **par projet**, à l'intérieur de la boucle : le script
structure la séquence, il ne contourne pas la saisie. En cas d'échec sur un
projet, il s'arrête et affiche comment reprendre uniquement les projets
restants (`-SeulementProjets`).

Vérifier ensuite l'état de tous les services (base + dédiés) via
`provisioning\windows\lister_projets_ccw.ps1`, ou depuis CCL via l'onglet
**CCW** de l'interface web.

### 8. Paire de clés de bootstrap « Projet CCW » (issue #554, 1/3)

`provisionner.ps1` (étape 4 ci-dessus) génère automatiquement, la première
fois, une paire de clés **RSA 3072 bits** destinée au futur chiffrement des
tokens (`GH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`) transmis par la case
« Projet CCW » du formulaire de création de projet (conception #554,
mécanisme complet à suivre en #555/#556 — **pas encore implémenté à ce
stade** : cette étape ne fait que poser la paire de clés elle-même).

- **Clé privée** : `C:\CCW\cles_bootstrap\bootstrap_privee.pem` — ne quitte
  **jamais** le PC fixe. Permissions restreintes par `icacls` (SYSTEM +
  Administrateurs + le compte de service `AlainW` en lecture seule),
  héritage coupé. Ce dossier est volontairement **hors** du clone git
  `C:\CCW\Bridge_Agent` (jamais committé) et hors de `C:\CCW_Share` (point
  de montage réseau accédé depuis CCL, cf. `BRIDGE_AGENT_DOC.md` §16.3 —
  la clé privée n'a rien à y faire).
- **Clé publique** : `C:\CCW\cles_bootstrap\bootstrap_publique.pem` — pas
  sensible, à récupérer côté CCL pour chiffrer les tokens avant inclusion
  dans le corps d'une future issue. Trois façons de la récupérer :
  - **automatique (recommandé, issue #559)** : bouton « 🔄 Rafraîchir la clé
    publique » dans le bloc d'instructions de la case « Projet CCW » du
    formulaire de création de projet (`POST /projet-ccw/rafraichir-cle`,
    `app/projet_ccw.py`) — met à jour le cache local
    `configs/ccw_bootstrap_publique.pem` via la session SSH existante. À
    relancer après CETTE étape de réinstallation (nouvelle paire de clés) ;
  - **copier-coller manuel** : `provisionner.ps1` affiche son contenu PEM
    intégral en toute fin d'exécution ;
  - **via la session SSH existante** (étape 3 ci-dessus, voir aussi
    `BRIDGE_AGENT_DOC.md` §16.2) :
    ```bash
    ssh -i ~/.ssh/ccl_ccw AlainW@<ip> type C:\CCW\cles_bootstrap\bootstrap_publique.pem
    ```

Génération via `openssl.exe`, installé par `provisionner.ps1` (installeur
autonome officiel Shining Light Productions depuis l'issue #658, winget en
repli optionnel) plutôt que `.NET` natif ou `age` — voir le commentaire
détaillé en tête de la section correspondante dans `provisionner.ps1` pour la
justification complète du choix.

> ⚠️ **La clé privée ne survit PAS à une réinstallation.** Comme le reste de
> l'état local du PC fixe, `C:\CCW\cles_bootstrap\` disparaît avec le disque
> effacé à l'étape 1 (réinstallation Windows) ; la paire de clés régénérée
> par l'étape 4 suivante n'a **aucun rapport** avec l'ancienne. Conséquence
> pratique à ne
> pas oublier (cas déjà identifié dans la conception #554) : **toute issue
> de bootstrap chiffrée avec l'ancienne clé publique, encore en attente de
> traitement au moment d'une réinstallation, devient définitivement
> indéchiffrable** — il faudra la ré-émettre depuis le formulaire une fois
> la nouvelle clé publique récupérée côté CCL. Ne pas soumettre une case
> « Projet CCW » juste avant une réinstallation planifiée du PC fixe.

### 9. Repérer et nettoyer les worktrees orphelins

Le nettoyage des worktrees `mode_write` (cf. `WORKTREES.md`) n'est **jamais**
automatique : ni `watcher.py` ni les scripts de réinstallation ne suppriment
un worktree ou sa branche `worktree-issue-<N>`. Après une réinstallation, des
worktrees orphelins peuvent donc traîner sur les clones concernés (tâche
interrompue par la réinstallation, dossier disparu alors que la métadonnée
git subsiste, ou l'inverse). Ce nettoyage reste **manuel**.

> ℹ️ Emplacement des worktrees sous CCW (issue #749) : depuis cette issue,
> les NOUVEAUX worktrees sont créés dans un dossier **dédié**
> `<parent de REP_TRAVAIL>\worktrees\<NOM_PROJET>-issue<N>` (ex.
> `C:\CCW\worktrees\scrabble-issue444` pour un projet dont `REP_TRAVAIL` est
> `C:\CCW\Scrabble`), et non plus directement en répertoire **frère** de
> `REP_TRAVAIL` (`<REP_TRAVAIL>\..\<NOM_PROJET>-issue<N>`, ancien
> comportement). Les worktrees créés AVANT cette issue restent à l'ancien
> emplacement frère — aucune migration automatique — et sont toujours
> trouvés par `git worktree list` ci-dessous, quel que soit leur
> emplacement réel. Voir `WORKTREES.md` (§2, « Emplacement ») pour le
> détail.

> ⚠️ Cette section concerne surtout les clones qui **survivent** à la
> réinstallation (ex. le `REP_TRAVAIL` d'un projet dédié, non touché par
> `provisionner.ps1`). Si le clone est entièrement refait par
> `provisionner.ps1` (`C:\CCW\Bridge_Agent`, disque effacé à l'étape 1),
> `.git/worktrees` repart de zéro avec le nouveau clone : il n'y a alors
> aucun orphelin local à nettoyer de ce côté.

**Repérer** — dans chaque clone concerné (`C:\CCW\Bridge_Agent` et le
`REP_TRAVAIL` de chaque projet dédié recréé à l'étape 7) :

```powershell
git -C <REP_TRAVAIL> worktree list
```

Toute ligne autre que `REP_TRAVAIL` lui-même est un worktree secondaire ; une
mention `prunable` signale un worktree dont le répertoire n'existe plus sur
le disque.

**Nettoyer** — après avoir vérifié que la branche ne contient rien à
récupérer (`git log master..worktree-issue-<N>`) :

```powershell
git -C <REP_TRAVAIL> worktree remove --force <chemin>   # répertoire encore présent
git -C <REP_TRAVAIL> worktree prune                     # entrées "prunable" (répertoire déjà disparu)
git -C <REP_TRAVAIL> branch -d worktree-issue-<N>       # -D si jamais mergée et abandonnée
```

> ⚠️ `--force` et `branch -D` jettent définitivement les modifications non
> commitées ou non mergées : relire `git log`/`git status` du worktree avant.
> Voir aussi `WORKTREES.md` (« Worktree orphelin ») pour le contexte complet.

---

## Prérequis côté Linux (ThinkPad) — `cifs-utils`

Sans rapport direct avec la réinstallation Windows, mais lié à
l'infrastructure CCW et à garder en mémoire au même endroit : le montage du
partage réseau avec l'option `credentials=` (utilisé pour accéder au PC fixe
CCW depuis le ThinkPad) nécessite le paquet **`cifs-utils`** côté Linux.
Sans lui, le montage échoue silencieusement ou avec une erreur peu explicite
sur `credentials=`. À installer une fois sur le ThinkPad si absent :

```bash
sudo apt install cifs-utils
```
