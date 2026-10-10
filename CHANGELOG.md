# CHANGELOG — bridge_agent

Historique complet des évolutions du projet, une section par issue, la
plus récente en premier. Auparavant maintenu comme un unique paragraphe
en pied de page de `BRIDGE_AGENT_DOC.md` ; extrait ici tel quel (issue
#252) car ce paragraphe avait fini par peser plusieurs dizaines de
milliers de caractères sur une seule ligne logique, coûteux à relire et
à réécrire, et sans garde-fou contre une perte silencieuse de contenu.

Convention d'ajout : voir §10 de `BRIDGE_AGENT_DOC.md`.

# CHANGELOG-746 — à fusionner dans CHANGELOG.md

## 10 octobre 2026 — issue #746

Retrait des bandeaux historiques « Éval Windows CCW » (#454) et « OAuth Token CCW » (#456), désormais suivis dans l'annuaire (#741/#742) ; libellé du bandeau de l'annuaire rendu générique.

- **`app/eval_windows.py` supprimé** : son appel dans `app/vues.py::index()` (paramètre `eval_windows`) et son bloc `{% if eval_windows %}` dans `templates/fragments/bandeaux.html` retirés. Le CSS (`.bandeau-eval-windows` et variantes `orange`/`rouge`/`gris`, `static/css/base.css`) est conservé tel quel : le bandeau de l'annuaire le réutilise.
- **Seuils déplacés** : `_niveau()`, `SEUIL_ORANGE` (14j) et `SEUIL_ROUGE` (5j) vivent désormais directement dans `app/jetons_annuaire.py` (plus d'import depuis le module supprimé) — valeurs et comportement strictement inchangés.
- **Libellé générique** : le message du bandeau de l'annuaire passe de « ⚠️ Jeton `<service>` (`<id>`) : ... » à « ⚠️ Échéance `<service>` (`<id>`) : ... », exact aussi bien pour un jeton que pour une échéance qui n'en est pas une (licence Windows). « N j restant(s) », « expire aujourd'hui », « expiré depuis N j », le tri par urgence, le plafond de 3 lignes et la ligne de synthèse (#742) sont inchangés.
- **`provisioning/windows/eval-expiration.json`** : clé `date_expiration_oauth_token` retirée (devenue redondante avec l'annuaire), ainsi que la phrase correspondante de `note`. Toutes les autres clés (`machine`, `windows`, `eval_jours`, `date_installation`, `date_expiration`) inchangées — `verifier_expiration_ccw.py` et la (re)création de la VM continuent de lire ce fichier normalement. Une ancienne copie du fichier qui contiendrait encore cette clé est simplement ignorée (clé surnuméraire sans effet, aucun lecteur ne s'y réfère plus).
- **Tests** : `tests/test_bandeau_jetons_annuaire_741.py` mis à jour (libellé « Échéance », docstring ne citant plus `app.eval_windows`). Nouveau fichier `tests/test_retrait_bandeaux_historiques_746.py` : module supprimé, `app/vues.py` propre, seuils réutilisables depuis `app/jetons_annuaire.py`, libellé générique pour une entrée « licence Windows » comme pour un jeton classique, rendu du gabarit `bandeaux.html` sans l'ancien bandeau (avec et sans bandeau annuaire), `eval-expiration.json` sans la clé retirée toujours lu correctement par `verifier_expiration_ccw.py`, ancienne copie avec la clé surnuméraire ignorée sans effet. Les 58 fichiers de `tests/test_*.py` (`tests/lancer_tous_les_tests.py`) passent.
- **Documentation** : `ARCHITECTURE.md` §9 réécrit (retrait du bandeau historique, libellé générique, seuils déplacés, mise à jour de la date de licence Windows à faire désormais dans l'annuaire lors d'une recréation de VM/machine CCW) et tableau §6.5 (bandeaux) mis à jour. `provisioning/windows/REINSTALLATION_CCW.md` ne cite ni `eval-expiration.json` ni l'échéance du jeton OAuth CCW : rien à y modifier. `BRIDGE_AGENT_DOC.md` non touché (hors périmètre).

**Rappel de déploiement** : après fusion, redémarrer `new_issue.py` (code serveur `app/vues.py`/`app/jetons_annuaire.py` et gabarit `templates/fragments/bandeaux.html` modifiés).

# CHANGELOG-744 — à fusionner dans CHANGELOG.md

## 10 octobre 2026 — issue #744

Suite #743 : lecture fiable de la sortie de `nssm get <service> AppEnvironmentExtra` (caractères NUL UTF-16) pour reconduire un jeton sans l'altérer.

Un essai réel sur le service CCW-Watcher-Scrabble a montré que cette sortie n'est PAS du texte propre dans PowerShell : nssm écrit en UTF-16, mais la console qui l'exécute (le décodage diffère entre session interactive et lancement à distance par SSH) la redécode parfois comme du texte 8 bits — un caractère NUL après CHAQUE caractère de la ligne, plus des lignes parasites d'un seul NUL entre chaque variable (CR et LF UTF-16 découpés séparément). Les anciennes fonctions de lecture (ligne « commence par CLE= ») ne trouvaient rien d'exploitable dans ce cas ; une extraction mal écrite aurait pu reconduire un jeton tronqué/altéré sans message d'erreur évident.

- **`provisioning/windows/mettre_a_jour_tokens_ccw.ps1`** — nouvelles fonctions `ConvertTo-LignesEnvironnementPropres` (retire TOUS les NUL de la sortie brute, puis redécoupe en lignes CR/LF/CRLF, coupe les espaces, ignore les lignes vides) et `Extraire-ValeurEnvironnementPropre` (découpe sur le PREMIER signe égal, refuse — sans modifier le service — si la valeur est vide, contient un caractère de contrôle résiduel, ou si la variable attendue apparaît plusieurs fois ou pas du tout). `Lire-EnvironnementActuelService` les compose. Contrôle de cohérence AVANT écriture : la longueur d'un jeton reconduit est comparée à une borne plausible (20 à 4096 caractères). Contrôle APRÈS écriture et redémarrage : relecture robuste de l'environnement du service, comparaison de la longueur de chaque jeton à ce qui a été écrit ; tout écart est signalé « à vérifier » dans le résumé final (code de sortie 2). Jamais de valeur affichée — seule la longueur peut figurer dans un message.
- **Port Python** (`app/ccw.py::_extraire_valeur_env_service`) — signature inchangée depuis #743, comportement interne renforcé (nettoyage des NUL, rejet des doublons/valeurs vides/caractères de contrôle). Nouvelle fonction pure `_longueur_plausible` (même borne que le script PowerShell), non câblée dans `_resoudre_jetons_renouvellement` (qui reste le port de la RÉSOLUTION des deux jetons côté #743, comportement strictement inchangé — vérifié par la suite de tests #743 existante, toujours verte).
- **Tests** : `tests/test_lecture_robuste_env_nssm_744.py` — échantillon FACTICE reproduisant fidèlement la sortie réelle (texte encodé en UTF-16 petit-boutiste puis redécodé comme texte 8 bits) et vérification que la lecture retrouve exactement les valeurs d'origine ; même test sur une sortie déjà propre ; lignes vides ignorées ; variable absente/en double ; valeur contenant un signe égal ; valeur vide ou caractère de contrôle résiduel refusés ; bornes de `_longueur_plausible` ; aucune valeur de jeton dans les messages d'erreur. `tests/test_ccw_renouveler_un_seul_jeton_743.py` repassé entièrement vert sans modification (comportement #743 strictement inchangé).
- **Documentation** : `ARCHITECTURE.md` §10.1 (nouvelle sous-section) et `provisioning/windows/REINSTALLATION_CCW.md` (encadré étape 5) décrivent la particularité nssm et le correctif.

**À vérifier à la main par Alain sur un premier service réel** (CCL n'a pas de machine Windows) : exécuter `mettre_a_jour_tokens_ccw.ps1` modifié sur un service réel avec un seul jeton fourni (confirmer que le jeton reconduit redémarre le service correctement, que le contrôle de longueur avant écriture ne déclenche pas de faux positif sur un jeton réel, et que le contrôle après redémarrage ne signale pas « à vérifier » à tort) ; si possible, reproduire une fois le cas où `nssm get` renvoie effectivement une sortie avec NUL (ex. via SSH non interactif) pour confirmer en conditions réelles que l'extraction retrouve la bonne valeur.

**Rappel de déploiement** : après fusion, redémarrer `new_issue.py` (`app/ccw.py` modifié) — les scripts Windows (`.ps1`) sont recopiés à chaque usage, aucune action supplémentaire nécessaire pour eux.

# CHANGELOG-743 — à fusionner dans CHANGELOG.md

## 9 octobre 2026 — issue #743

L'onglet CCW permet désormais de renouveler un seul jeton (GH_TOKEN ou CLAUDE_CODE_OAUTH_TOKEN) en conservant l'autre, et d'appliquer le jeton Claude à tous les services CCW-Watcher* en une seule saisie.

- **`app/ccw.py::ccw_finaliser_projet()`** — n'exige plus les DEUX jetons : au moins un est requis. Le fichier de valeurs (0600, supprimé des deux côtés — sécurité inchangée) ne contient désormais que les tokens effectivement fournis ; l'absence d'une clé est le signal, côté PowerShell, qu'il faut reconduire l'ancienne valeur plutôt que l'effacer. Comportement STRICTEMENT inchangé quand les deux jetons sont fournis.
- **`provisioning/windows/mettre_a_jour_tokens_ccw.ps1`** — nouvelle fonction `Lire-EnvironnementActuelService` : lit, pour le jeton omis, sa valeur ACTUELLE sur le service via `nssm get <service> AppEnvironmentExtra` (jamais affichée, jamais écrite sur disque en dehors de la mise à jour du service), et la réinjecte telle quelle dans les trois lignes reconstruites (PATH + GH_TOKEN + CLAUDE_CODE_OAUTH_TOKEN, logique #658 inchangée). Si cette lecture échoue ou que la variable y est absente (service neuf), abandon SANS AUCUNE modification, message clair demandant les deux jetons. `finaliser_projet_ccw_auto.ps1` n'a pas eu besoin d'être modifié (relais simple du même fichier de valeurs).
- **Port Python pur** (`app/ccw.py::_extraire_valeur_env_service`, `_resoudre_jetons_renouvellement`) de cet algorithme PowerShell — même patron que les fonctions SDDL de l'issue #717 — gardé uniquement pour des tests unitaires sans dépendre de Windows/nssm.
- **Nouvelle action « Poser ce jeton Claude sur tous les services CCW »** (`static/js/ccw.js::ccwPoserTokenTousLesServices`, section dédiée de `templates/fragments/onglet_ccw.html`) : une seule saisie du jeton Claude, posée séquentiellement sur chaque service connu en RÉUTILISANT la route `/ccw/finaliser-projet` existante (sans `gh_token` ni `topic`), jamais de nouvelle route dédiée côté serveur. Résumé par service (OK / à vérifier / échec / sauté) affiché après coup ; un échec sur un service n'interrompt pas les suivants.
- **Garde-fou avant redémarrage** : `planifierPoseTokenTous()` (logique pure, `static/js/ccw.js`) réutilise ce que l'interface sait déjà de l'état « en cours » de chaque projet (`resumeProjetMonitoring`, existant depuis #381/#627) — aucun appel réseau supplémentaire. Un service occupé (`enCours > 0`) est sauté et signalé dans le résumé, jamais redémarré de force ; état non déterminable → sauté par défaut, sauf confirmation explicite via une modale listant les projets concernés.
- **Interface** — les champs GH_TOKEN/CLAUDE_CODE_OAUTH_TOKEN de « Finaliser un projet » indiquent désormais « vide = conserver l'actuel » ; aucun jeton saisi n'est réaffiché après soumission (comportement déjà existant, désormais vrai aussi pour le nouveau champ de la pose groupée).
- **Tests** — `tests/test_ccw_renouveler_un_seul_jeton_743.py` (logique Python pure + route `ccw_finaliser_projet` avec SSH substitué) et ajouts à `static/js/tests/ccw.test.js` (`planifierPoseTokenTous`, `resumerResultatsPoseTokenTous`). Doc : `ARCHITECTURE.md` §10 (nouvelle section) et `provisioning/windows/REINSTALLATION_CCW.md` (étape 5) — `BRIDGE_AGENT_DOC.md` non touché.
- **Point non vérifiable depuis ce périmètre (pas de machine Windows accessible à CCL)** — le format réel de sortie de `nssm get <service> AppEnvironmentExtra` (une ligne par variable, hypothèse portée par analogie avec `nssm set` plusieurs arguments séparés) et le redémarrage effectif du service avec la valeur reconduite ; à vérifier par Alain au premier renouvellement à jeton unique sur un service réel (voir checklist dans le rapport de clôture de l'issue).

## 9 octobre 2026 — issue #742

Le bandeau des jetons de l'annuaire (issue #741, `app/jetons_annuaire.py`) trie désormais les jetons en alerte par urgence et plafonne l'affichage à 3 lignes : tri par `jours_restants` croissant (jetons déjà expirés en premier, le plus en retard d'abord), égalité départagée par `id` pour un affichage stable. Au-delà de `MAX_LIGNES_JETONS` (= 3, constante en tête du module) jetons en alerte, les lignes suivantes sont remplacées par une seule ligne de synthèse (« ⚠️ + N autre(s) jeton(s) à renouveler — voir l'annuaire », accord singulier/pluriel selon N) — avec 3 jetons ou moins, aucune ligne de synthèse. Le niveau du bandeau (`rouge`/`orange`) reste calculé sur tous les jetons en alerte avant troncature, jamais seulement sur les lignes visibles. La ligne « N entrée(s) ignorée(s) dans jetons.json » reste distincte : toujours en dernier, hors de ce plafond, logique de niveau inchangée. Aucun changement des règles de lecture, seuils ou robustesse existants ; gabarit (`templates/fragments/bandeaux.html`) et CSS non touchés (la ligne de synthèse est un message de plus dans la liste déjà itérée). Tests ajoutés à `tests/test_bandeau_jetons_annuaire_741.py` : tri en désordre, jetons expirés d'abord, égalité par id, 3/4/20 jetons, niveau rouge même si le jeton critique est masqué, ligne des entrées ignorées toujours en dernier, comportement inchangé à 1 ou 2 jetons. Doc : `ARCHITECTURE.md` §9 mis à jour — `BRIDGE_AGENT_DOC.md` non touché.

## 9 octobre 2026 — issue #741

Nouveau bandeau d'expiration des jetons de l'annuaire (issue #741) : `app/jetons_annuaire.py` lit en lecture seule, jamais n'écrit, le fichier `jetons.json` tenu par le projet séparé annuairetoken (métadonnées de jetons d'accès, jamais de valeur) — chemin par défaut `~/.config/annuairetoken/jetons.json`, surchargeable globalement à Bridge_Agent via la variable d'environnement `BRIDGE_JETONS_CHEMIN` (aucun autre mécanisme de réglage global n'existe, `configs/*.conf` étant par projet et interdit en écriture à CCL/CCW). Réutilise les seuils/niveaux du bandeau « OAuth Token CCW » existant (`app/eval_windows.py`, orange ≤14j, rouge ≤5j) pour les jetons de statut actif proches de l'échéance ; jamais d'alerte pour un statut abandonné/expiré ni pour un jeton sans expiration ; un jeton actif dont la date est dépassée s'affiche au niveau rouge (« expiré depuis N j »). Robustesse : fichier absent → silencieux ; fichier illisible (JSON invalide, clés `version`/`jetons` absentes) → message neutre « jetons.json illisible, bandeau désactivé » (nouveau niveau CSS `gris`), détail en logs ; entrée individuelle invalide (statut inconnu, date mal formée) → ignorée mais comptée (« N entrée(s) ignorée(s) »), jamais silencieuse. Affiché dans `templates/fragments/bandeaux.html`, sous le bandeau éval Windows. Tests : `tests/test_bandeau_jetons_annuaire_741.py` (fichiers `JETON_FACTICE_*` dans des dossiers `/tmp` jetables, sans réseau). Doc : `ARCHITECTURE.md` §9 (nouvelle section) — `BRIDGE_AGENT_DOC.md` non touché (réservé à la rédaction d'issues côté Claude Chat, hors périmètre d'un bandeau d'interface).

# CHANGELOG-740 — à fusionner dans CHANGELOG.md

## 9 octobre 2026 — issue #740

Sous CCL (Linux), les nouveaux worktrees `mode_write` (issue #337) sont désormais créés dans un dossier dédié `~/worktrees` plutôt qu'en répertoire frère du projet — le dossier personnel d'Alain ne se remplit plus de dossiers `<projet>-issue<N>` mélangés aux dossiers de projets.

- **`watcher.py`** — nouvelle variable globale `DOSSIER_WORKTREES_DEDIE` (défaut `~/worktrees`, modifiable sans toucher à `configs/*.conf`, hors de portée des issues). `_chemin_worktree` : sous CCW (Windows, `os.name == "nt"`), **aucun changement** — toujours le répertoire frère de `REP_TRAVAIL`. Sous CCL (Linux), le worktree est placé sous `DOSSIER_WORKTREES_DEDIE` (créé automatiquement au besoin) ; si ce dossier dédié ne peut pas être créé ou n'est pas accessible en écriture, repli automatique sur l'ancien emplacement (frère de `REP_TRAVAIL`), signalé par un `log.warning` explicite dans `logs/watcher-<projet>.log` — aucune issue n'est bloquée par ce repli.
- **`app/interruption.py`** — `_lister_worktrees_actifs` interrogeait jusqu'ici le répertoire PARENT de `REP_TRAVAIL` par nom de dossier pour retrouver les worktrees actifs lors d'une interruption (bouton ⛔). Cette hypothèse (worktree toujours frère du projet) ne tient plus sous CCL depuis ce correctif : la fonction interroge désormais `git worktree list` (via `watcher._lister_worktrees_secondaires`), exact quel que soit l'emplacement réel — y compris pour les worktrees hérités restés à l'ancien emplacement, et sans effet sur CCW.
- **Worktrees déjà existants : aucune migration.** Ils restent à leur ancien emplacement et restent trouvés/réutilisables par une RELANCE (issue #725) : `_trouver_worktree_reutilisable` compare toujours le NOM du dossier via `git worktree list`, jamais son emplacement. Le nettoyage manuel (`git worktree remove` + `git branch -d`) continue de fonctionner à l'identique.
- **Tests** — `tests/test_worktree_parallelisation_337.py` et `tests/test_reprise_worktree_725.py` isolent désormais `watcher.DOSSIER_WORKTREES_DEDIE` vers un dossier temporaire pour toute la durée du fichier (sinon les scénarios auraient créé/utilisé le vrai `~/worktrees` de la machine qui exécute les tests). Quatre nouveaux scénarios dans `test_worktree_parallelisation_337.py` : création sous le dossier dédié, création du dossier s'il manque, repli sur l'ancien emplacement si le dossier dédié est inaccessible (répertoire parent en lecture seule), prise en compte du réglage d'emplacement, et worktree hérité à l'ancien emplacement toujours trouvé par une relance. Nouveau fichier `tests/test_lister_worktrees_actifs_740.py` : `_lister_worktrees_actifs` retrouve un worktree quel que soit son emplacement (dossier dédié ou frère), ignore un simple dossier non enregistré comme worktree, et préserve le filtre par suffixe numérique existant.
- **`WORKTREES.md`** — §2 (« Slots suivants ») documente le nouvel emplacement CCL, le réglage `DOSSIER_WORKTREES_DEDIE`, le repli, et le fait que CCW et les worktrees hérités restent inchangés.
- **Non modifiés, volontairement** — `provisioning/windows/REINSTALLATION_CCW.md` (décrit CCW, qui garde l'ancien emplacement) et `BRIDGE_AGENT_DOC.md` (ne cite jamais l'emplacement des worktrees).
- **Point non vérifiable depuis ce périmètre** — le hook de relecture installé par `Relecture_Bridge` (diffs de commits par projet, dépôt séparé `~/Relecture_Bridge`, hors du périmètre de ce worktree CCL) n'a pas pu être inspecté. Le nom du dossier de chaque worktree (`<projet>-issue<N>`) reste identique à avant cette issue — seul son emplacement change sous CCL — donc tout mécanisme identifiant le projet par ce nom de dossier plutôt que par un chemin parent supposé fixe devrait rester correct ; à confirmer par Alain directement sur ce dépôt.

# CHANGELOG-739 — à fusionner dans CHANGELOG.md

## 9 octobre 2026 — issue #739

`regenerer_tableaux_projets.py` refuse désormais de réécrire les tableaux §2/§7 de `BRIDGE_AGENT_DOC.md` quand aucun `.conf` n'est trouvé, et deux commentaires de code pointant vers un §13 supprimé sont corrigés.

Problème corrigé : deux fois de suite (issues #736 et #737), `regenerer()` a été appelé sur le vrai `BRIDGE_AGENT_DOC.md` depuis un worktree CCL isolé — `configs/` y est gitignoré, donc absent/vide, et aucun projet n'était trouvé. La liste vide était écrite telle quelle dans les deux tableaux, les vidant intégralement. Chaque fois détecté et réparé manuellement ; au second incident, une restauration a en plus fait perdre des modifications en cours.

- **`regenerer_tableaux_projets.py`** — `regenerer()` : si `lire_projets()` ne renvoie aucun projet (dossier de configs absent, vide, ou ne contenant que des `.conf` sans champ NOM valide), la fonction s'arrête AVANT toute lecture/écriture du document : `erreur` porte le message « aucun projet trouvé dans \<dossier\> : régénération annulée, document inchangé. », `modifie` reste `False`. Aucun changement de la logique de génération des tableaux, des marqueurs, ni de la mise à jour de la ligne de date dans le cas normal (au moins un `.conf` valide).
- **`nouveau_projet.py`** — `mettre_a_jour_doc()` renvoie désormais aussi le champ `erreur` (jusqu'ici calculé en interne mais jamais exposé à l'appelant). `creer_projet()` : nouvelle branche `elif doc["erreur"]` qui affiche ce message tel quel dans l'étape « Documentation » (`ok: False`) au lieu du message générique « sections §2/§7 non trouvées — à vérifier » qui aurait été trompeur pour ce cas précis ; le commit/push automatique de la doc (étape 7) n'est plus tenté quand cette erreur est présente (symétrique à `supprimer_projet.py`, qui gérait déjà correctement ce cas via sa propre branche `elif doc["erreur"]`, inchangée ici).
- **`supprimer_projet.py`** — aucun changement de code : son traitement de `doc["erreur"]` affichait déjà le message tel quel sans planter ni committer la doc dans ce cas, et sans faire échouer la suppression globale (le `.conf`/répertoire du projet sont bien retirés malgré l'échec de régénération de la doc).
- **CLI** (`python3 regenerer_tableaux_projets.py`) : rendait déjà un code de sortie non nul quand `resultat["erreur"]` est renseigné (`main()`, inchangé) — comportement vérifié par un test dédié.
- **`watcher.py`** (`_compter_watchers_actifs`) — commentaire corrigé : retrait de la mention « §13 du DOC », section supprimée par le nettoyage de la doc (issue #737). Aucun changement de code.
- **`scripts/mesurer_api.py`** — en-tête corrigé : le renvoi vers `BRIDGE_AGENT_DOC.md §13` (déjà inexact avant le nettoyage — ni PID ni mesure API n'y figuraient) est remplacé par un renvoi vers `echantillon()`/les options CLI du script lui-même, où la méthode est réellement décrite, et vers le rapport de clôture de l'issue #263 pour les résultats.

**Tests** : nouveau `tests/test_garde_fou_aucun_conf_739.py` (5 scénarios, dossiers jetables sous `/tmp`, jamais sur le vrai `configs/`/`BRIDGE_AGENT_DOC.md` du dépôt) — dossier de configs absent, vide, ou avec un `.conf` sans champ NOM valide (ex. `ccw_ssh.conf`) : document identique octet pour octet, `erreur` renvoyée ; avec un `.conf` valide : comportement inchangé (régénération normale, `erreur` à `None`) ; CLI (`main()`, `regenerer()` stubbée) : code de sortie non nul dans le cas vide. Vérification en conditions réelles dans ce worktree (où `configs/` est effectivement absent) : `python3 regenerer_tableaux_projets.py` affiche l'erreur, rend le code 1, et le md5sum de `BRIDGE_AGENT_DOC.md` est identique avant/après. Suite complète (`tests/lancer_tous_les_tests.py`, 53 fichiers) rejouée sans régression.

**Documentation** : `ARCHITECTURE.md` §8 complété (nouveau paragraphe « Garde-fou "aucun .conf trouvé" »). `BRIDGE_AGENT_DOC.md` non touché (hors périmètre de l'issue).

**À faire après fusion** : aucun redémarrage obligatoire (le changement de `watcher.py` ne touche qu'un commentaire). Redémarrer `new_issue.py` seulement pour bénéficier de la nouvelle version de `nouveau_projet.py`/`regenerer_tableaux_projets.py`.

# CHANGELOG-738 — à fusionner dans CHANGELOG.md

## 9 octobre 2026 — issue #738

Création de projet : les valeurs par défaut proposées pour le dépôt GitHub et le répertoire de travail respectent désormais la casse saisie dans le nom du projet, et un avertissement non bloquant signale un dossier homonyme à casse différente.

Problème corrigé : saisir un nom avec des majuscules internes (`AnnuaireToken`) donnait jusqu'ici `AlainDelree/Annuairetoken` et `/home/alain/Annuairetoken` — deux causes cumulées, la casse saisie était perdue avant même le calcul des défauts (mise en minuscules dans `creer_projet`, l'assistant CLI, la route `verifier_nouveau_projet`, et côté JavaScript), puis `depot_defaut`/`rep_defaut` forçaient de toute façon tout le nom à `.capitalize()`. Le 06/10/2026, une création avec `~/AnnuaireToken` puis une seconde avec le chemin par défaut avaient ainsi produit deux dossiers distincts (Linux distingue la casse) et une doc (§2/§7) pointant vers le mauvais chemin — corrigé à la main par le commit `e823051` (hors scope de cette issue).

- **`nouveau_projet.py`** — nouvelle fonction `casse_proposee(nom_saisi)` : un nom contenant au moins une majuscule interne est repris tel quel (`AnnuaireToken`, `ChessCoach`) ; un nom tout en minuscules garde le comportement historique (première lettre capitalisée : `rummikub` → `Rummikub`, `bloc_score` → `Bloc_score`). `depot_defaut()`/`rep_defaut()` l'utilisent désormais, et reçoivent le nom **tel que saisi** plutôt que sa version mise en minuscules. `creer_projet()` conserve une variable `nom_saisi` avant le `.lower()` qui produit la clé interne (toujours en minuscules, comportement inchangé), et s'en sert pour ses propres défauts. L'assistant CLI (`etape_nom`, `etape_depot`, `etape_repertoire`) propage de même `nom_saisi` en plus de `nom`.
- **Avertissement non bloquant** — nouvelle fonction `rep_casse_differente(rep)` : si le répertoire proposé n'existe pas encore mais qu'un dossier de même nom à casse différente existe déjà dans le même dossier parent, renvoie son chemin (None sinon — répertoire déjà existant, aucun homonyme, ou homonyme de même casse). L'assistant CLI l'affiche à l'étape 3 ; la route `/nouveau-projet/verifier` (`app/nouveau_projet.py`) l'expose dans le champ JSON `rep_casse_differente`.
- **`app/nouveau_projet.py`** — `verifier_nouveau_projet()` ne met plus le nom en minuscules avant de calculer les défauts (seule la clé `nom` renvoyée, utilisée pour `configs/<nom>.conf`, reste en minuscules) ; ajoute `rep_casse_differente` à la réponse.
- **`static/js/app.js`** — `npVerifier()` transmettait jusqu'ici le nom en minuscules au serveur (`.toLowerCase()` avant l'appel réseau) : c'était la cause racine n°2, elle perdait la casse avant même que le serveur ne la voie. Transmet désormais le nom tel que tapé ; les messages portant sur la clé interne (ex. `configs/<nom>.conf existe déjà`) utilisent `r.nom` (renvoyé par le serveur, en minuscules) plutôt qu'une variable locale. Affiche l'avertissement `rep_casse_differente` sous le champ répertoire (nouveau `<span id="np-rep-msg">` dans `templates/fragments/modale_nouveau_projet.html`).
- **Inchangé** : validation du format de nom (minuscules/chiffres/underscore côté clé interne), création du dépôt GitHub, labels, mise à jour de la doc, et tout `configs/*.conf` existant.

**Tests** : `tests/test_casse_defauts_nouveau_projet_738.py` (12 scénarios) — `casse_proposee`/`depot_defaut`/`rep_defaut` sur nom à majuscule interne et nom tout minuscule ; `rep_casse_differente` dans ses quatre cas (homonyme à casse différente, aucun homonyme, répertoire déjà existant, homonyme de même casse) ; `creer_projet` conservant un NOM interne en minuscules tout en respectant la casse saisie pour dépôt/répertoire ; route `verifier_nouveau_projet` renvoyant les défauts depuis le nom tel que saisi, avec et sans avertissement. Suite complète (`pytest tests/`, 239 tests) rejouée sans régression.

**Documentation** : `ARCHITECTURE.md` §8 complété (nouveau paragraphe « Casse des valeurs par défaut dépôt/répertoire »). `BRIDGE_AGENT_DOC.md` non touché (réservé à ce dont Claude Chat a besoin pour rédiger des issues).

**À faire après fusion** (rappel de l'issue) : redémarrer `new_issue.py` (`app/nouveau_projet.py` et `nouveau_projet.py` modifiés), puis Ctrl+Maj+R côté navigateur (`static/js/app.js` et `templates/fragments/modale_nouveau_projet.html` modifiés).

# CHANGELOG-737 — à fusionner dans CHANGELOG.md

## 9 octobre 2026 — issue #737 (finitions)

Nettoyage de finition de `BRIDGE_AGENT_DOC.md` après relecture de la version publiée (743 → 635 lignes) : une contradiction, des restes et des condensations, sans renumérotation de section ni modification de code.

- **§16 vs §3.4 (contradiction)** — §16 restreignait le service CCW central (`REDACTEUR=bridge_agent`) aux projets « sans service dédié » ; §3.4 autorise correctement cette voie pour n'importe quel projet, y compris avec service dédié, à réserver à un besoin exceptionnel. §16 aligné sur §3.4 (restriction supprimée, renvoi conservé).
- **§6 (Champs spéciaux)** — retrait du paragraphe final sur les valeurs `TYPE=spec_*`, retirées du code par l'issue #734.
- **TIMEOUT par défaut (§3.3/§6/§19)** — vérifié dans `watcher.py` (`extraire_timeout`/`Config.timeout_claude`) : le défaut réel est celui du projet (`TIMEOUT_CLAUDE` du `.conf`), lui-même 300 s si absent du `.conf` — pas un flat 300 s comme l'affirmaient §6/§19. Les trois endroits réécrits à l'identique : « défaut du projet (`TIMEOUT_CLAUDE` du `.conf`, 300 s si non précisé) ».
- **§10 (CHANGELOG.md)** — règle périmée (« toute issue ajoute son entrée en tête de CHANGELOG.md ») et historique #237-#268 retirés ; remplacés par la description du mécanisme actuel (`CHANGELOG-<N>.md` par worktree, fusionné par `scripts/fusionner_changelog.py`) et la seule règle à conserver : maintenir la toute dernière ligne « Dernière mise à jour » au format attendu par `regenerer_tableaux_projets.py`.
- **§12 (exception configs/*.conf)** — condensé à 7 lignes : Alain seul modifie `configs/*.conf` ; CCL/CCW ne le font jamais, même si l'issue le demande ; garde-fou technique de `watcher.py` annule automatiquement. Historique (#298, #318), noms de fonctions internes et détail du mécanisme retirés — déjà dans `ARCHITECTURE.md` §2.6.
- **§13 (Commandes utiles)** — section supprimée en totalité : gestion de projet CLI déjà dans `ARCHITECTURE.md` §8, parallélisation `mode_write` déjà dans `WORKTREES.md`. Phrase sur la reprise de worktree par `RELANCE` ajoutée au §11 (absente jusqu'ici).
- **§14 (Chef → Ouvrier)** — réduit de ~86 à ~43 lignes : conservé le principe, le critère de décision + contre-exemple pour ne pas passer par un chef, le format des titres, le TIMEOUT généreux pour un chef, une phrase sur le rallumage des watchers `for-windows`. Retiré : note « injection automatique » et son historique (#209/#243/#241/#242), rappel détaillé de la contrainte d'exécution synchrone (déjà injectée par `consignes/globales.md`, renvoi conservé), exemple avec commande `gh issue create` complète.
- **§1** — note « Rafraîchissement automatique (issue #185) » réduite à une phrase.

Contrôles effectués : aucun renvoi `§N` cassé (vérifié par grep, toutes les sections référencées existent) ; tableaux §2/§7 et pied de page « Dernière mise à jour » non touchés ; suite de tests complète (`pytest tests/` — 227 tests) et scripts `test_*.py` autonomes tous verts ; `regenerer_tableaux_projets.regenerer()` testé sur une copie isolée (jamais sur le vrai dépôt).

Point d'attention signalé mais non traité (hors périmètre « aucune modification de code ») : deux commentaires de code pointent vers `BRIDGE_AGENT_DOC.md §13` (`watcher.py::_compter_watchers_actifs`, `scripts/mesurer_api.py`), section désormais supprimée — ces renvois étaient déjà incohérents avec le contenu de l'ancien §13 avant ce nettoyage (ni PID ni mesure API n'y figuraient), donc pas une régression introduite ici, mais à corriger dans une issue dédiée si jugé utile.

# CHANGELOG-736 — à fusionner dans CHANGELOG.md

## 8 octobre 2026 — issue #736 (3/3)

Nettoyage de `BRIDGE_AGENT_DOC.md`, §14 à §20 et bloc final : réécriture pour ne garder que ce dont Claude Chat a besoin pour rédiger une issue ou un fichier de dépôt (audit #731, suite des issues #733 1/3 et #735 2/3). Retrait de l'interface, du fonctionnement interne, des procédures d'exploitation et de l'historique d'issues passées ; aucune modification de code.

- **§14** (Délégation Chef → Ouvrier) — conservé sans changement de fond après vérification par rapport au code : le champ `| TYPE | chef |`/`| TYPE | ouvrier |` est bien reconnu par `deduire_type_issue()` (prioritaire sur le préfixe du titre), et déjà documenté au §6 avec renvoi vers cette section.
- **§16** (Agent Windows CCW, ~915 lignes) — réduit à un résumé d'une trentaine de lignes : ce qu'est CCW, qu'il ne pousse jamais, les champs d'en-tête utiles à une issue `for-windows` (`SOUS_DOSSIER`, `REPO_CIBLE`, `CREATION`), la possibilité d'utiliser le service CCW central (`REDACTEUR=bridge_agent`) pour un besoin exceptionnel sur n'importe quel projet (renvoi vers §3.4, qui la documente déjà en détail), la règle de build par copie locale avant partage, et le comportement du bouton d'interruption (arrête le service, nettoie le verrou, mais ne ferme jamais l'issue). Retiré : provisioning PowerShell, modèle de build historique, services NSSM et leurs droits (`sc.exe sdset`), renouvellement des jetons, onglet CCW, procédure d'interruption manuelle, création de projet CCW en CLI, bootstrap détaillé par le champ `CREATION`. Vérifié que le provisioning détaillé existe déjà dans `BUILD_WINDOWS_CCW.md` et `provisioning/windows/REINSTALLATION_CCW.md` : rien à y reporter, tout y est déjà.
- **§17** (Notifications centralisées, ~600 lignes) — supprimé en totalité (mécanisme interne : bip, bulle, ntfy, SSE, caches, badges d'interface). Rien reporté vers `ARCHITECTURE.md` : les conventions SSE générales y sont déjà couvertes (§2.4), et ce mécanisme précis n'apporte rien à la rédaction d'une issue.
- **§18** (Pièces jointes image) — condensé à 5 lignes : les images sont ajoutées par Alain depuis le formulaire web, Claude Chat n'en produit jamais. Toute la plomberie git (branche orpheline, hash-object, exceptions de push) retirée.
- **§19** (Calibration automatique du TIMEOUT) — réduit à une quinzaine de lignes utiles pour choisir un `TIMEOUT` : toujours en fixer un (défaut 300s), `TIMEOUT_suggéré` borné par un plafond de 3600s (issue #590) et à traiter comme une indication et non une règle, comportement de `RELANCE` sur une ligne `TIMEOUT` absente à l'origine, renvoi vers §6 pour `COMPLEXITE`/`RESEAU`. Algorithme, constantes, fichiers d'état et historique d'implémentation retirés. Chiffres mis à jour sur ceux du code (la table §19.4 retirée était déjà périmée) : `K_VARIABILITE` = 3 (issue #475, pas 4), plafond 3600s (issue #590, absent de l'ancienne table).
- **§20** (Formulaire web `new_issue.py`) — supprimé. L'avertissement « Claude Chat ne doit jamais produire de texte à coller dans le formulaire » était déjà présent en double aux §11 et §12 (renvois vers §20 corrigés) : rien à fusionner. Doublon de la liste des champs d'en-tête et fragment d'exemple de fichier retirés (l'exemple canonique reste au §3). La convention de titre `Suite #N : ` pour une issue de suivi, trouvée nulle part ailleurs, a été repliée dans la ligne `SUITE_DE` du tableau §6 plutôt que simplement perdue. La note « PROJET reste toujours bridge_agent pour les issues for-windows » n'a pas été reportée : elle décrivait l'ancien canal unifié mono-projet et contredit la règle actuelle, correcte, du §3.4 (REDACTEUR=PROJET, sauf exception REDACTEUR=bridge_agent).
- **Bloc final non numéroté** — journal d'incidents passés (issues #629, #584, #337) retiré après vérification que `CHANGELOG.md` contient les trois entrées correspondantes (sections dédiées, dates du 25/09, 22/09 et 02/08/2026). Ligne `*Dernière mise à jour : ...*` conservée (texte raccourci, mais toujours en tête de ligne pour `regenerer_tableaux_projets.py::_bump_date`) ; ligne finale « Historique complet : voir CHANGELOG.md » inchangée.

**Taille** : 2784 → 743 lignes (sections 14-20 + bloc final : ~2115 → ~75 lignes, soit environ -2040 lignes).

**Corrections de renvois** (conséquence directe des retraits ci-dessus) : tous les `(§20)`/`(voir §20...)` des §3.1, §6, §11, §12, §14 reformulés sans pointer vers une section supprimée ; `(§16.2)` du §14 généralisé en `(§16)`, §16 n'ayant plus de sous-sections numérotées.

**Tableaux §2/§7 et pied de page** : intégralement préservés (vérifiés caractère pour caractère identiques à la version précédente) — `regenerer_tableaux_projets.py` relu et rejoué (dry-run sur une copie, puis `_bump_date` testé directement sur le fichier réel) sans erreur de marqueur.

# CHANGELOG-735 — à fusionner dans CHANGELOG.md

## 8 octobre 2026 — issue #735 (2/3)

Nettoyage de `BRIDGE_AGENT_DOC.md`, §10 à §13 : réécriture pour ne garder que ce dont Claude Chat a besoin pour rédiger une issue ou un fichier de dépôt (audit #731, suite de l'issue #733 1/3). Retrait de l'interface, du fonctionnement interne, des procédures d'exploitation et de l'historique d'issues passées ; aucune modification de code.

- **§10** — arborescence du dépôt (périmée, omettait déjà `scripts/` et une grande partie de `app/`) remplacée par un renvoi d'une ligne vers `ARCHITECTURE.md` ; convention `CHANGELOG.md`/pied de page inchangée.
- **§11** — détail du hexdump BOM PowerShell condensé à l'essentiel (règle + raison + exception `autounattend.xml`) ; bullet « Parallélisation mode_write » conservé (recommandation de scope pour Claude Chat) mais le workflow de fusion détaillé d'Alain (déjà entièrement dans `WORKTREES.md`) supprimé au profit d'un renvoi.
- **§12** — paragraphe « Workflow » réaligné sur le flux réel : dépôt `.txt` dans `issues_inbox/` comme méthode normale, formulaire web en secours seulement, Claude Chat ne produit jamais de texte à coller. Mécanique détaillée des actions légitimes d'Alain sur `configs/*.conf` (issue #724) condensée : seule la règle « ne jamais modifier » (déjà énoncée juste au-dessus) reste dans ce document, le mécanisme technique déplacé vers `ARCHITECTURE.md` (absent jusqu'ici). §12.1 condensé au tableau des trois couches de consignes et à l'instruction de consulter `consignes/globales.md` via `curl` ; retrait de l'historique (#209/#211) et du détail d'emplacement/ordre interne dans le prompt.
- **§13** (le plus gros bloc, ~1100 lignes) — retrait quasi complet, contenu d'exploitation/maintenance : bloc de commandes shell (lancer l'interface, mot de passe, watcher manuel) et mesure du quota API GraphQL ; état serveur des cases cochées (backend #629 + interface #636) ; journal des messages éphémères/toasts (#730) et couleur d'accent des projets (#120 et suite), tous deux de l'interface ; cycle de vie des watchers (démarrage/extinction/systemd --user) ; boutons « Interrompre une issue bloquée » et « Relancer en needs-human » ; nettoyage de l'arbre de process (ctypes, Job Objects Windows, diagnostic « CCL ne démarre pas »). Conservé et condensé : commandes de création/suppression de projet (`nouveau_projet.py`/`supprimer_projet.py`), avec correction du texte qui affirmait à tort que la mise à jour de `BRIDGE_AGENT_DOC.md` après création/suppression de projet n'était « jamais poussée » — elle est commitée ET poussée automatiquement depuis l'issue #645 ; détail de l'orchestration déplacé vers `ARCHITECTURE.md` (absent jusqu'ici). Parallélisation mode_write par worktrees condensée à 3 lignes (worktree isolé, fusion manuelle par Alain, réutilisation sur RELANCE, séquentiel pour lecture) avec renvoi vers `WORKTREES.md`.

**Taille** : 4092 → 2784 lignes (sections 10-13 : ~1500 → ~190 lignes, soit environ -1310 lignes).

**Déplacements vers `ARCHITECTURE.md`** (information absente là-bas, reportée de façon concise) :
- nouvelle §2.6 : garde-fou `configs/*.conf` et actions légitimes d'Alain (issue #724) ;
- nouvelle §8 : orchestration `creer_projet()`/`supprimer_projet()`, avec la correction du commit/push automatique de la doc (#645).

Tout le reste du contenu retiré décrit de l'interface, du fonctionnement interne ou des procédures d'exploitation déjà entièrement couvertes par `WORKTREES.md` (parallélisation worktrees) ou sans destination identifiée qui en avait besoin — simplement supprimé.

**Renvois corrigés** (pointaient vers des sous-sections de §13 retirées) : §14 (rallumage automatique du watcher, reformulé sans numéro de section), §16 (service NSSM vs supervision systemd, reformulé), §16.4 (pendant CCL du bouton Interrompre, reformulé sans renvoi), §18.2 (push initial de `nouveau_projet.py`, renvoie désormais vers `ARCHITECTURE.md`).

**Doute signalé** : aucun — les renvois `§3.5`/`§3.8`/`§3.10`/`§3.11`/`§3.12`/`§3.15` laissés en suspens par l'issue #733 (1/3) sont tous situés en §16/§17/§20, hors périmètre de cette issue 2/3 ; à traiter par l'issue 3/3 ou une passe dédiée.

**Suite de tests** : `python3 -m pytest tests/ -q` → 227 passed ; `node --test static/js/tests/ static/js/socle/tests/` → 269 passed. Aucun test ne dépend du texte retiré. `regenerer_tableaux_projets.py` non relancé réellement dans ce worktree (pas de `configs/`, écraserait les tableaux comme noté dans le CHANGELOG de l'issue #733) — ancres `DEBUT:TABLEAU_PROJETS_ACTIFS`/`DEBUT:TABLEAU_PERIMETRE_PROJETS` et tableaux des §2/§7 vérifiés inchangés (non touchés par cette issue), et couverts par les tests pytest existants qui l'exercent via monkeypatch (`test_commit_doc_projet_645.py`, `test_supprimer_projet_587.py`, `test_topic_ntfy_facultatif_667.py`).

Après fusion : rien à relancer (doc seule).

# CHANGELOG-733 — à fusionner dans CHANGELOG.md

## 8 octobre 2026 — issue #733 (1/3)

Nettoyage de `BRIDGE_AGENT_DOC.md`, §1 à §9 : réécriture pour ne garder que ce dont Claude Chat a besoin pour rédiger une issue ou un fichier de dépôt (audit #731). Retrait de l'interface, du fonctionnement interne, des procédures d'exploitation et de l'historique d'issues passées ; aucune modification de code.

- **§1** — détail du `git pull --ff-only` condensé à quelques lignes ; ajout du choix CCL (`for-linux`)/CCW (`for-windows`) et du rôle de chacun, absent jusqu'ici de cette section.
- **§2** — tableau inchangé (ancre `regenerer_tableaux_projets.py`) ; retrait de la description de la colonne couleur (pastilles/badges, interface).
- **§3** — retrait de la journalisation interne (3.5), de la config optionnelle du watcher (3.7), du suivi dans l'onglet Résultats (3.8), du pilotage/cycle de vie depuis le panneau Infrastructure et `new_issue.py` (3.10 à 3.12), des événements SSE (3.15), et des mécaniques d'interface de `RELANCE`/`ATTENTE` (décoche de case, bouton, pastilles, routes, références à des fichiers de tests). Conservé et condensé : format du fichier (exemple canonique ajouté : `#Titre:`, en-tête, `## Contexte`/`## Tâche demandée`/`## Résultat attendu`), tableau des champs d'en-tête (une phrase par champ), `ATTENTE`, `RELANCE` (avec le modèle de texte libre recommandé), le dépôt de plusieurs blocs. Règle `REDACTEUR` (§3.4) reformulée en quelques phrases : cas normal `REDACTEUR == PROJET` y compris pour les projets à service CCW dédié (Scrabble, Rummikub, Actualise) ; possibilité supplémentaire, valable pour n'importe quel projet, `REDACTEUR=bridge_agent` + label `for-windows` pour le canal CCW central (réserver `SOUS_DOSSIER`), à réserver à un besoin exceptionnel — l'ancienne condition « seulement si pas de service dédié » abandonnée (jamais appliquée par le code, vérifié dans `valider_redacteur()`).
- **§4** — liste des labels corrigée d'après `nouveau_projet.py::LABELS` : ajout de `for-windows` (absent de la doc) ; précision que `mode_scratch` n'est pas provisionné automatiquement.
- **§5** — retrait de la liste détaillée des outils autorisés en lecture, de la note `cwd_effectif` et de l'incident Scrabble ; défense en profondeur de `mode_scratch` condensée à quelques phrases ; conservé le rappel clair du choix de mode pour exécuter un script (issue #722).
- **§6** — `MODELE` : exemple `claude-opus-4-5` (inexistant) remplacé par `claude-opus-4-8` partout, valeurs reconnues listées d'après `app/projets.py::MODELES_VALIDES` ; retrait de la mention d'une détection côté `new_issue.py` pour `MODE` ; `TYPE` précise que les valeurs `spec_*` ne sont pas documentées (traitées à part par Alain) ; renvoi à la règle `REDACTEUR` du §3.4.
- **§7** — tableau inchangé (même ancre) ; texte d'intro conservé tel quel (déjà concis).
- **§8** — condensé à une phrase : seul un auteur autorisé peut faire traiter une issue, quel que soit le label ; retrait de la mécanique du mot de passe et du gitignore.
- **§9** — retrait du tunnel Cloudflare et du mode `--lan` ; conservé uniquement l'accès à la doc par `curl` avec `?nocache=$(date +%s)`.

**Taille** : 4972 → 4092 lignes (sections 1-9 : 1271 → 391 lignes, soit -880 lignes).

**Déplacements** : aucun — tout le contenu retiré décrit de l'interface, du fonctionnement interne ou des procédures d'exploitation déjà hors du périmètre « ce dont Claude Chat a besoin », donc simplement supprimé (pas de destination identifiée qui en avait besoin).

**Doute signalé** : des renvois `§3.5`/`§3.8`/`§3.10`/`§3.11`/`§3.12`/`§3.15` subsistent plus loin dans le fichier (§16, §17, §20 — hors périmètre de cette issue 1/3) et pointent désormais vers des sous-sections retirées ; à corriger lors du nettoyage de ces sections (issues 2/3 ou 3/3 de la série, ou une passe dédiée).

**Suite de tests** : `python3 -m pytest tests/ -q` → 227 passed ; `node --test` (`static/js/tests/` + `static/js/socle/tests/`) → 269 passed. Aucun test ne dépend du texte retiré (les tests citant `BRIDGE_AGENT_DOC.md` par chemin utilisent des fichiers synthétiques, jamais le vrai fichier). `regenerer_tableaux_projets.py` testé manuellement : ses ancres et tableaux sont inchangés (⚠️ ce script écrase le contenu des tableaux si `configs/*.conf` est absent — sans effet ici car ce worktree n'a pas de `configs/`, mais à ne jamais relancer dans ce worktree sans l'avoir restauré, voir le commit de fix).

Après fusion : rien à relancer (doc seule).

# CHANGELOG-734 — à fusionner dans CHANGELOG.md

## 8 octobre 2026 — issue #734

Retrait du code mort des trois valeurs de TYPE `spec_vue`/`spec_metier`/`spec_persistance`, héritées de l'ancien pattern « Chef + Specs MVC » abandonné (doc retirée par #207) — relevées comme code mort par l'audit de la doc #731 : plus aucune consigne `type_spec_*.md`, plus aucune mention dans `BRIDGE_AGENT_DOC.md`, aucun test ne les citait.

- **`watcher.py`** : `TYPES_ISSUE` réduit à `("chef", "ouvrier", "normal")` ; `_classer_valeur_type` perd ses trois branches persistance/métier/vue (et la tolérance aux variantes « vue »/« métier »/« persistance ») ; docstrings de `_classer_valeur_type` et `deduire_type_issue` nettoyées des mentions spec_*. Comportement inchangé pour chef/ouvrier/normal (champ TYPE et préfixe de titre). Un champ TYPE spec_vue/spec_metier/spec_persistance (ou vue/métier/persistance) retombe désormais sur « normal », comme toute valeur inconnue.
- **Historique des durées** (`logs/historique_durees.json`, `logs/etat_timeout.json`) : aucune migration ni réécriture des entrées spec_* existantes — elles restent présentes mais deviennent orphelines (plus aucun type_issue produit ne les cible), sans erreur de lecture (clé de combinaison en simple chaîne, filtrage par égalité stricte dans `app/issues.py::estimer_duree`).
- **`app/issues.py`** : aucun changement — importe `deduire_type_issue` comme une fonction de classification opaque, ne dépend d'aucune des valeurs retirées.
- Tests (`tests/test_retrait_types_spec_mvc_734.py`, 5 scénarios) : TYPE spec_* (et variantes vue/métier/persistance) → normal ; spec_* absents de `TYPES_ISSUE` ; chef/ouvrier toujours reconnus par champ TYPE et par préfixe de titre ; un historique contenant d'anciennes entrées spec_* se filtre sans erreur via `estimer_duree`. Suite rejouée sans régression sur les tests liés (`test_backoff_ancrage_duree_typique_590.py`, `test_ordre_titre_entete_512.py`).
- Doc : aucune modification — `BRIDGE_AGENT_DOC.md` ne mentionnait déjà plus ces valeurs (vérifié, rien à retirer).

Après fusion : relancer les watchers de projet (`watcher.py` modifié), de préférence quand aucune issue en écriture ne tourne, ET redémarrer `new_issue.py` (il importe `watcher.py`).

# CHANGELOG-732 — à fusionner dans CHANGELOG.md

## 8 octobre 2026 — issue #732

Alerte explicite quand GitHub est en panne : lors d'un échec de `gh` classé « panne probable » (timeout, erreur réseau, réponse 5xx — jamais une erreur normale 404/401/403/422 ni la limite de débit déjà signalée par le bandeau ⚡), interroge `summary.json` de githubstatus.com (sans authentification) et affiche un message clair en français — plutôt que de laisser l'utilisateur deviner la cause (constat des pannes des 06-07/10/2026).

- **`app/github_status.py`** (nouveau) : `classer_echec_gh(message)` (pure, fondée sur le message d'erreur déjà construit par chaque appelant) ; `verifier_statut()` avec cache serveur ~60s (`SEUIL_CACHE_S`, délai réseau court `TIMEOUT_REQUETE_S`=5s, ne lève jamais) ; trois messages de repli par gravité (incident signalé / GitHub opérationnel malgré l'erreur / GitHub et sa page de statut injoignables) ; suivi d'épisode de panne (`signaler_resultat_gh`, persisté dans `logs/etat_panne_github.json`) ouvert au premier échec « panne probable », refermé au premier succès gh ; route `GET /github-statut`.
- **Points d'appel branchés** (aucun point central existant trouvé) : listes d'issues (`_lister_issues_labels`), détail (`issue_detail`), création (`creer_issue_gh`), relance (`app/interruption.py::relancer_issue`), labels (`modifier_label_notif`) — chaque réponse JSON d'échec porte désormais `panne_probable`. Classification INLINE (aucun appel réseau dans le chemin de la requête en échec) — la vérification réseau elle-même n'a lieu que côté `/github-statut`, appelée séparément par le JS.
- **`static/js/socle/panne_github.js`** (nouveau) : `signalerEchecPossible(reponseJson)` — ne déclenche rien sans `panne_probable:true` ; sinon interroge `/github-statut` et affiche un toast (`erreur` pour incident/injoignable, `avertissement` pour cause locale), répété toutes les 60s tant que l'incident dure, puis « GitHub est rétabli. » une fois au retour à la normale. Branché à `resultats.js` (liste), `app.js` (détail, relance — via `window.Bridge.panneGithub`), `creation.js` (création, mono-issue et lot), `panneau_lateral.js` (labels).
- **Journal des pannes** — `logs/pannes_github.log` (non versionné, taille bornée à `RETENTION_JOURS`≈1 an, purgé à chaque écriture) : une ligne PAR ÉPISODE (jamais par erreur), champs `debut`/`fin`/`duree_s`/`cause`/`incident`/`composants` — jamais de jeton ni de contenu d'issue. **`scripts/resume_pannes_github.py`** (nouveau, lecture seule) : résumé du nombre d'épisodes et de la durée cumulée, par mois et par cause.
- **Limite constatée, non corrigée** (hors périmètre — Watcher spool non modifié) : un fichier déposé dans `issues_inbox/` pendant une panne GitHub, si `gh issue create` échoue, est déplacé par `scripts/watcher_issues_inbox.py` vers `rejected/` exactement comme un rejet définitif (pas de distinction de cause à cet endroit) — il n'est pas perdu (visible dans `rejected/`, alarme de l'onglet « Résultats inbox ») mais rien ne le reprend automatiquement une fois la panne terminée. Voir `ARCHITECTURE.md` §7.5.
- Tests de logique pure, sans accès réseau (`tests/test_alerte_panne_github_732.py`, 21 cas ; `static/js/tests/panne_github.test.js`, 10 cas) : classification des échecs, lecture du résumé de statut, cache d'une minute, trois messages de repli, transition incident→rétabli, ouverture/fermeture d'épisode (une ligne, durée, taille bornée), résumé par mois/cause. Suite complète rejouée sans régression (50/50 scripts autonomes, 227 passed pytest, 269 passed `node --test`) — `tests/test_relancer_watcher_574.py` mis à jour (nouveau champ `panne_probable` dans la réponse JSON de `/relancer-issue`).
- Doc : `ARCHITECTURE.md`, nouvelle section 7 (« Alerte explicite de panne GitHub »), y compris le journal des pannes et sa limite. Rien ajouté à `BRIDGE_AGENT_DOC.md` (réservé aux conversations Claude Chat).

Après fusion : redémarrer `new_issue.py` (`app/*.py` modifié) puis `Ctrl+Maj+R`.

# CHANGELOG-730 — à fusionner dans CHANGELOG.md

## 8 octobre 2026 — issue #730

Messages éphémères (toasts, interface seule) : **journal consultable, pause au survol, erreurs persistantes** — `static/js/socle/toasts.js` restait le seul canal de notification non bloquante mais effaçait chaque message après ~4s quel que soit son type, sans aucune trace une fois disparu. Tout passe par le même point d'entrée (`afficher`) : aucun des appelants existants (`app.js`, `attente.js`, `ccw.js`, `panneau_lateral.js`, `resultats_coches.js`, `resultats.js`, `socle/api.js`, `socle/pont.js`) n'a été modifié.

- **Durée de vie selon le type** (`dureeAffichage`) : `info`/`succes` disparaissent seuls après 4s (inchangé) ; `erreur`/`avertissement` ne se ferment plus JAMAIS automatiquement — un bouton « × » toujours visible sur ces deux types est désormais la seule façon de les retirer. `toasts.confirmer(...)` reste inchangée (hors périmètre de l'issue).
- **Pause au survol** : tant que la souris reste sur un toast auto-effaçable, son minuteur est gelé (`mouseenter`/`mouseleave`) ; `calculerDelaiRestant(dureeRestante, debutActif, maintenant)` calcule le temps restant à la mise en pause, un nouveau `setTimeout` reprend avec cette valeur à la reprise.
- **Journal consultable** : chaque message affiché (quel que soit l'appelant) est consigné (`journaliser`) dans un historique borné à 50 entrées, FIFO (`ajouterEntreeJournal`), avec horodatage et type. Icône discrète dans l'en-tête (`#toasts-journal-bouton`, `templates/fragments/entete.html`, 🗒️) ouvrant un panneau listant ces messages du plus récent au plus ancien ; pastille (`#toasts-journal-badge`) affichant le nombre de messages non consultés depuis la dernière ouverture (`majNonLusApresAjout`, remis à zéro à l'ouverture). Branchement unique : `initJournalMessages()`, appelée une fois par `static/js/socle/index.js`.
- **Persistance** : journal stocké en `sessionStorage` (clé `bridge_toasts_journal`, hors `persistance.js` qui reste restreint aux préférences `localStorage`) — survit à un rechargement de page dans le même onglet, sans avoir besoin d'être conservé au-delà. Ne contient que ce qui est déjà affiché à l'écran (texte, type, horodatage) ; aucun changement côté serveur, watchers ni notifications sonores.
- Tests de logique pure (`static/js/tests/toasts.test.js`, 16 nouveaux cas) : `dureeAffichage` (durée par type), `ajouterEntreeJournal` (taille maximale, ordre FIFO, pureté), `majNonLusApresAjout` (compteur de non-lus selon l'état du panneau), `calculerDelaiRestant` (pause/reprise, jamais négatif) et `formaterHeureJournal` (horodatage affiché). Suite JS complète rejouée (227 passed, aucune régression).
- Vérification manuelle en navigateur réel (Playwright, serveur Flask local) : toast info survolé reste affiché au-delà de sa durée d'origine puis disparaît après la reprise ; toast erreur jamais fermé automatiquement, fermé seulement par son bouton « × » ; badge masqué après ouverture du panneau ; journal (2 entrées) retrouvé identique après un rechargement de page.
- Doc : `BRIDGE_AGENT_DOC.md`, nouvelle section « Journal des messages éphémères (toasts) — pause au survol, erreurs persistantes (issue #730) », juste avant « Couleur d'accent des projets ».

Après fusion : `Ctrl+Maj+R` suffit (JS/CSS seuls) — aucun redémarrage de `new_issue.py` nécessaire (aucun changement serveur).

## 8 octobre 2026 — issue #729

Onglet Résultats : rattrapage des événements manqués (issue #729, suite #705) — à chaque activation de l'onglet, si la dernière synchro réseau de la liste date de plus de 30 s (ou n'a jamais eu lieu), affiche immédiatement le contenu courant puis recharge liste + décomptes + cases cochées **en arrière-plan**, sans vider ni bloquer l'affichage (`fautRechargerAOuverture`, `rechargerEnArrierePlan`, `static/js/resultats.js`). Le ↻ et la resynchronisation automatique #705 relisent désormais aussi l'état des cases « traité/lu » (`resultats.rafraichir()` appelle `resultatsCoches.rechargerCases()`), dans le MÊME périmètre de projets qu'eux (filtre #428) — corrige le cas où une décoche serveur après `RELANCE` (#720) restait affichée cochée malgré un ↻. Heure de dernière synchro affichée discrètement près du ↻ (`formaterHeureSync`, `#resultats-derniere-sync`). Tests de logique pure (`static/js/tests/resultats.test.js`) et comportementaux DOM/réseau mockés (`static/js/tests/resultats_resync_729.test.js`). JS/CSS uniquement, aucun changement de protocole d'événements ni du serveur — `Ctrl+Maj+R` suffit après fusion. Doc : `BRIDGE_AGENT_DOC.md` §17.3/§17.4 (nouvelle) et section case « traité/lu ».

# CHANGELOG-728 — à fusionner dans CHANGELOG.md

## 8 octobre 2026 — issue #728

Onglet « En attente » (interface seule, issue #714 2/2) : **pastille nominative de projet** — remplace le point de 9px et le nom en petit texte gris clair (12px, #888) peu visibles par un repère coloré portant le NOM du projet en début de ligne, même esprit visuel que `.badge-projet` de l'onglet Résultats.

- `static/js/attente.js` : `descriptionLigneAttente` expose désormais `projetAffiche` (repli « projet inconnu » si le projet est vide/absent, `projet` brut conservé). Deux nouvelles fonctions pures exportées : `couleurFondPastilleProjet(projet)` (délègue à l'ancien `couleurProjet` via le pont — aucune table de couleurs dupliquée — ou gris neutre `#888` si le projet est vide) et `couleurTexteSurFond(couleurFond)` (choisit noir ou blanc selon le MEILLEUR contraste WCAG avec le fond fourni, hex `#RGB`/`#RRGGBB` ou `hsl(h, s%, l%)` — mêmes formats que `couleurProjet`/`couleurHashProjet` côté `app.js` — même formule que `_contraste_avec_noir` de `palette.py`). `construireLigneDOM` : les anciens éléments `.pastille-ligne` et `.attente-projet` sont remplacés par un unique `.pastille-projet` (fond + texte posés en inline), placé avant le titre.
- `static/css/attente.css` : règles `.pastille-ligne`/`.attente-projet` remplacées par `.attente-entete .pastille-projet` (badge arrondi, fond/texte inline posés par le JS) ; pas de légende séparée (elle devient inutile).
- Cause possible évoquée par l'issue (un bloc issu d'un fichier découpé en lot pourrait arriver en `en_attente/` avec un champ `PROJET` vide, cf. `decouper_corps_en_blocs` qui ignore tout contenu avant le premier `#Titre:`) : confirmée par lecture du code comme un cas limite THÉORIQUE, mais aucun fichier réel n'existe dans ce worktree isolé (`issues_inbox/en_attente/` n'existe pas ici — données d'exécution hors dépôt, hors périmètre de ce worktree) pour le constater empiriquement. Pour la création immédiate (hors `ATTENTE`), `valider()` rejette déjà tout bloc sans `PROJET` avant création — seul le chemin `ATTENTE`, qui court-circuite toute validation (§3.16 du DOC), pourrait laisser passer un `PROJET` vide. **Aucun changement d'`app/issues_inbox.py`** : le repli d'affichage « projet inconnu » (ci-dessus) couvre ce cas défensivement côté interface, qu'il soit atteignable en pratique ou non, conformément au périmètre de l'issue (« serveur uniquement si la cause est confirmée »).
- Tests : `static/js/tests/attente.test.js` — nouveaux cas pour `projetAffiche` (nom présent / repli « projet inconnu »), `couleurFondPastilleProjet` (délégation à l'ancien code, mocké via `global.window` comme `resultats_activation.test.js` / gris si projet vide) et `couleurTexteSurFond` (fond noir/blanc/gris/`#RGB`/`hsl()`/valeur non reconnue). Suite JS complète rejouée (202 passed, aucune régression) ; `tests/test_champ_attente_713.py` rejoué sans modification (23 passed — aucun changement serveur).
- `BRIDGE_AGENT_DOC.md`, §3 (« Onglet « En attente » (issue #714, 2/2) ») : paragraphe mis à jour pour décrire la pastille nominative, la source de la couleur de fond (`couleurProjet`, réutilisée) et le choix de la couleur de texte (`couleurTexteSurFond`), et l'absence de légende séparée.

Après fusion : Ctrl+Maj+R (JS/CSS seuls) suffit — aucun redémarrage de `new_issue.py` (aucun changement serveur).

# CHANGELOG-727 — à fusionner dans CHANGELOG.md

## 8 octobre 2026 — issue #727

Documentation uniquement, aucune modification de code : deux informations d'exploitation utilisées en pratique mais absentes du dépôt sont désormais écrites.

- `WORKTREES.md`, §3 (« Workflow normal d'Alain ») : nouvelle table « Après la fusion : quoi relancer » juste après l'étape de nettoyage — `watcher.py` modifié → relancer les watchers de projet (de préférence sans issue en écriture en cours) ; `app/*.py`/templates/modules importés par `new_issue.py` → redémarrer `new_issue.py` ; `scripts/watcher_issues_inbox.py` → relancer le Watcher spool (indépendant des watchers de projet) ; JS/CSS seul → Ctrl+Maj+R navigateur ; doc/tests seuls → rien à relancer. Rappel du principe : un processus lancé avant la fusion garde l'ancien code jusqu'à son redémarrage, même s'il a été lancé le même jour.
- `BRIDGE_AGENT_DOC.md`, §3.14 (champ `RELANCE`) uniquement : modèle recommandé pour le texte libre d'un fichier RELANCE — cause de l'échec puis correction apportée (ex. nouveau `TIMEOUT`), et après un dépassement de délai une phrase de reprise facultative (« Un travail partiel existe peut-être déjà dans le worktree... ») — facultative car le prompt de CCL rappelle déjà l'équivalent quand le worktree est repris sur relance (issue #725), mais la répéter renforce le message.

Aucun renvoi ajouté en §12 de `BRIDGE_AGENT_DOC.md` vers `WORKTREES.md` : un renvoi existait déjà pour la routine de fusion. Suite de tests complète relancée (206 passed) : aucun test de structure de la doc cassé.

# CHANGELOG-726 — à fusionner dans CHANGELOG.md

## 7 octobre 2026 — issue #726

Champ `RELANCE` (§3.14) : **le texte libre d'un fichier de relance est désormais ajouté au corps de l'issue**, pas seulement recopié dans le commentaire de trace — c'est le corps que lit CCL à la reprise, jamais les commentaires. Avant #726, pour transmettre une consigne (précisions, cause supposée de l'échec, consigne de reprise) à CCL via `RELANCE`, il fallait éditer le corps à la main sur GitHub avant de relancer ; seuls les champs d'en-tête corrigibles (`TIMEOUT`/`MODELE`/`SOUS_DOSSIER`/`REPO_CIBLE`) étaient fusionnés dans le corps.

- `scripts/watcher_issues_inbox.py`, nouvelle fonction `_ajouter_texte_libre(corps, texte_libre)` : ajoute le texte libre en fin de corps sous une section horodatée `## Relance du <date>`. Relances successives : chaque section s'ajoute à la suite, la plus récente en dernier, sans jamais effacer les précédentes. Texte libre vide : corps inchangé par ce mécanisme (seule la fusion des champs d'en-tête s'applique, comme avant). Garantie structurelle : la section complète le corps avec des lignes vides jusqu'à `ZONE_ENTETE_LIGNES` (§3.3) avant de s'ajouter si le corps existant est plus court — la nouvelle section reste ainsi toujours HORS de la zone d'en-tête bornée, qu'un texte libre imitant une ligne d'en-tête (ex. `| MODE | écriture |`) ne pourra donc jamais faire relire comme un véritable champ par `lire_champ_entete`/`_maj_ligne_entete` lors d'une relance ultérieure.
- `_traiter_relance` : appelle `_ajouter_texte_libre` juste après `_fusionner_entete`, AVANT le seul appel à `_modifier_corps_gh` — fusion des champs d'en-tête et ajout du texte libre dans une seule et même mise à jour du corps. Le commentaire de trace existant est conservé tel quel (texte libre toujours recopié dedans en plus, comme avant #726) : il reste l'historique visible sur GitHub. Échec de la mise à jour du corps : relance rejetée comme avant, `needs-human` conservé.
- Le mode réellement appliqué à CCL reste armé par le label GitHub (§3.14, #563), inchangé — ce changement n'ouvre aucune voie vers le mode écriture.
- Aucun changement de `watcher.py`, de la validation de `RELANCE`, ni du retrait de `needs-human`. Même comportement pour les issues for-linux et for-windows (le corps est le même).
- Tests : `tests/test_texte_libre_relance_726.py` (nouveau, logique pure, aucun appel `gh` réel) — les 6 scénarios demandés par l'issue : texte libre ajouté en fin de corps avec section horodatée ; texte vide → corps inchangé ; deux relances successives → deux sections dans l'ordre ; texte imitant un en-tête → jamais lu comme un champ (vérifié aussi après une correction d'en-tête ultérieure, qui cible toujours la vraie ligne) ; fusion des champs d'en-tête + ajout du texte dans une seule mise à jour du corps (un seul appel `_modifier_corps_gh`) ; échec de la mise à jour du corps → relance rejetée, `needs-human` conservé (`relancer_issue` jamais appelé). Suites existantes rejouées sans régression : `tests/test_champ_relance_516.py`, `tests/test_decoche_relance_720.py`, `tests/test_pas_de_ligne_fichier_recu_si_relance_719.py`, `tests/test_relancer_watcher_574.py`, `tests/test_demarrage_ccw_issues_inbox_711.py`.
- `BRIDGE_AGENT_DOC.md` §3.14 : nouveau paragraphe « Texte libre ajouté au corps de l'issue, désormais lu par CCL » décrivant le mécanisme et sa garantie structurelle vis-à-vis de la zone d'en-tête bornée ; exemple de fichier RELANCE complété d'une ligne de consigne libre ; ligne du tableau des champs `RELANCE` mise à jour ; référence au nouveau fichier de test ajoutée à côté des autres tests de §3.14.

Après fusion : relancer le Watcher spool (`scripts/watcher_issues_inbox.py` modifié). Aucun redémarrage de watcher de projet ni de `new_issue.py` nécessaire.

# CHANGELOG-725 — à fusionner dans CHANGELOG.md

## 7 octobre 2026 — issue #725

Reprise du worktree existant sur RELANCE : **une relance d'une issue mode_write qui échoue (timeout/needs-human) ne crée plus systématiquement un worktree `-bis` vierge basé sur master** — elle reprend tel quel (commits et modifications non commitées compris) un worktree déjà existant pour cette même issue, quand il est disponible. Avant #725, le travail déjà fait par la tentative précédente était abandonné à chaque relance, refait depuis zéro, avec des timeouts qui se répétaient et des worktrees qui s'accumulaient — constaté le 07/10/2026 sur Rummikub (issue #146 : `rummikub-issue146` + `rummikub-issue146-bis` coexistants).

- `watcher.py`, nouvelles fonctions : `_worktree_en_cours_de_traitement` (verrou inter-process #189/#322 posé sur le chemin du worktree — jamais de reprise d'un worktree encore occupé par un traitement), `_horodatage_dernier_commit` (départage plusieurs candidats hérités par le plus récemment modifié), `_trouver_worktree_reutilisable` (cherche, via `_lister_worktrees_secondaires`, un worktree déjà existant pour l'issue demandée — nom standard ou suffixe hérité `-bis`/`-ter`, branche correspondante, pas verrouillé — et choisit le plus récent s'il y en a plusieurs), `_commits_ecart_depuis_creation` (nombre de commits dont `master` a avancé depuis la création de la branche du worktree repris, SANS rebase automatique) et `_preparer_worktree_ecriture` (nouveau point d'entrée unique, retourne une `WorktreeResolu` : reprend d'abord un worktree existant via `_trouver_worktree_reutilisable`, sinon retombe sur le chemin historique `_creer_worktree_avec_retries` inchangé — nom standard, puis `-bis`, puis `-ter`, puis repli REP_TRAVAIL signalé activement, issue #611).
- `traiter_issue` appelle désormais `_preparer_worktree_ecriture` (au lieu de `_creer_worktree_avec_retries` directement) dans les deux chemins `MAX_WRITE_PARALLELE` (parallélisé et séquentiel) — comportement et signalements inchangés quand aucun worktree n'est réutilisable.
- `lancer_claude` : deux nouveaux paramètres `worktree_repris` / `commits_ecart_worktree` (transmis via `_executer_une_tentative`/`_traiter_issue_synchrone`/`_lancer_thread_ecriture`) injectent, quand le worktree a été repris lors d'une relance, un bloc de prompt dédié (même esprit que la clause « tentative précédente probable » #689) : le répertoire contient probablement le travail de la tentative précédente de cette même issue — à vérifier (qualité, complétude) plutôt qu'à refaire, à compléter si nécessaire, et à signaler explicitement comme une reprise de worktree dans le rapport final. Si `master` a avancé depuis la création du worktree, l'écart (nombre de commits) est mentionné dans ce bloc — jamais de rebase automatique, le merge manuel se fait en connaissance de cause.
- Compte-rendu de clôture (`_finaliser_succes`/`_gerer_abandon_max_essais`) : un avertissement `ℹ️ Worktree repris d'une tentative précédente de cette même issue...` est ajouté en tête du message posté sur l'issue, succès comme échec définitif, avec l'écart de commits s'il y en a un — même esprit que l'avertissement existant pour le repli REP_TRAVAIL (#611).
- Tests : `tests/test_reprise_worktree_725.py` (nouveau, logique pure sur dépôts git jetables) — les 7 scénarios demandés par l'issue (relance avec worktree valide existant → repris, aucun `-bis` créé ; première exécution → création normale ; dossier présent mais non enregistré comme worktree → repli `-bis` inchangé ; modification non commitée conservée lors de la reprise ; deuxième relance → le même worktree est de nouveau repris ; plusieurs worktrees hérités → le plus récent est choisi ; bloc de prompt de reprise présent seulement si le worktree a été repris) plus un scénario complémentaire (worktree par ailleurs valide mais verrouillé par un traitement en cours → jamais repris). Suite `test_worktree_parallelisation_337.py` rejouée : aucune régression.
- `BRIDGE_AGENT_DOC.md` (puce « Worktree » de la section parallélisation `mode_write`) et `WORKTREES.md` (§2 et §5 « Limites connues ») : nouveau paragraphe décrivant la réutilisation sur relance, ses conditions, et l'absence de rebase automatique.

Hors périmètre (rappel de l'issue) : mode lecture inchangé ; `MAX_WRITE_PARALLELE` et le garde-fou `configs/*.conf` non touchés ; calibration des durées de relance (#592) non touchée ; les worktrees `-bis` déjà existants ne sont ni supprimés ni migrés — le nettoyage reste entièrement manuel.

Après fusion : relancer les watchers (`watcher.py` modifié), de préférence quand aucune issue en écriture ne tourne. Aucun redémarrage de `new_issue.py` nécessaire.

# CHANGELOG-724 — à fusionner dans CHANGELOG.md

## 6 octobre 2026 — issue #724

Garde-fou `configs/*.conf` (#318) : **le garde-fou technique n'annule plus les actions légitimes d'Alain** faites depuis new_issue.py — création de projet, suppression de projet, enregistrement de l'onglet Configuration — quand elles tombent pendant qu'une issue mode_write (ou lecture active) tourne dans un **autre** projet. `configs/` est commun à tous les projets ; avant #724 le garde-fou traitait tout changement de ce dossier comme une violation de l'issue en cours, même un geste volontaire sans rapport avec elle — vécu deux fois le 06/10/2026 sur la création du projet AnnuaireToken (issues #138 et #140 du journal watcher Rummikub) : le `.conf` flambant neuf était supprimé juste après la création, laissant le projet en apparence créé (dépôt GitHub, dossier local, doc régénérée) mais inutilisable (« Projet introuvable »).

- Nouveau module `etat_configs_legitimes.py` (même mécanisme que `etat_son_issue.py`/`etat_cases_cochees.py` : `logs/configs_legitimes.json`, écriture atomique + verrou anti-collision) : `enregistrer(nom_fichier)` horodate une action volontaire, `instant_legitime(nom_fichier)` la relit en purgeant les entrées de plus d'une heure (`DUREE_VALIDITE_S`). Par construction, `enregistrer()` n'est appelée que depuis `nouveau_projet.ecrire_conf`, `supprimer_projet._supprimer_conf` et `app/projets.sauvegarder_conf` — jamais depuis le code de traitement d'une issue (`watcher.py`) : une issue ne peut donc pas s'ajouter elle-même à cette trace via le fonctionnement normal du bridge.
- `watcher.py` : `_restaurer_configs_modifies` (garde-fou #318) consulte désormais cette trace via la nouvelle fonction `_action_legitime_posterieure(nom_fichier, instant_debut)` avant d'agir sur chaque fichier changé — une entrée horodatée **après** le début du traitement (l'instant où `_empreinte_configs` a été prise, maintenant un couple `(empreinte, instant)`) fait passer le changement pour légitime : ni suppression, ni restauration, ni recréation, avec un message **INFO** explicite dans le journal (« reconnu comme une création de projet légitime depuis new_issue.py », etc.) à la place du WARNING habituel. Un changement sans trace — donc attribuable à l'issue elle-même — reste annulé et journalisé en WARNING exactement comme avant #724 : le rôle du garde-fou reste intact pour CCL/CCW.
- `nouveau_projet.py` (`ecrire_conf`), `supprimer_projet.py` (`_supprimer_conf`) et `app/projets.py` (`sauvegarder_conf`) appellent `etat_configs_legitimes.enregistrer(...)` juste après leur écriture disque — aucun changement de comportement visible pour Alain, ces trois chemins restent synchrones et inchangés côté interface.
- Tests : `tests/test_garde_fou_configs_actions_legitimes_724.py` (nouveau, logique pure, aucun watcher réel, `etat_configs_legitimes` et `configs/` isolés via monkeypatch comme `tests/test_cases_cochees_629.py`/`tests/test_supprimer_projet_587.py`) — les 6 scénarios demandés par l'issue : nouveau `.conf` créé par l'utilisateur pendant une issue → conservé ; nouveau `.conf` créé par l'issue elle-même (écriture directe, sans trace) → toujours supprimé ; modification via l'onglet Configuration pendant une issue → conservée ; modification par l'issue elle-même → toujours annulée ; suppression de projet par l'utilisateur → `.conf` non recréé ; trace expirée → comportement strict retrouvé — plus 2 scénarios sur le module `etat_configs_legitimes` lui-même (aller-retour, purge à la lecture). Suite complète vérifiée verte : `python3 tests/lancer_tous_les_tests.py` → 47 fichiers, tous réussis, aucune régression.
- `BRIDGE_AGENT_DOC.md` : §12 (garde-fou `configs/*.conf`, #318) — nouveau paragraphe « Actions légitimes d'Alain pendant une issue en cours — issue #724 » décrivant le mécanisme complet ; §13 (étapes de `nouveau_projet.py`/le bouton web), étape 2 (`configs/<nom>.conf`) — mention du nouveau traçage.

Hors périmètre (rappel de l'issue) : aucun changement pour une issue qui touche elle-même à `configs/*.conf` — elle reste annulée et journalisée, consigne `globales.md` inchangée ; logique de régénération des tableaux de la doc non touchée.

Après fusion : relancer les watchers (`watcher.py` modifié) et redémarrer `new_issue.py` (`app/projets.py`, `nouveau_projet.py`, `supprimer_projet.py` modifiés). Ne pas lancer l'issue de fusion elle-même pendant qu'une autre issue mode_write tourne dans un autre projet.

# CHANGELOG-723 — à fusionner dans CHANGELOG.md

## 6 octobre 2026 — issue #723

Case « traité/lu » + badges ✅/All : **la copie préfixe désormais une ligne d'identité** `Issue #N — <projet> — <titre>` suivie d'une ligne vide — jusqu'ici la copie ne contenait que le dernier commentaire (rapport ou « ❌ Échec après N tentatives »), sans numéro ni titre ni projet, forçant à redonner le numéro à Claude.ai pour rédiger une RELANCE.

- `static/js/resultats_coches.js` : nouvelles fonctions pures `ligneIdentite(it, projet)` (construit la ligne, titre aplati sur une seule ligne via `replace(/\s+/g, ' ').trim()` — robuste à un titre multiligne ou très long ; pas de « — » final orphelin si le détail d'issue n'a pas de titre), `prefixerIdentite(it, projet, texte)` (préfixe ligne d'identité + ligne vide, SAUF si `texte` est vide — pas de ligne orpheline sur une issue pas encore répondue, pour que la détection « pas encore disponible » du moteur de copie reste correcte) et `texteCopieAvecIdentite(variante, it, projet, texte)` (point d'assemblage unique : ajoute l'identité pour `'reponse'`/`'all'`, jamais pour `'diff'`). `texteReponse`/`texteAll` appellent désormais `texteCopieAvecIdentite` ; `texteDiff` inchangé (diff brut, hors périmètre).
- Le numéro et le titre viennent du détail d'issue déjà chargé par `detailIssue` (`/issue/<projet>/<numero>` → `number`, `title`) ; le projet vient du contexte de la copie (paramètre déjà transmis à `texteReponse`/`texteAll`). Aucune requête réseau supplémentaire.
- Tests : `static/js/tests/resultats_coches.test.js` — nouveaux tests pour `ligneIdentite` (forme attendue, titre absent, titre multiligne/très long aplati sur une seule ligne), `prefixerIdentite` (texte non vide préfixé, texte vide/blanc inchangé) et `texteCopieAvecIdentite` (identité présente pour `reponse`/`all`, absente pour `diff`). Suite complète vérifiée verte : `node --test static/js/tests/` → 193 tests, aucune régression.
- `BRIDGE_AGENT_DOC.md` : section « Case « traité/lu » côté interface + copie fiable (issue #636, étape 5b) » — nouveau paragraphe « Identité de l'issue en tête de la copie (issue #723) » ; mention des nouvelles fonctions dans la liste des tests de logique pure du module.

Hors périmètre (rappel de l'issue) : variante « diff » inchangée (diff brut) ; aucun changement côté watcher ni du commentaire posté sur GitHub (JS uniquement — le correctif s'applique donc aussi aux anciennes issues, sans réémission de commentaire) ; `configs/*.conf` non touché. Après fusion : Ctrl+Maj+R suffit, aucun redémarrage de `new_issue.py` nécessaire.

# CHANGELOG-722 — à fusionner dans CHANGELOG.md

## 6 octobre 2026 — issue #722

Documentation uniquement (`BRIDGE_AGENT_DOC.md`) : **le mode lecture ne peut exécuter aucun script, `python3` compris** — ce n'était écrit nulle part clairement, ce qui a conduit un Claude Chat (03/10/2026) à choisir la lecture seule pour une issue qui devait exécuter un script Python de simulation, provoquant un refus systématique des commandes `python3` (bloquées par la demande d'approbation interactive de Claude Code, inatteignable en session non-interactive) — comportement voulu du watcher, pas un bug.

- §5 (« Modes lecture seule / lecture active / écriture »), dans la description de la lecture seule : encadré rappelant qu'en dehors de la courte allowlist (`git fetch`, `git pull --ff-only`, heuristique interne Claude Code), aucune commande n'est exécutée, script ou `python3` compris ; pour exécuter un script d'analyse/simulation/mesure sans toucher au projet → lecture active (`| MODE | lecture active |`) ; pour un script qui doit modifier le projet → écriture (`| MODE | écriture |`) ; précise que ce refus ne concerne pas les issues déjà en écriture.
- §3.3 (« Format attendu du fichier », champ `MODE`) : encadré à l'endroit où Claude Chat choisit le `MODE` en rédigeant une issue — mots déclencheurs à repérer dans la tâche demandée (exécuter, lancer, mesurer, simuler, tester, `python3`, `pytest`, script) : leur présence signale presque toujours que le mode lecture (défaut) est le mauvais choix.

Hors périmètre (rappel de l'issue) : aucun changement de code ni de comportement du watcher ; `python3` non ajouté à `OUTILS_LECTURE_AUTORISES`.

# CHANGELOG-721 — à fusionner dans CHANGELOG.md

## 6 octobre 2026 — issue #721

§13 / état serveur des cases : **le bouton « 🔄 Relancer » d'une ligne Résultats décoche désormais la case « traité/lu »** — même intention que la décoche automatique du chemin fichier `RELANCE` d'`issues_inbox/` (#720) : une issue relancée va produire un nouveau résultat, elle ne doit plus apparaître comme déjà lue, quelle que soit la façon de la relancer.

- `app/cases_cochees.py` : logique de décoche + diffusion SSE factorisée hors de `notifier_case_decochee()` dans une nouvelle fonction `decocher_et_diffuser(projet, numero)` — décoche l'état serveur (`etat_cases_cochees.decocher_issue`, idempotente) PUIS diffuse l'événement SSE `case_decochee` (`app.fin_issue._diffuser`). `notifier_case_decochee()` (route POST appelée par le watcher spool, #720) en devient un mince wrapper HTTP, comportement inchangé.
- `app/interruption.py::route_relancer()` : appelle `decocher_et_diffuser(cfg.nom, numero)` juste après une relance réussie (`statut_global == "ok"`), uniquement si le dépôt correspond à un projet configuré localement (`cfg` non `None`). Appel direct, sans notification réseau — `route_relancer()` s'exécute dans le même process (`new_issue.py`) que l'état des cases, à la différence du watcher spool (process séparé) qui doit passer par la route HTTP. Comportement de `relancer_issue()` elle-même (labels, commentaire, `statut_global`) inchangé.
- Tests : `tests/test_decoche_bouton_relancer_721.py` (nouveau, dans le style de `tests/test_decoche_relance_720.py`, état isolé par `_EtatIsole`/monkeypatch, aucun appel `gh` réel) — relance réussie d'une issue cochée → case décochée + événement SSE diffusé à un onglet déjà ouvert ; relance réussie d'une issue non cochée → aucun effet, aucune erreur (idempotent) ; relance refusée/en erreur → la case ne change pas, aucun événement diffusé ; dépôt sans projet configuré (`cfg=None`) → aucun crash, aucune décoche tentée. Suite complète vérifiée verte : `pytest tests/` → 198 tests (194 existants + 4 nouveaux), aucune régression — `tests/test_decoche_relance_720.py` et `tests/test_relancer_watcher_574.py` en particulier toujours au vert.
- `BRIDGE_AGENT_DOC.md` : §13 (« Relancer une issue bloquée en needs-human ») — nouveau paragraphe « Décoche de la case « traité/lu » (issue #721) » ; section « État serveur des cases cochées » (#629) — décrit maintenant les DEUX appelants de `decocher_et_diffuser` (route `/notifier-case-decochee` pour le watcher spool, appel direct pour le bouton) ; §3.14 — le paragraphe qui indiquait que le bouton ne décochait rien est remplacé par la description du nouveau comportement partagé.

Hors périmètre (rappel de l'issue) : `configs/*.conf` non touché, création d'issues inchangée, autres boutons de ligne non touchés.

# CHANGELOG-720 — à fusionner dans CHANGELOG.md

## 5 octobre 2026 — issue #720

§3.14/§3.15 : **décoche automatique de la case « traité/lu » dans Résultats quand une issue est relancée** (champ `RELANCE`, #516) — une issue relancée va produire un nouveau résultat ; si Alain l'avait déjà cochée avant son échec, elle apparaissait sinon comme déjà lue à tort.

- `scripts/watcher_issues_inbox.py` : nouvelle fonction `_notifier_case_decochee(projet, numero)` (même famille best-effort que `_notifier_fichier_recu`/`_notifier_creation_issue`/`_notifier_fichier_refuse`) appelée depuis `_traiter_relance()` dès que `relancer_issue()` réussit (`statut_global == "ok"`) — jamais pour une `RELANCE` refusée (issue introuvable/fermée/dépôt incorrect). POSTe vers la nouvelle route `/notifier-case-decochee`.
- `app/cases_cochees.py` : nouvelle route `notifier_case_decochee()` (`POST /notifier-case-decochee`, sans `login_requis` — appelée par un script local, même famille que les routes `/notifier-fichier-*` d'`app/fin_issue.py`) : décoche réellement l'état serveur (`etat_cases_cochees.decocher_issue`, idempotente — réutilisée telle quelle, jamais réécrite) PUIS diffuse l'événement SSE `case_decochee` (`app.fin_issue._diffuser`) à tous les onglets Résultats déjà ouverts. Le watcher spool (process séparé) ne touche ainsi jamais lui-même à `logs/etat_cases_cochees.json`, qui reste la propriété exclusive de `new_issue.py` (évite tout conflit d'écriture concurrente).
- `static/js/socle/sse.js` : le canal `/stream` route l'événement `case_decochee` (`{projet, numero}`) vers une tranche dédiée du store, `derniereNotifCase` (même principe que `derniereNotifFichier`).
- `static/js/resultats_coches.js` : nouvelle fonction pure `appliquerCaseDecochee(etat, notif)` (réutilise `retirerDansEtat`, donc idempotente) + abonnement à `derniereNotifCase` dans `initialiser()` — décoche instantanément un onglet Résultats déjà ouvert, sans attendre le prochain chargement par projet (qui est le seul moment où l'état serveur des cases est relu aujourd'hui). Rafraîchir le reste de la ligne (état/labels) n'a pas été ajouté : une `RELANCE` ne change ni l'état `OPEN` ni les labels affichés avant l'ACK réelle du watcher cible, déjà couverte par l'événement `debut_issue` existant — l'ajouter ici aurait élargi le périmètre sans bénéfice visible.
- Un seul chemin de relance est concerné, comme demandé : le fichier `RELANCE` déposé dans `issues_inbox/` (y compris depuis l'onglet « En attente », #713). Le bouton « 🔄 Relancer » d'une ligne Résultats (`app/interruption.py::route_relancer`) réutilise la même `relancer_issue()` mais n'a volontairement pas été touché — signalé ici sans modification, comme demandé par l'issue : il cible typiquement une issue que l'utilisateur vient de constater en échec, donc rarement déjà cochée. Aucune autre voie de relance automatique n'existe dans l'interface.
- Tests : `tests/test_decoche_relance_720.py` (nouveau, 9 scénarios — route `/notifier-case-decochee` isolée du vrai `logs/etat_cases_cochees.json` via `_EtatIsole`, comme `tests/test_cases_cochees_629.py` ; `_traiter_relance`/`traiter_fichier` avec `_poster_best_effort` intercepté, comme `tests/test_champ_relance_516.py`/`tests/test_pas_de_ligne_fichier_recu_si_relance_719.py`) — décoche + diffusion SSE, idempotence (issue non cochée → aucun effet/erreur), requête incomplète → 400, relance réussie poste la décoche, relance refusée (introuvable, fermée) → aucune décoche, lot à plusieurs `RELANCE` → chaque issue décochée, lot mixte `RELANCE`+création → création inchangée, `new_issue.py` non lancé (urllib en panne, échappatoire `BRIDGE_AGENT_NOTIFS_RESEAU_FORCEES=1`) → la relance réussit quand même, seule la décoche est perdue silencieusement. `static/js/tests/resultats_coches.test.js` : 4 nouveaux scénarios pour `appliquerCaseDecochee` (retrait, idempotence, événement malformé, isolation entre projets). `tests/test_pas_de_ligne_fichier_recu_si_relance_719.py` adapté (3 assertions `appels == []` élargies pour isoler l'invariant #719, qui ne porte que sur `fichier_recu`/`fichier_refuse`, du nouvel événement `case_decochee` désormais co-émis). Suite complète vérifiée verte : `pytest tests/` → 194 tests, et `node --test static/js/tests/` → 186 tests, aucune régression.
- `BRIDGE_AGENT_DOC.md` : §3.14 (nouveau paragraphe « Décoche automatique de la case « traité/lu » »), §3.15 (nouvel événement `case_decochee` dans la liste + note sur son effet de bord côté serveur), et la section « État serveur des cases cochées » (#629/#636) — nouvelle route sans `login_requis`, et nouveau point dans la liste des évolutions côté interface (#636).

Hors périmètre (rappel de l'issue) : `configs/*.conf` non touché, création d'issues inchangée, comportement de la case pour les issues non relancées inchangé.

# CHANGELOG-719 — à fusionner dans CHANGELOG.md

## 5 octobre 2026 — issue #719

§3.8/§3.14/§3.15 : **plus de ligne « 📥 fichier reçu » fantôme dans Résultats pour un fichier (ou lot) dont tous les blocs restants sont des `RELANCE`** (champ `RELANCE`, #516) — même mécanisme que l'incident corrigé par #716 pour le champ `ATTENTE`, mais pour le cas RELANCE. Constaté en réel le 05/10/2026 avec `relance_issue_126.txt`.

- `scripts/watcher_issues_inbox.py` : nouvelle fonction pure `relance_demandee(bloc)` (miroir de `lire_condition_attente()` pour `ATTENTE`) — détecte un champ `RELANCE` non vide sur un bloc BRUT. Dans `traiter_fichier`, `_notifier_fichier_recu` est désormais sauté sur les deux branches concernées : fichier mono-issue entier portant `RELANCE` (sauté entièrement avant `_traiter_bloc`), lot multi-blocs dont **tous** les blocs restants (après filtrage `ATTENTE` éventuel, #716) sont des `RELANCE` (sauté avant `_traiter_lot`). Inchangé pour un lot mixte (`RELANCE` + création normale), pour une `RELANCE` seule parmi des blocs `ATTENTE`+création, et pour un fichier sans `RELANCE`. Une `RELANCE` refusée garde sa propre ligne rouge `fichier_refuse`, affichée comme avant (ce signal ne dépend pas de `fichier_recu`).
- Tests : `tests/test_pas_de_ligne_fichier_recu_si_relance_719.py` (nouveau, 7 scénarios, dans le style de `tests/test_pas_de_ligne_fichier_recu_si_attente_716.py`) — mono-issue `RELANCE` réussie (aucun événement), lot entièrement `RELANCE` (aucun événement), lot mixte `RELANCE`+création (`fichier_recu` toujours émis, non-régression), `RELANCE` refusée (ligne rouge affichée, sans `fichier_recu`), fichier sans `RELANCE` (idem non-régression), combinaison avec `ATTENTE` : lot `ATTENTE`+`RELANCE` sans création (aucun événement) et lot `ATTENTE`+`RELANCE`+création (`fichier_recu` toujours émis). Interception de `_poster_best_effort`, `_recuperer_issue`/`_modifier_corps_gh`/`relancer_issue` substitués (aucun appel réseau ni `gh` réel, comme `tests/test_champ_relance_516.py`). Suite complète `pytest tests/` vérifiée verte (185 tests, dont les 7 nouveaux, aucune régression).
- `BRIDGE_AGENT_DOC.md` §3.8 (lignes en direct) et §3.15 (événement `fichier_recu` + séquence multi-blocs) : exception `RELANCE` documentée à côté de celle, déjà en vigueur mais jusqu'ici non documentée dans ce fichier, du champ `ATTENTE` (#716) — les deux renvoient maintenant l'une vers l'autre. Nouveau paragraphe « Ligne « fichier reçu » dans Résultats (issue #719) » en fin de §3.14.

Hors périmètre (rappel de l'issue) : `configs/*.conf` non touché, circuit de création d'issues inchangé (seule la notification SSE `fichier_recu` est concernée).

# CHANGELOG-718 — à fusionner dans CHANGELOG.md

## 4 octobre 2026 — issue #718

§3.16 « Issues en attente » : l'onglet **« En attente » passe AVANT l'onglet « Résultats »** dans la barre d'onglets, pour plus de visibilité (demande d'usage d'Alain, suite #713/#714). **Résultats reste l'onglet actif au lancement du programme**, comme avant — le changement d'ordre ne déplace pas l'activation par défaut.

- `templates/fragments/onglets.html` : le bloc `data-onglet="attente"` est déplacé avant le bloc `data-onglet="resultats"` (qui garde seul la classe `actif`). Les autres onglets (Journal watcher, Configuration, CCW, Nouvelle issue) gardent leur position relative.
- Aucun changement de code JS nécessaire : l'association onglet ↔ panneau se fait déjà par **identifiant** (`data-onglet` / `panneau-<nom>`), pas par position dans le DOM (voir l'en-tête de `static/js/onglets.js`, issue #626) ; l'onglet actif au lancement est déjà désigné par une constante explicite (`ONGLET_PAR_DEFAUT = 'resultats'` dans `static/js/onglets.js`, reprise par `store.js` : `ongletActif: 'resultats'`), jamais par position dans la liste. Aucune mémorisation (`localStorage`) ni raccourci clavier de l'onglet actif n'existe par ailleurs. Vérifié : aucune règle CSS `nth-child`/`first-child`/`order` sur `.onglet` dans `static/css/base.css`.
- `BRIDGE_AGENT_DOC.md` §3 : correction de la mention « juste après Résultats » (issue #714) → « avant Résultats dans la barre d'onglets », avec rappel explicite que Résultats reste l'onglet actif au lancement.
- Tests : `tests/test_ordre_onglets_718.py` (nouveau, 3 scénarios, dans le style de `tests/test_champ_attente_713.py` — lecture directe des fichiers, aucune dépendance au DOM) — ordre des blocs `data-onglet` dans le gabarit (En attente avant Résultats), un seul onglet `actif` au chargement et c'est Résultats, `ONGLET_PAR_DEFAUT` désignant `'resultats'` par son nom dans `static/js/onglets.js`. Suite Python complète vérifiée verte (`pytest tests/` → 178 tests, dont les 3 nouveaux, aucune régression) ainsi que la suite JS (`node --test tests/` dans `static/js/` → 182 tests, inchangée).

Hors périmètre (rappel de l'issue) : `configs/*.conf` non touché, contenu/badge/boutons Lancer-Supprimer de l'onglet « En attente » inchangés.

# CHANGELOG-717 — à fusionner dans CHANGELOG.md

## 4 octobre 2026 — issue #717

§16 : **démarrer/arrêter les services CCW depuis Windows SANS SSH** (issue #717, étape F du retrofit CCW #712) — `new_issue.py` tournant nativement sous Windows (ThinkPad éteint, nouveau PC) appelle désormais `nssm` directement au lieu d'ignorer silencieusement l'absence d'hôte SSH configuré.

Constat vérifié le 04/10/2026, depuis un PowerShell NON élevé en `AlainW` : le compte est administrateur mais son jeton est bridé par l'UAC (groupe Administrators « deny only », niveau Medium) — `nssm status` fonctionne, `nssm start` échoue avec « OpenService(): Access is denied ». L'hypothèse « UAC désactivé » était donc fausse ; le démarrage par SSH marche parce qu'une session SSH d'administrateur reçoit les droits complets.

- `provisioning/windows/ccw-commun.psm1` : nouvelle fonction `Autoriser-DemarrageServiceCcw` — accorde à un compte (`AlainW` par défaut, SID résolu **dynamiquement**, jamais codé en dur) le droit de démarrer/arrêter/interroger un service SANS élévation UAC (`sc.exe sdset`, entrée `(A;;LCSWRPWPLOCRRC;;;<SID>)`). Idempotente : lit le descripteur actuel (`sc.exe sdshow`), ne fait rien si l'entrée existe déjà, sinon l'insère dans la section `D:` (avant `S:` si présente) sans retirer les entrées existantes (SYSTEM/Administrateurs/utilisateurs interactifs), puis réécrit via `sc.exe sdset`.
- `provisioning/windows/autoriser_demarrage_ccw.ps1` (nouveau) : à lancer **une seule fois**, en PowerShell administrateur, pour poser les droits sur tous les services `CCW-Watcher*` déjà existants (base comprise) — affiche le résultat par service.
- `provisioning/windows/ajouter_projet_ccw.ps1` : pose les mêmes droits en fin de script (persistance) — `nssm remove`+`install` efface sinon ce réglage à chaque recréation d'un projet.
- `app/ccw.py` : `_local_natif_sans_ssh()` détecte le cas natif Windows sans hôte SSH configuré (`os.name == "nt"` + config SSH absente — comportement Linux strictement inchangé). `_piloter_service_ccw_action` bascule alors sur une nouvelle branche locale (`_piloter_service_ccw_action_local` + `_nom_service_local`, même règle Bridge_Agent → `CCW-Watcher` sans suffixe) qui appelle `nssm` **directement en local**, sans ssh/scp — couvre à la fois le démarrage à la demande (`demarrer_service_ccw_arriere_plan`, toujours en thread démon non bloquant) et les actions Démarrer/Arrêter/Redémarrer de l'onglet CCW. Échec (droits non posés, service introuvable, nssm absent du PATH) → journalisé clairement, jamais silencieux.
- `app/ccw.py` : `_sddl_contient_sid` / `_inserer_ace_sddl` / `_ace_demarrage_arret` / `_ajouter_droit_demarrage_sddl` — port Python PUR de l'algorithme de manipulation du descripteur SDDL réellement exécuté en PowerShell (`ccw-commun.psm1`), gardé uniquement pour permettre des tests unitaires sans dépendre de Windows (suite de tests sous Linux).
- Tests : `tests/test_demarrage_ccw_windows_717.py` (nouveau, 19 scénarios en fonctions `test_*` collectées par pytest — comme `tests/test_champ_attente_713.py`/`tests/test_demarrage_ccw_a_la_demande_709.py`, avec le même `main()` autonome pour `python3 tests/test_demarrage_ccw_windows_717.py`) — manipulation idempotente de la chaîne SDDL (ajout, conservation des entrées existantes, insertion avant la section SACL, descripteur invalide), choix SSH ou nssm direct selon `os.name`/la config SSH, résolution du nom de service local, bascule transparente de `_piloter_service_ccw_action`/`_demarrer_service_ccw_sync` vers nssm local (succès, échec avec message clair, nssm introuvable, nom invalide). Suite complète vérifiée verte : `pytest tests/` → 175 tests (156 préexistants + 19 nouveaux), aucune régression.
- `BRIDGE_AGENT_DOC.md` §16 : correction de la mention « AlainW utilisateur non-administrateur » (3 occurrences) → AlainW est administrateur, avec un jeton filtré par l'UAC en session normale. Bloc « Deux limites connues » du retrofit #712 mis à jour (la limite « new_issue.py natif Windows » est résolue, documentée comme telle) ; nouveau paragraphe « Droits de démarrage/arrêt sans élévation UAC — sc.exe sdset » décrivant le mécanisme, le script à lancer une fois et la persistance via `ajouter_projet_ccw.ps1` ; entrée ajoutée au tableau des scripts pour `autoriser_demarrage_ccw.ps1`.

Hors périmètre (rappel de l'issue) : `configs/*.conf` non touché, service `CCW-Watcher` de base toujours actif (inchangé), jetons CCW non touchés. Validation réelle (`nssm start` puis `stop` en PowerShell non élevé sur CCW) à faire par Alain après fusion et exécution de `autoriser_demarrage_ccw.ps1`.

# CHANGELOG-716 — à fusionner dans CHANGELOG.md

## 4 octobre 2026 — issue #716

§3.16 « Issues en attente » : **plus de ligne « 📥 fichier reçu » fantôme dans Résultats pour un fichier (ou lot) ENTIÈREMENT mis en attente** (champ `ATTENTE`, #713) — correctif de l'incident documenté dans le changelog de #714 (« fichier reçu : mono.txt » resté affiché sans jamais être remplacé, puisqu'aucune issue n'est créée pour ces blocs).

- `scripts/watcher_issues_inbox.py::traiter_fichier` : cause confirmée — `_notifier_fichier_recu` était appelé en tout début de fonction, AVANT la détection du champ `ATTENTE` (#713). L'appel est déplacé après cette détection sur les trois branches concernées : fichier mono-issue (sauté entièrement si `ATTENTE` couvre tout le fichier, sinon émis juste avant `_traiter_bloc`), lot multi-blocs (sauté si `blocs_a_traiter` finit vide — tous les blocs avaient `ATTENTE` —, sinon émis une fois avant `_traiter_lot`, inchangé pour un lot mixte), extension invalide / lecture impossible (émis immédiatement, comportement inchangé — ces fichiers n'ont jamais de notion d'`ATTENTE`).
- Tests : `tests/test_pas_de_ligne_fichier_recu_si_attente_716.py` (nouveau, 4 scénarios, dans le style de `tests/test_champ_attente_713.py`) — fichier mono-issue avec `ATTENTE` (aucun événement), lot entièrement `ATTENTE` (aucun événement), lot mixte (événement `fichier_recu` toujours émis, non-régression), fichier sans `ATTENTE` (idem). Interception de `_poster_best_effort` comme `tests/test_evenements_issues_inbox_631.py`. Suite complète `pytest tests/` vérifiée verte (156 tests, dont les 4 nouveaux).

Hors périmètre (rappel de l'issue) : toute vérification automatique de la condition `ATTENTE`, inchangée.

# CHANGELOG-714 — à fusionner dans CHANGELOG.md

## 3 octobre 2026 — issue #714 (2/2)

§3.16 « Issues en attente » : **onglet web « En attente »** affichant les issues mises de côté par le champ `ATTENTE` (issue #714, 2/2 — suite de #713 qui posait le mécanisme et les routes côté serveur). Liste, badge, « Lancer » et « Supprimer » — Alain seul juge si la condition affichée est remplie, aucune vérification automatique.

- `static/js/attente.js` (nouveau module par fonctionnalité, suivant le modèle `resultats.js`/`ccw.js`) : chargement de la liste (`GET /issues-attente`) à l'ouverture de l'onglet et après chaque action ; une ligne par élément (pastille couleur projet via `couleurProjet` de l'ancien `app.js`, titre, date de dépôt, **condition mise en évidence** dans un encart ambré) ; état vide explicite « Aucune issue en attente ». « Lancer » (`POST /issues-attente/lancer`) retire la ligne et bascule un toast de succès (« … elle apparaîtra dans Résultats »), sans changer d'onglet ; « Supprimer » (`POST /issues-attente/supprimer`) demande d'abord confirmation via `toasts.confirmer` (suppression définitive, aucun archivage). Un échec (toast d'erreur, message du serveur si disponible) ne retire jamais la ligne, boutons réactivés. Pas de polling dédié : le badge suit le sondage déjà en place de `/issues-inbox/etat` (`rafraichirInbox`, `static/js/resultats.js`, issue #705) via un abonnement à `store.issuesInbox.nbEnAttente` — si l'onglet est ouvert quand ce compteur change, la liste se recharge automatiquement.
- `static/js/resultats.js` : `rafraichirInbox()` pousse désormais `nb_en_attente` dans `store.issuesInbox.nbEnAttente` (même cycle que l'alarme `rejetes`, aucun appel réseau supplémentaire).
- `static/js/socle/store.js` : tranche `issuesInbox` étendue avec `nbEnAttente: 0` par défaut.
- `static/js/socle/index.js` : `initAttente()` appelée une fois au chargement (comme `initJournal()`/`initialiserCcw()`), avant l'activation de l'onglet par défaut.
- `templates/fragments/onglets.html` : nouvel onglet `data-onglet="attente"` « En attente », juste après Résultats, avec `#badge-attente` (masqué par défaut, `display:none` tant que le compteur est à zéro — `decisionBadgeAttente`).
- `templates/fragments/onglet_attente.html` (nouveau fragment) + `templates/index.html` (inclusion + feuille de style) : panneau `#panneau-attente` / `#attente-liste`, suivant le patron des autres onglets de la refonte web.
- `static/css/attente.css` (nouveau, chargé en fin de cascade) : carte par élément, condition en encart ambré (même traitement que `.np-rappel-git`), badge compteur rouge cohérent avec `.pastille-notif`. Disposition en colonne unique avec `flex-wrap`, sans tableau ni défilement horizontal (contrainte 1360×768).
- Tests : `static/js/tests/attente.test.js` (nouveau, 12 scénarios Node) — `formaterDateAttente` (zéro-remplissage, absence), `decisionBadgeAttente` (seuil > 0), `descriptionLigneAttente` (replis titre/condition), `messageEchecAttente` (interprétation du corps JSON d'une réponse HTTP non-2xx, ces deux routes renvoyant 400/404/500 sur erreur contrairement à la convention `succes:false` + 200 des autres routes de l'inbox). `static/js/tests/pont_globales.test.js` : `attente` ajouté à la liste des onglets réels (`NOMS_ONGLETS`). Suite complète vérifiée verte : 216 tests Node (`node --test static/js/tests static/js/socle/tests`, y compris le garde-fou socle #653 et le garde-fou pont) et 152 tests Python (`pytest tests/`).
- `BRIDGE_AGENT_DOC.md` §3.16 : courte mention de l'onglet et de son fonctionnement (badge, Lancer, Supprimer) ajoutée en fin de section.
- Aucune modification côté serveur : `GET /issues-attente`, `POST /issues-attente/lancer`, `POST /issues-attente/supprimer` et `nb_en_attente` (issue #713) étaient déjà en place et inchangés.
- Point de vérification demandé par l'issue (neutralisation réseau #635 vs. l'incident « fichier reçu : mono.txt » observé pendant #713) : vérifié sans modification nécessaire. `tests/test_champ_attente_713.py` ne lance aucun sous-processus (appelle `traiter_fichier` directement en process) ; `utils._script_tests_direct()` le neutralise correctement que ce soit exécuté sous pytest ou en direct (`python3 tests/test_champ_attente_713.py`, confirmé par relecture de code et exécution réelle, aucune requête vers `localhost:5100` — le serveur réel tournait sur ce port pendant la vérification). Les sous-processus lancés par `tests/lancer_tous_les_tests.py` restent couverts : chaque fichier de test est son propre `__main__` sous `tests/`. `tests/test_neutralisation_notifs_reseau_635.py` (déjà existant) couvre explicitement `_notifier_fichier_recu` par interception d'`urlopen` — ré-exécuté, toujours vert. L'incident documenté dans l'issue provient très vraisemblablement d'une vérification manuelle ponctuelle hors du harnais de tests officiel (hors périmètre de cette issue : modification du comportement du watcher).

Hors périmètre (rappel de l'issue, non traité ici) : toute vérification automatique des conditions, le formulaire web, la modification du comportement du watcher.

# CHANGELOG-713 — à fusionner dans CHANGELOG.md

## 3 octobre 2026 — issue #713 (1/2)

§3.16 « Issues en attente » : **champ d'en-tête optionnel `ATTENTE` dans `issues_inbox/` qui met une issue de côté avant sa création, au lieu de la créer sur GitHub tout de suite** (issue #713, 1/2 — l'onglet web qui affichera ces éléments est l'objet de l'issue suivante, 2/2). Alain reçoit des issues à lancer tout de suite et d'autres à lancer plus tard (après la fusion d'une autre issue, après une vérification manuelle...) ; jusqu'ici rien ne distinguait les deux, les fichiers s'accumulaient dans `issues_inbox/` sans repère.

- `scripts/watcher_issues_inbox.py` : deux nouvelles fonctions pures, `lire_condition_attente()` (texte de la condition, ou `None` si champ vide/absent — miroir de `lire_champ_entete`) et `retirer_champ_attente()` (retire la ligne, reste intact — miroir de `retirer_ligne_entete`). `ATTENTE` ajouté à `CHAMPS_ENTETE`/`extraire_champs` pour que sa ligne soit nettoyée du corps comme les autres champs (y compris une valeur vide), sans jamais influencer les validations existantes. `ConfigInbox.en_attente_dir` (propriété dérivée d'`inbox_dir`, pas une clé `.conf`). Dans `traiter_fichier`, AVANT toute validation/création : un fichier mono-issue portant le champ est déplacé tel quel vers `issues_inbox/en_attente/` (suffixe numérique en cas de collision, ligne de journal `EN_ATTENTE`) ; pour un lot, chaque bloc concerné est écrit à part dans `en_attente/` avant tout traitement des autres blocs (rien ne peut se perdre), puis les blocs restants suivent `_traiter_lot` normalement — si aucun bloc ne reste, le fichier d'origine est supprimé. Cas limite documenté : si tous les blocs restants échouent ensuite, `_traiter_lot` déplace aussi le fichier d'origine entier vers `rejected/` (comportement #508 inchangé), qui contient alors un doublon sans conséquence des blocs déjà en attente. `issues_inbox/en_attente/` est un sous-dossier, déjà naturellement ignoré par `traiter_dossier()` (qui ne parcourt que les fichiers de la racine), exactement comme `rejected/`.
- `app/issues_inbox.py` : trois nouvelles routes — `GET /issues-attente` (liste du plus ancien au plus récent, `{id, titre, projet, date, condition}` par élément), `POST /issues-attente/lancer` (`{id}` validé comme simple nom de fichier sans séparateur de chemin ; retire le champ `ATTENTE` et réécrit le résultat dans `issues_inbox/` de façon atomique — fichier temporaire + `os.replace()` dans le même dossier, pour que le watcher ne lise jamais un fichier à moitié écrit — avant de supprimer l'élément d'`en_attente/` ; si l'écriture échoue, l'élément reste en place) et `POST /issues-attente/supprimer` (même validation, suppression simple, aucun archivage). `GET /issues-inbox/etat` étendu avec `nb_en_attente` (compteur durable relu du disque, jamais compté comme fichier à traiter) — ajouté à une route déjà interrogée en continu par le panneau « Watcher spool » plutôt que d'ouvrir un nouveau canal d'événements susceptible d'être manqué (cf. #705).
- `app/__init__.py` : les trois routes enregistrées avec la même protection `login_requis` que les routes voisines (`/issues-inbox/demarrer-watcher`, etc.).
- `BRIDGE_AGENT_DOC.md` §3 (tableau des champs d'en-tête) et nouvelle §3.16 : format du champ, comportement en lot, retrait au lancement, non-vérification automatique de la condition, formulaire web qui ignore cette convention. Consigne explicite aux Claude Chat : poser ce champ eux-mêmes dès qu'une issue est « à lancer après... », pas seulement le mentionner dans leur réponse.
- Tests : `tests/test_champ_attente_713.py` (nouveau, 23 scénarios) — fonctions pures (valeur présente/vide/absente, espaces superflus, casse, retrait, non-interférence avec les autres champs), watcher avec dossiers temporaires (mono avec/sans champ, lot mixte, lot entièrement en attente, collision de nom) et les trois routes avec le client de test Flask (liste triée, lancement sans boucle, écriture atomique sans résidu, suppression, identifiants invalides/introuvables/avec séparateur de chemin refusés). Aucun appel réseau ni `gh` réel (`_creer_issue`/`_issue_ouverte_meme_titre` substitués, leçon #702/#703/#710).

Hors périmètre (rappel de l'issue, non traité ici) : l'onglet web affichant ces éléments (issue 2/2), le formulaire web, toute vérification automatique des conditions.

## 3 octobre 2026 — issue #712

§16 « Agent Windows CCW » : **`AppExit 42 Exit` posé par défaut sur les services de projet dès leur création, documentation du modèle de démarrage à la demande** (issue #712, clôture du retrofit CCW ouvert par #709/#711). Le réglage `nssm set <service> AppExit 42 Exit` — validé en réel le 03/10/2026 sur `CCW-Watcher-Rummikub`/`-Scrabble`/`-Actualise` par pose manuelle — était jusqu'ici absent des scripts de provisioning : toute recréation d'un service de projet (nouveau projet, réinstallation Windows) l'aurait silencieusement remis en mode « toujours actif ».

- `provisioning/windows/ajouter_projet_ccw.ps1` : ajout de `nssm set $NomService AppExit 42 Exit` juste après `AppExit Default Restart` (qui reste en place pour les vrais plantages). Commentaires d'en-tête (ex-lignes 19-22) mis à jour : le code 42 signale l'auto-extinction après inactivité (#199/#200), le service reste éteint et est rallumé à la demande, jamais par une boucle NSSM.
- `provisioning/windows/provisionner.ps1` (service de base `CCW-Watcher`) : **aucun** `AppExit 42 Exit` posé — ajout d'un commentaire (avant la section 10, service NSSM) expliquant pourquoi ce service reste volontairement toujours actif : (1) canal central des issues `for-windows` des projets sans service CCW dédié, où le démarrage à la demande ne trouverait aucun service à rallumer ; (2) réception des délégations CCL→Windows créées par `gh issue create` direct (ex. #692), qui ne déclenchent aucun démarrage à la demande.
- `BRIDGE_AGENT_DOC.md` §16 : nouvel encadré décrivant le modèle complet (service de projet « à la demande » vs `CCW-Watcher` toujours actif et pourquoi), les trois points d'entrée de rallumage (formulaire web #709, `issues_inbox/` + relance #711), les deux limites connues (création directe par `gh issue create` ; `new_issue.py` natif Windows sans hôte SSH configuré) et leur repli manuel, ainsi que la commande de retour arrière (`nssm set <service> AppExit 42 Restart`). Table de provisioning (`ajouter_projet_ccw.ps1`) mise à jour pour refléter le nouveau réglage par défaut.
- `provisioning/windows/REINSTALLATION_CCW.md` §7 : même encadré (modèle à la demande, exception du service de base, limites, retour arrière) appliqué au contexte d'une réinstallation complète, où les services dédiés sont recréés à zéro.
- Vérifié sans modification nécessaire : `mettre_a_jour_tokens_ccw.ps1` et `finaliser_projet_ccw_auto.ps1` ne touchent qu'à `AppEnvironmentExtra` (tokens/PATH) puis redémarrent le service — aucun `nssm install`/`remove`/`AppExit` dans leur code, donc aucun risque de régression sur le réglage posé par `ajouter_projet_ccw.ps1`.
- CCL ne peut pas exécuter PowerShell/NSSM : cohérence vérifiée par relecture complète des deux scripts (diff de commandes, BOM UTF-8 préservé) et de `app/ccw.py` / `app/issues.py` / `scripts/watcher_issues_inbox.py` (mécanisme de démarrage à la demande déjà en place, #709/#711) ; validation réelle du réglage par défaut à faire lors d'une prochaine recréation de service.

## 3 octobre 2026 — issue #711

§16 « Agent Windows CCW » : **démarrage à la demande du service CCW depuis `issues_inbox/` (création et RELANCE) et depuis la relance de l'interface** (issue #711, étape D du retrofit CCW, suite de l'étape C/#709 qui ne couvrait que le formulaire web — plus de 99 % des issues d'Alain passent par `issues_inbox/`, chemin critique jusqu'ici non couvert).

- `scripts/watcher_issues_inbox.py`, création (`_traiter_bloc`) : l'appel à `redemarrer_si_eteint()` (watcher CCL, issue #486) devient conditionnel au label de l'issue créée — `for-linux` inchangé, `for-windows` démarre à la place le service CCW via `app.ccw.demarrer_service_ccw_arriere_plan` (#709) et ne démarre plus à tort le watcher Linux. Une ligne de journal par tentative ; un échec du démarrage CCW n'empêche jamais la création de l'issue.
- Même fichier, chemin RELANCE (`_traiter_relance`) : même distinction, en lisant les labels sur l'issue GitHub relancée (déjà rapatriés par `_recuperer_issue`, pas de nouvel appel `gh`). Le commentaire de trace posté à la relance ne contient pas le résultat du démarrage CCW (asynchrone, thread démon) — seul le redémarrage du watcher CCL (for-linux) y est tracé, comme avant.
- `app/interruption.py::route_relancer` : ajout de la branche `for-windows` (appel non bloquant à `demarrer_service_ccw_arriere_plan`), symétrique de la branche `for-linux` existante (#574) — labels déjà transmis par le front, aucune lecture supplémentaire nécessaire.
- Bug corrigé au passage dans `app/ccw.py` (découvert en écrivant les tests de ce chemin, point 4 de l'issue) : `_preparer()`/`_lister_projets_vm()` construisaient leur réponse d'erreur avec `jsonify(...)`, qui lève `RuntimeError: Working outside of application context` hors contexte Flask — précisément le cas du thread démon de `demarrer_service_ccw_arriere_plan` (#709) et de tout appel depuis `scripts/watcher_issues_inbox.py` (process sans Flask). Nouveau `_reponse_erreur_ssh()` : `jsonify(...)` si un contexte applicatif est actif (toutes les routes — comportement strictement inchangé), sinon un substitut minimal `_ReponseErreurSansContexte` (même interface `.get_json()`). Sans ce correctif, une issue `for-windows` déposée pour un projet sans SSH configuré aurait fait planter silencieusement le thread de démarrage (trace uniquement dans les logs du process, jamais remontée) au lieu du « ignoré silencieusement » attendu.
- Tests : `tests/test_demarrage_ccw_issues_inbox_711.py` (nouveau, chemin création + vérification de l'import de `app.ccw` sans contexte Flask) ; `tests/test_champ_relance_516.py` (nouveau scénario for-windows + labels `for-linux` ajoutés aux fixtures existantes, devenues sélectives) ; `tests/test_relancer_watcher_574.py` (scénario for-windows étendu). SSH et `gh` entièrement simulés partout (leçon #702/#703).

Hors périmètre (rappel de l'issue, non traité ici) : réglages NSSM des autres services, scripts de provisioning, création directe par `gh issue create`, préservation d'`AppExit` au re-provisioning (étape B).

## #710 — Garde-fou : les faux exécutables de tests ne peuvent plus laisser passer un appel vers le vrai GitHub

Suite à l'incident du 03/10/2026 (`test_projet_ccw_559.py` lancé sur CCW :
faux `gh` en script bash inopérant sous Windows → le vrai `gh.exe` a créé
deux VRAIES issues sur `AlainDelree/Bridge_Agent`, traitées ensuite par le
watcher). Les issues #704/#706 avaient déjà réglé le cas Windows (skip
`os.name == "nt"`) ; défense en profondeur ici pour toute AUTRE raison
possible (point de montage `noexec`, PATH inhabituel, future plateforme).

- Nouveau `tests/garde_fou_faux_executables.py` :
  `verifier_faux_executables_actifs(bin_dir, noms)` — à appeler juste après
  avoir placé `bin_dir` en tête du PATH, vérifie que CHAQUE commande de
  `noms` (`gh`, `git`, `claude`, `powershell`) résout bien DANS ce
  répertoire (`shutil.which` + comparaison du parent résolu). Échec fermé :
  lève `RuntimeError` avant le moindre appel réel si une seule commande
  échappe au faux. Intégré à `test_creation_bootstrap_ccw_556.py`,
  `test_projet_ccw_559.py`, `test_verrou_refus_precoce_584.py`,
  `test_init_git_local_258.py` (scénario faux `git`),
  `test_lecture_active_327.py`, `test_nettoyage_arbre_247.py`,
  `test_orphelin_verrou_perime_322.py` et
  `test_worktree_parallelisation_337.py` — tous les fichiers de tests
  s'appuyant sur un faux exécutable bash.
- `test_projet_ccw_559.py` et `test_creation_bootstrap_ccw_556.py` :
  remplacement du VRAI dépôt `AlainDelree/Bridge_Agent` par un dépôt
  fictif (`AlainDelree/depot-inexistant-test559`/`…test556`, même
  convention que `test_init_git_local_258.py`/`test_verrou_refus_precoce_584.py`)
  dans tous les scénarios concernés, y compris la config `bridge_agent`
  simulée (`_config_bridge_agent`) qui est le dépôt réellement ciblé par
  `gh issue create` dans le flux bootstrap — assertions adaptées en
  conséquence, aucun autre changement de logique.
- `test_projet_ccw_559.py`/`test_creation_bootstrap_ccw_556.py` : séparateur
  de PATH codé en dur (`:`) remplacé par `os.pathsep` (seule différence
  pratique sous Windows, déjà hors de portée de ces deux fichiers qui
  s'ignorent entièrement sous `os.name == "nt"` — corrigé par cohérence).
- Aucun code de production modifié. Suite complète (`lancer_tous_les_tests.py`)
  verte : 38/38 fichiers.

## 3 octobre 2026 — issue #709

§16 « Agent Windows CCW » : **démarrage à la demande du service CCW depuis le formulaire web** (issue #709, étape C du retrofit CCW, suite de l'étape A réelle sur `CCW-Watcher-Rummikub` — `AppExit 42 Exit` fait qu'un watcher CCW éteint par auto-extinction après inactivité n'est plus relancé par NSSM). Création d'une issue `for-windows` quand le service est éteint : `app/issues.py::envoyer()` le démarre désormais lui-même, symétrique de `redemarrer_si_eteint()` (for-linux), sans jamais bloquer ni faire échouer la réponse HTTP. Extraction d'une fonction PURE `app.ccw._piloter_service_ccw_action` (nom de projet + action nssm → résolution du service exact + exécution SSH + résultat structuré) depuis l'ancienne route `_piloter_service_ccw`, dont le comportement reste STRICTEMENT inchangé (vérifié par test) ; nouvelle option `eviter_si_deja_dans_cet_etat` (idempotence sans aller-retour SSH superflu, utilisée uniquement côté démarrage à la demande). Nouveau `app.ccw._demarrer_service_ccw_sync` (cœur testable sans thread : déjà en marche → rien, hôte SSH non configuré/projet sans service CCW → ignoré silencieusement, STOP_PENDING → une seule nouvelle tentative, jamais de boucle) et `demarrer_service_ccw_arriere_plan` (thread démon, bornés par les timeouts SSH déjà en place) pour ne jamais retarder la création d'issue. Champ `ccw_demarre` ajouté à la réponse JSON de `/envoyer`, analogue à `watcher_demarre` — toujours `None` par construction (le démarrage étant asynchrone, son résultat réel n'est connu que du journal serveur, jamais de la réponse HTTP elle-même ; limite assumée, documentée dans le code). Tests (`tests/test_demarrage_ccw_a_la_demande_709.py`) : SSH entièrement simulé, aucune vraie connexion ni vrai `gh`.

## #706 — Issue H (suite) : `valider_repo_cible` sous Windows, test #584, lanceur verbeux sur échec

Suite à la validation réelle du lanceur de tests (#704) sur CCW le
03/10/2026 : 35/37 fichiers réussis, 2 échecs identifiés et corrigés ici.

- `watcher.py::valider_repo_cible` (~ligne 1694) : la vérification de
  propriétaire (`resolu.stat().st_uid != os.getuid()`) plantait sous Windows
  avec `AttributeError: module 'os' has no attribute 'getuid'`, faisant
  échouer tout `REPO_CIBLE` pourtant valide (`tests/test_champ_relance_516.py`,
  scénario « REPO_CIBLE valide accepté avec PERIMETRE_DYNAMIQUE »). Même
  garde que `valider_sous_dossier` : sous `os.name == "nt"`, la vérification
  de propriétaire est ignorée (les trois autres contrôles — absolu,
  canonique, dossier existant — restent appliqués). Comportement Linux
  strictement inchangé.
- `tests/test_verrou_refus_precoce_584.py` : les scénarios
  `scenario_refus_precoce_libere_verrou` et
  `scenario_echec_rapide_sans_travail_libere_verrou` fabriquent de faux
  `gh`/`claude` en scripts bash, non exécutables sous Windows — les vrais
  outils auraient été appelés contre un dépôt fictif. Ajout d'un garde
  `os.name == "nt"` en tête de ces deux scénarios (même style de message
  « ignoré : ... non applicable sous Windows » que `scenario_pid_mort_*`
  dans ce même fichier). Les deux autres scénarios (sonde PID, sans faux
  exécutable) restent inchangés et continuent de s'exécuter sous Windows.
- `tests/lancer_tous_les_tests.py` : pour un fichier en échec, affiche
  désormais les lignes portant le marqueur `✗` ou le résumé
  « scénario(s) en échec », ou à défaut les 15 dernières lignes de sa
  sortie — au lieu de la seule dernière ligne non vide, qui pouvait n'être
  que du bruit normal émis par un scénario qui passe (cas réel : 516
  affichait « configs/bridge_agent.conf illisible », pas la vraie cause).
  Les fichiers réussis gardent une seule ligne de résumé.

Validé sur Linux (37/37, suite complète + fichiers ciblés). CCL ne peut pas
exécuter Windows : validation réelle à faire à la main sur CCW.

## #705 — Résultats : resynchroniser la liste au retour de l'onglet au premier plan et après une reconnexion SSE

- Front-end uniquement, comme demandé. Constat : la liste Résultats n'est
  alimentée que par les événements `/stream` ciblés (`creation_issue`,
  `debut_issue`, `fin_issue`, traités par `traiterNotif` dans
  `static/js/resultats.js`) — un événement manqué (onglet masqué, coupure
  réseau, redémarrage de `new_issue.py`) la laisse périmée indéfiniment,
  sans aucun rejeu côté serveur.
- Deux fonctions pures ajoutées à `static/js/resultats.js` (testées sous
  Node, `static/js/tests/resultats.test.js`), isolant la décision
  « faut-il resynchroniser (↻) ? » :
  - `fautResynchroniserApresMasquage(dureeMasqueeMs, seuilMs = SEUIL_RESYNC_MASQUAGE_MS)`
    — `SEUIL_RESYNC_MASQUAGE_MS = 30000` (30 s).
  - `fautResynchroniserApresReconnexionSse(premiereOuverture)` — ne resync
    que sur une RECONNEXION, jamais à la toute première ouverture (pas de
    double chargement au démarrage de la page).
- `static/js/socle/sse.js::creerCanalSse().connecter()` accepte désormais un
  paramètre optionnel `{ onOuvert }` (surcharge celui, le cas échéant, passé
  à la construction du canal) — nécessaire pour que `resultats.js` y
  branche sa propre logique de reconnexion sans coupler ce module générique
  à une logique métier.
- `static/js/resultats.js::initialiser()` : `sse.stream.connecter({ onOuvert:
  surOuvertureSse })` — `surOuvertureSse` distingue première ouverture et
  reconnexion (drapeau module `sseDejaOuverte`) et déclenche le ↻ via le pont
  (`appelerAncien('resynchroniserResultatsAuRetour')`) uniquement sur
  reconnexion.
- `static/js/app.js` :
  - Nouvelle fonction `resynchroniserResultatsAuRetour()` : garde anti-rafale
    simple (ne relance pas si un rafraîchissement est en cours ou vient
    d'avoir lieu, `DELAI_MIN_ENTRE_RESYNCS_AUTO_MS = 5000`), puis appelle
    `rafraichirResultats()` — le même rafraîchissement que le bouton ↻.
    Utilisée par les deux déclencheurs (retour d'onglet, reconnexion SSE),
    donc partagée entre les deux.
  - Gestionnaire `visibilitychange` (`demarrerCycleVie`) : mémorise
    l'horodatage de masquage (`momentMasquageOnglet`) ; au retour au premier
    plan, conserve l'appel existant à `envoyerHeartbeat()` puis, si la durée
    masquée dépasse le seuil (`window.Bridge.resultats.fautResynchroniserApresMasquage`),
    déclenche `resynchroniserResultatsAuRetour()`. Comportement inchangé tant
    que l'utilisateur reste sur la page (durée masquée nulle → pas de resync).
- `fautResynchroniserApresMasquage` publiée sous
  `window.Bridge.resultats` (pont, issue #625/#632) pour être consommée par
  l'ancien `app.js`, classique et non importable en module ES — même
  convention que `calculerBadgeModele`/`calculerBadgeSansRedacteur`.

## 3 octobre 2026 — issue #704

Suite de tests exécutable sous Windows (plan hybride, issue H) : ajout de `tests/lancer_tous_les_tests.py`, lanceur unique qui exécute chaque `tests/test_*.py` dans un sous-processus avec `PYTHONUTF8=1` forcé (sans quoi une sortie redirigée fait planter chaque script sur les symboles ✓/✗/❌ sous Windows, même famille que #686/#688), délai maximal par fichier, une ligne de résumé par fichier puis un résumé global, code de sortie non nul si au moins un fichier échoue ; mentionné dans `provisioning/windows/NEW_ISSUE_LOCAL_WINDOWS.md` (§3, vérifier une installation). Ajout de `requirements-dev.txt` (`pytest`, utilisé par plusieurs tests) et d'un pointeur depuis `requirements.txt`. Correction des 4 échecs réels identifiés par lecture du code (29-30/09/2026 sur CCW) : `test_champ_relance_516.py` utilise désormais un chemin `REPO_CIBLE` absolu neutre vis-à-vis de l'OS (`tempfile.gettempdir()`) au lieu de `/home/alain/Autre_Projet` codé en dur ; `test_creation_bootstrap_ccw_556.py` et `test_projet_ccw_559.py` s'ignorent désormais proprement sous Windows (convention déjà en place sur `327`/`247`/`322`/`337`), leurs scénarios reposant sur de faux `gh`/`powershell` shebang bash et sur `openssl` réel via PATH ; `test_init_git_local_258.py` n'ignore que son unique scénario dépendant d'un faux `git` shebang bash (timeout de push), les 4 autres scénarios du fichier restant exécutés sous Windows. Aucun code de production modifié.

## #701 — « Interrompre » un watcher Windows natif via le Job Object persistant (suite #695)

- #695 avait livré le côté producteur (`watcher.py`, déjà en master) : création
  d'un Job Object **persistant et nommé** (`nom_job_watcher_windows`) au
  démarrage du watcher sous Windows, auto-assignation du watcher (toute sa
  descendance en hérite automatiquement, claude compris). #701 livre le côté
  consommateur, dans `app/interruption.py` uniquement.
- `interrompre_linux` (nom historique — gère en réalité le watcher **local**,
  quel que soit son OS ; `interrompre_windows` reste le chemin **délégué**
  par SSH vers le PC fixe CCW, pour les issues `for-windows`, inchangé)
  bascule désormais sur une branche `os.name == "nt"` pour reconstruire/
  arrêter l'arbre de process : `/proc` (PPID) sous Linux, appartenance au Job
  Object persistant sous Windows (pas de `CreateToolhelp32Snapshot`, pas de
  dépendance externe).
- Nouvelles fonctions Windows (`app/interruption.py`) :
  - `_cmdline_windows(pid)` : nom de l'image du process (`QueryFullProcessImageNameW`,
    droits minimaux) pour l'affichage — pas de ligne de commande complète
    (demanderait une énumération de processus séparée, hors de portée de
    ctypes seul ; solution la plus simple retenue, comme demandé).
  - `_arreter_arbre_windows(cfg)` : rouvre le Job **par nom**
    (`OpenJobObjectW`, droits minimaux QUERY+TERMINATE), liste ses PID
    membres (`QueryInformationJobObject`/`JobObjectBasicProcessIdList`) pour
    l'affichage, tue tout via `TerminateJobObject`, ferme le handle dans tous
    les cas. Renvoie les mêmes noms d'étape que la branche Linux
    (`arreter_arbre_watcher`/`attente_fin_process`), même contrat à trois
    statuts (succes/rien_a_faire/echec).
- Cas limites gérés : Job introuvable (watcher déjà mort, ou lancé avant
  #695 sans job persistant) → `rien_a_faire`, jamais `echec` ; liste de PID
  tronquée (plus de membres que `_CAPACITE_PID_JOB_PERSISTANT`) → signalée
  dans le message, mais `TerminateJobObject` agit quand même sur tout le job
  (il n'a pas besoin de connaître les PID un par un, à la différence de
  l'énumération d'affichage) ; échec de `TerminateJobObject` → `echec` sur
  les deux étapes, handle quand même fermé (pas de fuite) ; process encore
  listé comme vivant après la fenêtre d'attente de 5s → `echec`, verrou NON
  nettoyé (même garde-fou que côté Linux).
- Comportement Linux strictement inchangé (code Windows entièrement derrière
  `os.name == "nt"`, aucune modification du bloc `/proc` existant — juste
  réindenté sous un `else`). `watcher.py` non modifié (côté producteur #695
  déjà en place, aucun bug constaté en le relisant).
- Tests : `tests/test_interruption_windows_701.py` — mock de `ctypes.windll`
  (`create=True`) + `os.name` forcé à `"nt"`, même pattern que
  `tests/test_nettoyage_arbre_windows_249.py` : job introuvable, succès
  (liste + terminaison), liste tronquée, échec de `TerminateJobObject`,
  process survivant après la fenêtre d'attente, et aiguillage par OS de
  `interrompre_linux` (monkeypatch, sans exécuter de vrai code ctypes
  Windows). Ces tests vérifient les appels ctypes, pas le comportement réel
  de Windows — à valider à la main sur CCW (procédure ci-dessous).

**Procédure de test manuel sur CCW** (à faire à la main, aucun test
automatisé ne peut la remplacer depuis Linux) :
1. Sur le PC fixe Windows, démarrer un watcher local pour un projet (pas via
   la délégation CCW habituelle) — vérifier dans ses logs qu'il journalise
   bien la création du Job persistant (`_preparer_job_persistant_windows`).
2. Depuis `new_issue.py` tournant sur ce même PC, envoyer une issue qui
   déclenche une tâche longue (ex. `sleep`/boucle) pour ce projet.
3. Une fois la tâche en cours, cliquer « Interrompre » sur l'issue dans
   l'onglet Résultats.
4. Vérifier : la réponse liste bien les PID (watcher + claude + descendance)
   avec leur image ; dans le Gestionnaire des tâches, **tout l'arbre**
   disparaît (watcher compris) ; aucun process résiduel ne reste accroché
   après quelques secondes.
5. Relancer le même scénario avec un watcher démarré **avant** le déploiement
   de #695 (pas de Job persistant) pour confirmer le repli en `rien_a_faire`
   (pas de plantage, pas de `echec` trompeur).

## #700 — [fermé]/[ouvert] toujours visible en fin de ligne, même titre tronqué

- Bug : numéro, titre et suffixe `[fermé]`/`[ouvert]` étaient concaténés
  dans un seul span `ligne-texte` (`static/js/app.js`), tronqué par
  l'ellipsis CSS (`overflow:hidden;text-overflow:ellipsis;white-space:
  nowrap`). Pour un titre assez long, l'ellipsis coupait avant d'atteindre
  `[fermé]`/`[ouvert]`, qui disparaissait alors complètement de la ligne.
- `static/js/app.js` (~ligne 913) : le suffixe `[fermé]`/`[ouvert]` sort
  du span `ligne-texte` (qui ne garde que `#N — ` + titre) et devient un
  span `ligne-etat` distinct, placé juste après.
- `static/css/resultats.css` : nouvelle règle `.ligne-issue .ligne-etat`
  avec `flex-shrink:0;white-space:nowrap` pour ne jamais être rogné par
  l'ellipsis. Les règles de couleur/barré de `.resultat-traite` (normal,
  hover, sélectionnée) étendues à `.ligne-etat` pour rester cohérentes
  avec `.ligne-texte` (le comportement visuel sur une ligne cochée/
  traitée reste identique à avant, juste réparti sur deux spans).
- Résultat : sur une ligne de titre long, le titre se tronque avec une
  ellipsis (…), mais `[fermé]`/`[ouvert]` reste toujours visible en fin
  de ligne, quelle que soit la longueur du titre.

## #699 — 4e option S=Silence au contrôle de son par issue (G/P/C existants inchangés)

- Besoin : couper le bip pour UNE issue précise, sans toucher à
  l'interrupteur global ni aux autres issues — 4e option à côté des 3
  déjà là (Global/Plat/Cloche), aucune ne disparaît.
- `etat_son_issue.py` : `SONS_VALIDES` étendu à `("plat", "cloche",
  "silence")`. Le module était déjà générique sur les valeurs de
  `SONS_VALIDES` (`son_choisi`, `sons_projet`, `definir_son`,
  `nettoyer_projet`, `nettoyer_entrees_perimees`) : aucun changement
  supplémentaire nécessaire, confirmé par les tests.
- `app/son_issue.py` (routes `GET`/`POST /son-issue/...`) : déjà générique
  via `SONS_VALIDES`, confirmé sans modification de logique (juste le
  docstring mis à jour).
- `scripts/traitement_fin.py::main()` : quand `son_a_jouer()` renvoie
  `"silence"`, aucun bip n'est joué (ni `bip()` ni `bip_plat()`) — le POST
  `notifier_fin_issue` (rafraîchissement SSE de l'onglet Résultats) reste
  appelé normalement, inchangé. Le canal ntfy (`notifications_poller.py`)
  n'est pas concerné par ce script et reste lui aussi inchangé : silence =
  coupe uniquement le son audible de CETTE issue.
- `static/js/actions_ligne.js` : 4e bouton `S` dans `boutonsSonLigne`/
  `rendreControleSonLigne`, état `silence` dans `etatsOptionsSonIssue`,
  normalisation dans `normaliserChoixSonIssue`/`sonIssueDepuisReponse`/
  `fusionnerSonsProjet`/`sonConnuDansCache` — même traitement que
  `'plat'`/`'cloche'`. Infobulle : « Son de cette issue : Silence — clic
  pour changer ».
- `static/css/resultats.css` : contrôle `.ligne-son-opt` pensé compact
  pour une largeur de ligne contrainte (issue #633) — padding horizontal
  resserré (4px→3px) pour absorber la largeur du 4e bouton sans casser la
  mise en page, plutôt que renoncer à la fonctionnalité.
- Tests : `tests/test_son_issue_630.py` (3 scénarios ajoutés — `definir_son`
  accepte `"silence"`, `son_a_jouer` le priorise par issue seule sur
  l'interrupteur global, `main()` ne joue aucun bip mais notifie quand même)
  et `static/js/tests/actions_ligne.test.js` (4e état couvert dans chaque
  fonction pure concernée) — tous passent (20/20 JS, 20/20 Python).
- Doc : `ARCHITECTURE.md`/`BRIDGE_AGENT_DOC.md` — mentions du contrôle
  « G/P/C » à 3 états mises à jour en « G/P/C/S » à 4 états.

## #698 — Suppression du doublon de logs des watchers locaux (suite #696)

- Diagnostic #696 confirmé : `app/watchers.py::demarrer_watcher()` redirige
  déjà stdout/stderr du process `watcher.py` lancé vers `cfg.fichier_log`,
  mais `watcher.py::configurer_logs()` ajoutait en plus un
  `StreamHandler(sys.stdout)` à côté du `FileHandler` — une fois stdout
  redirigé par le parent vers ce même fichier, chaque ligne de log s'y
  écrivait deux fois. Régression #682 (avant, `systemctl --user` envoyait
  stdout/stderr vers le journal systemd, jamais vers ce fichier).
- Correction : retrait de `logging.StreamHandler(sys.stdout)` de la liste
  `handlers` dans `configurer_logs()` (`watcher.py`), ne conserve que
  `handler_fichier`. Le filet de sécurité de la redirection stdout/stderr
  côté `app/watchers.py::demarrer_watcher()` reste intact pour la fenêtre
  avant `configurer_logs()` (crash très précoce) — pas de duplication
  possible à ce stade puisque rien d'autre n'écrit dans le fichier.
- `_forcer_utf8(sys.stdout/stderr)` conservé (toujours utile pour ce filet
  de sécurité et pour NSSM côté CCW) ; commentaire de `configurer_logs()`
  mis à jour en conséquence.
- Vérifié : aucun test ni autre code ne dépend d'une capture de logs sur
  stdout pour `watcher.py` (seul `scripts/watcher_issues_inbox.py`, hors
  périmètre de cette issue, a son propre `configurer_logs()` distinct avec
  un `StreamHandler` mais sans `FileHandler` — pas concerné par le doublon).

# CHANGELOG-694

## Issue #694 — Issue F (plan hybride Windows) : app/issues_inbox.py portable

- `demarrer_watcher_inbox()` (app/issues_inbox.py) : `subprocess.Popen(...,
  start_new_session=True)` était POSIX-only et levait une exception sous
  Windows. Remplacé par une branche `os.name == "nt"` utilisant
  `CREATE_NEW_PROCESS_GROUP`, même pattern que `watcher.py::lancer_claude`
  (déjà suivi par l'issue D pour `app/watchers.py`). Comportement Linux
  inchangé.
- Ajout d'un commentaire bref aux deux appels `os.kill(pid, signal.SIGTERM)`
  (`demarrer_watcher_inbox`, `arreter_watcher_inbox`) confirmant leur
  compatibilité Windows (CPython route SIGTERM vers `TerminateProcess()`,
  hors du piège `os.kill(pid, 0)`/`CTRL_C_EVENT` découvert issue #682) —
  aucun changement de code sur ce point, juste une note pour éviter une
  future modification par réflexe.

## #693 — Portée de `surveiller_transitions()` alignée sur `_lister_issues_labels()` (SSE, auto-refresh)

- Constat : le poller de notifications (`app/notifications_poller.py`)
  limitait la LISTE des issues surveillées (et donc le SSE `fin_issue`/
  `debut_issue` qui déclenche le rafraîchissement automatique de l'onglet
  Résultats) à un seul label (`BRIDGE_NOTIF_SCOPE`, `for-windows` par
  défaut) — alors que le chargement manuel de la même liste
  (`app.issues._lister_issues_labels()`, issue #479/#183) fusionne
  volontairement les deux labels (`for-linux` ET `for-windows`). Une issue
  #692 (`for-windows`) créée directement par `gh issue create` n'avait donc
  déclenché aucun rafraîchissement automatique sur l'instance Linux, alors
  qu'elle apparaît normalement dans la liste après un rafraîchissement
  manuel.
- Correction : `_balayage_initial()` (via la nouvelle `_labels_scope()`) et
  `ajouter_issue_surveillee()` (via `_dans_la_portee()`) surveillent
  désormais TOUJOURS les deux labels bridge, pour chaque projet configuré —
  seul `BRIDGE_NOTIF_SCOPE=off` coupe entièrement la surveillance.
- `BRIDGE_NOTIF_SCOPE` ne restreint plus que le BIP/bulle/ntfy réellement
  émis par ce poller (nouvelle `_bip_dans_la_portee()`, appelée dans
  `_traiter_transition`) — anti-doublon avec le watcher local (issue #187,
  point 4) conservé à l'identique : le SSE peut désormais se déclencher une
  seconde fois, silencieusement, pour une issue déjà notifiée par le
  watcher local, sans bip supplémentaire.
- Paramètres `BRIDGE_NOTIF_INTERVALLE`/`_RECENCE_MIN`/`_ESPACEMENT` vérifiés :
  aucun n'a été calibré en supposant un seul label (ils opèrent par issue
  déjà surveillée, pas par label), donc aucun ajustement nécessaire — le
  volume d'issues CCW/CCL simultanément surveillées reste faible en
  pratique.
- Tests : `tests/test_poller_issues_ccw_624.py` mis à jour (3 scénarios
  adaptés à la nouvelle portée toujours-deux-labels + 1 nouveau scénario
  couvrant directement le fix : SSE déclenché pour une issue hors
  `BRIDGE_NOTIF_SCOPE`, bip filtré) — 11 scénarios, tous verts.

## #691 — Idempotence règle pare-feu de `provisionner_new_issue_local.ps1`

- Correction : `Get-NetFirewallRule` (vérification) et `New-NetFirewallRule`
  (création) utilisaient deux noms différents (`-Name` interne vs
  `-DisplayName` réel), rendant la vérification d'idempotence inopérante.
  Unifié sur un seul nom (`Bridge Agent new_issue.py ($Port/tcp)`), vérifié
  et créé via `-DisplayName` dans les deux cas.
- Le nettoyage des deux règles en doublon existantes sur CCW (`Bridge Agent
  - new_issue.py` et `Bridge Agent new_issue.py (5100/tcp)`) ne peut pas être
  fait depuis ce worktree Linux (aucun accès à la machine Windows physique) —
  délégué via une issue `for-windows`.

## #690 — Provisioning pour new_issue.py natif sur Windows (plan hybride)

Suite à la première exécution native de `new_issue.py` sur le PC fixe
Windows (CCW) le 28/09/2026 (validation de l'issue D), faite entièrement à
la main : dépendances Python installées manuellement (aucun
`requirements.txt`), `gh auth login` fait à tâtons (session interactive
distincte du `GH_TOKEN` du service `CCW-Watcher`), règle de pare-feu créée
à la main pour le port 5100 entrant. Avant le changement de PC prévu d'ici
1-2 mois, capitalisation de cette expérience pour la prochaine machine.

- **`requirements.txt`** (nouveau, racine du dépôt) : dépendances Python
  propres à `new_issue.py`/`app/` — `flask>=3.1`, `werkzeug>=3.1` (seules
  dépendances non-stdlib trouvées après relecture des imports ; `watcher.py`
  n'en a besoin d'aucune, déjà couvert par `provisionner.ps1`).
- **`provisioning/windows/provisionner_new_issue_local.ps1`** (nouveau,
  BOM UTF-8) : script idempotent dédié à cet usage précis (distinct de
  `provisionner.ps1`, qui provisionne le service `CCW-Watcher` headless) —
  `pip install -r requirements.txt`, règle de pare-feu entrante TCP/5100
  (`Get-NetFirewallRule` avant `New-NetFirewallRule`), vérification de
  `gh auth status` avec invite à lancer `gh auth login` si besoin
  (authentification elle-même non automatisée — interaction humaine
  requise). Nécessite une console administrateur (`New-NetFirewallRule`) ;
  suppose Python et `gh` déjà installés (cf. `provisionner.ps1` sinon).
- **`provisioning/windows/NEW_ISSUE_LOCAL_WINDOWS.md`** (nouveau) :
  documente l'usage du script ci-dessus ainsi que l'alias PowerShell
  `bridge` (fonction dans `$PROFILE` lançant `new_issue.py --lan` d'une
  commande) — volontairement non automatisé (modification du profil
  personnel de l'utilisateur), commande prête à copier-coller.

Résultat : sur une machine Windows neuve, `provisionner_new_issue_local.ps1`
puis `gh auth login` (à la main) suffisent pour que `new_issue.py --lan`
fonctionne directement, sans repasser par le diagnostic pare-feu/dépendances
du 28/09/2026.

Fichiers touchés : `requirements.txt` (nouveau),
`provisioning/windows/provisionner_new_issue_local.ps1` (nouveau),
`provisioning/windows/NEW_ISSUE_LOCAL_WINDOWS.md` (nouveau).

## #689 — Informer chaque tentative de son rang et lui faire reconnaître le travail d'une tentative précédente dans le même worktree

Constaté à plusieurs reprises (dernier cas net : #687, « Durée réelle :
356s (TIMEOUT courant : 300s) ») : la tentative 1 termine réellement le
travail (commits inclus) mais dépasse le TIMEOUT de peu et se fait tuer
avant de pouvoir le rapporter. Le watcher relance alors la tentative 2 dans
le même worktree (les commits de la tentative 1 y sont déjà présents), mais
`lancer_claude()` ne recevait pas le numéro de tentative en paramètre :
chaque essai recevait exactement le même prompt, sans savoir qu'un essai
précédent avait pu réussir juste avant d'être interrompu — la tentative 2
décrivait alors le travail déjà fait comme une « exécution antérieure »
ambiguë, sans jamais faire le lien avec sa propre tentative précédente.

- `lancer_claude()` reçoit désormais `tentative` (1 = première), `max_tentatives`
  (`None` si issue critique = essais illimités) et `tete_avant_traitement` (SHA de
  `HEAD` capturé avant la toute première tentative de ce traitement).
- `_demarrer_traitement()` capture ce SHA via `_tete_git(cwd_effectif)`, en
  mode écriture uniquement (seul mode qui produit des commits) et hors
  dry-run — retourné en 5e élément du tuple, propagé par
  `_traiter_issue_synchrone` à chaque `_executer_une_tentative`.
- À partir de la tentative 2, `lancer_claude()` injecte dans le prompt un
  bloc dédié (après la clause worktree, avant le garde-fou de mode) : il
  indique le rang de la tentative en cours, et explique que des commits déjà
  présents et absents du SHA `tete_avant_traitement` proviennent très
  probablement de sa propre tentative précédente pour cette même issue,
  tuée par le TIMEOUT juste après avoir fini son travail — à vérifier plutôt
  qu'à refaire, et à signaler explicitement comme telle (pas comme une
  « exécution antérieure » non identifiée) dans le rapport final.
- Tentative 1 (comportement par défaut, valeurs par défaut des nouveaux
  paramètres) : aucun bloc injecté, prompt inchangé.

Fichiers touchés : `watcher.py` (`lancer_claude`, `_executer_une_tentative`,
`_demarrer_traitement`, `_traiter_issue_synchrone`).

## #687 — Favicon bleu distinct quand `new_issue.py` tourne nativement sur Windows

Trois interfaces web coexistent maintenant dans le navigateur d'Alain :
Bridge_Agent Linux (rouge, existant), Relecture_Bridge (vert) et désormais
Bridge_Agent tournant nativement sur Windows (issue D) — sans distinction
visuelle possible entre les deux premières instances Bridge_Agent puisque
le favicon SVG était un fichier unique et statique, indépendant de l'OS.

- **`static/img/favicon-windows.svg`** (nouveau) : même forme de pont
  stylisé que `favicon.svg`, couleur bleu Windows `#0078D4` à la place du
  rouge `#C0645C`. `favicon.svg` (Linux) reste inchangé.
- **`app/statique.py`** : nouvelle fonction `favicon_svg()` — retourne
  `img/favicon-windows.svg` si `platform.system() == "Windows"`, sinon
  `img/favicon.svg` ; exposée comme globale Jinja (même mécanisme que
  `url_statique`/`importmap_socle`, avec cache-busting `?v=<mtime>` via
  `url_statique()`).
- **`templates/index.html`** : le `<link rel="icon" type="image/svg+xml">`
  utilise désormais `{{ url_statique(favicon_svg()) }}` au lieu d'un chemin
  statique en dur. Le `<link>` `favicon.ico` (type image/x-icon) n'est pas
  concerné — non demandé par l'issue, les navigateurs modernes priorisent
  le SVG pour l'onglet.

Vérifié par rendu Jinja direct (`render_template_string`) avec
`platform.system` mocké sur "Windows" et non mocké (Linux) : URL générée
correcte dans les deux cas.

## #688 — suite #686 : `encoding="utf-8", errors="replace"` sur les appels subprocess restants

Inventaire élargi de #686 (grep exhaustif, hors `watcher.py` et tests) :
même défaut latent — `subprocess.run(..., text=True, ...)` sans
`encoding="utf-8"` explicite, qui retombe sur `cp1252` sous Windows et
corrompt les accents dans la sortie de `git`/`gh` — trouvé dans 10
fichiers restés hors périmètre de #686. Notable : `app/ccw.py` et les
deux fichiers `provisioning/windows/` tournent déjà, au moins en partie,
côté Windows.

Ajout de `encoding="utf-8", errors="replace"` (18 sites, même pattern que
#686/`watcher.py`) dans :
- `etat_rate_limit.py` (1) ; `app/interruption.py` (3, label/commentaire gh) ;
- `app/ccw.py` (1, scp — les deux autres appels de ce fichier gardent
  `encoding="cp1252"`, volontaire, sortie console Windows non-UTF-8) ;
- `app/projet_ccw.py` (3, scp clé publique + `gh issue create`/`comment` —
  l'appel `openssl` de ce fichier n'a pas `text=True`, sortie binaire,
  inchangé) ;
- `backfill_historique.py` (1) ; `nouveau_projet.py` (2, `gh`/`git`) ;
- `regenerer_tableaux_projets.py` (1) ;
- `scripts/watcher_issues_inbox.py` (2, `gh issue view`/`edit`) ;
- `provisioning/windows/creer_vm_ccw.py` (3, VBoxManage) ;
- `provisioning/windows/lancer_provisioning.py` (1).

Revérification exhaustive (AST, pas juste grep mono-ligne, pour capter les
appels où `text=True`/`encoding=` sont sur des lignes séparées) sur tout
le dépôt (hors tests) : plus aucun site oublié parmi les fichiers listés
ci-dessus. Deux zones restent volontairement intactes, hors périmètre de
cette issue :
- `watcher.py` — exclu explicitement par l'énoncé de #688 (déjà traité
  antérieurement).
- `app/issues.py` — l'énoncé de #688 le donne pour déjà corrigé par #686 ;
  en réalité la branche `worktree-issue-686` (commit `e6d18d8`) n'est
  **pas encore fusionnée dans `master`**, donc ce worktree (créé depuis
  `master`) ne contient pas ce correctif : `app/issues.py` présente donc
  encore, à ce stade, des appels `subprocess.run(text=True, ...)` sans
  `encoding=`. Point à vérifier par Alain lors de la fusion des deux
  branches (pas de conflit attendu, les fichiers touchés ne se recoupent
  pas) — ne pas considérer le dépôt "propre" sur ce point avant que #686
  soit effectivement mergé dans `master`.

Comportement Linux inchangé (le comportement par défaut de `text=True`
sans `encoding=` y était déjà UTF-8 via la locale du système).

## #686 — Forcer encoding="utf-8" sur les appels subprocess (git/gh) d'app/issues.py

Constaté le 28/09/2026, en conditions réelles sur `new_issue.py` tournant
nativement sur CCW (issue D) : les titres d'issues contenant des accents
s'affichaient corrompus (« RÃ©concilier », « dÃ©tecter »...), avec une
`UnicodeDecodeError: 'charmap' codec can't decode byte...` dans le log du
serveur. Cause : `app/issues.py` appelait `subprocess.run(..., text=True,
...)` sur `git`/`gh` sans préciser `encoding` — sous Windows ça retombe sur
l'encodage de la console (`cp1252` en français) alors que `git`/`gh`
produisent toujours de l'UTF-8, d'où la corruption dès qu'un accent
apparaît. Sous Linux ça marchait par hasard (UTF-8 système).

`watcher.py` avait déjà résolu ce même besoin ailleurs dans le dépôt
(`encoding="utf-8", errors="replace"` sur chacun de ses appels
`subprocess.run`). Même pattern appliqué ici aux 18 appels d'`app/issues.py`
(lignes 324, 391, 613, 625, 634, 655, 663, 670, 688, 704, 785, 891, 942,
1130, 1338, 1407, 1456, 1489). `app/notifications_poller.py` (lignes 165,
188) avait déjà été corrigé lors d'un commit antérieur — vérifié, rien à
faire dessus cette fois.

Vérification élargie au reste du dépôt (hors `watcher.py`, déjà correct,
et hors tests) : d'autres fichiers présentent le même défaut latent
(`text=True` sans `encoding=`) — `etat_rate_limit.py`, `app/interruption.py`,
`app/ccw.py`, `app/projet_ccw.py`, `backfill_historique.py`,
`nouveau_projet.py`, `regenerer_tableaux_projets.py`,
`scripts/watcher_issues_inbox.py`, `provisioning/windows/creer_vm_ccw.py`,
`provisioning/windows/lancer_provisioning.py` — hors du périmètre précis de
cette issue (qui ne visait que `app/issues.py` et
`app/notifications_poller.py`), donc non modifiés ; à traiter par une
future issue si souhaité.

Comportement Linux inchangé (UTF-8 explicite au lieu d'UTF-8 implicite,
même résultat) ; corrige la corruption d'accents sous Windows.

## #685 — §11/§20 : exiger de demander à Alain avant d'utiliser le formulaire web comme repli quand aucun outil fichier n'est disponible

Cas constaté (dont un le 28/09/2026, projet Rummikub) : une conversation
Claude Chat sans outil fichier (`bash`/`create_file`) présentait le texte
d'une issue en clair pour qu'Alain le copie-colle dans `new_issue.py`, en
violation apparente de §11. Cause : §20 documente ce formulaire comme un
repli légitime, mais §11 et §20 ne précisaient pas explicitement qui doit
initier ce choix — une conversation sans outil fichier pouvait donc, de
bonne foi, s'appuyer sur §20 pour justifier le copier-coller.

Aucune suppression de la mention du formulaire web dans la doc (option
écartée : masquerait un usage réel et actif du système pour toute autre
conversation, créant d'autres angles morts).

- **§11** (`BRIDGE_AGENT_DOC.md`) : ajout — si aucun outil fichier n'est
  disponible dans la conversation en cours, Claude Chat le signale
  explicitement à Alain et demande la marche à suivre, plutôt que de
  basculer silencieusement vers le formulaire web de sa propre initiative.
- **§20** : précision symétrique — le formulaire reste un repli légitime,
  mais c'est à Alain de décider de l'utiliser, jamais à Claude Chat d'y
  basculer lui-même en l'invoquant comme justification.

## #684 — docs(bridge_agent_doc): exception REDACTEUR=bridge_agent limitée aux projets sans service CCW dédié

`BRIDGE_AGENT_DOC.md` : la règle 2 de « Cohérence `REDACTEUR` / `PROJET` »
(§3.4) justifiait l'exception `for-windows` + `REDACTEUR == bridge_agent`
par « CCW passe toujours par le canal central `bridge_agent`, quel que soit
le `PROJET` » — formulation antérieure au modèle multi-projets CCW
(services NSSM dédiés `CCW-Watcher-<Projet>`, issue #170) qui pouvait
laisser croire que l'exception vaut pour tout `for-windows`, indistinctement
du projet. Cas réel constaté le 28/09/2026 : une issue `for-windows` pour
Rummikub rédigée avec `REDACTEUR: bridge_agent` alors que Rummikub venait de
recevoir son propre service `CCW-Watcher-Rummikub` — l'exception ne
s'applique plus à lui, `REDACTEUR` aurait dû valoir `rummikub` (règle 1).

- §3.4, règle 2 : ajout de la condition explicite — l'exception ne vaut que
  si le projet visé par `PROJET` n'a **pas** (encore) son propre service CCW
  dédié (dépendant du canal central partagé `bridge_agent` faute de service
  propre) ; dès qu'il en a un, c'est le cas `REDACTEUR == PROJET` (règle 1)
  qui s'applique. Exemple Rummikub ajouté à titre d'illustration.
- Tableau des champs spéciaux (« ## 6. Champs spéciaux dans le corps de
  l'issue », ligne `REDACTEUR` — déjà retouché par #665, visé par l'issue
  #684 sous la référence historique « §17.3 ») : même précision ajoutée,
  condition « projet n'ayant pas encore son propre service CCW dédié »
  explicitée.

Purement documentaire, aucun changement de code.

## #683 — point de rupture CSS pour écran plafonné ~1360×768 (poste fixe CCW)

Le PC fixe CCW est plafonné matériellement à 1360×768 (Intel HD Graphics
Ivy Bridge/G2020, aucun pilote plus récent disponible, câble VGA —
confirmé le 28/09/2026, remplacement prévu sous 1-2 mois mais l'interface
doit rester utilisable en attendant). À cette résolution, l'interface
n'avait qu'un seul point de rupture CSS existant, à `max-width:900px`
(`static/css/resultats.css`, issue #628/#633), trop étroit pour couvrir
1360px : la barre du haut, les onglets et le panneau latéral
« Infrastructure » se chevauchaient.

Deux nouveaux blocs `@media (max-width:1400px)`, dédiés et distincts du
`900px` existant (aucune touche à ce dernier, comportement mobile/tablette
inchangé) :
- `static/css/resultats.css` : `.resultats-layout{flex-direction:column}`,
  `.panneau-lateral-col{width:100%}`, `.panneau-lateral{width:auto}` —
  mêmes règles que le repli 900px, le panneau latéral Infrastructure passe
  sous le corps de l'onglet Résultats au lieu d'à côté.
- `static/css/base.css` : `.entete{flex-wrap:wrap}` et
  `.onglets{flex-wrap:wrap}` (+ `row-gap`) — la barre du haut (projet,
  boutons Nouveau projet/Lancer le watcher/Quitter) et les onglets
  (Résultats/Journal watcher/Configuration/CCW/Nouvelle issue) s'empilent
  proprement sur plusieurs lignes au lieu de déborder ou de forcer un
  défilement horizontal.

Seuil choisi à 1400px (marge au-dessus de 1360px pour absorber la
scrollbar verticale du navigateur) plutôt qu'exactement 1360px. Vérifié
par capture d'écran Playwright (serveur de dev local, sans configs de
projet dans ce worktree isolé) : à 1360×768 le panneau passe bien sous le
contenu sans chevauchement ; à 1600px de large le comportement d'origine
(panneau à côté) est inchangé — pas de régression sur écran large.
Aucune refonte visuelle : uniquement ces deux points de rupture ciblés,
réversibles en supprimant les blocs `@media` ajoutés.

## #665 — docs(bridge_agent_doc): PROJET reste le projet réellement ciblé même quand REDACTEUR=bridge_agent (canal CCW)

`BRIDGE_AGENT_DOC.md` : la règle 2 de « Cohérence `REDACTEUR` / `PROJET` »
(§3.4) — `for-windows` + `REDACTEUR == bridge_agent` valide « quel que soit
le `PROJET` réellement ciblé » — pouvait se lire comme si `PROJET` devait lui
aussi valoir `bridge_agent` sur le canal CCW. Erreur constatée deux fois en
usage réel (#661, #664 : issues de build Actualise routées dans la file de
`bridge_agent`).

- §3.4 : ajout, juste après la règle 2, d'un avertissement explicite
  (« `PROJET` ne devient JAMAIS `bridge_agent` du seul fait qu'une issue passe
  par le canal CCW — seul `REDACTEUR` le devient ») et d'un exemple d'en-tête
  contrastant les deux champs (`PROJET = actualise`, `REDACTEUR =
  bridge_agent`), avec rappel que `PROJET = bridge_agent` passerait la
  validation (règle 1) tout en envoyant l'issue dans la mauvaise file.
- §3.1 (tableau des champs d'en-tête `issues_inbox/`, ligne `REDACTEUR`) et
  §17.3 (tableau des champs d'en-tête, ligne `REDACTEUR`) : même précision
  ajoutée en une phrase, ces deux résumés reprenant la règle du canal CCW
  sans distinguer les deux champs.

Purement documentaire, aucun changement de code.

## #682 — cycle de vie des watchers locaux à la demande (Popen), sans systemd, portable Linux/Windows

Suite au diagnostic du chantier hybride (28/09/2026) : le cycle de vie des
watchers CCL reposait entièrement sur `systemctl --user`
(`app/watchers.py`, `app/interruption.py`), inexistant sous Windows.
Remplacé par un mécanisme portable réutilisant l'existant : auto-extinction
après inactivité déjà interne à `watcher.py`, isolation de groupe de
process déjà par-OS dans `watcher.py`, `start_new_session=True` déjà
utilisé côté POSIX par `app/issues_inbox.py`, sonde `_pid_vivant`
cross-plateforme (#584, dédupliquée par #680).

Terminologie retenue : watcher **local** = `new_issue.py` et le watcher
tournent sur la même machine, lancé à la demande (Linux ou Windows) ;
watcher **délégué** = mécanisme CCW (autre machine, SSH, inchangé par
cette issue).

- `app/watchers.py::demarrer_watcher` : lance désormais `watcher.py`
  directement via `subprocess.Popen([sys.executable, "watcher.py",
  "--config", ...])`, détaché (`start_new_session=True` POSIX,
  `CREATE_NEW_PROCESS_GROUP` Windows — flag déjà utilisé par
  `watcher.py::lancer_claude`), logs redirigés en ajout vers
  `cfg.fichier_log`. Le PID retourné est `proc.pid` (connu immédiatement,
  contrairement à l'ancien sondage du fichier PID nécessaire quand systemd
  gérait le process) ; `watcher.py` republie de toute façon ce même PID
  dans `logs/watcher-<nom>.pid` à son propre démarrage (issue #596,
  inchangé), sans effet puisque la valeur est identique.
- `app/watchers.py::arreter_watcher` : `SIGTERM` direct (`os.kill`,
  cross-plateforme — `TerminateProcess` sous Windows via la même API
  Python) au lieu de `systemctl --user stop`. Ne tue plus tout un cgroup
  (limite de l'ancien service, cause de l'incident relecture_bridge #73) :
  un arrêt manuel pendant une tâche en cours laisse désormais le process
  `claude` en cours orphelin plutôt que de le tuer aussi.
- Démarrage auto après création d'issue (§3.11) : déjà entièrement
  factorisé dans `redemarrer_si_eteint()` (issue #600), qui appelle
  `demarrer_watcher(cfg, forcer=False)` — celui-ci vérifie déjà
  `watcher_actif()` (basé sur `_pid_vivant`) avant tout lancement. Aucun
  changement nécessaire aux points d'appel (`app/issues.py`,
  `app/projet_ccw.py`, `scripts/watcher_issues_inbox.py`).
- `app/interruption.py::_neutraliser_relance_systemd` : supprimée.
  Protégeait contre une relance automatique par systemd
  (`Restart=on-failure`) qui aurait vu le SIGKILL de l'arbre de process
  comme un crash à relancer, contredisant le contrat #323 (« jamais de
  relance automatique après interruption »). Sans supervision systemd,
  aucun mécanisme ne peut plus relancer le watcher de son propre chef
  après un SIGKILL — aucun équivalent Popen nécessaire, le contrat est
  respecté sans action supplémentaire. L'étape correspondante disparaît de
  la liste `etapes` retournée par `POST /interrompre` (aucun consommateur
  frontend ne s'y référait par son nom).
- Comportement des boutons Lancer/Relancer/Arrêter (panneau latéral)
  inchangé du point de vue utilisateur — seule l'implémentation change.
  Non-régression Linux vérifiée : tests existants
  (`test_relancer_watcher_574`, `test_champ_relance_516`,
  `test_champ_redacteur_599`, `test_label_sans_redacteur_647`,
  `test_creation_issue_enrichie_634`, `test_projet_ccw_559`) passent tous
  sans modification ; cycle Popen/SIGTERM/`_pid_vivant` vérifié
  manuellement (process lancé, détecté vivant, SIGTERM appliqué).

Hors périmètre (inchangé, tel que demandé) : `app/ccw.py`, services NSSM,
`provisioning/windows/*.ps1` — un éventuel retrofit de CCW sur ce même
principe fera l'objet d'une issue séparée. Non traité non plus dans cette
issue (au-delà du strict périmètre demandé) : `systemd/watcher@.service`
et `installer_services.sh` restent présents dans le dépôt bien que devenus
obsolètes pour le déploiement CCL (dead code d'infrastructure, pas de code
applicatif) — nettoyage éventuel à discuter séparément.

Point d'attention (non bloquant, non demandé par cette issue) : sans
supervision OS, un process tué par `SIGTERM`/`SIGKILL` reste zombie tant
que le process `new_issue.py` (Flask) ne le réap pas — déjà documenté et
traité côté `app/interruption.py::_reaper_best_effort` pour le chemin
d'interruption ciblée (issue #323), mais pas côté
`app/watchers.py::arreter_watcher`/redémarrage forcé. Sans impact
fonctionnel observé (`watcher_actif()` se base sur la présence du fichier
PID, pas sur l'état du process, pour ce chemin) — seulement une
accumulation lente d'entrées zombies dans la table des process au fil des
redémarrages, à surveiller si ce comportement devient gênant en usage
prolongé.

## Issue #681 — rep_defaut() sensible à l'OS + which→shutil.which dans nouveau_projet.py

`nouveau_projet.py` : `rep_defaut()` utilise désormais `Path.home() / nom.capitalize()`
au lieu du chemin `/home/alain/...` câblé en dur — résout correctement sous
Windows comme sous Linux. La détection de `gh` (ligne ~939) utilise désormais
`shutil.which("gh")` au lieu de `subprocess.run(["which", "gh"], ...)`, alignée
sur le pattern déjà utilisé ailleurs dans le dépôt (`app/tunnel.py`,
`app/projet_ccw.py`, `watcher.py`, `provisioning/windows/*.py`). Comportement
inchangé sous Linux.

## #680 — refactor: déduplique _pid_vivant vers la version cross-platform de watcher.py

Diagnostic du chantier « Bridge_Agent hybride » : `app/interruption.py`
(fonction locale `_pid_vivant`) et `app/issues_inbox.py`
(`watcher_inbox_actif`) réimplémentaient chacune la sonde « ce PID est-il
vivant ? » via un `os.kill(pid, 0)` POSIX-only, dupliquant et masquant
`watcher._pid_vivant` (cross-plateforme POSIX/Windows, issue #584) — même
risque que celui corrigé dans `watcher.py` lui-même pour `_watcher_actif`
(issue #673). `app/watchers.py::watcher_actif` utilisait déjà la version
partagée depuis l'issue #617, servant de modèle pour cette dédup.

Fix : les deux modules importent désormais `_pid_vivant` depuis `watcher`
(comme `app/watchers.py`) et l'utilisent à la place de leur `os.kill(pid, 0)`
local :
- `app/interruption.py` : suppression de la fonction locale `_pid_vivant`
  (lignes ~166-171) ; le `os.kill(candidat, 0)` inline de
  `interrompre_linux()` (détection du PID du watcher à interrompre) est
  également remplacé par un appel à `_pid_vivant`, même test dupliqué au
  même endroit.
- `app/issues_inbox.py::watcher_inbox_actif` : même substitution, plus
  `sys.path.insert(0, str(DOSSIER_SCRIPT))` ajouté (la racine du dépôt,
  contenant `watcher.py`, n'était pas garantie sur `sys.path` avant cet
  import — seul `scripts/` l'était).

Recherche exhaustive (`grep -rn "os.kill(pid" --include="*.py"`) : aucune
autre réimplémentation trouvée hors `watcher.py` lui-même et les fichiers de
test (qui simulent des process pour leurs scénarios, pas une sonde
générique). Comportement Linux inchangé (mêmes tests passés :
test_relancer_watcher_574, test_champ_relance_516,
test_evenements_issues_inbox_631, test_verrou_refus_precoce_584,
test_nettoyage_arbre_247, test_orphelin_verrou_perime_322) ; ces deux points
deviennent automatiquement sûrs côté Windows sans logique supplémentaire.

## #679 — fix(web): détecte #Titre: n'importe où dans le corps collé (comme PROJET/TIMEOUT)

Dans l'onglet « Nouvelle issue » (`static/js/creation.js`),
`detecterTitreDansCorps()` ne reconnaissait `#Titre:` que sur la toute
première ligne du corps collé (`premiereLigne = valeur.slice(0, finLigne)`
testée seule), contrairement à `detecterProjetDansCorps()` (PROJET) et à la
détection TIMEOUT qui, via `lireChampEntete`, cherchent déjà n'importe où
dans `zoneEntete(corps)` (25 premières lignes, issue #512). Un texte collé
avec l'en-tête (PROJET/REDACTEUR/MODE) placé avant `#Titre:` — convention par
ailleurs valide côté `issues_inbox/` pour une issue seule — pré-remplissait
donc bien PROJET et TIMEOUT mais pas le titre.

Fix : `detecterTitreDansCorps()` cherche désormais `/^#titre:\s*(.*)$/im`
dans `zoneEntete(valeur)` au lieu de la seule première ligne, puis retire la
ligne trouvée avec la même logique que `retirerLigneEntete` (gestion de la
ligne vide adjacente, issue #512) au lieu du simple découpage sur le premier
`\n`. Le cas déjà géré (titre en première ligne, sans en-tête devant) reste
identique — vérifié par un test manuel (regex+retrait rejoués hors DOM).

Pas de garde-fou « valeur inchangée » ajouté (contrairement à
`detecterProjetDansCorps`) : la ligne `#Titre:` est toujours retirée du corps
une fois trouvée, donc jamais redétectée telle quelle au passage suivant —
une correction manuelle du champ Titre n'est ainsi jamais écrasée.

`decouperCorpsEnBlocs` (mode lot, issue #135) n'est pas concerné : il
cherchait déjà `#Titre:` sur tout le corps via une regex globale
(`/^#titre:/gim`) — seul son commentaire de tête, qui renvoyait à l'ancien
comportement de `detecterTitreDansCorps`, a été mis à jour pour rester exact.

Fichier touché : `static/js/creation.js`. Suite de tests JS existante
(`static/js/tests/creation.test.js`, 24 tests) rejouée sans régression —
`detecterTitreDansCorps` n'étant pas exportée (dépend du DOM), sa nouvelle
logique a été vérifiée hors DOM par un script Node ad hoc reproduisant
regex + retrait de ligne sur trois cas (en-tête avant #Titre:, titre en
1re ligne sans en-tête, aucun #Titre:).

## #677 — doc(ccw): section « Repérer et nettoyer les worktrees orphelins » dans REINSTALLATION_CCW.md

Suite à #669 (lecture seule, avait produit le texte prêt à coller sans
l'appliquer) : ajout de l'étape `### 9.` dans
`provisioning/windows/REINSTALLATION_CCW.md`, juste après l'étape 8 et
avant le `---` séparant la procédure Windows du prérequis Linux
`cifs-utils`. Reprend le texte proposé par #669 tel quel (repérage via
`git worktree list`, nettoyage via `worktree remove --force` +
`worktree prune` + `branch -d`/`-D`, avertissement sur la perte de
données non commitées/mergées, renvoi vers `WORKTREES.md`).

Précision ajoutée par rapport au texte de #669 (demandée explicitement
dans #677) : un encadré `> ⚠️` en tête de la section indique qu'elle
concerne surtout les clones qui **survivent** à la réinstallation (ex.
le `REP_TRAVAIL` d'un projet dédié) — si le clone est entièrement refait
par `provisionner.ps1` (`C:\CCW\Bridge_Agent`, disque effacé à l'étape
1), `.git/worktrees` repart de zéro avec le nouveau clone et il n'y a
aucun orphelin local à nettoyer de ce côté.

## 28 septembre 2026 — issue #676

Interface web : la clé de signature des cookies de session (`SECRET_KEY`) est désormais **persistée** dans `configs/secret_key.bin` (gitignoré, permissions 0600) au lieu d'être régénérée à chaque lancement de `new_issue.py` — c'était la vraie cause de la reconnexion systématique en mode `--externe`, puisque `new_issue.py` n'est pas un service permanent. Générée une seule fois (`app/__init__.py::_cle_secrete_persistante`), relue sinon. `PERMANENT_SESSION_LIFETIME` fixé à 30 jours et `session.permanent = True` posé à l'authentification réussie (`app/auth.py::login_post`) : une session survit désormais aux redémarrages fréquents de l'interface, sans devenir illimitée.

## #673 — fix(watcher): _watcher_actif() réutilise _pid_vivant() au lieu de os.kill(pid, 0)

`watcher.py` : `_watcher_actif()` (ligne ~2240) sondait la vivacité d'un
process watcher via `os.kill(pid, 0)`, idiome purement POSIX. Sous Windows,
le signal `0` correspond à `CTRL_C_EVENT` dans l'API Win32 — `os.kill(pid, 0)`
y envoie un vrai Ctrl+C via `GenerateConsoleCtrlEvent` : sur son propre pid
(cas de `_compter_watchers_actifs()`, qui teste tous les projets connus y
compris le projet courant) le process s'auto-interrompt
(`KeyboardInterrupt` → `sys.exit(0)` dans `main()`) — crash silencieux
observé 3 fois le 28/09/2026 sur CCW-Watcher (bridge_agent) ; sur le pid
d'un autre projet, `GenerateConsoleCtrlEvent` échoue avec
`OSError: [WinError 87]` (cause très probable de l'erreur repérée le
27/09/2026 sur CCW-Watcher-Actualise, non diagnostiquée jusqu'ici).

La fonction sœur `_pid_vivant()` (issue #584) gérait déjà correctement les
deux plateformes (`os.kill(pid, 0)` sur POSIX, `OpenProcess` en droits
minimaux sur Windows) mais n'était pas réutilisée ici. `_watcher_actif()`
délègue désormais à `_pid_vivant()` : plus aucun appel direct à
`os.kill(pid, 0)`, comportement inchangé sur Linux, plus de faux Ctrl+C ni
de WinError 87 sur Windows. Repli identique dans les 4 cas testés
manuellement (pas de fichier PID, PID vivant, PID mort, PID invalide) ;
aucun test automatisé dédié à `_watcher_actif()` n'existait au préalable.

## 28 septembre 2026 — issue #671

`provisioning/windows/` : ajout de **`REINSTALLATION_WINDOWS.md`** (issue #671), procédure autonome en amont de `REINSTALLATION_CCW.md` — celui-ci ne couvrait le provisioning CCW (SSH, `provisionner.ps1`, tokens) qu'à partir d'un Windows déjà installé, son étape 1 se limitant à une phrase renvoyant à `autounattend.xml` (en réalité réservé à la VM `CCW-Build`, pas au PC fixe physique). Le nouveau document couvre : fabrication de la clé USB bootable (Rufus en mode normal — partition unique FAT32 vérifiée par `lsblk -f` le 28/09/2026, pas Ventoy — ISO officielle Windows 11 IoT Enterprise LTSC via evalcenter Microsoft), boot BIOS/UEFI sur ce PC fixe, cas standard vs réparation en place (limite « conserver les fichiers personnels » seulement, rencontrée le 27/09/2026 faute de clé USB à jour — issue #658), et désactivation complète et durable de Windows Update au niveau système (service `wuauserv`, stratégie/registre `NoAutoUpdate`, tâches planifiées `UpdateOrchestrator`) suite au plantage `ucrtbase.dll` du 27/09/2026 — à distinguer de la désactivation limitée au provisioning faite par `provisionner.ps1`. `REINSTALLATION_CCW.md` étape 1 mise à jour pour y renvoyer en préalable.

## #670 — fix(provisioning): REP_TRAVAIL dérivé de $RepDepot au lieu de C:\CCW_Share (suite #668)

`provisioning/windows/provisionner.ps1` : `$RepTravail` était figé à
`"C:\CCW_Share"` (héritage de l'ancien modèle CCW unifié, issue #231,
abandonné), déconnecté de `$RepDepot` (`C:\CCW\Bridge_Agent`, déjà utilisé
pour cloner le dépôt). Conséquence : `ccw.conf` était généré avec un
`REP_TRAVAIL`/`PERIMETRE` erroné à chaque provisioning complet (constaté et
corrigé à la main le 27/09/2026, cf. #668).

`$RepTravail = "C:\CCW_Share"` devient `$RepTravail = $RepDepot` — cohérent
avec le modèle multi-projets actif et `Get-CheminsProjetCcw`
(`ccw-commun.psm1`). `REP_TRAVAIL` et `PERIMETRE` dans `ccw.conf` en
héritent automatiquement (tous deux dérivés de `$RepTravail`). Commentaires
adjacents mis à jour en conséquence.

Aucun autre usage de `$RepTravail` ni de `C:\CCW_Share` en tant que
répertoire de travail n'existe dans le script — les autres occurrences de
`C:\CCW_Share` (`$CacheDir`/`$cacheDir`, lignes 129/327/417) concernent le
cache de téléchargement, intentionnellement distinct et hors périmètre de
cette correction (confirmé par le diagnostic #668).

Sans effet sur le `ccw.conf` déjà en place (corrigé à la main) — ce
correctif protège uniquement la prochaine réinstallation Windows complète.

Vérification par relecture du code uniquement : `pwsh` n'est pas disponible
dans ce worktree Linux, donc `.\provisionner.ps1 -DryRun` n'a pas pu être
exécuté ici (script destiné au PC Windows CCW). La substitution
`$RepTravail = $RepDepot` est une réutilisation directe d'une variable déjà
initialisée (ligne 128) et éprouvée plus haut dans le script (clonage,
AppDirectory du service) — pas de risque de syntaxe PowerShell introduit.

# CHANGELOG-667 — à fusionner dans CHANGELOG.md

## 27 septembre 2026 — issue #667

`TOPIC_NTFY` devient réellement facultatif — plus de valeur placeholder exigée pour démarrer un watcher ou créer un projet. Jusqu'ici ce champ faisait partie de `CHAMPS_REQUIS` (`watcher.py`) sans justification fonctionnelle : `url_ntfy` construisait l'adresse d'envoi par simple interpolation (`f"https://ntfy.sh/{self.topic_ntfy}"`) sans jamais vérifier si `topic_ntfy` était vide, d'où l'exigence défensive côté validation plutôt qu'un vrai traitement du cas absent. En pratique, Alain n'utilise quasiment jamais les notifications ntfy et devait systématiquement consulter son gestionnaire de mots de passe pour retrouver une valeur qui ne lui servait à rien.

- **`watcher.py`** : `TOPIC_NTFY` retiré de `CHAMPS_REQUIS` (ne contient plus que `NOM`/`DEPOT`/`REP_TRAVAIL`). Le champ `topic_ntfy` de `Config` passe dans la section « Optionnels » du dataclass, défaut `""`. `charger_config` lit désormais `TOPIC_NTFY` via `brut.get(..., "")` plutôt que `brut["TOPIC_NTFY"]`. La propriété `url_ntfy` renvoie `""` quand `topic_ntfy` est vide/absent, au lieu de construire l'URL invalide `https://ntfy.sh/`.
- **`notifications.py`** : `notifier_ntfy()` garde désormais en tête de fonction — `url_ntfy` vide → aucune requête réseau tentée (`subprocess.run` jamais appelé), au plus un `log.debug`, jamais un `log.error`/`log.warning` (ce n'est pas un échec). Seul point de garde nécessaire : tous les appelants (`watcher.py`, `notifications.notifier()`, `app/notifications_poller.py`) passent déjà par cette même fonction.
- **`nouveau_projet.py`** : retrait du placeholder `TOPIC_NTFY_DEFAUT` (`"hippocampe-ff-galerie-xyz123"`), qui était imposé silencieusement quand le champ était laissé vide (`ecrire_conf`/`creer_projet`/prompt CLI `etape_conf`). Un topic laissé vide — à la création via le script CLI, ou via le formulaire web « Nouveau projet » (dont le champ `#np-topic` était déjà vide par défaut côté JS, `ouvrirNouveauProjet()`) — reste désormais vide dans le `.conf` généré, au lieu d'être remplacé par l'ancien topic partagé. Le gabarit `GABARIT_CONF` déplace `TOPIC_NTFY` hors de la section « Requis » du `.conf`, avec un commentaire explicite sur le comportement à vide.
- **Onglet Configuration** (`static/js/config.js`, `app/projets.py`) : vérifié — aucun correctif nécessaire. Ni le champ HTML (`#conf-TOPIC_NTFY`, pas d'attribut `required`), ni `sauvegarderConfig`, ni la route serveur `post_config`/`sauvegarder_conf` (`app/projets.py`) ne valident une valeur non vide ; une valeur vide s'enregistre déjà sans erreur.
- **`BRIDGE_AGENT_DOC.md`** (§17, notifications centralisées) : note sur le caractère désormais facultatif de `TOPIC_NTFY`, le comportement exact de `url_ntfy`/`notifier_ntfy()` à vide, et le fait qu'aucun redémarrage supplémentaire du watcher n'est requis au-delà de celui déjà nécessaire pour tout changement de `.conf`.
- **Non touché, hors périmètre de cette issue** : le champ `CREATION_TOPIC_NTFY` du bootstrap automatique d'un service CCW (§16.6 de la doc, `app/ccw.py`/`app/projet_ccw.py`, scripts PowerShell `finaliser_projet_ccw*.ps1`) et la validation « topic obligatoire si case Projet CCW cochée » du formulaire web (`static/js/app.js::soumettreNouveauProjet`) — mécanisme distinct qui écrit un `.conf` CCW dédié sur la machine Windows physique via un fichier de valeurs chiffré, pas concerné par l'optionalité de `TOPIC_NTFY` du `.conf` watcher lui-même.

Tests : `tests/test_topic_ntfy_facultatif_667.py` (11 scénarios pytest) — `CHAMPS_REQUIS` sans `TOPIC_NTFY`, `charger_config` sur un `.conf` sans la ligne, `url_ntfy` vide/non-vide, `notifier_ntfy`/`notifier()` avec url vide (mock de `subprocess.run`, jamais appelé, aucun log error/warning), `ecrire_conf`/`creer_projet` avec topic vide (placeholder disparu), `sauvegarder_conf` avec `TOPIC_NTFY` vide. Suite complète (125 tests) : aucune régression. Aucune modification de `configs/*.conf`. Aucun `git push`.

# CHANGELOG-666 — à fusionner dans CHANGELOG.md

## 27 septembre 2026 — issue #666

Onglet CCW, section « Finaliser » : `ccwFinaliserProjet()` (`static/js/ccw.js`) vidait déjà `#ccw-fin-gh` et `#ccw-fin-oauth` après soumission (succès ou échec) mais oubliait `#ccw-fin-topic` — constaté par Alain en finalisant plusieurs projets à la suite (Bridge_Agent, Scrabble, Actualise), le champ TOPIC_NTFY affichait la valeur du projet précédent (aucune donnée réelle affectée, uniquement visuel). Second point, plus sérieux : changer de projet sélectionné (clic sur une ligne du tableau ou sélection directe dans le menu déroulant `#ccw-fin-nom`) ne vidait aucun des trois champs — un token resté affiché pour l'ancien projet aurait pu être posé par erreur sur le nouveau via « Finaliser ».

- **`static/js/ccw.js`** : extraction de `ccwViderChampsFinalisation()` (exportée), qui vide les trois champs (`#ccw-fin-topic`, `#ccw-fin-gh`, `#ccw-fin-oauth`). Appelée : (1) dans `ccwFinaliserProjet()`, aux deux points où les tokens étaient déjà vidés (succès/avertissement et erreur réseau) — remplace les deux paires d'affectations dupliquées ; (2) dans `ccwPreselectionnerProjet()`, dès qu'une sélection valide est appliquée (clic sur une ligne du tableau) ; (3) via un nouveau gestionnaire délégué (`dom.surAction`) sur l'événement `change` de `#ccw-fin-nom`, pour la sélection directe dans le menu déroulant.
- **`static/js/tests/ccw.test.js`** : test DOM minimal (stub `global.document.getElementById`, patron déjà utilisé par `resultats_activation.test.js`) vérifiant que `ccwViderChampsFinalisation()` vide bien les trois champs.
- **`VERIFICATIONS_MANUELLES.md`** : deux nouvelles cases dans la section « Onglet CCW » (remise à zéro au changement de sélection ; remise à zéro du topic après finalisation).

Tests : `node --test static/js/tests/` (164 tests, tous passent, aucune régression). Aucune modification de `configs/*.conf`. Aucun `git push`.

# CHANGELOG-659 — à fusionner dans CHANGELOG.md

## 27 septembre 2026 — issue #659

Réconciliation de la contradiction PATH/`AppEnvironmentExtra` entre l'ancien fix #558 (`ajouter_projet_ccw.ps1`) et #658 (`mettre_a_jour_tokens_ccw.ps1`), signalée dans les deux fichiers depuis #658 sans être résolue.

**Archéologie (lecture des commits/issues, pas supposition)** : le fix #558 (743f068) avait diagnostiqué qu'un tableau splatté (`@envExtra`) passé à `nssm set … AppEnvironmentExtra` était fautif, et l'avait remplacé par une chaîne unique jointe par `` `n``. Mais la clôture #558 confirme que cette cause n'a JAMAIS été reproduite sur un nssm réel (lecture du code seule — l'étape « reproduire le bug » demandée par l'issue n'a pas été faite), et n'a jamais été testée avec une ligne PATH (contenant des espaces, ex. « Program Files ») — PATH n'existait pas encore dans `AppEnvironmentExtra` à l'époque (ajouté par #658). #658 a lui constaté empiriquement, sur ce PC fixe et nssm 2.24, l'inverse pour une valeur à espaces : la chaîne unique jointe par `` `n`` ne pose PAS de ligne PATH effective, alors que des arguments SÉPARÉS fonctionnent — y compris pour cette valeur à espaces, donc a fortiori pour des tokens qui n'en ont pas.

**Décision** : arguments séparés retenu comme SEULE méthode dans tout le dépôt (le fix #558 n'ayant jamais eu de confirmation empirique propre, contrairement à #658).

- **`provisioning/windows/ajouter_projet_ccw.ps1`** : la réapplication des tokens préservés (relance sur projet déjà finalisé, issue #181) ne joint plus les entrées en une chaîne unique — elle les retrouve par clé (PATH/GH_TOKEN/CLAUDE_CODE_OAUTH_TOKEN, l'ordre/le nombre variant selon que le service a ou non déjà une ligne PATH) puis les repasse à `nssm set` comme autant d'arguments scalaires distincts (0 à 3, jamais de tableau splatté). Commentaire « BUG #558 » retiré et remplacé par l'explication de la réconciliation.
- **`creer_projet_ccw_complet.ps1`** (racine, script courant hors `provisioning/windows/`) : même alignement — PATH/GH_TOKEN/CLAUDE_CODE_OAUTH_TOKEN passés à `nssm set` comme 3 arguments séparés au lieu d'une chaîne jointe par `` `n``.
- **`provisioning/windows/mettre_a_jour_tokens_ccw.ps1`** : déjà aligné depuis #658, commentaire mis à jour pour référencer la réconciliation (#659) plutôt que renvoyer à une contradiction non résolue.
- **`provisioning/windows/finaliser_projet_ccw.ps1`/`finaliser_projet_ccw_auto.ps1`** : aucun changement nécessaire — ils délèguent déjà entièrement la pose d'`AppEnvironmentExtra` à `mettre_a_jour_tokens_ccw.ps1`, déjà correct.
- **`tests/test_ajouter_projet_ccw_env_558.py`** : réécrit pour vérifier la nouvelle méthode (arguments séparés) sur les 3 scripts qui posent `AppEnvironmentExtra`, avec contrôles négatifs sur l'ancien pattern (splat ET chaîne jointe).

**Non résolu ici (nécessite un accès Windows/nssm réel, hors de portée de CCL/Linux)** : la certitude absolue sur l'origine exacte du bug #558 (splat vs qualité des données relues via `nssm get`) et la vérification directe de l'état réel du service `CCW-Watcher-Scrabble` (créé aujourd'hui via l'onglet CCW). Délégué à CCW via l'issue for-windows #660 (test jetable sur nssm 2.24 + vérification/correction immédiate de `CCW-Watcher-Scrabble` si affecté).

Tests : `python3 tests/test_ajouter_projet_ccw_env_558.py` (6 scénarios, tous passent) + suite complète relancée (`tests/test_*.py`), aucune régression. BOM UTF-8 préservé sur les 3 scripts `.ps1` modifiés. Aucune modification de `configs/*.conf`. Aucun `git push`.

# CHANGELOG-663 — à fusionner dans CHANGELOG.md

## 27 septembre 2026 — issue #663

`static/js/resultats.js` (`reconcilierRejetes()`) : une ligne rouge « fichier refusé » reçue en direct (SSE, `source: 'sse'`) se referme désormais toute seule, sans recharger la page, dès que le fichier correspondant quitte `issues_inbox/rejected/` — même traitement que les lignes `source: 'etat'` (reconstruites au rechargement), sans distinction de source pour la purge. Avant cette issue, une ligne SSE restait affichée indéfiniment jusqu'au rechargement complet de la page, même après nettoyage manuel du fichier (constaté en usage réel par Alain — un geste d'entretien répétitif).

Pas de course critique sur un fichier tout juste refusé : `scripts/watcher_issues_inbox.py` déplace toujours le fichier vers `rejected/` AVANT d'émettre l'événement SSE `fichier_refuse` (`_rejeter`), donc au prochain cycle de polling `/issues-inbox/etat` (7 s, `POLL_INBOX_MS`) le fichier y est déjà listé — la ligne SSE fraîchement affichée y survit intacte, aucun délai de grâce supplémentaire à ajouter.

Point d'attention non traité (hors périmètre de cette issue, marquée « court ») : dans un lot multi-blocs partiellement réussi (`_traiter_lot`, `nb_ok > 0`), le fichier original est directement supprimé (`unlink()`) — jamais déplacé vers `rejected/` — donc la ligne SSE d'un bloc refusé au sein de ce lot ne figurera JAMAIS dans `rejetes` et disparaîtra désormais dès le premier cycle de polling suivant son apparition (≤ 7 s), au lieu de persister jusqu'au rechargement comme avant. Comportement inchangé pour un fichier mono-bloc ou un lot entièrement refusé (déplacés vers `rejected/` avant notification SSE).

Tests (`static/js/tests/resultats_fichiers.test.js`) : nouveaux cas couvrant explicitement la purge d'une ligne SSE dont le fichier a quitté `rejetes`, sa conservation tant qu'il y reste, et la non-purge d'une ligne « reçu » (statut `recu`, jamais concernée). `VERIFICATIONS_MANUELLES.md` mis à jour (fin de la mention « persistance jusqu'au rechargement » pour les lignes SSE, nouvelle case de vérification manuelle dédiée).

# CHANGELOG-662 — à fusionner dans CHANGELOG.md

## 27 septembre 2026 — issue #662

Purge automatique des sidecars `.motifs` orphelins de `issues_inbox/rejected/` : quand un fichier rejeté est retiré manuellement (explorateur de fichiers, hors de tout mécanisme applicatif), son sidecar `rejected/.motifs/<nom>.motif` (issue #631) restait indéfiniment sur le disque sans jamais gêner le fonctionnement, mais polluant le dossier avec le temps.

- `scripts/watcher_issues_inbox.py::purger_motifs_orphelins()` : nouvelle fonction, appelée à chaque cycle de `boucle()` juste après `traiter_dossier()` — compare `rejected/.motifs/` à `rejected/` et supprime tout sidecar dont le fichier rejeté associé n'existe plus. Purge silencieuse (aucun log, aucune notification) : sans effet sur le comportement observable de l'application (`/issues-inbox/etat`, rejets normaux inchangés).

Tests : `tests/test_purge_motifs_orphelins_662.py` (5 scénarios pytest) — sidecar orphelin supprimé, sidecar avec fichier rejeté toujours présent conservé, dossier `.motifs` absent ou vide sans plantage, mélange orphelin/conservé.

# CHANGELOG-658 — à fusionner dans CHANGELOG.md

## 27 septembre 2026 — issue #658

`provisioning/windows/provisionner.ps1` : réinstallation réelle du PC fixe CCW menée avec Alain le 27/09/2026 — échec systématique dès la toute première étape (`Bootstrap-Winget`) sur l'édition Windows 11 IoT Enterprise LTSC de ce PC. Cause racine : App Installer dépend de `Microsoft.VCLibs.140.00` (sans le suffixe `.UWPDesktop`), pour lequel aucune source de téléchargement autonome fiable n'existe. Décision : ne plus dépendre de winget du tout pour Git/GitHub CLI/Python/NSSM.

- **Installations sans winget** : Git (dernier `git-for-windows/git` GitHub Releases, résolu dynamiquement via l'API), GitHub CLI (dernier `.msi` `cli/cli`, même mécanisme), Python 3.12 (installeur officiel `python.org`, version fixe à vérifier tous les 3 mois), NSSM (archive `.zip` `nssm.cc`, extraite dans `C:\NSSM`, ajouté au `PATH` machine) — tous silencieux, tous idempotents. OpenSSL reste sur un installeur autonome (Shining Light Productions) par défaut ; winget n'est tenté que si `-TenterWinget` est explicitement fourni, avec repli automatique sur l'installeur autonome en cas d'échec. Plus aucune étape obligatoire ne dépend de winget (`Bootstrap-Winget`/`Install-WindowsAppRuntime`/`Installer-Winget` conservées, réservées à ce repli).
- **`Get-Credential` → `Read-Host -AsSecureString`** pour le mot de passe du compte de service NSSM : `Get-Credential` ouvre une fenêtre graphique invisible qui bloque le script sans erreur visible en session SSH — constaté le 27/09/2026.
- **`AppEnvironmentExtra` inclut désormais le `PATH`** : `provisionner.ps1` pose une ligne `PATH=…` (machine + `<CompteService>\.local\bin` + `WindowsApps`) à la création du service ; `mettre_a_jour_tokens_ccw.ps1` a été mis à jour pour la RECONSTRUIRE (pas la préserver telle quelle) en même temps que `GH_TOKEN`/`CLAUDE_CODE_OAUTH_TOKEN`, sous forme de **trois arguments distincts** passés à `nssm set` — une chaîne unique jointe par `` `n`` ne fonctionne pas avec `nssm set` (constaté le 27/09/2026 ; note : ceci contredit le commentaire « BUG #558 » d'`ajouter_projet_ccw.ps1`, à réconcilier séparément si confirmé plus largement — non touché ici, hors périmètre du canal `for-windows`).
- **Claude Code** : ajout explicite de `<profil>\.local\bin` au `PATH` **utilisateur** après l'installation (l'installeur le signale en sortie sans agir dessus).
- **Windows Update désactivé** (`Stop-Service wuauserv` + `Disabled` + clé de registre `NoAutoUpdate`), nouvelle étape standard — décision d'Alain suite au plantage `ucrtbase.dll` du 27/09/2026 causé par une mise à jour cumulative.
- **Mode `-DryRun` (alias `-WhatIf`)** : affiche toutes les actions prévues sans rien exécuter, pour une relecture avant la prochaine réinstallation (~3 mois).
- **Résumé final** : logiciels installés + chemins, état du service, rappel des étapes encore manuelles (authentification Claude Code, tokens, `TOPIC_NTFY`) et rappel qu'une session déjà ouverte ne voit pas le nouveau `PATH` avant reconnexion/redémarrage.

`REINSTALLATION_CCW.md` : winget retiré des prérequis, section détaillée sur les changements ci-dessus, nouvel avertissement sur le collage de blocs PowerShell multi-lignes via SSH (mélange l'ordre des lignes — préférer `Set-Content` + `-File`).

`BRIDGE_AGENT_DOC.md` (tableau `provisioning/windows/`) et `ajouter_projet_ccw.ps1` (commentaire d'en-tête) : mis à jour pour ne plus mentionner winget comme dépendance de `provisionner.ps1`.

Tests : aucun test automatisé possible pour l'essentiel de ce script (installation Windows réelle) — le mode `-DryRun` sert de garde-fou de relecture. Pas d'accès à un environnement PowerShell dans ce worktree Linux : vérification faite par relecture manuelle + contrôle d'équilibrage des accolades/parenthèses + recherche des pièges classiques de concaténation de chaînes en mode commande PowerShell (`Info "a" + "b"` n'est PAS une concaténation valide hors expression parenthésée).

# CHANGELOG-656 — à fusionner dans CHANGELOG.md

## 26 septembre 2026 — issue #656

Configuration : le modèle CCL par défaut d'un projet (`MODELE_CCL` du `.conf`) se choisit désormais dans une liste déroulante, plus de champ texte libre ni de faute de frappe silencieuse possible.

`MODELES_VALIDES` était dupliquée à l'identique dans `app/issues.py` et `scripts/watcher_issues_inbox.py`. Déplacée vers **`app/projets.py`** (SOURCE UNIQUE avec `MODELE_DEFAUT_GLOBAL`) — `app/issues.py` l'importe désormais d'ici plutôt que de la redéfinir (la définir dans `app/issues.py` aurait créé un import circulaire, ce module important déjà `projet_par_nom` depuis `app/projets.py`) ; `scripts/watcher_issues_inbox.py` fait de même. Confirmé au préalable (4 appels réels `claude --model <valeur> --print`) que les 4 valeurs reconnues (`claude-sonnet-5`, `claude-opus-4-8`, `claude-haiku-4-5`, `claude-fable-5`) sont bien toutes utilisables par le CLI Claude Code — aucune à exclure.

- **`app/projets.py`** : `MODELES_VALIDES`/`MODELE_DEFAUT_GLOBAL` (déplacées depuis `app/issues.py`). `get_config` expose deux champs supplémentaires dans sa réponse JSON : `modeles_valides` (liste triée) et `modele_defaut_global` — pour que l'interface construise sa liste dynamiquement, sans une troisième copie en dur côté JavaScript.
- **`app/issues.py`** : importe `MODELES_VALIDES`/`MODELE_DEFAUT_GLOBAL` depuis `app.projets` au lieu de les redéfinir ; comportement de `extraire_modele_entete`/`modele_defaut_projet` inchangé.
- **`scripts/watcher_issues_inbox.py`** : importe `MODELES_VALIDES` depuis `app.projets` au lieu de sa propre copie.
- **`templates/fragments/onglet_config.html`** : `#conf-MODELE_CCL` passe d'un `<input type="text">` (placeholder `ex: claude-opus-4-5`, déjà obsolète) à un `<select>` vide, peuplé par le JS ; nouveau `<div id="conf-MODELE_CCL-avertissement" class="message avertissement">` pour le cas d'une ancienne valeur non reconnue.
- **`static/js/config.js`** : nouvelle fonction pure `construireOptionsModeleCCL(modelesValides, valeurActuelle, defautGlobal)` — une option vide en tête (« -- Défaut global (claude-sonnet-5) -- »), puis les modèles triés reçus du serveur (`cfg.modeles_valides`, jamais dupliqués en dur ici). Si la valeur déjà enregistrée dans le `.conf` du projet n'est plus reconnue (ancienne valeur, faute de frappe historique), elle est ajoutée comme option supplémentaire en fin de liste plutôt que silencieusement remplacée — la page reste utilisable, un avertissement discret s'affiche sous le champ (`inconnue: true`). Nouvelle fonction `remplirSelectModeleCCL(cfg)` (DOM) appelée par `chargerConfig`. `sauvegarderConfig` inchangée : `select.value` se lit exactement comme `input.value`.
- **Tests** : `static/js/tests/config.test.js` — 4 nouveaux scénarios sur `construireOptionsModeleCCL` (vide, valeur reconnue, casse/espaces normalisés, valeur inconnue → option supplémentaire + `inconnue: true`). `tests/test_modele_ccl_liste_deroulante_656.py` (nouveau, pytest) — `MODELES_VALIDES` est le même objet partagé entre les 3 modules, `GET /config/<projet>` expose bien `modeles_valides`/`modele_defaut_global`, et un `.conf` avec un `MODELE_CCL` non reconnu reste chargeable sans erreur.
- **`BRIDGE_AGENT_DOC.md`** (§ badge « modèle forcé », issue #638) : paragraphe sur la source unique `MODELES_VALIDES`/`MODELE_DEFAUT_GLOBAL` dans `app/projets.py` et sur la liste déroulante.
- **`VERIFICATIONS_MANUELLES.md`** (onglet Configuration) : nouvelle case décrivant la liste déroulante, l'option vide par défaut, et le cas d'une ancienne valeur non reconnue.

Tests : `node --test static/js/tests/ static/js/socle/tests/` → 195/195 OK (191 précédents + 4 nouveaux). `python3 -m pytest tests/` → 109 passed (108 précédents + 1 nouveau fichier, 3 scénarios). `py_compile` sur tous les fichiers Python touchés (`app/projets.py`, `app/issues.py`, `scripts/watcher_issues_inbox.py`) = OK.

# CHANGELOG-655 — à fusionner dans CHANGELOG.md

## 26 septembre 2026 — issue #655

Panneau latéral : bouton « ⏹ Arrêter » par projet pour les watchers CCL.

Depuis la suppression de l'onglet Watchers (issue #626, étape 2), la ligne d'un watcher CCL du panneau latéral (`rendrePanneauLateralMonitoring`, `static/js/panneau_lateral.js`) n'offrait que « ▶ Lancer »/« ↺ Relancer » — aucun moyen de l'arrêter immédiatement depuis l'interface, alors que la route serveur `POST /arreter-watcher` (`app/watchers.py::arreter_watcher_route`/`arreter_watcher`, `systemctl --user stop`) existait déjà et n'était utilisée que par le bouton Configuration. Un watcher actif finissait par s'éteindre seul (auto-extinction, 20 min par défaut), mais rien ne permettait de l'arrêter tout de suite (ex. avant de modifier son `.conf`, ou pour libérer des ressources).

- **`static/js/panneau_lateral.js`** : nouvelle fonction pure `afficherBoutonArreterWatcherCcl(actif)` (même patron que `afficherBoutonDemarrer`/`afficherBoutonArreter` de `ccw.js`, issue #203) — le bouton n'apparaît que si le watcher est actif. Nouveau bouton `⏹ Arrêter` (`data-action="pl-arreter-ccl"`) affiché à côté de `↺ Relancer` dans ce cas, dans un nouveau wrapper `<span class="pl-ligne-btns">` (nécessaire pour garder deux boutons dans une ligne `.pl-ligne` en `justify-content:space-between`, qui n'attendait jusqu'ici que deux enfants). Nouvelle fonction réseau `sidebarArreterWatcherCCL(nom, btn)` : confirmation (`toasts.confirmer`, même style que `sidebarArreterWatcherInbox`), `POST /arreter-watcher`, bouton désactivé pendant l'appel, puis rafraîchissement — même mécanique que `sidebarRelancerWatcherCCL`. Reste interne au module (pas exposée en `window.*`, contrairement à `sidebarRelancerWatcherCCL` que `app.js` appelle encore directement).
- **`static/css/resultats.css`** : règle `.pl-ligne-btns{display:flex;gap:6px;flex-shrink:0}` pour le nouveau wrapper.
- **`static/js/tests/panneau_lateral.test.js`** : 3 nouveaux tests sur `afficherBoutonArreterWatcherCcl` (actif → affiché, inactif → masqué, `undefined` → masqué), sur le modèle de `ccw.test.js`.
- **`VERIFICATIONS_MANUELLES.md`** : nouvelle case dans la zone monitoring du panneau latéral décrivant le bouton, sa visibilité conditionnelle et le comportement de confirmation.
- **`BRIDGE_AGENT_DOC.md`** (§3.11, watcher spool) : la phrase « contrairement aux watchers CCL de projet, pas de bouton Arrêter » était devenue fausse — reformulée pour renvoyer vers le nouveau bouton CCL (même mécanique de confirmation).

Tests : `node --test static/js/tests/*.test.js` → 157/157 OK (154 précédents + 3 nouveaux). `py_compile` sans changement côté Python (aucun fichier `.py` touché, la route serveur existait déjà).

# CHANGELOG-652 — à fusionner dans CHANGELOG.md

## 26 septembre 2026 — issue #652

Refonte interface web (dernier chantier, ARCHITECTURE.md §6/§6.7) : le formulaire « Nouvelle issue » quitte `static/js/app.js` pour un module ES dédié `static/js/creation.js`. Objectif PUREMENT structurel — comportement strictement inchangé (backup manuel, seul moyen de joindre un fichier à une issue). `app.js` passe de 5022 à 3823 lignes (~1199 retirées).

- **`static/js/creation.js`** (nouveau) : regroupe l'intégralité de l'onglet de création trouvée par grep exhaustif depuis `onglet_creation.html` — `collecterFormulaire`, `envoyerIssue`, la bibliothèque de **templates** (#284 : `chargerTemplates`, `templateSelectionne`, `onTemplateSelectChange`, `chargerTemplateDansFormulaire`, `creerTemplate`, `modifierTemplateSelectionne`, `supprimerTemplateSelectionne`), la **pièce jointe image** (#191/#192 : `majEtatBoutonImage`, `insererDansCorps`, `joindreImage`), l'**envoi en lot** (#135/#505 : `decouperCorpsEnBlocs`, `enModeLot`, `projetEffectifBloc`, `modeEffectifBloc`, `mettreAJourBoutonLot`, `afficherResumeLot`, `envoyerLot`), les **détecteurs d'en-tête à la frappe** (`detecterTitreDansCorps`, `detecterProjetDansCorps` #109, `detecterTimeoutDansCorps` #111, `detecterModeDansCorps` #326) et le **parsing d'en-tête** partagé (`zoneEntete`/`lireChampEntete`/`retirerLigneEntete` #512/#129), le **résumé d'en-tête** (#117 : `mettreAJourResumeEntete`), l'**aperçu** (`afficherApercu`), les modales (`afficherModalConfirmation`/`afficherModalIncoherence`/`afficherModalErreur`, `detecterIncoherenceProjet` #44), `mettreAJourBoutonEnvoi`, `viderFormulaire`, les helpers `afficherMessage`/`afficherToast`/`cacherRetours`, et la **mémorisation de `notif_pc`** (#93 : `appliquerNotifPc`).
- **Délégation du socle à la place des handlers inline** : `templates/fragments/onglet_creation.html` (le fragment qui en portait le plus, 10) n'a plus aucun `onclick=`/`onchange=` — ils deviennent des attributs `data-action="creation-*"` routés par `dom.surAction`. Les 6 détecteurs déclenchés sur `input` de `#corps` (à la frappe/collage) sont enregistrés dans le MÊME ORDRE qu'avant (titre → projet → timeout → mode → résumé → bouton lot) ; la brique de délégation exécute les règles d'un type dans leur ordre d'enregistrement. Le bouton d'envoi a un point d'entrée unique (`creation-envoyer`) qui choisit `envoyerLot`/`envoyerIssue` selon `enModeLot()` — remplace l'ancien basculement de `btn.onclick`.
- **Initialisation par IMPORT DIRECT** depuis `static/js/onglets.js` (`import { initCreation }`) plutôt que par le pont : `activerOnglet` appelle `initCreation()` (idempotente) à l'activation de l'onglet `creation`. `initialisationsPour('creation')` reste `[]` (pont non utilisé, cf. test `onglets.test.js`).
- **Pont résiduel** (à retirer avec le pont en fin de refonte) : `creation.js` publie `window.chargerTemplates` et `window.afficherMessage` (encore appelées PAR LEUR NOM depuis `app.js` — respectivement `onProjetChange` au changement de projet et `lancerWatcher` pour ses erreurs) dès l'évaluation du module ; et appelle `onProjetChange()` / `mettreAJourInfoProjet()` (restés dans `app.js`) via `appelerAncien`.
- **`notif_pc` non factorisée davantage** : vérifié par grep — cette clé n'est lue/écrite QUE par le formulaire (le panneau latéral dérive l'état de ses cases 🔔 des labels GitHub de l'issue, `panneau_lateral.js::etatsCasesNotif`, sans lire cette clé). `creation.js` utilise directement la brique `persistance` du socle et sa clé unique `persistance.CLES.notifPc` (déjà point d'accès unique depuis #644), sans duplication.
- **Tests Node** (`node --test`, 158 + 29 OK) : nouveau `static/js/tests/creation.test.js` couvrant la logique PURE jusqu'ici non testée — `zoneEntete`, `lireChampEntete`, `retirerLigneEntete`, `normaliserTexteMode`/`reconnaitreModeTexte`, `detecterIncoherenceProjet`, `decouperCorpsEnBlocs`, `projetEffectifBloc`, `modeEffectifBloc` (exportées à cette fin ; le module reste sûr à importer sous Node — aucun accès DOM/réseau au chargement, exposition `window.*` gardée par `typeof window`). `pont_globales.test.js` gagne un garde-fou du **pont inverse** : les globales `window.*` qu'`app.js` appelle encore par leur nom (`chargerTemplates`, `afficherMessage`) doivent être publiées par un module et ne plus être définies dans `app.js`.
- **Docs** : `ARCHITECTURE.md §6.5` (creation.js ajouté aux modules « déjà sortis », note de réalisation #652), `VERIFICATIONS_MANUELLES.md` (section « Nouvelle issue » enrichie : détection auto, envoi en lot, notif_pc, init paresseuse), `CONTEXTE.md` (état d'avancement).

Aucune modification Python. `git push` non effectué (Alain pousse après revue).

# CHANGELOG-653 — à fusionner dans CHANGELOG.md

## 26 septembre 2026 — issue #653

URGENT — régression #646 : `dom.$` supprimé à tort, casse tout le panneau latéral.

Le « balayage exhaustif » de #646 a retiré `dom.$`/`dom.$$`/`creerElement` de `static/js/socle/dom.js` en affirmant zéro appelant restant. Faux pour `dom.$` : `static/js/panneau_lateral.js` l'utilise à 17 endroits (`grep -rn "dom\.\$(" static/js/*.js`). Effet observé en usage réel : `TypeError: dom.$ is not a function` en rafale (sélection de ligne, chaque événement SSE `debut_issue`/`fin_issue`, ouverture de page) — le bouton « Tester le son » restait grisé en permanence (`testerSonActif()` le désactive puis appelle `majBoutonTesterSonActif()`, qui plantait avant de le réactiver), et plus largement tout le panneau latéral (monitoring, son, actions, notifications) était affecté.

- **`static/js/socle/dom.js`** : restauration de `export function $(selecteur, racine)` (querySelector), reprise à l'identique du commit précédant #646 (`git show 39ed79d:static/js/socle/dom.js`). `dom.$$` et `creerElement` **non restaurés** : confirmés sans appelant (recherche généralisée sur `\.\$\b` / `\.\w+\b` par module, pas seulement le style d'appel `dom.$(` qui avait fait manquer la régression à #646).
- **Autres retraits de #646 vérifiés sans effet** (méthode élargie, ne présumant plus d'un style d'appel précis) : le canal `/events` de `static/js/socle/sse.js` (jamais connecté, `app.js` garde son propre `EventSource('/events')` indépendant), la classe CSS orpheline `.barre-issue` (zéro occurrence, JS ou template).
- **Nouveau test `static/js/socle/tests/exports_socle.test.js`** (modèle `pont_globales.test.js`, issue #632) : scanne tous les `static/js/*.js` à la recherche de `dom.<nom>` / `persistance.<nom>` (exports top-level, import en espace de noms) et de `api.<nom>` / `store.<nom>` (clés de l'objet exporté) ; échoue si un nom utilisé ne correspond à rien d'exposé par le module concerné. Inclut un cas explicite : `panneau_lateral.js` appelle bien `dom.$`, `dom.js` l'exporte bien. Vérifié que ce test échoue effectivement si `dom.$` est retiré (reproduction de la régression avant correctif).

Fichiers modifiés : `static/js/socle/dom.js`, `static/js/socle/tests/exports_socle.test.js` (nouveau).

Tests : `node --test static/js/` → 138/138 OK (133 précédents + 5 nouveaux). `py_compile` sans changement côté Python (aucun fichier `.py` touché).

# CHANGELOG-651 — à fusionner dans CHANGELOG.md

## 26 septembre 2026 — issue #651

Refonte web, étape 12 — sortie de l'onglet Configuration d'`app.js` vers `static/js/config.js`.

Dernier chantier de la refonte de l'interface web (ARCHITECTURE.md §6, procédure §6.7), en parallèle des autres onglets restants. Traite l'onglet Configuration (hors son, déjà retiré par #643).

- **`static/js/config.js`** (nouveau) : `chargerConfig()`/`sauvegarderConfig()` (paramètres éditables du projet actif) et l'ensemble de la **zone dangereuse** — `ouvrirSupprimerProjet()`/`fermerSupprimerProjet()`, l'aperçu dry-run (`spChargerApercu`, `GET /supprimer-projet/verifier/<nom>`), l'activation du bouton de suppression (`spMajBoutonEtat`) et la soumission (`soumettreSupprimerProjet`, `POST /supprimer-projet`) — déplacés d'`app.js` à l'identique (garde-fous #587 inchangés : 3 cases + nom retapé). Trois fonctions PURES extraites et testées : `construireResumeIdentite` (résumé HTML de l'identité du projet), `suppressionActivable` (condition d'activation du bouton de suppression) et `messageStatutCommitDoc` (message de fin selon le statut du commit automatique de `BRIDGE_AGENT_DOC.md`, issue #645). `sauvegarderConfig`/`spChargerApercu`/`soumettreSupprimerProjet` passent désormais par `api.post`/`api.get` (au lieu de `fetch()` en dur) : une panne réseau, jusqu'ici totalement silencieuse pour `sauvegarderConfig` (aucun `try/catch` dans l'ancien code), est maintenant signalée par un toast, en plus du message inline existant.
- **Branchement par import direct** (comme `journal.js`, issue #650, étape 11) : `static/js/onglets.js` importe `chargerConfig` et l'appelle directement dans `activerOnglet('config')` ; `initialisationsPour('config')` ne pousse plus `'chargerConfig'`. Particularité propre à cet onglet : l'ancien `app.js` (`onProjetChange`, script classique) rappelle aussi `chargerConfig()` directement quand l'onglet Configuration est déjà actif au moment d'un changement de projet (sélecteur global) — `config.js` publie donc en plus `window.chargerConfig` (même patron que `window.rafraichirPanneauLateralResultats`, `panneau_lateral.js`), pour que cet appel direct depuis un script classique continue de fonctionner.
- **`static/js/socle/index.js`** : import de `initialiserConfig`, appelé une fois au chargement (délégation des boutons/inputs, comme les autres modules par fonctionnalité).
- **`templates/fragments/onglet_config.html`** : retrait des `onclick="sauvegarderConfig(...)"`/`onclick="ouvrirSupprimerProjet()"`/`oninput="..."` (curseur Tâches en parallèle) inline, remplacés par `data-action="config-enregistrer"`/`"config-enregistrer-relancer"`/`"config-ouvrir-suppression"`/`"config-max-write-parallele"` (délégation du socle).
- **`templates/fragments/modale_supprimer_projet.html`** : retrait des `onchange="spMajBoutonEtat()"` (3 cases), `oninput="spMajBoutonEtat()"` et `onclick="fermerSupprimerProjet()"`/`onclick="soumettreSupprimerProjet()"` inline, remplacés par `data-action="sp-case"`/`"sp-nom-confirmation"`/`"sp-fermer"`/`"sp-supprimer"`.
- **`static/js/app.js`** : `majChampConfig`/`chargerConfig`/`sauvegarderConfig` et tout le bloc « Suppression de projet » (`spNomCourant`, `ouvrirSupprimerProjet`, `fermerSupprimerProjet`, `spChargerApercu`, `spMajBoutonEtat`, `spMsg`, `soumettreSupprimerProjet`) retirés — plus aucune trace de ces fonctions dans l'ancien code. `retirerProjetDuSelecteur` **reste** dans `app.js` (symétrique d'`ajouterProjetAuSelecteur`) : il manipule le sélecteur global `#projet` du bandeau supérieur, pas un élément de l'onglet Configuration — `config.js` l'appelle via le pont (`appelerAncien`).
- **Hors périmètre, documenté et non touché** : le bouton global « + Nouveau projet » (bandeau supérieur, PAS dans l'onglet Configuration) et tout son flux (`ajouterProjetAuSelecteur`, modale « Nouveau projet », `ccwCreerProjet`…) — à traiter séparément si Alain le souhaite un jour.
- **Tests** : `static/js/tests/config.test.js` (nouveau, 12 scénarios sur les 3 fonctions pures) ; `static/js/tests/onglets.test.js` ajusté (`initialisationsPour('config')` → `[]`) ; `static/js/tests/pont_globales.test.js` inchangé, toujours au vert (`appelerAncien('retirerProjetDuSelecteur')` toujours couvert, plus aucun appel `appelerAncien('chargerConfig')` à couvrir).
- **`ARCHITECTURE.md`** §6.5/§6.7 : `config.js` déplacé de la liste des « futurs modules » vers les modules déjà sortis, nouveau paragraphe « Étape 12 réalisée ».
- **`VERIFICATIONS_MANUELLES.md`** : section « Onglet Configuration » complétée (note sur le branchement par import direct + `window.chargerConfig`, vérification du rechargement au changement de projet en onglet déjà actif, et des garde-fous #587 de la zone dangereuse).

Fichiers modifiés : `static/js/config.js` (nouveau), `static/js/onglets.js`, `static/js/socle/index.js`, `static/js/app.js`, `templates/fragments/onglet_config.html`, `templates/fragments/modale_supprimer_projet.html`, `static/js/tests/config.test.js` (nouveau), `static/js/tests/onglets.test.js`, `ARCHITECTURE.md`, `VERIFICATIONS_MANUELLES.md`.

Tests : `node --test static/js/tests/ static/js/socle/tests/` → 144 tests, tous au vert (12 nouveaux pour `config.js`). Vérification manuelle du comportement visible (chargement/sauvegarde, suppression de projet avec ses garde-fous) laissée à Alain (VERIFICATIONS_MANUELLES.md), non rejouable en session non interactive (nécessite un navigateur).

# CHANGELOG-650 — à fusionner dans CHANGELOG.md

## 26 septembre 2026 — issue #650

Refonte web, étape 11 — sortie de l'onglet Journal watcher d'`app.js` vers `static/js/journal.js`.

Dernier chantier de la refonte de l'interface web (ARCHITECTURE.md §6, procédure §6.7), le plus petit morceau restant : l'onglet Journal watcher.

- **`static/js/journal.js`** (nouveau) : `demarrerJournal()` (ouvre une connexion SSE `/journal/<projet>`, ferme la précédente si déjà ouverte, code couleur des lignes selon leur contenu — `classeLigneJournal()`, extraite en fonction pure) et `viderTerminal()`, déplacées d'`app.js`. La variable `sourceSSE`, propriété exclusive de ces deux fonctions (vérifié : aucune autre partie d'`app.js` ne la lisait), devient une variable de module (`sourceJournal`), non exposée globalement. `initJournal()` branche la délégation du bouton « Vider l'affichage ».
- **`static/js/onglets.js`** : `demarrerJournal` importé DIRECTEMENT (plus via le pont `appelerAncien`) et appelé dans `activerOnglet('journal')` ; `initialisationsPour('journal')` ne pousse plus `'demarrerJournal'`.
- **`static/js/socle/index.js`** : import de `initJournal`, appelé une fois au chargement (comme les autres modules par fonctionnalité).
- **`templates/fragments/onglet_journal.html`** : retrait de l'`onclick="viderTerminal()"` inline, remplacé par `data-action="journal-vider"` (délégation du socle).
- **`static/js/app.js`** : `demarrerJournal`/`viderTerminal`/`sourceSSE` retirés — plus aucune trace de l'onglet Journal watcher dans l'ancien code.
- **Tests** : `static/js/tests/journal.test.js` (nouveau, logique pure de `classeLigneJournal`) ; `static/js/tests/onglets.test.js` ajusté (`initialisationsPour('journal')` → `[]`) ; `static/js/tests/pont_globales.test.js` inchangé, toujours au vert (plus aucun appel `appelerAncien('demarrerJournal')` à couvrir).
- **`ARCHITECTURE.md`** §6.5/§6.7 : `journal.js` déplacé de la liste des « futurs modules » vers les modules déjà sortis, nouveau paragraphe « Étape 11 réalisée ».
- **`VERIFICATIONS_MANUELLES.md`** : section « Onglet Journal watcher » complétée (note sur le branchement par import direct + vérification de la fermeture propre de la connexion SSE au changement de projet/onglet).

Fichiers modifiés : `static/js/journal.js` (nouveau), `static/js/onglets.js`, `static/js/socle/index.js`, `static/js/app.js`, `templates/fragments/onglet_journal.html`, `static/js/tests/journal.test.js` (nouveau), `static/js/tests/onglets.test.js`, `ARCHITECTURE.md`, `VERIFICATIONS_MANUELLES.md`.

Tests : `node --test static/js/tests/` (110 tests) et `node --test static/js/socle/tests/` (29 tests) → tous au vert. Vérification manuelle du comportement visible (journal en direct, réinitialisation au changement de projet) laissée à Alain (VERIFICATIONS_MANUELLES.md), non rejouable en session non interactive (nécessite un navigateur).

# CHANGELOG-649 — à fusionner dans CHANGELOG.md

## 26 septembre 2026 — issue #649

Refonte web : sortie de l'onglet CCW d'`app.js` vers `static/js/ccw.js` — dernier chantier de la refonte (ARCHITECTURE.md §6.7).

Fonctions déplacées (bandeau « Onglet CCW », issue #174/#447) : `ccwMessage`, `ccwAfficherSortie`, `ccwOccupe`, `ccwOuvrirOnglet`, `ccwChargerProjets`, `ccwPreselectionnerProjet`, `ccwRedemarrerProjet`, `ccwDemarrerProjet`, `ccwArreterProjet`, `ccwNettoyerVerrous`, `ccwAjouterProjet`, `ccwFinaliserProjet`, ainsi que l'état `ccwProjetsConnus`/`obtenirCcwProjetsConnus` (issue #375, lu par le panneau latéral) qui vivait juste avant ce bandeau. Aucun token n'est journalisé ni passé en argument — contrainte préservée telle quelle.

- **`static/js/ccw.js`** (nouveau) : appels réseau migrés vers **api** (`{silencieux:true}`, l'erreur reste affichée dans `#ccw-message` plutôt qu'en double par un toast) ; `confirm()` natif remplacé par `toasts.confirmer()`, `alert()` par `toasts.succes/erreur`. Logique pure extraite et testée : `couleurEtatCcw`, `libelleTopicCcw`, `afficherBoutonDemarrer`/`afficherBoutonArreter`, `selectionRestauree`.
- **`templates/fragments/onglet_ccw.html`** : gestionnaires `onclick=` inline (Rafraîchir/Créer/Finaliser) retirés au profit de `data-action` + délégation du socle (`dom.surAction`). Idem pour les lignes générées du tableau des projets (jusque-là construites en texte avec `onclick=` dans `ccwChargerProjets`) : chaque ligne et chaque bouton d'action porte désormais un `data-action`/`data-projet`. La règle de pré-sélection d'une ligne ignore explicitement les clics dont la cible est un `<button>` — la délégation à écouteur unique du socle ne rejoue pas la bulle DOM entre règles, donc l'ancien `event.stopPropagation()` n'aurait ici aucun effet sur les autres règles déjà enregistrées.
- **Couplage panneau latéral (rapport #632)** : `static/js/panneau_lateral.js` importe désormais DIRECTEMENT `obtenirCcwProjetsConnus`/`ccwChargerProjets`/`ccwRedemarrerProjet`/`ccwNettoyerVerrous` depuis `ccw.js` (deux modules ES — plus simple et plus sûr que le pont, erreur de compilation immédiate si un nom disparaît). Le sens inverse (`ccwChargerProjets` doit déclencher `rafraichirPanneauLateralResultats()` après un rechargement de la liste, issue #375) reste sur le pont (`appelerAncien`) : importer `panneau_lateral.js` depuis `ccw.js` créerait un cycle d'imports ES, et cette fonction n'est de toute façon publiée que comme globale pour l'ancien app.js — usage du pont dans le sens module → module qu'il ne dessert normalement pas, retenu ici pour éviter le cycle sans dupliquer la fonction.
- **`static/js/onglets.js`** : AUCUN changement — le mécanisme générique `initialisationsPour('ccw')` → `appelerAncien('ccwOuvrirOnglet')` continue de fonctionner tel quel, `ccwOuvrirOnglet` étant désormais une globale publiée par `ccw.js` (même principe que les fonctions restées dans app.js).
- **`static/js/app.js`** : bloc CCW entier retiré (fonctions + état `ccwProjetsConnus`). L'appel direct `ccwRedemarrerProjet(nom)` fait par `interrompreEtRelancer()` (issue #381, script classique, ne peut pas importer un module) continue de fonctionner sans changement : `ccw.js` publie `window.ccwRedemarrerProjet` (même patron que `window.sidebarRelancerWatcherCCL` publié par `panneau_lateral.js`).
- **`static/js/socle/index.js`** : import + appel de `initialiserCcw()` (installe la délégation de clic de l'onglet et publie les deux globales `ccwOuvrirOnglet`/`ccwRedemarrerProjet` encore appelées par l'ancien app.js).
- **`static/js/tests/pont_globales.test.js`** (garde-fou #632) : resté vert sans modification — le garde-fou couvre déjà les globales publiées par un module, quel qu'il soit.
- **Tests** : `static/js/tests/ccw.test.js` (nouveau, 8 tests de logique pure). `node --test static/js/tests/` → 112 passed (104 avant + 8 nouveaux, aucune régression). `node --test static/js/socle/tests/` → 29 passed.
- **`ARCHITECTURE.md`** §6.5/§6.7 et **`VERIFICATIONS_MANUELLES.md`** (section « Onglet CCW ») mis à jour.

Fichiers modifiés : `static/js/ccw.js` (nouveau), `static/js/panneau_lateral.js`, `static/js/app.js`, `static/js/socle/index.js`, `templates/fragments/onglet_ccw.html`, `static/js/tests/ccw.test.js` (nouveau), `ARCHITECTURE.md`, `VERIFICATIONS_MANUELLES.md`, `CONTEXTE.md`.

Vérifications manuelles (DOM/réseau/rendu) non rejouées par CCL — voir `VERIFICATIONS_MANUELLES.md` section « Onglet CCW » à rejouer par Alain.

# CHANGELOG-648 — à fusionner dans CHANGELOG.md

## 26 septembre 2026 — issue #648

URGENT — le label `sans-redacteur` n'existait sur aucun dépôt, `gh issue create` échouait systématiquement pour une issue sans REDACTEUR (régression bloquante #647).

Cause : `LABELS` (`nouveau_projet.py`), la liste des labels provisionnés à la création de chaque projet, n'avait pas été mise à jour par #647 pour y inclure `sans-redacteur` — le label posé par `construire_labels()` dès que `REDACTEUR` est absent de l'en-tête n'existait donc sur AUCUN dépôt GitHub, provoquant l'échec de `gh issue create` (`could not add label: 'sans-redacteur' not found`) et le rejet du fichier entier pour toute issue sans ce champ facultatif.

- **`nouveau_projet.py`** : ajout de `("sans-redacteur", "c2b280", "Posé automatiquement — l'issue ne précisait pas REDACTEUR")` à `LABELS` — tout nouveau projet le provisionne désormais d'office (via `creer_labels()`/`etape_labels()`, inchangés sinon).
- **Dépôts existants** : `sans-redacteur` créé manuellement (`nouveau_projet.creer_labels()`, idempotent) sur les 13 dépôts listés au §1 de `BRIDGE_AGENT_DOC.md` — `AlainDelree/{Actualise, AlChess, ApiSelect, Bloc_score, Bridge_Agent, Chesscoach, Diagnostique_Programme, Ecole, FF_Galerie, GestionMail, Relecture_Bridge, Rummikub, Scrabble}`. Résultat : `sans-redacteur` créé sur les 13 (aucun ne l'avait) ; aucun autre label standard manquant détecté au passage. `configs/*.conf` non modifié (hors périmètre autorisé) — seul l'état GitHub des dépôts a été corrigé.
- **`app/issues.py`** : nouvelle fonction `creer_issue_gh(depot, titre, labels, chemin_body, env=None, timeout=30)`, point d'appel commun de `gh issue create` — retire automatiquement de la liste tout label ABSENT du dépôt cible (détecté via le message d'erreur exact de gh, `could not add label: '<nom>' not found`) et journalise l'anomalie (`log.warning`, nouveau `log = logging.getLogger(__name__)` du module) au lieu de faire échouer toute la création. gh échouant de façon **atomique** avant de créer l'issue dès qu'un label manque (vérifié par test direct), réessayer sans le label fautif ne crée jamais de doublon ; comme gh ne rapporte qu'un seul nom manquant à la fois, la boucle retire les labels un par un (plafonnée au nombre de labels de départ). Retourne `(succes, resultat, labels_effectifs, labels_omis)`.
  - `envoyer()` : remplace l'appel `subprocess.run` direct par `creer_issue_gh()` ; réponse JSON enrichie d'un champ `labels_omis` (informatif, ignoré si absent côté navigateur) ; blocs `except subprocess.TimeoutExpired`/`FileNotFoundError` désormais gérés à l'intérieur de `creer_issue_gh()`, supprimés de `envoyer()` (devenus redondants).
- **`scripts/watcher_issues_inbox.py::_creer_issue()`** : réutilise `creer_issue_gh()` (importé depuis `app.issues`) au lieu de dupliquer l'appel `gh issue create` ; journalise (`log.warning`) le ou les labels omis, sans changer la signature externe `(succes, resultat)` consommée par `_traiter_bloc()`.
- **Option retenue et pourquoi** : retrait silencieux (côté GitHub) + journalisation, plutôt que création à la volée du label manquant — un `gh label create` déclenché automatiquement à chaque issue exigerait de connaître une couleur/description pertinente pour un label ARBITRAIRE (notamment ceux du champ `LABELS` de l'en-tête, jamais définis dans `nouveau_projet.LABELS`) et modifierait l'état du dépôt sans validation préalable ; omettre le label secondaire garantit que la création de l'issue — l'objectif prioritaire — ne dépend jamais d'un provisionnement GitHub oublié, au prix d'un label cosmétique manquant une fois, visible dans les logs.
- **`BRIDGE_AGENT_DOC.md`** : §4 (ajout de `sans-redacteur` au tableau des labels) et §17.3 (paragraphe dédié à la régression #647→#648 et au mécanisme de repli).
- **Tests** : `tests/test_label_manquant_648.py` (nouveau) — `nouveau_projet.LABELS` contient `sans-redacteur` ; `creer_issue_gh()` omet un label manquant et réussit (reproduction du bug #648) ; gère plusieurs labels manquants successifs ; n'entre pas en boucle sur une erreur gh d'un autre type (dépôt inconnu). Non-régression : `tests/test_label_sans_redacteur_647.py`, `tests/test_champ_redacteur_599.py`, et l'ensemble de la suite (106 tests, tous au vert).

Fichiers modifiés : `nouveau_projet.py`, `app/issues.py`, `scripts/watcher_issues_inbox.py`, `BRIDGE_AGENT_DOC.md`, `tests/test_label_manquant_648.py` (nouveau).

Tests : `python3 -m pytest tests/` → 106 passed. `py_compile` sur tous les fichiers Python touchés = OK.

# CHANGELOG-647 — à fusionner dans CHANGELOG.md

## 26 septembre 2026 — issue #647

Avertissement visible (non bloquant) quand une issue arrive sans champ REDACTEUR.

Besoin d'Alain : dans les conversations Claude Chat longues (plusieurs projets abordés sans changer de session), Claude Chat peut rédiger une issue sans indiquer `REDACTEUR` (issue #599) — l'absence totale de signal fait qu'Alain ne s'en aperçoit pas. `REDACTEUR` reste optionnel, sans changement de comportement (rétrocompatibilité volontairement conservée) : ce correctif ajoute un simple **signal visuel**, jamais un blocage.

- **`watcher.py`** : nouvelle constante `LABEL_SANS_REDACTEUR = "sans-redacteur"`, aux côtés des autres labels du protocole partagé.
- **`scripts/watcher_issues_inbox.py::construire_labels()`** : pose ce label sur l'issue créée **uniquement** quand `REDACTEUR` est absent de l'en-tête (cas déjà accepté par `valider_redacteur()`, qui renvoie `(True, "")` pour ce cas). `REDACTEUR` présent (cohérent ou non — l'incohérence a son propre traitement, rejet vers `rejected/`, inchangé) → jamais posé. Garde anti-doublon si le label est déjà demandé manuellement via le champ `LABELS` de l'en-tête.
- **`app/issues.py::envoyer()` (formulaire web) : volontairement NON modifié.** Ce chemin ne propose aucun champ `REDACTEUR` — `construire_labels(data)` n'en lit jamais depuis `data` du formulaire. Y appliquer la même logique aurait posé le label sur 100 % des créations de ce chemin sans exception (Alain tapant directement dans le navigateur, jamais Claude Chat) : un signal toujours vrai ne distinguant jamais rien, donc du code mort en pratique — écarté sciemment, documenté dans `BRIDGE_AGENT_DOC.md` §17.3.
- **Badge « sans REDACTEUR » (onglet Résultats)** : nouvelle fonction pure `calculerBadgeSansRedacteur(labels)` dans `static/js/resultats.js`, même patron que le badge « modèle forcé » (#638) — enrichissement à partir des labels déjà connus (aucun appel GitHub supplémentaire), span toujours présent dans le DOM (masqué si rien à afficher), rafraîchi à chaque tick par `majBadges()`. Réutilise `normaliserNomsLabels()` (désormais exportée par `static/js/actions_ligne.js`) plutôt que de dupliquer la normalisation objet/chaîne des labels GitHub. Pastille ambrée discrète (`.badge-sans-redacteur`, `static/css/resultats.css`), infobulle « Créée sans REDACTEUR », placée juste après le badge modèle dans `static/js/app.js` (construction de la ligne). Exposée sous `window.Bridge.resultats.calculerBadgeSansRedacteur`.
- **Documentation** : `BRIDGE_AGENT_DOC.md` §3.4 (pose du label côté validation) et §17.3 (badge côté navigateur, y compris le choix de ne pas modifier le formulaire web) ; `VERIFICATIONS_MANUELLES.md` (nouvelle case à cocher sous le badge modèle #638).

Fichiers modifiés : `watcher.py`, `scripts/watcher_issues_inbox.py`, `static/js/actions_ligne.js`, `static/js/resultats.js`, `static/js/app.js`, `static/css/resultats.css`, `static/js/tests/resultats.test.js`, `BRIDGE_AGENT_DOC.md`, `VERIFICATIONS_MANUELLES.md`, `tests/test_label_sans_redacteur_647.py` (nouveau).

Tests : `python3 -m pytest tests/test_label_sans_redacteur_647.py` (6 scénarios, dont le chemin complet `traiter_fichier()`) + non-régression `tests/test_champ_redacteur_599.py`/`tests/test_modele_effectif_638.py`/`tests/test_creation_issue_enrichie_634.py` — tous au vert. `node --test static/js/tests/` — 104/104 OK (dont les 4 nouveaux scénarios `calculerBadgeSansRedacteur`). `py_compile` sur tous les fichiers Python touchés = OK.

## 26 septembre 2026 — issue #646

Refonte interface web — étape 11 (finale) : balayage final.

Dernière étape de la refonte de l'onglet Résultats (#625→#645) : nettoyage de ce que les étapes précédentes avaient laissé de côté, sans rouvrir de chantier fonctionnel.

- **`scripts/son_actif.txt` retiré du suivi git** (`git rm --cached`, fichier et contenu inchangés sur disque) et ajouté à `.gitignore` — c'est un fichier d'ÉTAT COURANT (interrupteur global plat/cloche, réécrit à chaque bascule depuis l'interface), même nature que `configs/*.conf` déjà gitignorés pour la même raison. Il n'apparaîtra plus dans `git status` après une bascule de son. Aucun mécanisme (watcher, tests) ne supposait qu'il était versionné.
- **Nouveau module partagé `plafond_nettoyage.py`** (`seuil_nettoyage(numeros, marge)` + `numeros_perimes(numeros, marge)`) : factorise la règle « plus grand numéro connu par projet moins une marge de 50 » jusqu'ici dupliquée entre `etat_cases_cochees.nettoyer_anciennes()` (#629) et `etat_son_issue.nettoyer_entrees_perimees()` (#630). Chaque appelant garde son propre format de stockage (liste pour l'un, dict numéro→valeur pour l'autre) ; seul le calcul du seuil et la sélection de ce qui doit partir sont mutualisés. Comportement observable inchangé (mêmes entrées retirées, tests existants inchangés au vert). Nouveau test `tests/test_plafond_nettoyage_646.py` (6 scénarios) sur la fonction de seuil, indépendamment du format de stockage.
- **Résidus JS de la refonte retirés** (zéro appelant trouvé, en production comme en test, y compris via le pont `window.Bridge.*`) :
  - `static/js/socle/dom.js` : `$`, `$$`, `creerElement` (seul `echapperHtml` + le registre de délégation restent).
  - `static/js/socle/sse.js` : `estOuvert`/`source` (accesseurs du contrôleur de canal), `connecterTout`/`fermerTout`, et tout le canal `/events` (`surShutdown`, jamais connecté — `/events` reste géré indépendamment par l'ancien `app.js`, qui a sa propre `EventSource` et son propre handler `shutdown`, ne lisant jamais `store.serveurArrete`).
  - `static/css/resultats.css` : classe orpheline `.barre-issue` (absente de tous les templates).
  - Aucun résidu Watchers/Résultats-inbox trouvé (déjà proprement retirés aux étapes précédentes) ; aucun `alert()`/`confirm()` introduit par `resultats.js`/`resultats_coches.js`/`panneau_lateral.js`/`actions_ligne.js` en dehors de ceux d'`app.js` déjà connus.
- **Commentaires de transition corrigés** (devenus factuellement inexacts au fil des étapes, sans changement de comportement) : `static/js/socle/index.js` (le bloc « le socle ne remplace pas tout encore » décrivait un état d'étape 1 alors que `/stream`, la délégation et le rendu piloté par le store sont actifs depuis #627/#628/#632), `static/js/socle/store.js` et `static/js/socle/sse.js` (mêmes affirmations obsolètes), `static/js/app.js` (commentaire de `restaurerCasesCocheesResultats` référençant encore le localStorage alors que l'état est serveur depuis #636), `etat_cases_cochees.py` et `app/cases_cochees.py` (« aucun front ne les appelle encore » — faux depuis #636), `BRIDGE_AGENT_DOC.md` §3.15/§17.3 (« `fichier_recu`/`fichier_refuse` restent backend seul » — faux depuis la fusion #639), `ARCHITECTURE.md` §6.2/§6.3 (description `sse`/`dom` alignée sur le retrait ci-dessus et sur la connexion réelle de `/stream` depuis #627). Commentaires de doc de `resultats.js`/`resultats_coches.js` précisés pour lister exactement ce qui passe par le pont `window.Bridge.*` (`initialiser`/`rechargerCases` n'y passent pas) ; doc de `api.js` complétée (`api.lireJson` manquait de la liste des méthodes exposées).
- **`VERIFICATIONS_MANUELLES.md`** : déplacement de la vérification one-shot « Migration du localStorage » (issue #636, plus rien à rejouer en pratique) vers une nouvelle section « Archives » en fin de fichier, contenu conservé.

Fichiers modifiés : `.gitignore`, `scripts/son_actif.txt` (détracké), `plafond_nettoyage.py` (nouveau), `etat_cases_cochees.py`, `etat_son_issue.py`, `app/cases_cochees.py`, `static/js/app.js`, `static/js/resultats.js`, `static/js/resultats_coches.js`, `static/js/socle/{dom,sse,store,index,api}.js`, `static/css/resultats.css`, `ARCHITECTURE.md`, `BRIDGE_AGENT_DOC.md`, `VERIFICATIONS_MANUELLES.md`, `tests/test_plafond_nettoyage_646.py` (nouveau).

Tests : `python3 tests/test_*.py` — 30 fichiers, tous au vert (dont le nouveau). `node --test static/js/tests/ static/js/socle/tests/` — 129/129 OK, inchangé avant/après. `py_compile` sur tous les fichiers Python touchés = OK.

## 26 septembre 2026 — issue #645

Création/suppression de projet : `creer_projet()`/`supprimer_projet()` committent et poussent désormais **automatiquement** la mise à jour de `BRIDGE_AGENT_DOC.md` (§2/§7) dans le dépôt Bridge_Agent (issue #645) — jusqu'ici cette mise à jour restait purement locale sur disque, sans qu'aucun mécanisme n'invite Alain à la committer/pousser. Nouvelle fonction `regenerer_tableaux_projets.committer_pousser_doc()` : `git diff --quiet` décide s'il y a réellement quelque chose à committer (jamais de commit vide), puis `git add`/`commit`/`push`, avec un statut distinct par cas (`rien_a_faire`/`ok`/`push_echoue`/`echec`) — un push en échec (réseau, conflit…) ne fait pas échouer la création/suppression du projet, seule la doc reste à repousser à la main. Messages de fin (interface web `static/js/app.js` et scripts CLI) mis à jour en conséquence : l'encart « pousser la doc » côté création et le message de fin côté suppression ne s'affichent plus que si le commit/push automatique a réellement échoué, et ne mentionnent plus `configs/*.conf` (gitignoré, jamais committable). Tests : `tests/test_commit_doc_projet_645.py` (succès, push en échec, aucun changement réel, dépôt absent) + mise à jour de `tests/test_supprimer_projet_587.py` pour la nouvelle étape « Commit doc Bridge_Agent ».

## 26 septembre 2026 — issue #644

Refonte interface web — étape 10 : purge des fuites `localStorage`, accès centralisé via `persistance.js`.

`persistance.js` (issue #625, étape 1) était conçu depuis le début comme LE point d'accès unique au `localStorage`, mais son propre en-tête documentait que les clés historiques restaient lues/écrites directement par l'ancien `app.js` à l'étape 1. Cette étape termine cette migration et corrige la fuite connue de la suppression de projet.

- **Migration complète d'`app.js` vers `window.Bridge.persistance`.** Tous les accès directs à `localStorage` d'`app.js` (`bridge_projet_actif`, `bridge_limite_issues_projet`, `bridge_filtres_resultats`, `bridge_filtre_ouvriers`, `bridge_notif_pc`, `bridge_cache_detail_*`) passent désormais par `window.Bridge.persistance` (pont socle→ancien, `static/js/socle/pont.js`) — plus aucun accès `localStorage` direct en dehors de `persistance.js` (grep exhaustif de tous les `static/js/*.js`, confirmé). Les constantes de clé dupliquées dans `app.js` (`CLE_LIMITE_ISSUES`, `CLE_FILTRES_RESULTATS`, `CLE_FILTRE_OUVRIERS`, `CLE_NOTIF_PC`, `CLE_CACHE_DETAIL`) sont retirées au profit de `persistance.CLES.*` — source unique.
- **Deux amorçages déplacés après `DOMContentLoaded`.** `restaurerProjet()` et `initNotifPc()` (IIFE) tournaient à l'analyse du script, AVANT que le module socle publie `window.Bridge` (script classique `app.js` exécuté en premier, module `socle/index.js` différé — voir `templates/fragments/scripts.html`) : ils lisaient donc `window.Bridge` inexistant. Corrigé en les posant sur `window.addEventListener('DOMContentLoaded', …)`, comme `rafraichirReplisRepTravail` le faisait déjà pour la même raison.
- **Fuite corrigée : suppression d'un projet (flux #587).** `soumettreSupprimerProjet()` ne purgeait AUCUNE clé `localStorage` du projet supprimé. Nouvelle fonction `persistance.purgerProjet(nom)` : retire tout le cache détail du projet (`bridge_cache_detail_<nom>_*`, via `supprimerParPrefixe`) et son entrée dans `bridge_filtres_resultats`.
- **Accumulation du cache détail réduite.** Le cache détail n'expirait qu'à la LECTURE (TTL 60s) et ne se supprimait jamais tout seul ; il n'était purgé que par `rafraichirResultats()` (↻ explicite), et seulement pour les projets actifs du filtre — un projet consulté puis retiré du filtre accumulait indéfiniment. Désormais : `rafraichirResultats()` purge TOUT le cache détail (`purgerCacheDetailProjets(null)` — simplification, les projets actifs en filtre étaient de toute façon déjà repurgés avant #644) ; `basculerFiltreProjet()`/`basculerTousLesFiltres()` purgent en plus les entrées des projets sortis du filtre (`purgerCacheDetailHorsProjets`), à chaque bascule.
- **Autre accès direct trouvé au grep exhaustif.** `resultats_coches.js::migrerLocalStorage()` scannait tout le `localStorage` en direct (`localStorage.length`/`.key`/`.getItem`) pour retrouver les clés historiques `resultat-coche:*` — remplacé par la nouvelle `persistance.toutesLesEntrees()` (le module importait déjà `persistance` correctement pour la suppression, seule la lecture restait directe).

Nouvelles fonctions dans `persistance.js` : `cleCacheDetail(nom, numero)`, `toutesLesEntrees()`, `clesCacheDetailPourProjets(cles, noms)` / `clesCacheDetailHorsProjets(cles, nomsActifs)` (sélection PURE, testée), `purgerCacheDetailProjets(noms)` / `purgerCacheDetailHorsProjets(nomsActifs)` / `purgerProjet(nom)`.

Fichiers modifiés : `static/js/socle/persistance.js` (nouvelles fonctions + `CLES` promu source unique), `static/js/app.js` (migration complète, ~15 sites), `static/js/resultats_coches.js` (`migrerLocalStorage` via `toutesLesEntrees`), `static/js/socle/tests/persistance.test.js` (9 nouveaux tests), `ARCHITECTURE.md` (§6.3 + note étape 10), `VERIFICATIONS_MANUELLES.md` (suppression de projet → purge `localStorage`), `CONTEXTE.md`.

Tests : `node --test static/js/socle/tests/ static/js/tests/` = 129 OK (120 avant + 9 nouveaux). `node --check` sur les 3 fichiers JS modifiés = OK. Aucun changement Python.

## 26 septembre 2026 — issue #643

Refonte interface web — étape 8 : retrait des réglages de son de l'onglet Configuration.

Décision d'Alain, dès le début de la refonte : abandonner le réglage de son PAR PROJET (script bip et tonalité), déjà retiré du chemin réel du bip depuis #630 au profit du choix par issue (#630/#637/#641/#642). Cette étape retire les deux derniers champs qui l'exposaient encore dans l'interface.

- **`templates/fragments/onglet_config.html`** : retrait des champs « Script bip » (`#conf-SCRIPT_BIP`) et « Tonalité du bip » (curseur `#conf-TONALITE_BIP` + bouton « Tester le son »).
- **`static/js/app.js`** : `chargerConfig()`/`sauvegarderConfig()` ne lisent/écrivent plus `SCRIPT_BIP`/`TONALITE_BIP` ; suppression de `testerBip()`.
- **`app/projets.py`** : `SCRIPT_BIP`/`TONALITE_BIP` retirés de `CLES_EDITABLES` (ne sont plus éditables via `post_config`, silencieusement filtrés s'ils sont soumis) ; `get_config` ne les expose plus dans sa réponse JSON ; suppression de `tester_bip()`.
- **`app/__init__.py`** : retrait de la route `/tester-bip/<nom_projet>` et de son import.
- **`app/son.py`** : `tester_son()` (bouton « Tester le son » du panneau latéral, interrupteur global) ne lit plus `cfg.tonalite_bip` — tonalité toujours neutre, cohérent avec le chemin réel du bip depuis #630 (cette lecture par projet était devenue un résidu trompeur : le vrai bip de fin d'issue n'en tenait déjà plus compte).
- **`nouveau_projet.py`** : suppression de `SCRIPT_BIP_DEFAUT` (pointait vers `scripts/bip_Cloche.py`, supprimé par #630) et du paramètre `script_bip` (`ecrire_conf`, `creer_projet`, `etape_conf`) ; le gabarit `GABARIT_CONF` n'écrit plus de ligne `SCRIPT_BIP` ni le commentaire `# TONALITE_BIP = 0` dans le `.conf` d'un nouveau projet.
- **Tolérance préservée** : `watcher.py::charger_config()` continue de lire `SCRIPT_BIP`/`TONALITE_BIP` s'ils sont présents dans un `.conf` existant (défauts sensés sinon), sans erreur ni avertissement bruyant — les `configs/*.conf` d'Alain qui portent encore ces clés (ex. l'ancien `chesscoach.conf` → `bip_Cloche.py`) continuent de fonctionner ; leur retrait manuel reste à sa discrétion (`configs/*.conf` gitignorés, hors périmètre agent, §11).
- **Documentation** : `BRIDGE_AGENT_DOC.md` §17 (modèle son à deux niveaux uniquement — interrupteur global + choix par issue, plus de tonalité par projet) et §14 (comparaison de slider devenue obsolète) ; `VERIFICATIONS_MANUELLES.md` (onglet Configuration : plus aucun réglage de son ; panneau latéral : « Tester le son » à tonalité neutre) ; commentaires obsolètes corrigés dans `app/__init__.py`, `templates/fragments/panneau_lateral.html`, `scripts/traitement_fin.py`, `watcher.py`.
- **Tests** : `tests/test_retrait_son_par_projet_643.py` (nouveau) — `CLES_EDITABLES` sans `SCRIPT_BIP`/`TONALITE_BIP` ; `get_config`/`post_config` tolèrent un `.conf` existant qui les porte encore, sans erreur, sans les exposer ni les modifier ; gabarit `nouveau_projet.ecrire_conf()` sans `SCRIPT_BIP`/`TONALITE_BIP`/`bip_Cloche.py` ; signature de `creer_projet()` sans `script_bip`. 86 tests pytest et 100 tests Node passent (aucune régression).

## 26 septembre 2026 — issue #642

Refonte interface web — correctif étape 6 : interrompre une issue en LECTURE (capacité perdue), crayon purement informatif, infobulles.

Retour d'Alain après vérification de #641 : `interrompreIssue()` (`static/js/app.js`) fonctionne pour une issue en LECTURE comme en ÉCRITURE — ce n'est pas une action réservée à `mode_write`. Mais #641 n'affichait l'action « interrompre » sur la ligne QUE via le préfixe ✏️ (donc uniquement pour une issue en écriture), et avait retiré du panneau latéral le bouton autonome « Interrompre l'issue » (ne laissant que « Interrompre et relancer », qui arrête TOUT le watcher du projet) — résultat : aucun moyen d'interrompre UNIQUEMENT une issue en LECTURE en cours sans relancer tout le watcher (régression par rapport à avant #641).

- **✏️ mode_write redevient purement informatif.** `static/js/actions_ligne.js` : `prefixeInformatifLigneOuverte()` (renommée depuis `actionLigneOuverte()`) et `rendrePrefixeLigneOuverte()` (renommée depuis `rendreBadgeActionLigne()`) ne posent plus d'`onclick` sur ✏️ — juste une infobulle « Mode écriture en cours ». ⚠️ needs-human reste cliquable, inchangé (« Retirer needs-human et relancer », déjà avec infobulle depuis #641).
- **Icône dédiée d'interruption, indépendante du mode.** Nouvelle fonction pure `afficherIconeInterruption(labels, timing)` (`actions_ligne.js`) : `true` dès que `timing.debut` est renseigné (même état que le décompte TIMEOUT actif de `resultats.js`, PAS le seul label `mode_write`) et que l'issue ne porte pas `needs-human` — donc aussi bien pour une issue en LECTURE qu'en ÉCRITURE ; `false` pour une issue « en file » (pas encore prise en charge), `needs-human` (déjà arrêtée) ou fermée. Rendu (`rendreIconeInterruption()`) : petit carré **vert « ✓ »** au repos, **rouge « ✕ » au survol** (CSS pur, aucun état JS intermédiaire) — le clic appelle directement `interrompreDepuisLigne()` → `interrompreIssue()` (`static/js/app.js`, INCHANGÉES) : même route `/interrompre`, même `confirm()`, même modale de résultat détaillée, aucune logique dupliquée. Comme le `timing` n'est pas toujours connu à la construction de la ligne, l'icône est toujours posée masquée (`display:none`) puis révélée par `resultats.js::majBadges()` à chaque recalcul (import direct de `afficherIconeInterruption` depuis `actions_ligne.js`) — même patron que `.ligne-tempsrestant`/`.ligne-estimation`, ce qui permet à l'icône d'apparaître dès le passage « en file » → « en cours » (événement `debut_issue`) sans reconstruire toute la ligne.
- **Panneau latéral inchangé.** Le bouton « Interrompre et relancer (watcher CCL) » reste tel quel (action à l'échelle du watcher, distincte de l'icône par-ligne).
- **CSS** (`resultats.css`) : `.badge-mode-ecriture` (curseur normal, plus cliquable) et `.badge-interrompre-ligne` (carré vert/rouge, bascule au survol via deux spans imbriqués `.badge-interrompre-ok`/`.badge-interrompre-stop`).
- **Tests.** `static/js/tests/actions_ligne.test.js` réécrit : non-régression du préfixe informatif (`prefixeInformatifLigneOuverte`), et couverture complète de `afficherIconeInterruption` (en cours lecture/écriture/sans-limite → true ; en file/needs-human/timing absent → false). 120 tests Node passent (`node --test static/js/tests/*.test.js static/js/socle/tests/*.test.js`).
- **Documentation.** `ARCHITECTURE.md` §6 (correctif étape 6), `BRIDGE_AGENT_DOC.md` (§ « Interrompre une issue bloquée » et § « Relancer une issue bloquée en needs-human », noms de fonctions à jour), `VERIFICATIONS_MANUELLES.md` (nouvelle case « icône dédiée d'interruption, en LECTURE comme en ÉCRITURE »), `CONTEXTE.md`.

## 26 septembre 2026 — issue #641

Refonte interface web — étape 6 : actions directes sur la ligne (retirer needs-human, interrompre, son par issue), retrait des doublons du panneau.

Remplace, pour une ligne OUVERTE de l'onglet Résultats, les préfixes purement statiques ⚠️ needs-human / ✏️ mode_write par des actions cliquables directement sur la ligne — pour éviter de sélectionner l'issue puis d'aller chercher l'action dans le panneau latéral (#628). Les badges ✅/Diff/All d'une ligne FERMÉE+done (issue #636) sont un mécanisme séparé, non touché.

- **Badge d'action sur la ligne.** `prefixeIssue()` (`static/js/app.js`) reste inchangée pour une ligne FERMÉE ; pour une ligne OUVERTE, `construireLigneIssueDOM` délègue désormais à `window.Bridge.actionsLigne.rendreActionsLigneOuverte` (nouveau module `static/js/actions_ligne.js`). ⚠️ needs-human devient cliquable → `relancerIssue()` (même route `/relancer-issue`, même confirmation qu'avant) ; ✏️ mode_write (sans needs-human) devient cliquable → `interrompreIssue()` (même route `/interrompre`, même confirmation détaillée + modale de résultat). `stopPropagation()` empêche la sélection de la ligne au clic (même patron que les badges ✅/Diff/All existants).
- **Son par issue déplacé du panneau à la ligne.** Contrôle compact « G/P/C » (Global/Plat/Cloche) sur chaque ligne ouverte, adapté à la largeur de ligne contrainte (#633) — remplace le contrôle textuel du panneau (issue #637, étape 7b), retiré de là. Les fonctions pures posées à #637 (`sonIssueDepuisReponse`, `normaliserChoixSonIssue`, `etatsOptionsSonIssue`) sont réutilisées telles quelles, déplacées de `panneau_lateral.js` vers `actions_ligne.js`. Chargement réseau **en bloc** : nouvelle route `GET /son-issue/<nom_projet>` (`app/son_issue.py::get_sons_projet`, `etat_son_issue.py::sons_projet`) renvoie tous les choix d'un projet en une requête — une seule requête **par projet** au premier rendu d'une ligne de ce projet, jamais par ligne (cache `fusionnerSonsProjet`/`sonConnuDansCache`, resync des lignes déjà rendues si la réponse arrive après coup). Le clic reste sur la route existante `POST /son-issue/<projet>/<numero>` (#630), mise à jour optimiste sans reconstruire toute la ligne.
- **Panneau allégé.** `panneau_lateral.js` perd les 3 actions désormais sur la ligne (bouton « Interrompre l'issue » seul, « Retirer needs-human », contrôle de son) — un seul emplacement par action. Reste dans le panneau : surveillance des watchers CCL/CCW + leurs relances, contrôle du watcher spool + historique, interrupteur GLOBAL de son, toggles 🔔 Notifications, « Interrompre et relancer » et **Fermer définitivement** (`fermerIssue`, action de clôture manuelle distincte, jamais demandée sur la ligne).

Fichiers modifiés : `static/js/app.js` (branchement de la ligne ouverte + 3 fonctions relais `retirerNeedsHumanDepuisLigne`/`interrompreDepuisLigne`/`choisirSonIssueDepuisLigne`), `static/js/panneau_lateral.js` (retrait des 3 actions + fonctions son), `static/js/socle/index.js` (import + pont), `static/css/resultats.css` (badge d'action + contrôle son compacts), `etat_son_issue.py` (`sons_projet`), `app/son_issue.py` (`get_sons_projet`), `app/__init__.py` (route `/son-issue/<nom_projet>`). Nouveau : `static/js/actions_ligne.js`, `static/js/tests/actions_ligne.test.js`. Tests mis à jour : `static/js/tests/panneau_lateral.test.js` (tests son déplacés), `tests/test_son_issue_630.py` (route/fonction groupées). Docs : `ARCHITECTURE.md` (§6.5, étape 6), `BRIDGE_AGENT_DOC.md`, `VERIFICATIONS_MANUELLES.md`, `CONTEXTE.md`.

Tests : `node --test static/js/socle/tests/ static/js/tests/` = 113 OK. `python3 tests/test_son_issue_630.py` = 17 OK. `python3 -m py_compile etat_son_issue.py app/son_issue.py app/__init__.py` = OK.

## 26 septembre 2026 — issue #639

Refonte interface web — étape 9b : fusion de « Résultats inbox » dans la liste Résultats, suppression de l'onglet séparé.

Branche l'interface sur le backend de l'étape 9a (#631, trois événements SSE `/stream`) : un fichier déposé dans `issues_inbox/` apparaît désormais **directement dans la liste Résultats** au lieu d'un onglet séparé, qui disparaît. Toute la logique vit dans `static/js/resultats.js` (moteur de l'onglet Résultats) et `static/js/socle/sse.js` ; `app.js` perd son ancien `rafraichirInbox()`.

- **Lignes en direct via SSE.** `sse.js` répartit deux nouveaux événements `/stream` (`fichier_recu`, `fichier_refuse`) dans une tranche dédiée `store.derniereNotifFichier` ; `creation_issue` transporte déjà le nom du fichier (#634). `resultats.js` en dérive un tableau de lignes affichées **en tête** de la liste :
  - `fichier_recu` → ligne **« 📥 fichier reçu : <nom> »** (sans case à cocher ni badges de temps) ;
  - `creation_issue` (avec fichier) → la **1ʳᵉ** création d'un fichier **retire** sa ligne « reçu » (la vraie ligne d'issue la remplace) ; les créations suivantes d'un fichier multi-issues s'ajoutent sans doublon ;
  - `fichier_refuse` → **transforme** la ligne « reçu » du fichier en **ligne rouge « ✕ fichier refusé : <nom> — <motif> »** (même position) ou, à défaut, insère directement une ligne rouge en tête (repli « refusé, motif indisponible » si le motif manque). Un lot multi-blocs partiellement refusé produit une ligne rouge **distincte par bloc refusé**.
- **Exclusion propre.** Ces lignes sont rendues en `.ligne-fichier` (jamais `.ligne-issue`) et **absentes de `store.issues`** : elles échappent nativement aux filtres projet, au quota d'affichage, aux pastilles, à la case à cocher / « Cocher tout » / « Tout à zéro » et au badge modèle — exclusion structurelle, pas seulement visuelle. Texte posé via `textContent` (aucun risque d'injection depuis un nom de fichier ou un motif).
- **Reconstruction/purge au rechargement.** Les lignes en direct sont **éphémères** (perdues au F5), sauf les fichiers **encore rejetés** : le polling `/issues-inbox/etat` (7 s, repris de `app.js` vers `resultats.js`, continu quel que soit l'onglet actif) reconstitue une ligne rouge par fichier de `rejetes` (`reconcilierRejetes`) et la **purge** dès que le fichier quitte `rejected/`. Les lignes reconstruites (`source:'etat'`) ne doublent jamais une ligne SSE encore présente.
- **Badge d'alerte déplacé.** Le badge 🚨 (`badge-alarme-inbox`), piloté par la présence de fichiers dans `issues_inbox/rejected/`, passe de l'ancien onglet à **l'onglet Résultats** (toujours à jour hors de cette vue grâce au polling continu).
- **Onglet supprimé, panneau enrichi.** Le fragment `onglet_inbox.html` et l'entrée `inbox` de la barre d'onglets disparaissent (retirés de `onglets.html`, `index.html`, `onglets.js#initialisationsPour`). L'**historique récent** du watcher spool (dernières lignes de `logs/issues_inbox.log`) rejoint le **panneau latéral**, sous le contrôle du watcher spool déjà présent (#628), dans un repli discret « Historique récent » (`<details>` fermé par défaut), sans fetch supplémentaire (réutilise l'`/issues-inbox/etat` déjà chargé par le panneau).

Fichiers modifiés : `static/js/socle/sse.js` (événements `fichier_recu`/`fichier_refuse`), `static/js/resultats.js` (logique pure des lignes + polling inbox + rendu), `static/js/panneau_lateral.js` (historique dans la zone extras), `static/js/onglets.js` (plus d'init `inbox`), `static/js/app.js` (suppression de `rafraichirInbox` + polling), `templates/fragments/onglets.html` (badge sur Résultats, plus d'onglet inbox), `templates/index.html` (include retiré), `static/css/inbox.css` (réduit au badge + historique du panneau), `static/css/resultats.css` (styles `.ligne-fichier`). Supprimé : `templates/fragments/onglet_inbox.html`. Nouveau : `static/js/tests/resultats_fichiers.test.js`. Tests mis à jour : `static/js/tests/onglets.test.js`. Docs : `ARCHITECTURE.md`, `BRIDGE_AGENT_DOC.md`, `VERIFICATIONS_MANUELLES.md`, `CONTEXTE.md`. Aucun changement Python (backend #631 réutilisé tel quel). Tests : `node --test static/js/tests/` = 88 OK.

## Issue #640 — Badge modèle absent sur une issue créée via issues_inbox tant que la page n'est pas rechargée

- **Backend** : l'événement SSE `creation_issue` transporte désormais `modele`/`modele_defaut` (dans le dict `timing`, mêmes primitives `extraire_modele_entete()`/`modele_defaut_projet()` que l'issue #638) — ajoutés dans les deux émetteurs, `app/issues.py::envoyer()` (formulaire web) et `scripts/watcher_issues_inbox.py::_traiter_bloc()` (issues_inbox), sans appel GitHub supplémentaire.
- **Frontend** : `majBadges()` (`static/js/resultats.js`) met désormais aussi à jour le badge « modèle forcé » d'une ligne déjà construite (via `calculerBadgeModele()` + `store.get('issues')`), sans reconstruire toute la ligne — corrige le cas où `debut_issue` backfillait `modele`/`modele_defaut` dans le store (issue #638) sans jamais redessiner le badge. `construireLigneIssueDOM()` (`static/js/app.js`) émet désormais systématiquement le span `.badge-modele` (masqué si rien à afficher), pour que `majBadges()` puisse le retrouver.
- Extraction d'une fonction pure `construireIssueCreation()` (testée sous Node) pour la construction de l'entrée `issues` du store à la création, incluant `modele`/`modele_defaut`.
- Tests : 4 nouveaux tests Node (`static/js/tests/resultats.test.js`) sur `construireIssueCreation()` ; suite Python existante (`tests/test_creation_issue_enrichie_634.py`, `tests/test_evenements_issues_inbox_631.py`) non modifiée, toujours verte (l'enrichissement est passé par le dict `timing` déjà opaque à ces tests). Entrée ajoutée à `VERIFICATIONS_MANUELLES.md` pour la partie DOM de `majBadges()`, non testable sous Node par convention du projet (aucun DOM dans les tests JS).

## 26 septembre 2026 — issue #636

Refonte interface web — étape 5b : case « traité/lu » à état serveur, copie fiable au cochage, pastilles et « Cocher tout » cohérents.

Branche l'interface sur le backend de l'étape 5a (#629, routes `/cases-cochees`) et corrige trois défauts connus de la case à cocher, dans un module dédié **`static/js/resultats_coches.js`** (sorti d'`app.js` selon `ARCHITECTURE.md §6.7` — choix d'un module propre, plus lisible que d'alourdir `resultats.js`). `app.js` ne garde que de minces relais appelés par le markup inline des lignes (`estResultatCoche`/`basculerCocheResultat`/`cocherToutesVisibles` et les badges de copie délèguent au module via le pont).

- **État serveur de la case.** La case « traité/lu » ne vit plus dans le `localStorage` (`resultat-coche:<projet>:<numero>`) mais dans `store.casesCochees` (`{ nomProjet: [numero, …] }`), synchronisé avec le serveur : **un seul `GET /cases-cochees/<projet>` par projet** au chargement (jamais un par issue). L'état survit à un plantage/redémarrage du PC et est **identique quel que soit le navigateur ou l'adresse** (localhost / `--lan`).
- **Migration idempotente de l'existant.** Au premier chargement, les clés héritées `resultat-coche:*` du `localStorage` sont extraites (`extraireCasesLegacy`), envoyées **en une fois** à `POST /cases-cochees/importer`, puis retirées du `localStorage`. Rejouable sans dégât (import idempotent côté serveur ; clés retirées seulement après succès de l'import).
- **Copie fiable au cochage.** Cocher une case (ou cliquer un badge ✅/Diff/All) **engage la copie pendant le geste utilisateur**, plus jamais après un ou plusieurs fetch réseau (cause des échecs intermittents) : en **contexte sécurisé** (localhost/HTTPS) via un `ClipboardItem` alimenté par une **promesse** (`navigator.clipboard.write` appelé synchroniquement au clic, le détail+diff est fetché ensuite) ; en **contexte non sécurisé** (`--lan`, API presse-papier moderne indisponible) via un **préchargement** en tâche de fond du détail+diff des issues visibles décochées, puis `execCommand` **synchrone** au clic. `decisionModeCopie(contexteSecurise, clipboard, clipboardItemDispo)` tranche entre les deux modes. Les copies apparentées (badges Diff/All/✅) sont **factorisées** dans le même moteur (`lancerCopie`) au lieu d'être dupliquées.
- **Feedback honnête.** Plus jamais de ✓ affiché sur un échec : un échec de copie est signalé par un **toast** (composant socle, disparaît seul — jamais de boîte « OK »). Le cochage lui-même (persistance serveur, grisage, pastilles) **ne dépend jamais** de la réussite de la copie. Décocher ne copie rien.
- **Pastilles ↔ « Cocher tout » alignés.** Choix retenu : **élargir « Cocher tout »** au périmètre exact compté par les pastilles (les N premières issues par projet, `premieresParProjet`, sans le quota d'affichage ni le filtre ouvriers) plutôt que restreindre les pastilles — la pastille garde ainsi son sens (nombre réel d'issues à traiter par projet). Après « Cocher tout » (pour les projets filtrés), aucune pastille des projets actifs ne reste.
- **Nouveau bouton « ⊘ Tout à zéro »** (à côté de « Cocher tout ») : marque comme cochées, côté serveur (`POST /cases-cochees/importer`), **toutes** les issues chargées de **tous** les projets, quel que soit le filtre courant. Confirmation légère (`toasts.confirmer`). **Ne déclenche aucune copie.**

Fichiers : nouveau `static/js/resultats_coches.js` ; nouveau `static/js/tests/resultats_coches.test.js` (logique pure : fusion de l'état dans le store, décision du mode de copie, migration idempotente, périmètre `premieresParProjet`). Modifiés : `static/js/socle/store.js` (tranche `casesCochees`), `static/js/socle/index.js` (import + `installerPont` + `initialiser`), `static/js/app.js` (relais + nouveau bouton), `static/css/resultats.css` (style du bouton), `ARCHITECTURE.md` (§6.5/§6.7 étape 5b), `BRIDGE_AGENT_DOC.md`, `VERIFICATIONS_MANUELLES.md`, `CONTEXTE.md`. Aucun changement Python (backend #629 réutilisé tel quel). Tests : `node --test static/js/tests/ static/js/socle/tests/` = 75 OK.

## 26 septembre 2026 — issue #638

Résultats : mettre en évidence les issues qui forcent un modèle différent du défaut du projet.

Constat : une issue peut imposer un modèle précis via le champ `| MODELE | … |` de son en-tête (§3), mais rien ne distinguait visuellement, dans l'onglet Résultats, une issue lancée sous un modèle forcé (ex. Opus) d'une issue tournant sous le modèle par défaut du projet.

- **Serveur — modèle effectif exposé par trois routes** (`app/issues.py`) : les réponses de `/issues-liste`, `/recherche-issues`, `/issues-en-attente` et `/issue` portent désormais deux champs par issue :
  - `modele` — modèle effectif lu dans le champ `MODELE` du **corps** de l'issue, `null` si le champ est absent, vide ou porte une valeur inconnue. Une **primitive unique**, `extraire_modele_entete(body)`, dédiée à la lecture depuis un corps d'issue GitHub (distincte de `watcher.extraire_modele`, qui retombe sur son `CFG` global, et du parseur d'`issues_inbox` de `scripts/watcher_issues_inbox.py`), partagée par les quatre routes ;
  - `modele_defaut` — modèle par défaut **réel du projet** (`MODELE_CCL` du `.conf` s'il en fixe un, sinon `claude-sonnet-5`), via `modele_defaut_projet(cfg)` — une valeur par projet, répétée sur chaque issue pour garder des tableaux JSON simples.
  `/issues-liste` (et `/recherche-issues`, via `_lister_issues_labels`) demandent désormais le champ `body` à `gh issue list`, retiré aussitôt après extraction du modèle (`_enrichir_modele`) : il ne transite jamais jusqu'au navigateur.
- **Navigateur — badge discret « modèle forcé »** : la décision « afficher/masquer » est prise par l'unique fonction pure `calculerBadgeModele(modele, modele_defaut)` de `static/js/resultats.js` (exposée via `window.Bridge.resultats`), qui n'affiche le badge que si le modèle effectif diffère du défaut du projet ; `libelleModele()` en dérive le nom court (« opus », « haiku », « fable », « sonnet »). `static/js/app.js` (`construireLigneIssueDOM`) insère le badge entre le titre et les badges de temps, sans les recouvrir — présent aussi pour les issues fermées et dans la fenêtre de recherche par titre. Une issue sans champ `MODELE`, ou avec le modèle par défaut du projet, n'affiche rien de plus qu'avant. Style discret (pastille violet sourd) dans `static/css/resultats.css`. Les issues créées/mises à jour via SSE (`surCreationIssue`/`surDebutIssue`/`fin_issue`) et le rafraîchissement du timing propagent aussi ces champs dans le store.
- Tests : `tests/test_modele_effectif_638.py` (pytest — extraction depuis un corps : présent, absent, invalide/inconnu/vide → aucun plantage ; insensibilité à la casse ; `modele_defaut_projet` ; `_enrichir_modele`) ; `static/js/tests/resultats.test.js` (`node --test` — `calculerBadgeModele`/`libelleModele` : rien sans `MODELE`, rien quand le modèle forcé est le défaut, badge affiché sinon, défaut projet non-Sonnet).
- Documentation : `BRIDGE_AGENT_DOC.md` §17.3 (nouveaux champs de réponse `modele`/`modele_defaut` et badge) et `VERIFICATIONS_MANUELLES.md` (onglet Résultats) mis à jour.

## 26 septembre 2026 — issue #637

Refonte interface web — étape 7b : contrôle à 3 états « Son de cette issue » (Global/Plat/Cloche) dans le panneau latéral.

Contexte : l'étape 7a (#630) avait posé le backend du son par issue (`etat_son_issue.py`, routes `GET`/`POST /son-issue/<projet>/<numero>`) sans aucun bouton dans l'interface. L'étape 6 (badges ✅/Diff/All de la ligne Résultats → actions sur la ligne) n'étant pas encore faite, le contrôle est ajouté dans la zone Actions du panneau latéral (issue sélectionnée), à côté des toggles 🔔 Notifications déjà présents.

- **`static/js/panneau_lateral.js`** : fonctions pures `sonIssueDepuisReponse` (réponse serveur → `'plat'|'cloche'|null`), `normaliserChoixSonIssue` (valeur du bouton cliqué → valeur à poster), `etatsOptionsSonIssue` (état actif des 3 boutons, mutuellement exclusifs) ; rendu `rendreSonIssue()` dans `rendrePanneauLateralActions()` (devenue `async`), visible tant que l'issue sélectionnée n'est pas fermée. Une seule requête `GET /son-issue` par sélection d'issue (mise en cache — `sonIssueSelectionCle`/`sonIssueSelectionValeur` — tant que la sélection ne change pas, pas de refetch au cycle de rafraîchissement de 30s). Clic sur une option : mise à jour optimiste + `POST /son-issue`, retour à l'état précédent et toast d'erreur (via `api.post`, non silencieux) en cas d'échec réseau.
- **`templates/fragments/panneau_lateral.html`** : infobulle sur la ligne « Timbre » de l'interrupteur global (`#pl-zone-son`) rappelant qu'un choix par issue prime sur lui pour cette issue précise ; commentaire d'en-tête mis à jour pour `#pl-zone-actions`.
- **`app/son_issue.py`** : docstring mis à jour (l'étape backend seule #630 a désormais son bouton, étape 7b #637).
- Tests : `static/js/tests/panneau_lateral.test.js` — 13 nouveaux cas (`sonIssueDepuisReponse`, `normaliserChoixSonIssue`, `etatsOptionsSonIssue`, dont la bascule des 3 états). `node --test static/js/tests/ static/js/socle/tests/` → 69/69.
- `VERIFICATIONS_MANUELLES.md` (nouvelle entrée détaillée sous « Zone actions contextuelles ») et `BRIDGE_AGENT_DOC.md` (§ son PAR ISSUE) mis à jour pour documenter l'emplacement choisi et sa reprise prévue à l'étape 6.

## 26 septembre 2026 — issue #635

Tests : ne jamais envoyer d'événements au `new_issue.py` réel (toasts « mise à jour impossible » pour des projets fictifs).

Constat : pendant qu'une issue exécutait la suite de tests (ou qu'Alain lançait `pytest`/un script de `tests/` à la main), l'interface web en service recevait de vrais POST `/notifier-debut-issue`/`/notifier-fin-issue` pour des projets/numéros fictifs (`tests/test_worktree_parallelisation_337.py` exerce le vrai code de `watcher.py` de bout en bout) et affichait un toast rouge « mise à jour impossible » pour chacun.

- **Neutralisation globale et automatique** (`scripts/utils.py::notifications_reseau_neutralisees()`) : détecte un run pytest (`PYTEST_CURRENT_TEST` ou `pytest` déjà importé) OU l'exécution directe d'un script situé sous `tests/` (`sys.modules['__main__'].__file__`, cas des tests autonomes historiques de ce dépôt, ex. `test_worktree_parallelisation_337.py`). Un seul point d'appel dans chacun des deux émetteurs best-effort — `scripts/traitement_fin.py::_notifier()` (notifier_fin_issue/notifier_debut_issue) et `scripts/watcher_issues_inbox.py::_poster_best_effort()` — retourne immédiatement sans tenter le POST. Échappatoire explicite si un futur test doit vérifier l'envoi réel : variable d'environnement `BRIDGE_AGENT_NOTIFS_RESEAU_FORCEES=1`. Les tests qui interceptent déjà ces envois en remplaçant la fonction entière (`traitement_fin.notifier_fin_issue`, `w._poster_best_effort`) ne sont pas affectés.
- **Défense en profondeur côté interface** (`static/js/resultats.js::planifierEvenementSse`) : nouveau paramètre `projetsConnus` — un événement `/stream` dont le projet ne figure pas parmi les projets configurés (sélecteur global `#projet`) est ignoré avant même de regarder son type, donc sans jamais déclencher de fetch ni de toast.
- **Anti-empilement des toasts** (`static/js/socle/toasts.js`) : une rafale de toasts identiques (même type + même texte) réutilise le toast déjà affiché (compteur « (×N) », minuteur de disparition relancé) au lieu d'en empiler un nouveau à chaque fois.
- Tests : `tests/test_neutralisation_notifs_reseau_635.py` (neutralisation active pendant pytest, détection du script direct, échappatoire, aucun appel `urlopen` depuis `_notifier`/`_poster_best_effort`) ; `static/js/tests/resultats.test.js` (3 nouveaux cas `planifierEvenementSse` pour le filtrage par projet connu/inconnu). Suite complète revérifiée : `python3 -m pytest tests/` (71 passés) + les 20 scripts autonomes de `tests/` exécutés directement (dont `test_worktree_parallelisation_337.py`) ; `node --test static/js/tests/ static/js/socle/tests/` (58 passés).
- `VERIFICATIONS_MANUELLES.md` mis à jour (onglet Résultats : absence de toast parasite pendant la suite, anti-empilement).

## 26 septembre 2026 — issue #634

Refonte interface web — badge « en file » qui disparaît et labels absents à la création d'une issue via `issues_inbox` (issue #634, suite #626→#633).

Cause identifiée dans `static/js/resultats.js` : après `creation_issue`, `surCreationIssue()` enchaînait un fetch `chargerTimingProjet()` pour enrichir labels/estimation — mais juste après `gh issue create`, la réponse de `/issues-en-attente` peut ne pas encore contenir l'issue tout juste créée (décalage d'indexation GitHub). `chargerTimingProjet()` purgeait alors INCONDITIONNELLEMENT toutes les entrées de timing du projet avant de les réinjecter : l'entrée « en file » de l'issue absente de la réponse disparaissait, et ses labels (jamais transportés par l'événement `creation_issue`) restaient vides jusqu'à la prise en charge par le watcher (`debut_issue`).

- **Événement `creation_issue` enrichi côté serveur** (`app/issues.py`) : nouvelle fonction `donnees_temps_creation(cfg, titre, body, labels, historique=None)`, source UNIQUE du calcul timeout/max_essais/backoff/priorite/sans_limite/estimation — réutilisée par `issues_en_attente()` (route `/issues-en-attente`, comportement inchangé) ET par les deux chemins de création, sans aucun appel GitHub supplémentaire :
  - `app.issues.envoyer()` (formulaire web) calcule `donnees_temps_creation()` juste après le `gh issue create` réussi et la transmet à `app.fin_issue.emettre_creation_issue()` (appel direct, même process) ;
  - `scripts/watcher_issues_inbox.py::_traiter_bloc()` fait de même et la transmet à `_notifier_creation_issue()` → `POST /notifier-creation-issue` → `emettre_creation_issue()`. `_traiter_bloc()`/`_traiter_relance()` retournent désormais un tuple à 7 éléments (`+labels, +donnees_temps`, `None`/`None` pour un échec ou une `RELANCE`, qui ne crée jamais d'issue).
  - `emettre_creation_issue()`/`notifier_creation_issue()` diffusent `labels`/`timing` dans l'événement SSE : `{"projet", "numero", "titre", "fichier", "labels", "timing"}` — `timing` a exactement la forme de ce que `/issues-en-attente` calcule, `debut` valant toujours `null` (issue « en file », jamais prise en charge).
- **Côté navigateur** (`static/js/resultats.js`) : `surCreationIssue()` affiche désormais la ligne avec ses **vrais labels** et son **estimation/« en file »** directement depuis les champs `labels`/`timing` de l'événement — plus aucun fetch réseau après la création.
- **Robustesse générale de `chargerTimingProjet()`** (utilisée par `debut_issue` et ↻) : nouvelle fonction pure `fusionnerTimingProjet(ancienTiming, nom, liste, issuesConnues, maintenant)` — une issue OUVERTE et RÉCENTE (< `FENETRE_RECENTE_TIMING_MS` = 30s) absente de la réponse n'est plus effacée (décalage GitHub) ; passé ce délai, l'absence est traitée comme une vraie fin d'issue (clôture, `needs-human` — issue #523) et l'entrée est retirée normalement. Le retrait explicite reste déclenché par `fin_issue`/la vérification post-dépassement (#334)/↻, jamais par une simple absence.
- Tests : `tests/test_creation_issue_enrichie_634.py` (contenu de `donnees_temps_creation()`, cohérence avec `estimer_duree()`, `app.issues.envoyer()` bout en bout — un seul appel `gh`) ; `static/js/tests/resultats.test.js` (5 nouveaux cas `fusionnerTimingProjet`, `node --test`) ; mise à jour de `tests/test_evenements_issues_inbox_631.py`, `tests/test_champ_relance_516.py`, `tests/test_champ_redacteur_599.py` pour la nouvelle forme des tuples/événements.
- `BRIDGE_AGENT_DOC.md` (§3.15, §17.3) et `VERIFICATIONS_MANUELLES.md` mis à jour.

Tests : `python3 tests/test_*.py` (26 fichiers, tous OK) ; `node --test static/js/tests/` → 35/35.

## 25 septembre 2026 — issue #633

Refonte interface web — correctifs après vague 1 (issue #633, suite #626→#632) : cinq défauts relevés par vérification manuelle après la vague 1.

- **Largeur de la liste Résultats** : `.fenetre` (`static/css/base.css`) élargie de 1160px à 1520px — depuis #628 le panneau latéral occupe sa propre colonne (340px + 16px de gap) au lieu de flotter en overlay, ce qui avait réduit d'autant la largeur disponible pour la liste ; celle-ci retrouve donc, panneau ouvert, au moins sa largeur d'avant #628.
- **Redimensionnement de la colonne titre (issue #95) entièrement retiré**, sur diagnostic d'Alain : la poignée de 5px juste avant le titre se déclenchait par accident, et la largeur mémorisée (`bridge_largeur_titre`) activait un défilement horizontal qui sortait les badges de temps (décompte/estimation) de la zone visible — poignée, `demarrerRedimTitre`/`surRedimTitre`/`finRedimTitre`/`appliquerLargeurTitre` (`static/js/app.js`), styles `.poignee-titre`/`.titre-redimensionne` (`static/css/resultats.css`) supprimés ; `resultats.js#initialiser` purge désormais la clé `bridge_largeur_titre` du localStorage au chargement pour qu'un ancien navigateur ne reste pas bloqué avec une largeur mémorisée sans effet. Le titre (`flex:1` + ellipsis) et les badges (`flex-shrink:0`) suffisaient déjà à garantir qu'une ligne ne déborde jamais de la liste, panneau ouvert ou fermé.
- **Panneau latéral flottant (au moins une fois, sans repro fiable)** : recherche exhaustive de résidu de l'ancien `position:fixed` (retiré par #628) — aucun trouvé dans le CSS/JS actuel. Cause la plus probable : un onglet resté ouvert depuis avant #628 (JS/CSS pré-fix encore en mémoire), ou un cache navigateur non invalidé malgré le cache-busting par mtime (`app/statique.py`). En garde-fou, `.panneau-lateral-col`/`.panneau-lateral` déclarent désormais explicitement `position:static` (`static/css/resultats.css`) contre toute résurgence future de ce type de bug.
- **Cases de notification du panneau ne reflétant pas les labels réels (relecture_bridge #77)** : cause identifiée — `chargerTimingProjet()` (`static/js/resultats.js`), qui lit `/issues-en-attente` (labels GitHub réels inclus), ne recopiait dans le store que les champs de timing et jetait les labels/titre. Une issue apparue par `creation_issue` (placeholder `labels:[]`, voir `surCreationIssue`) restait donc bloquée avec des labels vides indéfiniment — y compris après un `debut_issue` ultérieur (branche « déjà connue » qui ne réécrivait jamais l'issue). `chargerTimingProjet()` met désormais aussi à jour `labels`/`title` de toute issue déjà connue du store à partir de la réponse fraîche de `/issues-en-attente`, quel que soit le chemin d'arrivée (creation_issue, debut_issue, fin_issue, chargement initial/↻ — ces deux derniers étaient déjà corrects via `remplacerIssues`). Extraction de la dérivation des 3 cases (`etatsCasesNotif`, `static/js/panneau_lateral.js`) en fonction pure testée sous Node (`static/js/tests/panneau_lateral.test.js`).
- **Lien « Vérifier le service CCW de ce projet »** affiché même pour une issue for-linux (relecture_bridge #77) : n'apparaît plus que si l'issue sélectionnée porte le label `for-windows` (`rendrePanneauLateralActions`, `static/js/panneau_lateral.js`).
- `VERIFICATIONS_MANUELLES.md` mis à jour (zone Résultats : largeur/défilement horizontal, retrait de la mention du redimensionnement de colonne ; panneau latéral : jamais flottant, cases de notification conformes, lien CCW conditionné à for-windows).

Tests : `node --test static/js/socle/tests/ static/js/tests/` → 50/50 (ajout de `panneau_lateral.test.js`, 5 tests sur `etatsCasesNotif`).

## 25 septembre 2026 — issue #632

Refonte interface web — raccord de la vague 1 (issue #632, suite #625/#626/#627/#628) : `onglets.js` appelait encore, via le pont, `chargerListeIssues`/`demarrerTempsRestant`/`demarrerPanneauLateral` (activation de Résultats) et `arreterTempsRestant`/`arreterPanneauLateral` (désactivation), toutes retirées d'app.js depuis #626/#627 — la liste Résultats et le panneau latéral ne démarraient donc plus jamais au chargement. `resultats.js` et `panneau_lateral.js` s'abonnent désormais directement à `store.ongletActif` (`initialisationsPour()` ne renvoie plus rien pour `resultats` ; journal/config/ccw/inbox inchangés, toujours via le pont vers app.js). `socle/index.js` sépare l'installation de la délégation de clic (`initialiserOnglets()`) de l'activation de l'onglet par défaut (nouvelle `activerOngletParDefaut()`), appelée en dernier après `resultats.initialiser()` et `initPanneauLateral()` pour garantir que les abonnements existent avant la première notification. `resultats.js` n'appelle plus `rafraichirPanneauLateralResultats` via le pont (communication de module à module par `window`) : `panneau_lateral.js` s'abonne lui-même à `store.derniereNotifIssue`. Suppression du code mort `chargerWatchers`/`#panneau-watchers` (onglet Watchers retiré par #626, condition toujours fausse) et des globales `window.demarrerPanneauLateral`/`arreterPanneauLateral` devenues inutiles (plus aucun appelant). Tests : `onglets.test.js` mis à jour, ajout de `resultats_activation.test.js` (l'activation de Résultats ne déclenche le chargement initial qu'une seule fois) et de `pont_globales.test.js` (échoue si un nom passé à `appelerAncien` ne correspond à aucune fonction déclarée dans app.js ni publiée par un module — garde-fou contre ce type de rupture lors des prochaines fusions). `VERIFICATIONS_MANUELLES.md` : retrait des mentions de l'onglet Watchers, correction de la trace console attendue au chargement (`[socle] briques chargées et inertes` n'existe plus). `CONTEXTE.md` ramené de 4067 à 3877 caractères par condensation (aucune information perdue).

## Issue #628 — Refonte interface web, étape 4 : panneau latéral (mise en page non recouvrante, monitoring VM mort)

Sortie du panneau latéral « Infrastructure » de `app.js` vers son propre
module `static/js/panneau_lateral.js` (§6.7 ARCHITECTURE.md), premier module
de la refonte à piloter réellement une zone de l'écran (au lieu du socle inerte
posé par #625).

- **Mise en page** : le panneau était en `position:fixed`, collé au bord droit
  au-dessus du contenu — il recouvrait la fin des lignes de la liste Résultats
  (badges de temps). Remplacé par une vraie colonne flex à côté de la liste
  (`.resultats-layout` / `.resultats-corps` / `.panneau-lateral-col`,
  `templates/fragments/onglet_resultats.html` + `static/css/resultats.css`) :
  ne recouvre plus jamais la liste ; sur écran étroit, passe sous la liste au
  lieu de la recouvrir (`flex-direction:column`).
- **État ouvert/fermé** : mémorisé (`localStorage`, socle `persistance.js`) et
  conservé d'un onglet à l'autre — auparavant réinitialisé à chaque entrée dans
  l'onglet Résultats. Ouvert par défaut.
- **Monitoring VM supprimé** : appel mort à `/ccw/vm-statut` (résidu
  VirtualBox, route disparue côté serveur depuis #447, 404 avalé en silence),
  bloc d'affichage « VM », appel à `sidebarDemarrerVm` (jamais défini), styles
  associés.
- **Actions dupliquées retirées du détail d'issue** (`construireHtmlIssue`,
  `static/js/app.js`) : « Interrompre cette issue » et « Fermer définitivement »
  faisaient double emploi avec le panneau (`#pl-zone-actions`) — ne restent
  plus que dans le panneau. Le détail lui-même (hors bloc d'actions) n'a pas
  été touché.
- **Mutualisation `/watchers`** : une seule lecture périodique
  (`rafraichirWatchersPartages`, `static/js/panneau_lateral.js`), écrite dans
  `store.watchers` (socle) — le bandeau de repli REP_TRAVAIL (`app.js`,
  `rafraichirReplisRepTravail`) s'y abonne désormais au lieu de fetcher lui-même ;
  affichage du bandeau inchangé.
- **Zone son** déplacée telle quelle (comportement inchangé), seule la brique
  réseau change (`api.*`/`toasts.*` du socle au lieu de `fetch()`/`alert()` en
  dur).
- Événements migrés vers la délégation du socle (`dom.surAction`,
  attributs `data-action="pl-*"`) au lieu des `onclick=` inline.
- Glue de transition minimale conservée dans `app.js` (pont socle→ancien,
  `appelerAncien`) pour ce qui dépend d'un état encore propriété d'autres
  fonctionnalités non migrées (liste des issues, onglet CCW) : getters
  `obtenirCcwProjetsConnus`/`obtenirIssueSelectionnee`, mutateur
  `actualiserLabelIssueLocal`, `resumeProjetMonitoring` conservé.
- `VERIFICATIONS_MANUELLES.md` et `BRIDGE_AGENT_DOC.md` mis à jour
  (terminologie « panneau flottant » → « panneau latéral », chemins de
  fonctions, nouvelles vérifications non-régression).

Vérifié : `node --test static/js/socle/tests/` (20/20 OK), `node --check` sur
les 3 fichiers JS touchés/ajoutés, rendu de `/` via le client de test Flask
(200, aucune référence fonctionnelle résiduelle à `/ccw/vm-statut` ni
`sidebarDemarrerVm`), fichiers statiques servis (200, `text/javascript`).
Pas de test navigateur réel (pas d'environnement graphique) — à rejouer par
Alain via `VERIFICATIONS_MANUELLES.md`.

## 25 septembre 2026 — issue #627

Refonte de l'interface web, **étape 3/n : la liste Résultats pilotée par le store
et le SSE**. Étape la plus sensible (Résultats est l'outil quotidien d'Alain) :
elle sort d'`app.js` le **moteur** de l'onglet — chargement, canal `/stream`,
badges de temps — avec le **store** pour source de vérité unique, sans changement
visible pour l'utilisateur. Trois anomalies confirmées corrigées à la racine.

### 1. Nouveau module — `static/js/resultats.js`

Premier **module par fonctionnalité** de la refonte (cf. `ARCHITECTURE.md §6.5`).
Il détient et orchestre :

- **Chargement** : un chargement initial UNIQUE (à la première activation de
  l'onglet), puis des mises à jour ciblées par événement `/stream`, plus le ↻
  explicite. **Plus aucun rechargement complet à l'activation de l'onglet.** Le
  **cache de liste en `localStorage` est supprimé** : le store est la seule vérité.
- **Canal `/stream`** ouvert via la brique `sse` (`sse.stream.connecter()`), UNE
  SEULE connexion — l'ancien `demarrerStreamFinIssue()` d'`app.js` est retiré dans
  le même mouvement (jamais deux connexions). Traitement **toujours CIBLÉ** sur le
  projet+issue concernés, jamais tous les projets :
  - `debut_issue` : recharge les données de temps **de cette issue** (le décompte
    TIMEOUT démarre) et l'ajoute à la liste si absente ; ne passe **JAMAIS** par la
    vérification post-dépassement ;
  - `fin_issue` : met à jour la ligne (état final, arrêt du décompte) via un fetch
    unique `/issue/<projet>/<numero>` ;
  - `creation_issue` (contrat de l'étape 9a : `projet`, `numero`, `titre`,
    `fichier` si créée via `issues_inbox`) : fait apparaître la ligne avec son
    estimation et « en file », puis l'enrichit par un fetch ciblé. **Codé même si
    l'événement n'est pas encore émis.**
  - le **fetch unique post-dépassement de #334** est conservé, réservé au décompte
    tombé à zéro.
- **Badges** d'estimation et de décompte TIMEOUT : calcul (logique pure) +
  application au DOM + tick 1 s + programmation du fetch #334.
- **Store** : nouvelles tranches `issues` (déjà présente) et **`timing`** ; le
  `derniereNotifIssue` posé par `sse.js` déclenche le traitement ciblé.

### 2. Anomalies corrigées à la racine

1. **Rechargement complet à chaque activation de l'onglet** (~2 appels gh/projet
   pour la liste + 1/issue ouverte pour les temps) → supprimé. Chargement initial
   unique + événements ciblés + ↻. *Vérifiable : aucun appel `/issues-liste` ni
   `/issues-en-attente` en changeant d'onglet (onglet Réseau).*
2. **`debut_issue` cassé** : l'ancien `gererEvenementIssue` rechargeait la liste
   sans les temps, ou — si l'issue était déjà affichée — passait par
   `verifierIssueApresDepassement` (prévu pour #334), laissant le badge « ⏳ en
   file » et marquant l'issue « dépassement déjà vérifié » (faussant plus tard le
   badge de dépassement). Désormais `debut_issue` recharge le timing ciblé et ne
   touche jamais la vérif post-dépassement.
3. **Projet en échec de chargement** : ses issues disparaissaient en silence.
   Désormais, un projet dont le fetch échoue **conserve ses issues précédentes** et
   l'échec est signalé par un **toast**.

### 3. Ce qui reste temporairement dans `app.js` (et pourquoi)

`app.js` conserve, pendant la transition, tout ce qui est **hors périmètre #627**
et/ou entrelacé avec le rendu DOM d'une ligne, piloté par `resultats.js` via un
MIROIR du store (hooks `window.__resultats*`) :

- **Rendu DOM d'une ligne** (`construireLigneIssueDOM`, `rendreListeIssues`,
  `remplacerLigneIssue`, `brancherEvenementsLigneIssue`) : le markup contient la
  **case à cocher**, les **badges ✅/Diff/All** et la copie, l'ouverture du
  **détail** — toutes fonctionnalités hors périmètre. `resultats.js` fournit les
  données et déclenche le rendu ; `app.js` produit le DOM.
- **Filtres** (boutons projet, filtre ouvriers, limite « par projet », ↻) :
  `construireBoutonsFiltre`/`appliquerFiltresListe` construisent aussi le bouton
  **« Cocher tout »** et les **pastilles** (hors périmètre) et lisent l'état de
  filtre persisté — extraction repoussée avec ces fonctionnalités.
- **Sélection, détail d'issue, recherche par titre, lignes issues_inbox, panneau
  latéral** : explicitement hors périmètre — inchangés, alimentés par le miroir
  (`listeIssuesResultats`/`timingIssues`) via le pont.
- `cleTiming`, `trouverLigneIssue`, `remplacerLigneIssue` : petits utilitaires DOM
  encore consommés par ce qui précède.

Le pont (`window.Bridge.resultats`) et le miroir disparaîtront quand ces zones
seront à leur tour migrées (étapes suivantes).

### 4. Tests et vérifications

- **Logique pure** testée sous Node — `static/js/tests/resultats.test.js`
  (`formaterDuree`, calcul des badges de décompte/estimation, `planifierEvenementSse`
  dont le cas `debut_issue`, fusion de chargement conservant un projet en échec).
  Lancer : `node --test static/js/socle/tests/ static/js/tests/` (36 tests OK).
- `app/statique.py` : l'**import map** couvre désormais aussi les modules de
  fonctionnalité de `static/js/` (hors `app.js`, script classique), pour leur
  cache-busting `?v=<mtime>` ; le partage d'instance du store est garanti (mêmes
  URL résolues).
- `VERIFICATIONS_MANUELLES.md` (zone Résultats) et `BRIDGE_AGENT_DOC.md §17.3`
  mis à jour.

### 5. Fichiers touchés

- **Nouveaux** : `static/js/resultats.js`, `static/js/tests/resultats.test.js`,
  `static/js/package.json` (`{"type":"module"}`).
- **Modifiés** : `static/js/app.js` (moteur Résultats retiré, remplacé par des
  relais vers le pont ; ancienne connexion `/stream` supprimée),
  `static/js/socle/store.js` (tranche `timing`), `static/js/socle/sse.js`
  (événement `creation_issue`), `static/js/socle/index.js` (import + amorçage
  `resultats`), `app/statique.py` (import map élargi), `ARCHITECTURE.md`,
  `BRIDGE_AGENT_DOC.md`, `VERIFICATIONS_MANUELLES.md`, `CONTEXTE.md`,
  `static/js/socle/tests/README.md`.

## 25 septembre 2026 — issue #626

Refonte de l'interface web, **étape 2/n : onglets**. Sortie de la mécanique de
bascule des onglets d'`app.js` vers `static/js/onglets.js`, selon la procédure
type du §6.7 d'`ARCHITECTURE.md`.

### 1. Nouveau module `static/js/onglets.js`

- Association onglet ↔ panneau par **identifiant** (`data-onglet` sur chaque
  `.onglet`, comparé à l'id `panneau-<nom>`), plus par position dans le DOM :
  l'ancien `basculerOnglet()` parcourait un tableau de noms dans l'ordre des
  éléments, ce qui cassait l'association au moindre réordonnancement.
- `activerOnglet(nom)` publie l'onglet actif dans le store (`ongletActif`,
  nouvelle tranche de `socle/store.js`) pour que chaque zone puisse réagir à
  son activation/désactivation, et appelle — via le pont, pendant la
  transition — les initialisations existantes de chaque onglet dans
  `app.js` (`initialisationsPour()`, fonction pure testée séparément).
  **Inchangé** : ce que fait l'activation de Résultats (rechargement de la
  liste, badges, panneau latéral) — périmètre de l'étape 3.
- `initialiserOnglets()`, appelé une seule fois par `socle/index.js`, branche
  la délégation de clic (`dom.surAction`) et active Résultats par défaut.
- Tests : `static/js/tests/onglets.test.js` (`node --test static/js/tests/`),
  7 cas sur `initialisationsPour()` (la partie pure, sans DOM).

### 2. Nouvel ordre des onglets + Résultats par défaut

`templates/fragments/onglets.html` : Résultats en premier (actif au
chargement, décision d'Alain — avant #626 c'était Nouvelle issue), Nouvelle
issue en dernier (n'est plus qu'un backup, seul moyen de joindre un fichier à
une issue, usage très rare), les autres onglets dans leur ordre relatif
inchangé. `onglet_creation.html`/`onglet_resultats.html` : classe `actif`
déplacée en conséquence.

### 3. Suppression de l'onglet « Watchers »

Le tableau des watchers + cases à cocher + actions Lancer/Relancer/Éteindre
par lot n'existent plus : fragment `onglet_watchers.html` supprimé, son
`{% include %}` retiré d'`index.html`, fonctions `statutWatcher`/
`chargerWatchers`/`selectionnerTous`/`mettreAJourCompte`/`actionWatchers` et
`intervalWatchers` supprimés d'`app.js`. La surveillance des watchers reste
dans le **panneau latéral Infrastructure** de l'onglet Résultats (actions par
projet individuel, pas de sélection multiple) — vérifié qu'aucune fonction
supprimée n'y était encore utilisée ; ses appels à `/watchers` (panneau
latéral) et au bandeau de repli REP_TRAVAIL (`rafraichirReplisRepTravail`)
sont inchangés.

### 4. Documentation

`ARCHITECTURE.md` §6.5/§6.7 : module `onglets.js` marqué comme sorti,
nouvelle description de la suppression de l'onglet Watchers et du nouvel
ordre. `BRIDGE_AGENT_DOC.md` : mentions de l'onglet Watchers remplacées par
le panneau latéral Infrastructure et le bouton « Lancer le watcher » du
bandeau global. `VERIFICATIONS_MANUELLES.md` : section « Onglet Watchers »
retirée, ajout d'une vérification de l'onglet par défaut et du nouvel ordre,
mention de `node --test static/js/tests/` en plus des tests du socle.

### 5. Autres ajustements

`app/statique.py` (`importmap_socle()`) étendu pour verser aussi les modules
de fonctionnalité de `static/js/` (hors `app.js`, script classique) dans
l'import map — nécessaire pour que `socle/index.js` importe `../onglets.js`
avec cache-busting. `app/watchers.py` : commentaires mis à jour (routes
utilisées par le panneau latéral/l'onglet Configuration, plus par l'ex-onglet
Watchers).

Tests : `node --test static/js/socle/tests/` (20 passent) et
`node --test static/js/tests/` (7 passent).

## 25 septembre 2026 — issue #631

Refonte de l'interface web, **étape 9a/n : événements `issues_inbox` et
création d'issue (backend seul)**. Prépare la fusion de l'onglet « Résultats
inbox » dans Résultats (étape 9b, décision d'Alain) : un fichier déposé dans
`issues_inbox/` doit y apparaître aussitôt comme une ligne « fichier reçu »,
qui se transforme au fil du traitement en ligne d'issue (succès) ou ligne
rouge avec motif (bloc refusé). **Aucun changement visible tant que l'étape
9b n'est pas faite** — le code actuel de l'onglet Résultats ignore les
événements qu'il ne connaît pas.

### 1. Trois nouveaux événements SSE sur `/stream`

Même famille que `/notifier-fin-issue`/`/notifier-debut-issue` (`app/fin_issue.py`,
issue #350/#515) : POST best-effort, timeout court, échec silencieux si
`new_issue.py` n'est pas lancé, pas de `login_requis` (appelées par un script
local).

- **`fichier_recu`** (`POST /notifier-fichier-recu`) — émis par
  `scripts/watcher_issues_inbox.py::traiter_fichier()` dès la prise en charge
  d'un fichier, avant tout parsing. `{"fichier": <nom>}`.
- **`creation_issue`** (`POST /notifier-creation-issue`) — émis après chaque
  création RÉUSSIE d'une issue (jamais pour un bloc `RELANCE`, qui n'en crée
  aucune) : par `watcher_issues_inbox.py` (POST, process séparé) et par
  `app.issues.envoyer()` (formulaire web, appel direct à la nouvelle
  `app.fin_issue.emettre_creation_issue()`, même process → pas de HTTP).
  `{"projet", "numero", "titre", "fichier"}` — `fichier` absent (`null`) pour
  une création via le formulaire.
- **`fichier_refuse`** (`POST /notifier-fichier-refuse`) — émis pour chaque
  bloc refusé (fichier mono-issue entier, ou un bloc d'un lot multi-issues,
  §3.13) : un événement par bloc, dans l'ordre de traitement, jamais groupé.
  `{"fichier", "titre", "motif"}`.

`app/fin_issue.py` factorise la diffusion SSE elle-même (`_diffuser()`),
désormais partagée entre les événements historiques (`fin_issue`/`debut_issue`)
et les trois nouveaux.

### 2. Motif de refus exposé dans `/issues-inbox/etat`

`_deplacer_vers_rejected()` (`scripts/watcher_issues_inbox.py`) écrit
désormais, en plus du renommage habituel du fichier, un sidecar
`issues_inbox/rejected/.motifs/<nom-du-fichier-rejeté>.motif` contenant le
motif de refus **en texte intégral** (le nom du fichier lui-même ne porte
qu'un slug tronqué à 40 caractères, sans accents). `GET /issues-inbox/etat`
(`app/issues_inbox.py`) lit ce sidecar et ajoute un champ `motif` à chaque
entrée de `rejetes` — simple lecture disque, donc consultable après coup, y
compris après un redémarrage de `new_issue.py` ; `None` pour un rejet
antérieur à cette fonctionnalité (rétrocompatibilité). Sous-dossier `.motifs/`
dédié (plutôt qu'un `<nom>.motif` posé directement dans `rejected/`) : un tel
nom aurait aussi matché tout code énumérant `rejected/` par motif de nom (ex.
un glob `*REJETE*`, comme dans `tests/test_champ_redacteur_599.py` — bug
attrapé en cours de développement et corrigé par l'isolation dans ce
sous-dossier).

### 3. Tests et documentation

`tests/test_evenements_issues_inbox_631.py` (15 scénarios pytest, collectés
par `pytest tests/`) : construction et validation des trois routes POST,
appel direct de `emettre_creation_issue()`, ORDRE des événements best-effort
pour un fichier mono-bloc (succès/rejet) et pour un lot de 4 blocs (succès,
rejet, RELANCE-sans-événement, succès), absence de doublon quand tous les
blocs d'un lot échouent, exposition/rétrocompatibilité du motif dans
`etat_inbox()`. Aucun appel réseau ni `gh` réel (`_poster_best_effort` et
`_traiter_bloc` substitués). Suite complète (29 tests pytest + 22 scripts
autonomes) vérifiée verte après ce changement.

Documentation : nouveau §3.15 (contenu et ordre des trois événements) et
mise à jour de §3.2 (sidecar `.motifs/`) et §17.3 (mention des trois
nouvelles routes) dans `BRIDGE_AGENT_DOC.md`.

### Fichiers touchés

`app/fin_issue.py`, `app/__init__.py`, `app/issues.py`, `app/issues_inbox.py`,
`scripts/watcher_issues_inbox.py`, `tests/test_evenements_issues_inbox_631.py`
(nouveau), `BRIDGE_AGENT_DOC.md`.

## 25 septembre 2026 — issue #630

Refonte de l'interface web, **étape 7a/n : son plat/cloche par issue
(backend seul)**. Décision d'Alain : l'interrupteur GLOBAL plat/cloche
(`scripts/son_actif.txt`, #498/#527) reste la règle par défaut ; en plus,
n'importe quelle issue peut désormais être basculée en plat ou en cloche pour
elle-même. Le réglage PAR PROJET envisagé un temps (tonalité `TONALITE_BIP`,
script `SCRIPT_BIP`) est abandonné au profit de ce choix plus fin, par issue.
Interface prévue aux étapes 7b/8 — cette étape-ci ne touche à rien de visible.

### Stockage et routes

- `etat_son_issue.py` (racine du dépôt, sans dépendance Flask, sur le modèle
  de `notifications.py`/`etat_rate_limit.py`) : `logs/son_issues.json`
  (`{projet: {numéro: "plat"|"cloche"}}`), écriture atomique + verrou
  anti-collision — même mécanisme que `etat_rate_limit.json` (#615).
  `son_choisi`/`definir_son`/`nettoyer_projet`/`nettoyer_entrees_perimees`.
- `app/son_issue.py` : `GET`/`POST /son-issue/<nom_projet>/<numero>`, même
  famille que les routes `/son-actif` existantes (`app/son.py`).

### Nettoyage

Même règle que les cases cochées côté navigateur : au démarrage de
`new_issue.py`, purge PAR PROJET des entrées dont le numéro est ≤ (plus grand
numéro connu de ce projet dans `son_issues.json` − 50) ; purge TOTALE d'un
projet à sa suppression (`supprimer_projet.py`, best-effort, non bloquant).

### Résolution au moment du bip

`scripts/traitement_fin.py::son_a_jouer(projet, numéro)` : le choix de
l'issue s'il existe, sinon l'interrupteur global (`son_actif()`) — valable
pour les issues CCL (`watcher.py::bip()`/`notifier()`) comme pour les issues
CCW (`app/notifications_poller.py::_notifier_transition()`), qui transmettent
toutes deux `--projet`/`--numero` au script.

### TONALITE_BIP / SCRIPT_BIP retirés du chemin réel du bip

`watcher.py` et `app/notifications_poller.py` appellent désormais toujours
`scripts/traitement_fin.py` (script partagé) avec une tonalité neutre (`0`),
quel que soit le `.conf` du projet. `scripts/bip_Cloche.py` (legacy,
pitch-shift via `sox`) est **supprimé**. Le code tolère la présence
résiduelle de `SCRIPT_BIP`/`TONALITE_BIP` dans les `configs/*.conf`
existants (jamais modifiés directement par CCL) : ces deux clés restent
lues/exposées par l'onglet Configuration (`/config`, `/tester-bip/<projet>`,
`app/projets.py`) et écrites par `nouveau_projet.py` pour les nouveaux
projets — **volontairement non touchés** par cette étape, retrait prévu à
l'étape 8 avec l'onglet lui-même.

### Tests

`tests/test_son_issue_630.py` (13 scénarios pytest) : résolution du son
(choix par issue, repli sur l'interrupteur global, absence de projet/numéro),
stockage (écriture/lecture isolées par projet+numéro, valeur invalide
refusée, remise à zéro), nettoyage (purge par projet, conservation des 50
dernières issues connues par projet), routes Flask.

Mise à jour de `BRIDGE_AGENT_DOC.md` §17 (nouveau modèle de son).

## 25 septembre 2026 — issue #629

Refonte de l'interface web, étape 5a (§6 d'`ARCHITECTURE.md`) : bascule côté serveur de l'état des cases « traité/lu » de l'onglet Résultats, jusqu'ici 100% localStorage (issue #154) — état perdu après un plantage du PC, différent selon l'adresse d'accès (localhost/LAN), clés accumulées sans fin. Backend seul cette fois, aucun front ne l'utilise encore. Nouveau module `etat_cases_cochees.py` (racine) : fichier JSON `logs/etat_cases_cochees.json`, écriture atomique + verrou anti-collision, même modèle que `etat_rate_limit.py` (issue #615). Routes Flask `app/cases_cochees.py`, protégées par `login_requis` : `GET /cases-cochees/<projet>` (lire), `POST`/`DELETE /cases-cochees/<projet>/<numero>` (cocher/décocher), `POST /cases-cochees/importer` (import en masse idempotent, servira à la reprise du localStorage existant à l'étape 5b). Nettoyage sans aucun appel GitHub : au démarrage de `new_issue.py`, pour chaque projet, retire les coches dont le numéro est ≤ (plus grand numéro connu du projet − 50, le plafond de `app/issues.py::LIMITE_ISSUES_MAX`) ; à la suppression d'un projet (flux #587, `supprimer_projet.py`), retire toutes ses coches (nouvelle étape 4, best-effort). Tests : `tests/test_cases_cochees_629.py` (17 scénarios) + mise à jour de `tests/test_supprimer_projet_587.py` pour la nouvelle étape. Documenté dans `BRIDGE_AGENT_DOC.md` (nouvelle section après « Suppression de projet »).

## 25 septembre 2026 — issue #625

Refonte de l'interface web, **étape 1/n : socle**. Architecture retenue par
Alain : modules JavaScript natifs (`<script type="module">`), **sans étape de
build**, briques partagées + modules par fonctionnalité (à venir). Cette étape
pose les fondations pour que les étapes suivantes tournent **en parallèle** dans
des worktrees distincts. **Contrainte absolue tenue : aucun changement visible
pour l'utilisateur** — corps de `index.html` vérifié byte-identique après rendu
Flask (hors entête/scripts), CSS reconcaténé byte-identique à l'ancien
`style.css`.

### 1. Briques partagées — `static/js/socle/`

Nouveau sous-dossier de modules ES, **inertes à cette étape** (chargés, testés,
mais ne remplacent rien) :

- `store.js` — source de vérité unique : tranches issues (indexées par
  `projet#numero`), sélection, filtres, projets, watchers, issues_inbox, son,
  rate-limit ; `get`/`set`/`maj`/`abonner`/`abonnerCle` + aides issues.
  `creerStore()` fabrique générique testable.
- `api.js` — accès unique aux routes Flask, vérifie **systématiquement**
  `response.ok`, lève `ErreurApi` et remonte via toasts (plus d'erreur avalée).
- `sse.js` — canaux `/stream` et `/events` centralisés, **NON connectés** (pas de
  double connexion tant que l'ancien code gère les siennes).
- `toasts.js` — notifications non bloquantes (jamais de « OK » à cliquer) + LA
  seule modale, réservée aux confirmations destructives. Styles auto-injectés.
- `dom.js` — utilitaires (`$`, `$$`, `creerElement`, `echapperHtml`) + registre
  de délégation d'événements (`surAction`) destiné à remplacer les handlers
  inline.
- `persistance.js` — localStorage restreint aux préférences d'interface.
- `index.js` — point d'entrée module ; `pont.js` — mécanisme de transition.

### 2. Coexistence avec l'ancien code

`app.js` reste chargé comme **script CLASSIQUE** (ses ~233 fonctions restent
globales pour les >70 gestionnaires inline). Le module d'entrée est chargé **à
côté** (différé ⇒ après app.js). `pont.js` est l'unique point de contact
(`window.Bridge` pour ancien→socle, `appelerAncien()` pour socle→ancien), conçu
pour être **retiré entièrement à la dernière étape**. Ordre de chargement
préservé (variables Jinja disponibles pour les deux mondes).

### 3. Découpage des fichiers

- `templates/index.html` → squelette + `templates/fragments/` (un fragment par
  onglet, panneau latéral, bandeaux, entête, chaque modale, scripts).
- `static/css/style.css` → 6 feuilles par zone (`base`, `composants`,
  `resultats`, `modales`, `recherche-interruption`, `inbox`), chargées dans
  l'ordre qui **préserve exactement la cascade** (reconcaténation byte-identique
  vérifiée). `app.js` reste d'un seul tenant (vidé par les étapes suivantes).

### 4. Fichiers servis (cache-busting)

Nouveau `app/statique.py` : `url_statique()` (ajoute `?v=<mtime>` aux CSS/JS) et
`importmap_socle()` (import map versionnant les imports relatifs entre modules ES,
sans build). Vérifié : modules servis en `text/javascript` et CSS en `text/css`,
statut 200, en local / `--lan` / `--externe`, **y compris session expirée** (les
statiques ne sont pas derrière `login_requis`).

### 5. Filet de sécurité

- Tests de logique pure avec le module intégré de Node (`node:test`, aucune
  dépendance) : `store`, `persistance`, `dom` — **20 tests, tous verts**.
  Lancement : `node --test static/js/socle/tests/` (cf. README des tests).
- `VERIFICATIONS_MANUELLES.md` (racine) : liste de non-régression à rejouer par
  Alain après chaque étape (tous onglets, panneau latéral, modes `--lan`/externe).

### 6. Documentation

- `ARCHITECTURE.md` §6 : carte de migration complète (arborescence, rôle de
  chaque brique, mécanisme de transition, correspondance zones↔fichiers,
  versionnage, procédure type pour sortir une fonctionnalité de l'ancien code).
- `CONTEXTE.md` mis à jour et ramené sous le plafond de 4000 caractères.

Fichiers : +`static/js/socle/*` (8 modules + package.json), +`static/js/socle/tests/*`,
+`templates/fragments/*` (18 fragments), +`static/css/{base,composants,resultats,
modales,recherche-interruption,inbox}.css`, +`app/statique.py`,
+`VERIFICATIONS_MANUELLES.md` ; ~`templates/index.html`, ~`app/__init__.py`,
~`ARCHITECTURE.md`, ~`CONTEXTE.md` ; −`static/css/style.css` (découpé).

## 25 septembre 2026 — issue #624

Remplace #623 (fermée après 3 dépassements de TIMEOUT, conception laissée
ouverte). Corrige la régression diagnostiquée en #621 : depuis #614,
`_projets_dans_la_portee()` (`app/notifications_poller.py`) filtrait les
projets interrogés par `gh` sur le champ `LABEL` de leur `.conf` — un
**défaut** de projet, pas la vérité, puisque c'est le label `for-windows`/
`for-linux` posé sur **chaque issue** (exclusifs, §16) qui dit si elle
concerne CCW. Aucun `.conf` CCL ne portant `LABEL=for-windows`, le poller
n'interrogeait plus aucun projet et ne détectait plus aucune transition
d'issue CCW sur le ThinkPad — seul chemin de notification pour CCW, le
watcher Windows postant ses signaux SSE vers `localhost:5100`, sa propre
machine, jamais atteinte depuis le ThinkPad.

Le poller surveille désormais une **liste d'issues** (`depot`, `numéro`),
pas des projets : `app.notifications_poller._ISSUES_SURVEILLEES`, remplie
par un balayage unique de toutes les issues ouvertes `for-windows` sur tous
les projets configurés au démarrage de `new_issue.py`
(`_balayage_initial()`), et tenue à jour en direct à chaque création ou
relance d'une telle issue depuis le ThinkPad — formulaire web
(`app.issues.envoyer`), bouton « Relancer » de l'onglet Résultats
(`app.interruption.route_relancer`), et `scripts/watcher_issues_inbox.py`
via la nouvelle route `POST /notifier-issue-a-surveiller` (ce dernier tourne
dans un process séparé, incapable de muter directement la liste du process
`new_issue.py`). Liste vide → aucun appel `gh` à ce cycle (cas courant, CCW
n'étant utilisé qu'une ou deux fois par semaine).

À chaque cycle, pour chaque issue de la liste : détection de la prise en
charge (commentaire ACK), en réutilisant `app.issues._debut_traitement`/
`_commentaires_issue` (logique de `/issues-en-attente`) plutôt que de la
dupliquer, avec poussée d'un événement SSE `debut_issue` sur `/stream` ;
détection des transitions terminales (`done`/`needs-human`), notifiées comme
avant (bip/bulle/ntfy selon les labels `notif_*`) plus, désormais, un
événement SSE `fin_issue` sur `/stream` — décorrélé des labels `notif_*`,
comme `watcher.py::notifier_fin_sse` pour CCL. Une issue est retirée de la
liste dès sa transition terminale ; une relance réussie l'y réinjecte.
Garde-fous conservés : anti-spam au démarrage (aucune notification pour une
ACK/transition déjà présente à l'amorçage), filtre de récence, lecture des
labels `notif_*` courants au moment de la détection.

Limite documentée, non traitée : une issue `for-windows` créée directement
sur GitHub ou par un chef n'est ajoutée à la liste surveillée qu'au prochain
démarrage de `new_issue.py` (rattrapée par `_balayage_initial()`).

Tests (`tests/test_poller_issues_ccw_624.py`) : remplissage de la liste
(balayage initial multi-projets, ajout direct filtré par
`BRIDGE_NOTIF_SCOPE`), retrait après transition terminale (avec/sans
amorçage, filtre de récence), détection de l'ACK réutilisant réellement
`_debut_traitement`, et liste vide → aucun appel `gh`. Aucun appel `gh` réel
dans ces tests : `_gh_list`/`_gh_view_issue`/`_commentaires_issue` sont
monkeypatchés.

Doc : BRIDGE_AGENT_DOC.md §17 (poller), §17.1 (mécanisme SSE désormais
décorrélé des labels `notif_*` côté CCW aussi), §17.2 (correction de la
période de polling indiquée — 20 s dans la doc, 60 s dans le code depuis
#188), §17.3 (nouvelle route `/notifier-issue-a-surveiller`).

Fichiers modifiés : `app/notifications_poller.py` (remplacement du
balayage par projet par la liste surveillée, nouvelle route Flask),
`app/__init__.py` (enregistrement de la route), `app/issues.py`
(`numero_depuis_url`, hook dans `envoyer()`), `app/interruption.py` (hook
dans `route_relancer()`), `scripts/watcher_issues_inbox.py` (hooks dans
`_traiter_bloc`/`_traiter_relance`, POST best-effort vers la nouvelle
route), `tests/test_poller_issues_ccw_624.py` (nouveau),
`BRIDGE_AGENT_DOC.md`.

## 25 septembre 2026 — issue #620

Diagnostic #579 (bas niveau, point 2) : `nouveau_projet.py` (~1450 lignes)
mélangeait plusieurs responsabilités ; la plus clairement séparable — la
science des couleurs (~410 lignes, algorithmes WCAG/Lab, génération de
palette, `couleur_affichee`, `couleur_hash_projet`) — était en outre
autonome, sans dépendance vers le reste du fichier.

Extraite telle quelle vers un nouveau module `palette.py` à la racine du
dépôt : constantes (`SATURATION_PALETTE`, `COULEURS_PROJETS_EXISTANTS`,
`PALETTE_COULEURS`, `PROJETS_COULEUR_RECYCLEE`, etc.), fonctions privées
(`_hsl_vers_hex`, `_linearise_srgb`, `_luminance_relative`,
`_contraste_avec_noir`, `_plancher_contraste_teinte`, `_plancher_effectif`,
`_lab_depuis_hsl`, `_distance_lab`, `_teinte_lab`, `_ecart_teinte`,
`_lab_depuis_hex`) et fonctions publiques (`generer_palette`,
`couleur_hash_projet`, `couleur_affichee`). `nouveau_projet.py` importe
désormais `COULEURS_PROJETS_EXISTANTS`/`PALETTE_COULEURS` depuis `palette` ;
`couleurs_utilisees()`/`couleurs_disponibles()`, qui combinent ces couleurs
avec la lecture de `configs/*.conf`, restent inchangées sur place.

Bénéfice concret : `regenerer_tableaux_projets.py` faisait un import local
différé de `nouveau_projet` pour accéder à `couleur_affichee` — un
`from nouveau_projet import couleur_affichee` en tête de fichier créait un
cycle (ce module importe déjà `regenerer_tableaux_projets` à son chargement,
issue #571/#608). Avec `palette.py`, sans dépendance vers `nouveau_projet`,
l'import se fait désormais proprement en tête de fichier
(`from palette import couleur_affichee`).

`app/nouveau_projet.py` (accès à `couleurs_disponibles`) continue de
fonctionner sans modification, ces fonctions restant dans `nouveau_projet.py`.
Vérifié : `py_compile` sur les trois fichiers, suite de tests existante
(pytest + scripts autonomes) toujours verte, `create_app()` toujours
fonctionnel, et test manuel de `lire_projets()` sur un dossier `.conf`
temporaire (couleur gelée, couleur recyclée grisée, couleur `.conf`
persistée — les trois niveaux de priorité de `couleur_affichee`).

## 25 septembre 2026 — issue #620

Extraction de la science des couleurs des projets (issue #620, suite diagnostic #579 point 2) : les ~410 lignes autonomes de `nouveau_projet.py` (constantes `SATURATION_PALETTE`/`SEUIL_CONTRASTE_NOIR`/`COULEURS_PROJETS_EXISTANTS`/etc., fonctions privées `_hsl_vers_hex`/`_lab_depuis_hsl`/`_distance_lab`/`_teinte_lab`/etc. et publiques `generer_palette`/`couleur_hash_projet`/`couleur_affichee`) déménagent dans un nouveau module `palette.py` à la racine du dépôt, sans dépendance vers le reste de `nouveau_projet.py`. `nouveau_projet.py` importe désormais `COULEURS_PROJETS_EXISTANTS`/`PALETTE_COULEURS` depuis `palette.py` (comportement de `couleurs_utilisees()`/`couleurs_disponibles()` inchangé, vérifié bit-à-bit identique à l'ancien code). `regenerer_tableaux_projets.py` importe `couleur_affichee` directement en tête de fichier depuis `palette.py` — l'ancien import local différé (`import nouveau_projet` à l'intérieur de `lire_projets()`) n'existait que pour éviter un cycle avec `nouveau_projet.py` (qui importe `regenerer_tableaux_projets`, issue #571) ; `palette.py` n'a aucune dépendance vers `nouveau_projet.py`, le cycle disparaît donc avec l'extraction. `app/nouveau_projet.py` (accès à `couleurs_disponibles()`) continue de fonctionner sans modification.

## 25 septembre 2026 — issue #619

Diagnostic #579 (bas niveau, point 2) : `_traiter_issue_synchrone` (watcher.py)
faisait ~610 lignes et empilait séquentiellement plusieurs responsabilités
distinctes (guards, bootstrap CCW, résolution de périmètre, verrou, lecture
active, boucle de tentatives, succès/échec, nettoyage) — correcte mais
difficile à naviguer. Découpée en 12 sous-fonctions privées nommées d'après
les blocs commentés déjà présents, comportement strictement identique :

- `_guards_precoces_et_bootstrap` — déjà en cours / déjà en échec définitif /
  déjà traitée / bootstrap CCW (issue #556).
- `_deduire_mode_et_logguer` — priorité/critique/timeout/modèle/mode +
  avertissements de log associés.
- `_resoudre_contexte_execution` (+ dataclass `ContexteExecution`) —
  périmètre effectif (worktree isolé #337, REPO_CIBLE #125, SOUS_DOSSIER
  #550), avec repli sur `CFG.perimetre`/`CFG.rep_travail`.
- `_acquerir_verrou_pour_issue` — verrou anti-collision inter-process (#189).
- `_preparer_lecture_active` — dossier scratch + empreinte REP_TRAVAIL (#327).
- `_demarrer_traitement` — détection RELANCE, ACK, chrono, pre-flight token,
  empreinte configs/*.conf.
- `_executer_une_tentative` — appel `lancer_claude` + garde-fou de format
  (#581) + restauration configs modifiés.
- `_verifier_violation_scratch` — garde-fou niveau 2 lecture active (#327).
- `_finaliser_succes` — commentaire de résultat, fermeture, historique des
  durées, calibration TIMEOUT (#221/#222), notification.
- `_tracer_tentative_expiree` — trace timeout dans l'historique des durées
  (#220) + calibration backoff.
- `_gerer_abandon_max_essais` — retry infini si critique, sinon diagnostic +
  needs-human + notification.
- `_nettoyer_apres_traitement` — libération verrou, nettoyage scratch, log
  fin de worktree (bloc `finally`).

`_traiter_issue_synchrone` devient un orchestrateur de 93 lignes qui
enchaîne ces appels avec les mêmes retours anticipés qu'avant. Point
d'attention préservé : `_preparer_lecture_active` retourne `chemin_scratch`
même en cas d'abandon (échec du `mkdir` après résolution du chemin), pour
que le nettoyage dans `finally` reste identique au comportement historique.

Vérification : suite de tests existante (21 fichiers) verte sans
modification, `py_compile` OK, plus 3 scénarios manuels bout-en-bout
(succès dry-run, abandon après max_essais, guard needs-human) exerçant
l'orchestration réelle en mockant les I/O réseau — aucune régression
observée. Pas de lancement d'issue réelle CCL de bout en bout dans cette
tâche (limitation d'environnement, aucun accès à une vraie issue GitHub
depuis ce worktree) ; les scénarios manuels ci-dessus couvrent le même
enchaînement de fonctions.

## 25 septembre 2026 — issue #618

Diagnostic #579 (bas niveau, point 2) : extraction de `TEMPLATE_LOGIN`
(`app/auth.py`) vers `templates/login.html`, sans changement fonctionnel.

- La chaîne Python `TEMPLATE_LOGIN` (~42 lignes HTML+CSS+Jinja inline)
  est déplacée telle quelle vers `templates/login.html`, cohérent avec
  `templates/index.html` (déjà un fichier Jinja séparé).
- `app/auth.py` : les trois appels `render_template_string(TEMPLATE_LOGIN,
  ...)` (`login()`, `login_post()` ×2) remplacés par
  `render_template("login.html", ...)`. Import Flask allégé
  (`render_template_string` → `render_template`). Constante
  `TEMPLATE_LOGIN` et docstring module mis à jour en conséquence.
- Vérification : `py_compile` OK, suite de tests existante verte
  (14 passed), rendu réel testé via `app.test_client()` — page login
  affichée (200, contenu attendu), variables Jinja `erreur` et `bloque`
  bien transmises (message d'erreur, `disabled` sur input/bouton).

## 25 septembre 2026 — issue #617

Diagnostic #579 (bas niveau, points 1/2/3.4) : trois petites duplications
niveau 3 éliminées, sans changement fonctionnel visé.

- **`_ecrire_json_atomique` dupliquée** (`watcher.py` et
  `scripts/archiver_historique.py`, même logique fichier temp +
  `os.replace`) : extraite vers `scripts/utils.py::ecrire_json_atomique`,
  nouveau module bas niveau partagé. `watcher.py` (déjà `sys.path.insert`
  sur `scripts/` pour `traitement_fin`) l'importe sous l'alias
  `_ecrire_json_atomique` pour ne rien changer aux appelants internes ;
  `scripts/archiver_historique.py` fait de même. Un seul exemplaire du
  code, deux points d'entrée inchangés.
- **`os.system(aplay)` → `subprocess.run`** (`scripts/traitement_fin.py`,
  fonctions `bip_plat()` et `bip()`, ~l.91 et ~l.113) : les deux appels
  `os.system(f'aplay {tmp} 2>/dev/null')` remplacés par
  `subprocess.run(["aplay", tmp], capture_output=True)` — même résultat
  (échec silencieux, pas d'exception si `aplay` absent ou en erreur), sans
  passer par un shell, cohérent avec `scripts/bip_Cloche.py`.
- **Sonde PID inline** (`app/watchers.py::watcher_actif()`) : le
  `os.kill(pid, 0)` inline remplacé par un appel à `watcher._pid_vivant`
  (déjà importé sans cycle — `app/watchers.py` importait déjà `Config` et
  `taches_en_cours` depuis `watcher`), fonction cross-plateforme
  POSIX/Windows (issue #584) plutôt qu'un troisième exemplaire de sonde de
  process. Note : `_pid_vivant` traite `PermissionError` comme « vivant »
  par prudence (asymétrie volontaire documentée dans `watcher.py`, contre
  un faux négatif en cas de PID recyclé), alors que l'ancien code local le
  traitait comme « inactif » — différence mineure, cohérente avec l'usage
  qu'en fait déjà `watcher.py` pour ses propres verrous.

Vérification : `py_compile` OK sur les 5 fichiers touchés/ajoutés, import
réel de `watcher`, `app.watchers` et `scripts/archiver_historique.py`
testé (pas seulement compilation syntaxique), les 21 scripts de `tests/`
passent (code de sortie 0), et un test manuel de `bip_plat()`/`bip()` via
`subprocess.run` confirme que le son de fin d'issue continue de fonctionner.

## 25 septembre 2026 — issue #616

Depuis le passage au PC fixe physique (issue #446, août 2026), le §16 de
`BRIDGE_AGENT_DOC.md` (Agent Windows CCW) accumulait de nombreux blocs
marqués explicitement « obsolète — conservé à titre historique » décrivant
l'ancienne architecture VM VirtualBox (éval 90 jours, `VBoxManage`,
`creer_vm_ccw.py`, `autounattend.xml`, `lancer_provisioning.py`,
`demarrer_ccw.sh`, `eval-expiration.json`, `verifier_expiration_ccw.py`,
partage réseau `\\VBoxSvr\CCW_Share`) : dette documentaire payée en tokens
à chaque conversation Claude Chat chargeant la doc, et source de confusion
entre l'état révolu et l'état courant. Décision actée (issue) : supprimer
ces blocs, pas les extraire vers un fichier historique séparé.

- Tableau des scripts de provisioning (§16) : suppression des 6 lignes
  purement obsolètes (`creer_vm_ccw.py`, `autounattend.xml`,
  `lancer_provisioning.py`, `demarrer_ccw.sh`, `eval-expiration.json`,
  `verifier_expiration_ccw.py`) ; retrait des mentions « (dans la VM… )»
  sur les 6 scripts encore actifs (`mettre_a_jour_tokens_ccw.ps1`,
  `ajouter_projet_ccw.ps1`, `lister_projets_ccw.ps1`,
  `finaliser_projet_ccw_auto.ps1`, `finaliser_projet_ccw.ps1`,
  `surveiller_builds.ps1`) ; `provisionner.ps1` conservé comme référence
  des étapes d'installation logicielle, description nettoyée des mentions
  VM.
- Bloc « Lancer le provisioning (obsolète — via VM) » et son extrait bash
  (`lancer_provisioning.py`) supprimés.
- Sous-section entière **§16.1 Maintenance périodique (renouvellement à
  90 jours)** supprimée (recréation de VM, `eval-expiration.json`,
  `VBoxManage storageattach`, ré-attachement d'ISO) — le renouvellement des
  tokens GitHub/Claude, seule partie encore valide, était déjà documenté
  plus haut dans le §16 (script `mettre_a_jour_tokens_ccw.ps1`). Le renvoi
  `cf. §16.1` restant dans la description du token par projet a été retiré.
  La numérotation des sous-sections n'a pas été renumérotée (le §16 passe
  directement de son intro à 16.2, comme le document passe déjà du §14 au
  §16 sans §15).
- §16.3 : callout « Étape 0 et note safe.directory obsolètes » + bloc bash
  associé supprimés, ainsi que les deux notes historiques (safe.directory,
  staging local) mentionnant l'ancien partage VirtualBox ; reformulation
  mineure de la note « Récupération des artefacts » et de la note
  « staging local » pour retirer les mentions VirtualBox devenues sans
  objet.
- §16.4 (bouton « Interrompre ») : reformulation du callout et du
  paragraphe technique pour retirer les deux mentions `VBoxManage
  guestcontrol` (remplacées par « ancien mécanisme de pilotage à distance
  de la VM » / « à distance »), sans supprimer la documentation du
  fonctionnement actuel du bouton (`app/interruption.py::
  interrompre_windows`, toujours inopérant sur PC physique — pas de
  changement de code dans le cadre de cette tâche, doc uniquement).
- Renvoi orphelin « Specs MVC §15 » (§12) corrigé en « Specs MVC » (le §15
  n'existe plus dans le document).
- Conservé tel quel : l'encart « ⚠️ Changement de plateforme (depuis août
  2026, issue #446) » en tête du §16, qui explique en quelques lignes le
  passage VM → PC fixe — seul contexte minimal encore utile pour comprendre
  d'anciens commits mentionnant une VM.

Vérification : plus aucune mention de VirtualBox/VBoxManage/
`creer_vm_ccw.py`/`autounattend.xml`/`lancer_provisioning.py`/
`demarrer_ccw.sh`/`eval-expiration.json`/`verifier_expiration_ccw.py` dans
le §16 en dehors de l'encart « Changement de plateforme » conservé
volontairement (et d'une brève justification historique déjà concise sur
le compte NSSM `AlainW`, hors périmètre de nettoyage de l'issue). Fences
markdown et séquence des titres `###` du §16 vérifiées cohérentes après
coup. `py_compile` sans objet (fichier `.md`).

## 25 septembre 2026 — issue #615

Le widget `/rate-limit` (#607) n'était rafraîchi que par le polling JS à
intervalle fixe (30s) — une rafale de consommation gh entre deux polls
pouvait épuiser le quota sans que le widget le reflète, et aucun log ne
permettait de corréler une consommation anormale avec sa source.

Piste initiale (capturer les headers HTTP `x-ratelimit-*` de chaque appel
`gh` existant via `--include`) écartée après vérification : les
sous-commandes utilisées dans ce projet (`gh issue list/view/create/
close/edit/comment`) n'exposent pas `--include`/`-i` — seule `gh api`
l'a (gh 2.45.0). Réécrire tous ces appels en `gh api` équivalents aurait
été disproportionné pour ce ticket. Repli explicitement permis par
l'issue retenu à la place :

- **`etat_rate_limit.py`** (nouveau) : état partagé du quota GraphQL,
  persisté dans `logs/etat_rate_limit.json` (écriture atomique + verrou
  anti-collision, même pattern que `etat_timeout.json`/`etat_ambiance.json`,
  issue #221) puisque `watcher.py` tourne dans un process séparé de
  l'app Flask qui sert `/rate-limit`. `maj_rate_limit(origine)` appelle
  `gh api rate_limit` (n'entame NI le quota `core` NI le quota `graphql`,
  issue #263) et journalise la mise à jour en DEBUG avec l'`origine`
  (module.fonction appelant) — permet de corréler une consommation
  anormale avec sa source lors d'un futur épisode. `lire_rate_limit()`
  lit l'état sans jamais lever d'exception (fichier absent/corrompu →
  `None`).
- **`watcher.py`** : `fermer_issue()` appelle `maj_rate_limit("watcher.
  fermer_issue")` juste après la fermeture effective de l'issue —
  rafraîchit le quota dans les secondes qui suivent l'appel gh
  significatif, sans attendre le prochain polling du widget.
- **`app/issues.py`** : `maj_rate_limit()` appelé après création
  (`envoyer`), annulation (`annuler_issue`) et fermeture définitive
  (`fermer_issue`) d'une issue.
- **`app/notifications_poller.py`** : `maj_rate_limit()` appelé une
  seule fois par cycle complet de `surveiller_transitions()` (pas par
  projet) — ce poller vise justement à alléger la charge gh cumulée
  (#188, #614) ; un appel rate_limit par projet irait à rebours de cet
  objectif pour un gain de fraîcheur négligeable.
- **`app/rate_limit.py`** : la route `GET /rate-limit` sert d'abord
  l'état partagé s'il a moins de `SEUIL_FRAICHEUR_S` (20s, sous la
  cadence de polling JS de 30s) — potentiellement rafraîchi entretemps
  par un autre process (watcher.py). Sinon, retombe sur l'appel gh
  direct d'origine (issue #607), qui met lui-même à jour l'état partagé
  au passage. Contrat de la route inchangé (`{ok, used, limit,
  remaining, reset}`) : le widget JS (`static/js/app.js`) n'a pas eu à
  changer.

Vérification : `py_compile` sur tous les modules touchés + import de
`app.create_app()` et `etat_rate_limit` (résolution du `sys.path`
inséré par `app.projets`) ; suite de tests existante (`pytest tests/`,
14 passed) toujours verte.

## 25 septembre 2026 — issue #614

Réduit la consommation GraphQL du poller de notifications (`app/notifications_poller.py`) :
le filtre `_dans_la_portee()` (diagnostic #613) n'intervenait qu'**après** les
appels `gh issue list`, sur les transitions déjà récupérées — avec 14 projets
configurés, `surveiller_transitions()` interrogeait donc systématiquement les
14 projets à chaque cycle (2 appels gh chacun, 28/cycle) quel que soit
`BRIDGE_NOTIF_SCOPE`, alors que le défaut `for-windows` n'a besoin que des
projets CCW.

- **Nouvelle fonction `_projets_dans_la_portee()`** : filtre la liste retournée
  par `lister_projets()` **avant** la boucle principale de
  `surveiller_transitions()`, sur le champ `LABEL` du `.conf` de chaque projet
  (`cfg.label`) — `SCOPE=for-windows`/`for-linux` ne gardent que les projets au
  label correspondant, `SCOPE=all` garde tout (comportement inchangé),
  `SCOPE=off` reste court-circuité plus haut (aucun changement). Distincte de
  `_dans_la_portee()` (conservée telle quelle), qui filtre les *transitions*
  sur les labels de l'*issue* elle-même — sécurité complémentaire en aval, non
  redondante.
- **Log de chaque appel gh** : `_gh_list()` journalise désormais
  `gh issue list <dépôt> label=<label> state=<état>` avant chaque appel réseau
  (log de `new_issue.py`), pour permettre un diagnostic précis lors d'un futur
  épisode d'épuisement de quota GraphQL.
- **BRIDGE_AGENT_DOC.md §17** mis à jour : décrit le filtrage par SCOPE en
  amont des appels gh et la disponibilité du log par appel.
- Suite de tests existante toujours verte (14 passed).

## 25 septembre 2026 — issue #612

Corrige trois incohérences laissées par #609/#611 : docstring obsolète,
commentaire erroné sur l'incident `relecture_bridge` #73, extension du
mécanisme de report aux autres déclencheurs de redémarrage.

- **Docstring `repli_rep_travail` déjà simplifiée par #611** (vérifié) :
  ne décrit plus qu'un seul cas — le repli en tout dernier recours après
  échec des 3 tentatives de création de worktree (#589). Aucune trace
  résiduelle du « Cas 1 » (premier slot dans `REP_TRAVAIL`) supprimé par
  #611.
- **Commentaire erroné sur #73 corrigé** (`app/watchers.py` ×3,
  `static/js/app.js` ×2, `BRIDGE_AGENT_DOC.md` ×2) : attribuaient
  l'incident au repli #589 (« reprise sur un worktree déjà pris, repli
  silencieux sur REP_TRAVAIL »). Diagnostic confirmé le 24/09/2026 :
  `#73` tournait dans son worktree dédié avec `MAX_WRITE_PARALLELE=1` ;
  Alain a changé la valeur à 2 et relancé le watcher ; `systemctl --user
  restart` a tué tout le cgroup (dont le process CCL en cours) ; le
  watcher a repris `#73` comme premier slot et l'a lancée directement
  dans `REP_TRAVAIL` — l'ancien comportement du premier slot, supprimé
  depuis par #611. Aucune ligne « déjà pris » dans les logs. Les
  commentaires décrivent maintenant la vraie cause (kill systemd du
  cgroup au redémarrage), distincte du repli #589.
- **`BRIDGE_AGENT_DOC.md`** : paragraphe « Signal d'interface (issue
  #609) » mis à jour — il ne subsiste plus qu'un seul cas de repli
  (#589), plus deux cas à distinguer comme avant #611 ; le bandeau ne
  s'allume donc plus à chaque tâche `mode_write` normale.
- **Extension aux autres déclencheurs (vérification, point 3)** :
  - Bouton « Relancer » du panneau Infrastructure/onglet Watchers :
    déjà couvert — passe par la même route `/lancer-watcher` →
    `demarrer_watcher_ou_differer` que « Enregistrer et relancer »
    (`sidebarRelancerWatcherCCL`/`actionWatchers`, `static/js/app.js`).
    Aucun code à ajouter, documenté explicitement dans
    `BRIDGE_AGENT_DOC.md`.
  - Redémarrage systemd sur crash (`Restart=on-failure`) : NE PEUT PAS
    être intercepté côté Python (le process CCL est tué avant d'avoir la
    main). Limite documentée explicitement dans `BRIDGE_AGENT_DOC.md`
    (§16 et §"Redémarrage forcé différé"), pour ne pas laisser croire que
    #609/#611 couvrent ce cas.
- Suite de tests existante toujours verte (14 tests pytest + 19 scripts
  autonomes, tous OK).

## 25 septembre 2026 — issue #611

Corrige l'incohérence entre l'encart #577 de `BRIDGE_AGENT_DOC.md`
(« REP_TRAVAIL n'est plus jamais touché directement ») et le code réel
depuis #337 : à `MAX_WRITE_PARALLELE > 1`, le premier slot d'un lot
`mode_write` était délibérément dispatché dans `REP_TRAVAIL`
(`worktree=None`), sans isolation — un redémarrage du watcher pendant
ce premier slot tuait le processus CCL et laissait du travail inachevé
mélangé dans `REP_TRAVAIL` (`relecture_bridge` #73).

- **`watcher.py`** : le bloc `if not actifs:` de `traiter_issue` (premier
  slot direct sur `REP_TRAVAIL`) est supprimé — toute tâche `mode_write`,
  quel que soit son rang dans le lot, passe désormais par la création d'un
  worktree dédié. Nouvelle fonction `_creer_worktree_avec_retries(numero)` :
  enveloppe `_creer_worktree` avec jusqu'à 2 tentatives supplémentaires sous
  noms alternatifs (`-bis`, `-ter`, via le nouveau paramètre `suffixe` de
  `_chemin_worktree`/`_branche_worktree`/`_creer_worktree`) quand l'échec est
  attribuable à un chemin/branche déjà pris (reliquat non nettoyé, #589) —
  aucune retentative sur une erreur git générique, qu'un changement de nom
  ne résoudrait pas. Si les 3 tentatives échouent, nouvelle fonction
  `_signaler_repli_worktree_echoue(numero, raison)` : `notify-send` immédiat
  (`notifier_bureau`, urgence `critical`) + `log.warning` explicite avec le
  chemin, avant le repli en tout dernier recours sur `REP_TRAVAIL` (toujours
  en tâche de fond à `MAX_WRITE_PARALLELE > 1`, pour que la boucle
  principale reste libre). `_lancer_thread_ecriture` et
  `_traiter_issue_synchrone` transmettent `echec_worktree_deja_pris` dans ce
  cas aussi, pour que le compte-rendu de clôture (#589) mentionne le repli
  quel que soit le chemin qui y a mené.
- **`tests/test_worktree_parallelisation_337.py`** : nouveaux scénarios pour
  `_creer_worktree_avec_retries` (réussite via `-bis`, épuisement des 3
  tentatives, pas de retry sur erreur générique) et pour le repli signalé
  (`notify-send` capturé par un faux exécutable) à `MAX_WRITE_PARALLELE <= 1`
  et `> 1`. Scénario de parallélisation à 2 tâches mis à jour : les deux
  obtiennent désormais chacune un worktree dédié (plus aucune dans
  `REP_TRAVAIL`).
- **`BRIDGE_AGENT_DOC.md`** : encart et section détaillée réécrits pour
  décrire le comportement sans exception (worktree pour toute tâche
  `mode_write`) et la séquence de repli (tentatives `-bis`/`-ter` puis
  signalement actif en dernier recours).

Suite de tests existante (21 fichiers) toujours verte.

## 24 septembre 2026 — issue #609

Enregistrer la configuration d'un projet ne redémarre plus son watcher
pendant une tâche en cours — vécu sur `relecture_bridge` (issue #73) :
juste après le lancement d'une issue `mode_write`, une config enregistrée
via l'onglet Configuration (« Enregistrer et relancer ») a redémarré le
watcher en plein traitement ; au redémarrage, l'issue a été reprise, son
worktree dédié était « déjà pris » par la première tentative, repli sur
REP_TRAVAIL (#589), et le travail — non isolé — a été embarqué dans un
commit automatique d'un autre outil puis poussé par erreur.

**Point 1 (vérification du log) non traité** : `logs/watcher-relecture_bridge.log`
vit dans `/home/alain/Bridge_Agent/logs/` (dépôt principal), hors du
périmètre strict de ce worktree (`/home/alain/bridge_agent-issue609`).
Signalé plutôt que contourné.

- **`watcher.py`** : `acquerir_verrou()` prend désormais un paramètre `mode`,
  consigné dans le fichier de verrou (`logs/verrous/*.lock`, champ `mode=`,
  positionné avant `rep=` qui reste en dernier). Nouvelle fonction publique
  `taches_en_cours(nom_projet)` : scanne les verrous actifs (pid propriétaire
  vivant) et retourne les tâches en cours d'un projet — seul canal permettant
  à `new_issue.py` (process séparé du watcher) de savoir si un projet a une
  tâche en cours, `issues_en_cours` restant en mémoire du process watcher.
- **`app/watchers.py`** : `tache_en_cours(cfg)` (liste des tâches actives),
  `repli_rep_travail(cfg)` (une tâche `mode_write` tourne directement dans
  REP_TRAVAIL, hors worktree isolé — premier slot d'une parallélisation
  normale ET repli #589, même risque dans les deux cas, non distingués).
  `demarrer_watcher_ou_differer(cfg, forcer)` remplace `demarrer_watcher`
  comme point d'entrée de la route `/lancer-watcher` : un redémarrage forcé
  d'un watcher occupé n'est plus exécuté immédiatement (il couperait la
  tâche) — mémorisé dans `_redemarrages_differes`, exécuté automatiquement
  par le nouveau thread démon `surveiller_redemarrages_differes` dès la fin
  de la tâche (sondé toutes les `INTERVALLE_SURVEILLANCE_DIFFERE` = 15 s).
  `demarrer_watcher()`/`redemarrer_si_eteint()` (toujours `forcer=False`)
  restent inchangés — jamais concernés, un watcher avec une tâche en cours
  étant par construction déjà actif.
- **`new_issue.py`** : démarre `surveiller_redemarrages_differes` en thread
  démon, aux côtés de `surveiller_heartbeat`/`surveiller_transitions`.
- **Interface** : route `/watchers` expose `tache_en_cours`,
  `repli_rep_travail`, `redemarrage_differe` par projet. Onglet Watchers
  (`templates/index.html`, `static/js/app.js`) : nouvelle colonne « Statut »
  (⏳ tâche en cours / ⏳ redémarrage différé / ⚠️ REP_TRAVAIL en écriture).
  Bandeau global (même principe que le bandeau éval Windows #454), visible
  sur tous les onglets, listant les projets dont une tâche `mode_write`
  tourne actuellement dans REP_TRAVAIL. `sauvegarderConfig(relancer)` affiche
  « redémarrage différé, appliqué automatiquement à la fin de la tâche en
  cours » au lieu de « Watcher relancé » quand `/lancer-watcher` répond
  `differe: true`.
- **`BRIDGE_AGENT_DOC.md`** : nouveau point 4 dans « Cycle de vie des
  watchers » ; note ajoutée dans la section worktrees/repli #589.

Aucune régression sur les 5 appelants existants de `redemarrer_si_eteint`
(toujours `forcer=False`, jamais différés) ni sur `interrompre_linux`
(tue déjà tout l'arbre du watcher puis le laisse éteint — aucun redémarrage
forcé automatique à sa suite).

## 24 septembre 2026 — issue #608

Colonne « Couleur » ajoutée au tableau des projets actifs (§2 de
`BRIDGE_AGENT_DOC.md`) : `relecture_web` (projet `relecture_bridge`) n'a
accès qu'à ce tableau public — `configs/` est hors de son périmètre — et
voulait pouvoir afficher la couleur d'accent de chaque projet sans confondre
des noms proches (`bridge_agent`/`relecture_bridge`, `alchess`/`chesscoach`).

- **`nouveau_projet.py`** : nouvelle fonction `couleur_affichee(nom,
  couleur_conf)`, miroir Python de `couleurProjet()` (`static/js/app.js`) —
  réutilise `COULEURS_PROJETS_EXISTANTS`/`COULEUR_PROJET_INACTIF` existants
  plutôt que de dupliquer la règle de priorité. Ajout de
  `PROJETS_COULEUR_RECYCLEE` (ensemble miroir de `COULEURS_PROJET` côté JS
  pour `ecole`/`ff_galerie`, issue #540) et de `couleur_hash_projet()`
  (miroir de `couleurHashProjet()`, converti en hex via `_hsl_vers_hex`
  plutôt qu'en `hsl(...)`).
- **`regenerer_tableaux_projets.py`** : la colonne `Couleur` est ajoutée en
  **dernière position** du tableau `TABLEAU_PROJETS_ACTIFS` (pour ne décaler
  aucune colonne existante — vérifié qu'aucun autre lecteur du dépôt ne parse
  ce tableau par position). `lire_projets()` importe `nouveau_projet`
  localement (pas en tête de fichier) pour éviter un cycle d'import avec
  `nouveau_projet.py`, qui importe déjà `regenerer_tableaux_projets` à son
  chargement (issue #571) — testé dans les deux ordres d'import.
- **`BRIDGE_AGENT_DOC.md`** : §2 et « Couleur d'accent des projets » mis à
  jour pour documenter la nouvelle colonne et le cas des projets à couleur
  recyclée. Le tableau généré lui-même n'a **pas** été régénéré dans ce
  worktree isolé : `configs/*.conf` (gitignoré) n'y est pas présent — à
  lancer par Alain (`python3 regenerer_tableaux_projets.py`) après fusion,
  sur un checkout ayant accès aux vrais `.conf`.

## 24 septembre 2026 — issue #607

Indicateur compact du rate limit GitHub GraphQL dans le bandeau
supérieur de `new_issue.py`, toujours visible quel que soit l'onglet
actif (entre le titre « Bridge Agent » et le compteur « N projet(s)
disponible(s) ») — répond au cas concret du 24/09 (13 watchers
démarrés simultanément) où l'onglet Résultats affichait « Aucune
issue à afficher » sans explication pendant que le quota était épuisé.

- **`app/rate_limit.py`** (nouveau) : route `GET /rate-limit`, exécute
  `gh api rate_limit --jq '.resources.graphql'` côté serveur et
  renvoie `{ok, used, limit, remaining, reset}` — ou `{ok: false,
  erreur}` en cas d'échec (gh absent, timeout, rate limit REST atteint)
  sans jamais lever d'erreur HTTP. Cet appel ne consomme NI le quota
  `core` NI le quota `graphql` (vérifié empiriquement, issue #263,
  `scripts/mesurer_api.py`) : son polling ne peut donc pas lui-même
  épuiser le quota qu'il surveille.
- **`app/__init__.py`** : enregistrement de la route (`login_requis`,
  comme `/watchers`/`/statut`).
- **`templates/index.html`** : `<span id="rate-limit-widget">` inséré
  entre `<h1>` et `.statut`.
- **`static/js/app.js`** : `rafraichirRateLimit()`, polling global
  indépendant de l'onglet actif (`setInterval`, 30s — même cadence que
  le monitoring infrastructure de la sidebar Résultats), format
  `⚡ 132 / 5000 · reset 20:15` (heure de reset convertie en local côté
  navigateur via `toLocaleTimeString`). État dégradé `⚡ ? / 5000` en
  gris si l'appel échoue, sans faire disparaître le widget.
- **`static/css/style.css`** : classes `.rate-limit` + `.rl-vert` /
  `.rl-orange` / `.rl-rouge` / `.rl-gris` (mêmes teintes que les
  badges de temps restant existants). Seuils de couleur : vert < 70%
  utilisé, orange 70-90%, rouge > 90% (risque immédiat). Le
  `margin-left:auto` qui poussait `.statut` à droite est déplacé sur
  `.rate-limit` : le widget, le compteur de projets et les boutons
  d'en-tête restent groupés à droite, comme avant.

Vérification : valeurs de `/rate-limit` comparées à `gh api rate_limit
--jq '.resources.graphql'` en terminal (identiques) ; seuils de
couleur testés à 69/70/90/91% ; état d'erreur simulé (PATH sans `gh`)
→ `{ok: false, erreur: "gh introuvable dans le PATH."}`, HTTP 200 (pas
de plantage) ; `py_compile` sur tous les modules Python touchés +
suite de tests existante (`pytest tests/`, 14 passed) toujours verts.

## 24 septembre 2026 — issue #606

§16 « Agent Windows CCW » : extraction de `provisioning/windows/ccw-commun.psm1` (issue #606, sous-issue A de l'étude de faisabilité #604, suite du diagnostic #579) — regroupe ce qui était dupliqué entre les 3 scripts CCW **locaux** (`creer_projet_ccw_complet.ps1` à la racine, `provisioning/windows/ajouter_projet_ccw.ps1`, `provisioning/windows/finaliser_projet_ccw.ps1`) : helpers d'affichage `Info`/`Ok`/`Avert` (préfixe fixé une fois via `Set-PrefixeCcw`), `Get-CheminsProjetCcw` (dérivation `NomService`/`RepDepot`/`NomConf`/`NomLog`/`CheminConf` à partir du seul `NomProjet`, avec le cas spécial `Bridge_Agent` → service `CCW-Watcher` sans suffixe, même convention que `lister_projets_ccw.ps1`/`finaliser_projet_ccw_auto.ps1`), et `Lire-ValeurFichier` (lecture d'une clé dans un `.conf`, reprise de `mettre_a_jour_tokens_ccw.ps1`). Les 3 scripts locaux importent désormais le module (`Import-Module (Join-Path $PSScriptRoot '...ccw-commun.psm1') -Force`) au lieu de dupliquer cette logique. `app/ccw.py::ccw_ajouter_projet()` copie maintenant `ccw-commun.psm1` en plus de `ajouter_projet_ccw.ps1` vers `C:\Windows\Temp\` (seul script local également poussé seul par SCP). Scripts distants (`finaliser_projet_ccw_auto.ps1`, `mettre_a_jour_tokens_ccw.ps1`, `lister_projets_ccw.ps1`) non touchés — leur autonomie sans dépendance externe reste délibérée (#604) ; `lister_projets_ccw.ps1` traité séparément dans la sous-issue B si retenue.

## 24 septembre 2026 — issue #603

Alignement de `creer_projet_ccw_complet.ps1` (racine du dépôt) sur les
conventions des 11 autres scripts `.ps1` de `provisioning/windows/`
(diagnostic #579, point 4) — 4 problèmes à risque réel corrigés :

- **BOM UTF-8** ajouté en tête du fichier (`EF BB BF`) — sans lui,
  PowerShell 5.1 plante silencieusement au premier accent ajouté.
- **`.conf` sans BOM** : remplacement de `Set-Content -Encoding UTF8`
  (qui écrit un BOM parasite) par `[IO.File]::WriteAllText(...,
  UTF8Encoding($false))`, comme `ajouter_projet_ccw.ps1` — évite de
  corrompre silencieusement la lecture par `watcher.py`.
- **Fuite de secret BSTR** : ajout de la fonction
  `ConvertFrom-SecureStringPlain` (try/finally +
  `Marshal::ZeroFreeBSTR`), même pattern que
  `mettre_a_jour_tokens_ccw.ps1`, appliquée aux deux tokens saisis.
- **Chemin codé en dur** : `$CheminClaude` dérivé dynamiquement de
  `$env:USERPROFILE` au lieu du compte `AlainW` en dur — ne casse plus
  silencieusement si le compte de service change.

Le point 5 du diagnostic (extraction d'un module commun
`provisioning/windows/ccw-commun.psm1` pour la dérivation de chemins
projet dupliquée entre ce script et `ajouter_projet_ccw.ps1`/
`finaliser_projet_ccw.ps1`) dépasse la COMPLEXITE `normal` de cette
issue — reporté à l'issue séparée #604, comme prévu par le corps de
#603.

Aucun test PowerShell direct (script non exécutable côté Linux) ; le
test statique existant `tests/test_ajouter_projet_ccw_env_558.py`
(cohérence `AppEnvironmentExtra` entre les 3 scripts qui le posent) et
l'ensemble des tests Python (`py_compile` + suite `tests/`) restent
verts.

## 24 septembre 2026 — issue #602

Retrait des 2 étapes manuelles caduques depuis #597 du corps de l'issue CCL
généré par `app/projet_ccw.py::_corps_issue_ccl()` (case « Projet CCW » du
formulaire de création, issue #559).

- `app/projet_ccw.py::_corps_issue_ccl()` : supprime les 2 anciennes étapes
  numérotées (ajout d'une entrée au tableau `$Projets` de
  `reinstaller_projets_ccw.ps1` + ligne dans le tableau de rappel de
  `REINSTALLATION_CCW.md` §7) — toutes deux automatisées depuis #597
  (dérivation dynamique de `$Projets` depuis `configs\*-ccw.conf`) et #556
  (le fichier `.conf` est déjà créé par le flux CREATION). Le corps devient
  purement informatif (section « Contexte » expliquant qu'aucune action
  manuelle n'est requise), conservant la référence croisée vers l'issue CCW.
- `tests/test_projet_ccw_559.py::scenario_corps_issue_ccl_contenu` : les
  assertions vérifient désormais l'ABSENCE des 2 anciennes instructions
  plutôt que leur présence.
- `BRIDGE_AGENT_DOC.md` §16 (séquence `bootstrap_projet_ccw`, point 3) :
  description mise à jour pour refléter le corps simplifié.
- Évaluation demandée par l'issue : le corps de l'issue CCL, une fois les 2
  étapes retirées, ne contient plus aucune action exécutable (seulement du
  contexte + la cross-référence) — l'issue CCL elle-même pourrait donc être
  supprimée du flux (route `bootstrap_projet_ccw`, frontend, doc, tests).
  Non fait ici : ce retrait toucherait le contrat de l'issue CCW (paramètre
  `numero_ccl`), le template/JS affichant les 2 liens d'issue, et une bonne
  partie de `tests/test_projet_ccw_559.py` — portée plus large que la
  COMPLEXITE `normal` déclarée pour #602, et l'issue demande explicitement
  de ne pas supprimer le flux sans confirmation. Recommandation : ouvrir une
  issue dédiée si ce retrait complet est souhaité (même logique de scission
  que #601/#602).

Tests : suite complète (21 fichiers `tests/test_*.py`) toujours verte.

## 24 septembre 2026 — issue #601

Factorisation du tableau markdown `## En-tête` dans une fonction commune
`formater_entete()` (diagnostic #579 §3.2) : ce tableau était construit à
la main dans trois sites (`app/issues.py`, `app/projet_ccw.py` ×2,
`scripts/watcher_issues_inbox.py`), avec des divergences déjà présentes
(TIMEOUT/PRIORITE en dur à certains endroits, ligne COMPLEXITE hors
tableau) — or ce tableau est re-parsé tel quel par `watcher.py`, une
dérive future aurait pu casser le parsing silencieusement.

- `app/issues.py` : nouvelle fonction `formater_entete(mode, priorite,
  timeout, projet, *, source="CC", dest="CCL", retour="CC", modele=None,
  complexite=None)` — reproduit EXACTEMENT le format existant (`timeout`
  sans le suffixe `s`, ajouté par la fonction ; `MODELE` et `COMPLEXITE`
  optionnels, absents par défaut). `construire_body()` l'utilise
  désormais au lieu de construire ses lignes à la main.
- `app/projet_ccw.py` : `_corps_issue_ccl()` et `_corps_issue_ccw()`
  appellent `formater_entete()` (import local, comme le reste des imports
  `app.issues` de ce module, pour éviter tout souci d'import circulaire).
  Le bloc `CREATION_*` de `_corps_issue_ccw()` reste construit à part et
  concaténé après l'en-tête (format spécifique à ce seul site, non inclus
  dans la fonction commune).
- `scripts/watcher_issues_inbox.py` : `construire_body()` appelle
  `formater_entete()` au lieu de dupliquer les lignes du tableau.

Format de sortie vérifié identique bit-à-bit à l'ancien code (comparaison
manuelle des chaînes produites, avant/après, pour les trois sites) — pas
de modification du format attendu par `watcher.py`. Suite de tests
existante (21 fichiers, dont `tests/test_projet_ccw_559.py`) toujours
verte sans aucune modification des tests.

## 24 septembre 2026 — issue #600

Factorisation de l'enrobage « redémarrer le watcher s'il est éteint »,
dupliqué à 5 endroits avec des comportements divergents en cas d'échec
(diagnostic #579) — nouveau helper `redemarrer_si_eteint()` dans
`app/watchers.py`.

- `app/watchers.py` : nouvelle fonction `redemarrer_si_eteint(cfg, *,
  tracer=False)`, enrobage de `demarrer_watcher(cfg, forcer=False)`.
  Retourne `(demarre, pid, trace)` — `demarre` distingue désormais
  `True` (relancé), `False` (tournait déjà) et `None` (échec, repris
  d'`app/interruption.py`) ; `trace` est une chaîne prête à insérer dans
  un commentaire GitHub (non vide seulement si `tracer=True`). Un échec
  produit systématiquement un `log.warning` — jamais silencieux, à la
  différence de l'ancien `except: pass` d'`app/projet_ccw.py`.
- 5 sites remplacés par des appels à ce helper : `app/issues.py`
  (~l.356), `app/interruption.py` (~l.531), `app/projet_ccw.py` (~l.416),
  `scripts/watcher_issues_inbox.py` (~l.621 et ~l.864).
- Garde `for-linux` **non** internalisée dans le helper : dans
  `app/issues.py` et `app/interruption.py`, elle porte sur le routage de
  l'issue (labels for-linux/for-windows, #164), une décision propre à
  l'appelant — le helper ne reçoit qu'un `cfg` de projet, sans notion de
  labels. Les 3 autres sites ne l'avaient jamais eue (contexte déjà
  filtré sur bridge_agent) : rien à y ajouter.
- `tests/test_champ_redacteur_599.py` et `tests/test_champ_relance_516.py` :
  les scénarios qui substituaient `w.demarrer_watcher` (attribut copié
  au moment de l'import dans `watcher_issues_inbox.py`) substituent
  désormais `app.watchers.demarrer_watcher` directement, puisque
  `redemarrer_si_eteint()` résout `demarrer_watcher` par lookup dans son
  propre module (`app.watchers`) et non plus dans celui de l'appelant.
  Suite de tests (21 fichiers scénarios) toujours verte.

## 24 septembre 2026 — issue #599

Ajout du champ d'en-tête optionnel `REDACTEUR` dans `issues_inbox/`, validé
pour cohérence avec `PROJET` **avant** toute création d'issue GitHub — filet
de sécurité contre une issue rédigée par Claude Chat dans le contexte d'un
projet puis déposée par erreur sous un `PROJET` différent (distraction,
relecture insuffisante d'Alain avant dépôt du fichier).

- `scripts/watcher_issues_inbox.py` : `REDACTEUR` ajouté à `CHAMPS_ENTETE`
  et à `extraire_champs()` ; nouvelle fonction `valider_redacteur()` appelée
  par `valider()` avant toute autre vérification. Trois règles : (1)
  `REDACTEUR == PROJET` → OK ; (2) label `for-windows` **et**
  `REDACTEUR == bridge_agent` → OK (canal central CCW, quel que soit le
  `PROJET` réellement ciblé) ; (3) tout autre cas → rejet vers
  `issues_inbox/rejected/` avec message explicite de discordance, journalisé
  dans `issues_inbox.log`. `REDACTEUR` absent → aucune validation
  (rétrocompatibilité avec les issues existantes).
- `BRIDGE_AGENT_DOC.md` : `REDACTEUR` ajouté au tableau des champs
  d'en-tête de `issues_inbox/` (§3.3), règle de validation détaillée dans
  §3.4, et entrée miroir dans le tableau général des champs spéciaux (§6).
- `tests/test_champ_redacteur_599.py` (12 scénarios) : extraction du champ,
  les 3 règles de `valider_redacteur()`, et le chemin complet
  `traiter_fichier()` pour les 4 cas de vérification demandés par l'issue
  (REDACTEUR == PROJET, REDACTEUR d'un autre projet sans for-windows,
  canal CCW for-windows + REDACTEUR=bridge_agent, REDACTEUR absent).

## 23 septembre 2026 — issue #598

Ajout d'un `PATH` explicite dans `systemd/watcher@.service` : les services
systemd --user démarrent avec un `PATH` minimal, sans les chemins ajoutés
par le shell interactif — notamment `~/.npm-global/bin` (où réside `claude`)
et `~/Bridge_Agent/venv/bin`. Après la migration systemd de #596, l'issue #67
(relecture_bridge) a échoué immédiatement avec « Claude Code introuvable
(claude non trouvé dans PATH) ». Même piège que celui déjà documenté côté
CCW/NSSM (§16 du DOC).

Un correctif manuel (`systemctl --user edit --full` + `daemon-reload` +
`restart`) avait déjà été appliqué en prod sur toutes les instances, mais
ne vivait que dans `~/.config/systemd/user/` — perdu à la prochaine
exécution d'`installer_services.sh`, qui écrase ce fichier depuis le
gabarit du dépôt.

- `systemd/watcher@.service` : directive `Environment="PATH=..."` ajoutée
  dans `[Service]`, en chemins absolus (systemd n'interprète pas `~`) —
  `/home/alain/Bridge_Agent/venv/bin`, `/home/alain/.npm-global/bin`,
  `/home/alain/.local/bin`, `/home/alain/bin`, puis le PATH système standard.
  Validé avec `systemd-analyze verify`.
- `BRIDGE_AGENT_DOC.md` (section « Watchers supervisés par systemd --user ») :
  nouveau point documentant l'exigence du `PATH` explicite, la cause, et la
  commande de vérification post-installation (`/proc/<pid>/environ`).

## 23 septembre 2026 — issue #596

Réactivation des watchers de projet en services `systemd --user`
(`watcher@<projet>.service`), abandonnée une première fois par l'issue #119 :
`Restart=always` + `RestartSec=10` relançait systématiquement tout watcher
qui venait de s'éteindre proprement pour inactivité (`DELAI_INACTIVITE_MIN`,
#199/#200), en boucle sans fin. Constaté concrètement le 22/09/2026 lors d'un
redémarrage du ThinkPad ayant interrompu plusieurs watchers en cours, sans
aucune supervision pour les relancer.

Correction de l'incompatibilité : `Restart=on-failure` + `SuccessExitStatus`
sur un code de sortie dédié à l'auto-extinction (distinct de 0), pour que
systemd relance un crash réel mais jamais un arrêt volontaire — qu'il
s'agisse de l'auto-extinction pour inactivité ou d'une interruption manuelle
(#323).

- `watcher.py` :
  - Nouvelle constante `EXIT_INACTIVITE = 42` — code de sortie de
    l'auto-extinction pour inactivité, désormais `sys.exit(EXIT_INACTIVITE)`
    au lieu de `sys.exit(0)`.
  - `main()` publie désormais son propre fichier PID
    (`logs/watcher-<nom>.pid`) dès son démarrage, quel que soit son mode de
    lancement (terminal, `systemctl`, ou bouton de l'interface) — jusqu'ici
    c'était uniquement `app/watchers.py::demarrer_watcher` (via
    `subprocess.Popen`) qui l'écrivait après coup, ce qui n'aurait plus
    fonctionné pour un watcher lancé directement par systemd. Toute la
    détection existante basée sur ce fichier (`watcher_actif`,
    `_watcher_actif`/`detecter_conflit_watcher`, `interrompre_linux`) reste
    inchangée. Nettoyage du fichier PID ajouté aussi sur `KeyboardInterrupt`
    (Ctrl+C manuel), par symétrie avec l'auto-extinction.
- `systemd/watcher@.service` : `Restart=always` → `Restart=on-failure`,
  ajout de `SuccessExitStatus=42`.
- `installer_services.sh` : la liste de projets codée en dur est remplacée
  par une lecture dynamique de `configs/*.conf` valides via
  `app.projets.lister_projets()` (même définition de « projet actif » que le
  reste de l'interface) ; mise à jour des commentaires d'en-tête (l'ancien
  avertissement de conflit avec le bouton « Lancer/Arrêter watcher » de
  l'interface ne s'applique plus, les deux mécanismes étant désormais
  unifiés).
- `app/watchers.py` :
  - `demarrer_watcher()` appelle `systemctl --user start|restart
    watcher@<projet>` au lieu de `subprocess.Popen` (avec un court sondage
    du fichier PID pour renvoyer le nouveau pid).
  - `arreter_watcher()` appelle `systemctl --user stop watcher@<projet>` au
    lieu d'un `os.kill(pid, SIGTERM)` direct.
  - `watcher_actif()`/`chemin_pid()` inchangés (toujours basés sur le
    fichier PID).
  - Imports `signal`/`sys` retirés (devenus inutiles) ainsi que la constante
    `DOSSIER_SCRIPT` (plus utilisée).
- `app/interruption.py` : nouvelle fonction
  `_neutraliser_relance_systemd()`, appelée par `interrompre_linux()` juste
  après confirmation de la mort de l'arbre de process. Sans elle, le SIGKILL
  existant du bouton « Interrompre cette issue » (#323) serait vu par
  systemd comme un crash et le watcher serait relancé après 10 s par
  `Restart=on-failure` — contredisant le contrat de #323 (« jamais de
  relance automatique après une interruption manuelle »). Appelle
  `systemctl --user stop watcher@<projet>`, un arrêt délibéré du point de
  vue de systemd qui n'active jamais la politique `Restart=`. Best-effort :
  ne fait jamais échouer l'interruption elle-même (watcher lancé hors
  systemd, ou service non installé pour ce projet).
- `BRIDGE_AGENT_DOC.md` : remplacement du bloc « Historique : services
  systemd (abandonnés) » par la documentation du mécanisme actif
  (démarrage/relance, installation dynamique, unification avec les boutons
  de l'interface, interaction avec le bouton Interrompre, absence de sudo
  nécessaire) ; mise à jour de la section « Cycle de vie des watchers » pour
  mentionner systemd et le nouveau code de sortie `EXIT_INACTIVITE`.

Hors périmètre (conforme à l'intention de l'issue) : `new_issue.py` reste
lancé manuellement (pas de service systemd dédié) ; le watcher spool
(`scripts/watcher_issues_inbox.py`) garde son propre mécanisme de
durée/échéance.

Vérification : suite de tests existante (20 fichiers `tests/test_*.py`,
dont `test_auto_extinction_217.py` qui pilote le vrai `watcher.main()`)
toujours verte après ces changements ; `py_compile` OK sur tous les fichiers
Python modifiés. L'installation réelle des services (`installer_services.sh`,
`systemctl --user enable --now`) et la vérification post-redémarrage du
ThinkPad restent à faire par Alain — hors de portée d'une session CCL en
worktree isolé (nécessite d'agir sur `~/.config/systemd/user/` et
`loginctl enable-linger` de la session réelle, hors du périmètre de ce
worktree).

## 23 septembre 2026 — issue #595

Modal « Supprimer le projet » (zone dangereuse) : le bouton « Supprimer
définitivement » restait visuellement identique (rouge plein) même une
fois désactivé (`disabled`), car aucune règle CSS ne stylait cet état —
un utilisateur pouvait croire le bouton actif alors qu'un clic ne
déclenchait rien (comportement natif HTML silencieux, sans retour
visuel). La logique de grisage elle-même (`spMajBoutonEtat()` dans
`static/js/app.js`, issue #587) était déjà correcte : bouton désactivé
à l'ouverture, tant que les 3 cases ne sont pas cochées et que le nom
retapé ne correspond pas exactement au projet ciblé. Ajout de
`button.danger-plein:disabled{...}` dans `static/css/style.css` (fond
gris `#ccc`, texte `#888`, curseur `not-allowed`) pour que l'état
désactivé soit visible, symétriquement à `button.primaire:disabled`
déjà existant. Vérifié en conditions réelles (Playwright + Chromium
headless, projet de test temporaire hors dépôt) : gris tant que le nom
est incorrect, rouge dès la correspondance exacte.

## 23 septembre 2026 — issue #594

Onglet Configuration → Zone dangereuse : ajout d'un rappel « **Projet ciblé : <nom>** » (gras, rouge) juste au-dessus du bouton « 🗑 Supprimer ce projet… » (issue #594) — mis à jour dynamiquement, sans rechargement de page, à chaque changement de la combobox `#projet` en haut de page (`appliquerAccentProjet()` dans `static/js/app.js`, appelée par `onProjetChange()`), pour qu'un utilisateur ne regardant que le bas de la page sache sans ambiguïté quel projet sera supprimé avant de cliquer.

## 23 septembre 2026 — issue #593

Retrait de `testrelectureprojet` de `BRIDGE_AGENT_DOC.md` : projet test
supprimé, qui avait été ajouté manuellement (hors création standard
Bridge_Agent) pour apparaître dans Relecture_Bridge.

- `BRIDGE_AGENT_DOC.md` :
  - Ligne 85 (tableau §2, projets actifs) : suppression de la ligne
    `| testrelectureprojet | AlainDelree/Testrelectureprojet | ~/Testrelectureprojet | (conf local) |`.
  - Ligne 723 (tableau §7, REP_TRAVAIL par projet) : suppression de la ligne
    `| testrelectureprojet | /home/alain/Testrelectureprojet |`.
  - Vérifié : `grep -i "testrelectureprojet" BRIDGE_AGENT_DOC.md` ne retourne
    plus aucun résultat.

## 23 septembre 2026 — issue #592

Exclusion des RELANCES de la mise à jour de `duree_typique` (biais de mesure
EWMA, §19/§21). Quand une issue est relancée via le champ RELANCE (#516)
après un échec `needs-human` ou un timeout, `watcher.py` peut retrouver dans
le worktree du travail déjà effectué par la tentative précédente : la durée
mesurée (nouvelle ACK → clôture) est alors artificiellement courte et tirait
`duree_typique` vers le bas. Quantifié sur GitHub : 7 RELANCES sur 192 issues
`done` depuis le 2026-09-02 (3.6%).

- `watcher.py` :
  - Nouveau marqueur `MARQUEUR_ECHEC_TENTATIVES = "❌ Échec après"` (préfixe
    du message d'échec définitif déjà posté par le watcher avant
    `needs-human`, ~L4453).
  - Nouvelles fonctions `_lister_commentaires(numero)` (lecture best-effort
    des commentaires actuels de l'issue via `gh issue view --json comments`)
    et `_issue_est_relance(commentaires)` (True si `MARQUEUR_ECHEC_TENTATIVES`
    est déjà présent dans cet historique).
  - `_traiter_issue_synchrone` : détection `est_relance` juste AVANT le
    commentaire d'ACK (donc sur l'historique strictement antérieur à cette
    exécution) — un seul appel réseau, réutilisé côté succès plus bas.
  - `_maj_combinaison_timeout` / `maj_calibration_timeout` : nouveau
    paramètre `relance` (défaut `False`). Sur succès avec `relance=True`,
    la durée est traitée comme CENSURÉE, même principe que le timeout :
    aucune mise à jour de `duree_typique`/`variabilite`/succès rapides/
    backoff, ni de F_reseau/F_local (même biais de durée artificiellement
    courte) — seul un compteur `n_relances_exclues` (par combinaison) est
    incrémenté à titre de traçabilité.

- `tests/test_relance_exclusion_calibration_592.py` (nouveau) : 4 scénarios
  — détection RELANCE sur l'historique des commentaires (positif/négatif/
  historique vide), exclusion de `duree_typique`/`variabilite` avec
  incrément de `n_relances_exclues`, non-régression d'un succès normal
  (mise à jour comme avant #592), et `maj_calibration_timeout` bout en bout
  (amorce → RELANCE inchangée → issue normale de nouveau mise à jour).
  Suite de tests existante (20 fichiers) toujours verte.

## 23 septembre 2026 — issue #590

Backoff EWMA irrécupérable (§19) — ancrage de la condition « succès rapide »
sur `duree_typique` au lieu du `TIMEOUT` courant, et plafond de sécurité sur
`TIMEOUT_suggéré`. Constaté sur `relecture_bridge|normal|write|normal` :
`multiplicateur_backoff` monté à 7481.83 (→ `TIMEOUT_suggéré` ~2 062 012s,
~23 jours) et `relecture_bridge|normal|write|lourd` à 7.59 — dans les deux
cas le backoff ne pouvait plus jamais redescendre seul.

- `watcher.py` :
  - Cause : `_maj_combinaison_timeout` comparait `duree_s` à
    `SEUIL_SUCCES_RAPIDE × timeout_courant`, où `timeout_courant` est le
    `TIMEOUT` de l'en-tête de CETTE exécution — une valeur décorrélée du
    comportement réel de la combinaison (peut rester basse d'une issue à
    l'autre, ex. constaté « 300s, TIMEOUT plancher, trop court »). Un succès
    pourtant nettement plus rapide que la normale pouvait ainsi ne jamais
    franchir la barre, bloquant `succes_rapides_consecutifs` à 0 et le
    backoff dans son état emballé — sans recours (verrou permanent).
  - Correctif de fond : la comparaison est désormais ancrée sur
    `duree_typique + K_VARIABILITE × variabilite` — le repère historique
    EWMA propre à la combinaison — totalement indépendant du `TIMEOUT` de
    l'exécution en cours et donc du `multiplicateur_backoff` lui-même.
    Suppression du paramètre `timeout_courant`, devenu inutile, de
    `_maj_combinaison_timeout` et `maj_calibration_timeout` (et des deux
    points d'appel dans `_traiter_issue_synchrone`).
  - Filet de sécurité : nouvelle constante `TIMEOUT_SUGGERE_PLAFOND = 3600`
    (1h — largement au-dessus des complexités `lourd` observées à ce jour)
    et nouvelle fonction `_timeout_suggere_borne()` (formule §19.2 + bornage
    plancher/plafond), utilisée par `maj_calibration_timeout` et
    `lire_timeout_suggere` — protège contre tout emballement futur non
    anticipé du backoff, même après le correctif d'ancrage ci-dessus.
  - Correction manuelle des deux valeurs anormales dans
    `logs/etat_timeout.json` demandée par l'issue : **non appliquée** —
    ce fichier (gitignoré, état d'exécution) vit dans le clone de travail
    réel (`/home/alain/Bridge_Agent`), hors du périmètre de ce worktree
    isolé (`/home/alain/bridge_agent-issue590`). Alain doit remettre
    manuellement `multiplicateur_backoff` à `1.0` pour les combinaisons
    `relecture_bridge|normal|write|normal` (7481.83) et
    `relecture_bridge|normal|write|lourd` (7.59) dans
    `/home/alain/Bridge_Agent/logs/etat_timeout.json` après déploiement
    de ce fix.

- `tests/test_backoff_ancrage_duree_typique_590.py` (nouveau) : 4 scénarios
  — succès rapide détecté malgré un backoff emballé (cas réel), 3 succès
  rapides consécutifs réinitialisant le backoff, succès non notablement
  rapide remettant le compteur à zéro sans y toucher, et plafonnement de
  `TIMEOUT_suggéré` (`_timeout_suggere_borne`). Suite de tests existante
  (18 fichiers) toujours verte.

## 22 septembre 2026 — issue #589

Repli silencieux sur REP_TRAVAIL quand la création du worktree échoue
(chemin ou branche déjà pris) — rendu visible sans changer le comportement
du repli lui-même, qui reste volontaire et propre (cf. BRIDGE_AGENT_DOC.md).
Scénario déclencheur : une tentative interrompue (TIMEOUT trop court)
laisse un worktree orphelin ; la relance échoue à recréer un worktree au
même chemin/branche et retombe sur REP_TRAVAIL sans aucun signal — découvert
seulement en tentant un nettoyage manuel plus tard.

- `watcher.py` :
  - `_creer_worktree` retourne désormais `(chemin, raison_deja_pris)` au lieu
    de `chemin` seul. `raison_deja_pris` n'est renseignée QUE quand l'échec
    est attribuable à un chemin ou une branche déjà pris (les deux
    vérifications sont faites AVANT l'appel à `git worktree add`, pas par
    reconnaissance de mots-clés dans le message d'erreur git — localisé,
    donc peu fiable) ; reste `None` pour une erreur git générique, afin de ne
    pas présumer une cause qu'on n'a pas vérifiée. Nouvelle vérification de
    la branche (`git rev-parse --verify`) en plus de celle déjà existante sur
    le chemin. Dans les deux cas « déjà pris », un `log.warning` explicite
    mentionne désormais le chemin concerné et la cause précise, distinct du
    `log.warning` générique pour les autres échecs.
  - `_traiter_issue_synchrone` : nouveau paramètre `echec_worktree_deja_pris`
    — quand renseigné, un avertissement (`avertissement_worktree_deja_pris`)
    est injecté en tête du compte-rendu de clôture posté sur l'issue (succès
    comme échec final), avant le corps du résultat, sur le même principe que
    `avertissement_conflit` déjà en place.
  - `traiter_issue` : les deux points d'appel de `_creer_worktree` (chemin
    parallélisé et chemin séquentiel MAX_WRITE_PARALLELE<=1, issue #577)
    transmettent désormais `raison_deja_pris` à `_traiter_issue_synchrone`.
- `tests/test_worktree_parallelisation_337.py` :
  - `scenario_creer_worktree_succes_et_repli` : adapté à la nouvelle
    signature tuple, vérifie que `raison` est `None` au succès et renseignée
    (avec le chemin) pour le repli « chemin déjà pris ».
  - `scenario_max_1_repli_si_worktree_echoue` : étendu pour vérifier les deux
    volets de #589 — un `log.warning` explicite (chemin + « déjà pris »),
    capturé via le nouvel utilitaire `_capturer_logs_watcher`, et la présence
    de la mention dans le compte-rendu réellement posté sur l'issue (corps
    capturé par le faux `gh` de test, `corps-<numero>.md`).

Hors scope, comme demandé : aucune suppression automatique du worktree
orphelin — le nettoyage reste toujours manuel (`git worktree remove` jamais
appelé automatiquement), y compris dans ce chemin.

Vérifié : `py_compile` sur les deux fichiers touchés, les 9 scénarios de
`tests/test_worktree_parallelisation_337.py` passent (dont les deux
nouvelles assertions #589), ainsi que l'intégralité des 16 autres suites de
tests existantes (aucune régression).

## 22 septembre 2026 — issue #588

Correction de `_debut_traitement()` (`app/issues.py`) : affichait à tort
« ⏳ en file » avec une estimation fraîche pour une issue qui venait
d'épuiser ses 3 tentatives, pendant la courte fenêtre où `watcher.py` a déjà
posté le commentaire « Échec après N tentatives » mais pas encore le label
`needs-human` (deux appels `gh` distincts, non atomiques). Le marqueur
« Échec après N tentatives » ne réinitialise plus systématiquement `debut` à
`None` : il ne le fait que s'il n'est **pas** récent (nouvelle constante
`FENETRE_TRANSITOIRE_ECHEC_S = 120`, marge couvrant le pire cas des deux
appels `gh` à 30s de timeout chacun). En-dessous du seuil, `debut` reste
l'ACK du cycle qui vient réellement de tourner plusieurs minutes. Au-dessus,
comportement #525 inchangé (issue relancée après retrait manuel de
`needs-human`, ACK du cycle précédent dans l'historique → « en file »
préservé jusqu'à une nouvelle ACK).

- `app/issues.py` : ajout `FENETRE_TRANSITOIRE_ECHEC_S`, `_echec_recent()`,
  condition ajoutée dans `_debut_traitement()`, docstring mise à jour.
- `tests/test_fenetre_transitoire_echec_588.py` (nouveau) : 6 scénarios
  purs (aucun accès réseau) — échec récent → `debut` conservé, échec juste
  sous le seuil, non-régression #525 (échec ancien → « en file », nouvelle
  ACK après relance fait foi), aucun commentaire, ACK simple sans échec.

## 22 septembre 2026 — issue #587

Flux de suppression de projet — côté CCL/local, symétrique à la création
(diagnostic #580). Décommissionner un projet exigeait jusqu'ici une
chirurgie manuelle sur au moins 8 cibles, avec un risque réel d'oubli ; cette
issue couvre volontairement les 4 cibles côté CCL/local, le dépôt GitHub et
le côté CCW faisant l'objet d'issues séparées.

- `supprimer_projet.py` (nouveau) : orchestrateur `supprimer_projet(nom,
  dry_run)` symétrique à `nouveau_projet.creer_projet()`, qui démonte dans un
  ordre sûr — répertoire de travail (contenu + dépôt git local, une seule
  opération de disque puisque `.git` y vit) puis `configs/<nom>.conf` puis
  régénération immédiate de §2/§7 de `BRIDGE_AGENT_DOC.md`
  (`regenerer_tableaux_projets.regenerer()`) — en s'arrêtant dès qu'une étape
  échoue plutôt que de continuer aveuglément. Ordre volontairement inverse de
  la création : le `.conf` n'est retiré qu'une fois le répertoire de travail
  effectivement supprimé, pour ne jamais laisser un répertoire orphelin sans
  trace de son existence en cas d'échec. Mode à blanc
  (`previsualiser_suppression`/`--dry-run`) : aucune écriture disque ni sur
  la doc. CLI interactif avec confirmation par saisie du nom (`--oui` pour
  l'usage scripté).
- `app/supprimer_projet.py` (nouveau) : réutilise ce script sans le
  dupliquer. `GET /supprimer-projet/verifier/<nom_projet>` (dry-run, 404 si
  absent) et `POST /supprimer-projet` (suppression réelle), toutes deux
  protégées par `login_requis`. La route POST revérifie indépendamment côté
  serveur que le champ `confirmation` reproduit exactement le nom du
  projet — la checklist côté interface, elle, peut être contournée par un
  appel direct.
- `app/__init__.py` : enregistrement des deux routes.
- `templates/index.html` : zone dangereuse dans l'onglet Configuration
  (bouton « 🗑 Supprimer ce projet… ») et modal de confirmation — aperçu
  chargé automatiquement, 3 cases à cocher (une par cible) + nom du projet
  retapé à l'identique, double garde-fou avant que le bouton de suppression
  définitive ne s'active.
- `static/js/app.js` : `ouvrirSupprimerProjet`/`fermerSupprimerProjet`,
  `spChargerApercu` (peuple l'aperçu depuis la route GET), `spMajBoutonEtat`
  (active le bouton seulement si les 3 cases + le nom retapé sont corrects),
  `soumettreSupprimerProjet` (appelle la route POST, affiche le compte-rendu
  par étape), `retirerProjetDuSelecteur` (symétrique de
  `ajouterProjetAuSelecteur`, retire l'option du sélecteur global au succès).
- `regenerer_tableaux_projets.py` : docstring mise à jour — elle admettait
  explicitement l'absence de flux de suppression automatisé (citée dans le
  diagnostic #580) ; documente désormais que `supprimer_projet.py` déclenche
  lui aussi la régénération, au même titre que `nouveau_projet.py`.
- `BRIDGE_AGENT_DOC.md` : nouvelle sous-section « Suppression de projet,
  côté CCL/local (issue #587) », symétrique de celle décrivant déjà la
  création (juste avant), plus la commande CLI dans §13.
- `tests/test_supprimer_projet_587.py` (nouveau) : aperçu (projet absent,
  projet présent — aucune écriture), dry-run (ne touche à rien), succès réel
  (ordre des étapes, `.conf` + répertoire supprimés, doc régénérée une seule
  fois), arrêt propre si la suppression du répertoire échoue (`.conf`
  conservé, doc jamais régénérée), nom vide, et les deux routes Flask
  (dry-run 404, confirmation incorrecte → 400, succès → 200).

Explicitement hors scope (décision actée dans le diagnostic #580) :
suppression du dépôt GitHub et de ses labels (geste manuel volontaire), et
tout le côté CCW (clone Windows, `configs\<nom>-ccw.conf`, service NSSM,
tokens, entrée `$Projets`, ligne `REINSTALLATION_CCW.md` §7).

Vérifié : `py_compile` sur tous les fichiers touchés, `create_app()` démarre
sans erreur et expose bien les deux nouvelles routes, les 9 scénarios de
`tests/test_supprimer_projet_587.py` passent, ainsi que l'intégralité des 16
autres suites de tests existantes (aucune régression). Non vérifié dans ce
worktree (pas d'accès réseau/GitHub authentifié) : test bout en bout réel
sur un projet jetable — demandé en vérification de l'issue, à faire par
Alain avant de considérer le flux entièrement validé.

## 22 septembre 2026 — issue #585

Retrait du diagnostic temporaire #157 (`app/diag_heartbeat.py`), balisé
« à retirer » depuis son ajout le 19 juillet mais resté câblé plus de
deux mois après validation du correctif heartbeat/SSE. Procédure de
retrait suivie telle qu'écrite dans le module lui-même : suppression du
fichier (88 lignes), de l'import et des quatre appels `diag_heartbeat.log_*()`
dans `app/cycle_vie.py` (heartbeat, connexion/déconnexion SSE, arrêt par
`surveiller_heartbeat`), de l'import et de l'enregistrement de route dans
`app/__init__.py`, et du bloc `console.log`/`fetch('/diag-visibilite')`
dans `demarrerCycleVie()` (`static/js/app.js`) — en conservant
`envoyerHeartbeat()` sur `visibilitychange`, qui fait partie du correctif
et non du diagnostic. Point de sécurité traité au passage : la route
`/diag-visibilite` disparaît avec le reste, ce qui élimine une route POST
qui n'était pas protégée par `login_requis`, contrairement au reste de
l'application. `logs/heartbeat_diag.log` n'existait pas dans ce
worktree, rien à supprimer sur ce point. Vérifié : `py_compile` OK,
`create_app()` démarre sans erreur, `/diag-visibilite` répond 404, aucune
référence résiduelle (`grep` sur `diag_heartbeat`/`diag-visibilite`/`DIAG
#157`), suite de tests existante verte (un seul échec,
`test_init_git_local_258.py`, pré-existant et sans rapport — dépendant du
réseau, échoue identiquement avant ce commit).

## 22 septembre 2026 — issue #586

Fix `tests/test_init_git_local_258.py`, périmé et non collecté par pytest
(diagnostic #579). Deux causes cumulées, une seule anticipée par le
diagnostic :

1. `scenario_deja_git` comparait le résultat de `initialiser_git()` par
   égalité stricte de dictionnaire à une valeur écrite avant le fix #530
   (filet de sécurité email noreply GitHub), donc sans la clé
   `email_corrige` que la fonction renvoie désormais toujours. Dictionnaire
   attendu mis à jour avec `"email_corrige": None`.
2. Non anticipé par #579 : `scenario_contenu_preexistant_pas_de_push`
   vérifiait `"public" in res["detail"]`, texte retiré du message `detail`
   de `nouveau_projet.py` par le fix #528 (choix public/privé du dépôt à la
   création) — un dépôt n'est plus systématiquement public. Assertion
   corrigée pour ne plus exiger ce mot, seule la mention « non relu »
   restant garantie et pertinente.

Par ailleurs, aucune fonction du fichier n'était préfixée `test_` : un
`pytest tests/` classique ne testait donc rien de ce fichier, l'échec ne se
manifestant qu'en exécution directe
(`python3 tests/test_init_git_local_258.py`). Les 5 fonctions
`scenario_*` renommées en `test_*` (et leurs références dans `main()`)
pour que pytest les collecte réellement.

Vérifié : les 5 scénarios passent en exécution directe (code retour 0) et
via `pytest tests/test_init_git_local_258.py` (5 passed). Seul le fichier
de test a été modifié, aucune logique de production touchée.

## 19 septembre 2026 — issue #575

Incident réel en mode `--externe` sur mobile : le bouton « Déconnexion »
se trouve pile sous le doigt quand on veut fermer le panneau
Infrastructure sur petit écran — clic accidentel, déconnexion
immédiate, obligeant à retaper le mot de passe.

`templates/index.html` : le bouton « Déconnexion » demande désormais
confirmation (`confirm('Se déconnecter ?')`) avant de naviguer vers
`/logout` — annulable, sans action si refusée. Même pattern déjà en
place pour le bouton « Quitter » (fonction `quitter()`,
`static/js/*.js`). Aucun changement d'apparence, de disposition ni de
media query : uniquement l'`onclick` du bouton, identique sur desktop
et mobile.

# CHANGELOG-556 — entrées à fusionner dans CHANGELOG.md

## 15 septembre 2026 — issue #556 (2/3)

Traitement du champ d'en-tête `CREATION` dans `watcher.py` — bootstrap
automatique d'un service CCW dédié, suite de la conception validée en #554
et de la génération de la paire de clés RSA 3072 (#554 1/3) : ENTIÈREMENT
déterministe, n'invoque JAMAIS `claude` (décision #554 §2.5) — réutilise
directement les scripts PowerShell déjà testés (`ajouter_projet_ccw.ps1`
puis `finaliser_projet_ccw_auto.ps1 -FichierValeurs`, format vérifié par
lecture du script avant écriture du code, identique à celui déjà produit
par `app/ccw.py`).

`_traiter_issue_synchrone` détecte `| CREATION | oui |` tôt dans le
dispatch, AVANT tout ce qui touche au pipeline `lancer_claude`. Convention
de 6 champs d'en-tête proposée et documentée (`CREATION`,
`CREATION_NOM_PROJET`, `CREATION_DEPOT`, `CREATION_TOPIC_NTFY`,
`CREATION_GH_TOKEN`, `CREATION_OAUTH_TOKEN`) : les deux tokens transitent
chiffrés individuellement (RSA/OAEP-SHA256 via `openssl pkeyutl -encrypt`,
clé publique de bootstrap) puis encodés en base64 sur une seule ligne.
`_extraire_champ_entete` compare le nom de champ EXACTEMENT (pas une
sous-chaîne comme les extracteurs existants SOUS_DOSSIER/REPO_CIBLE) : évite
la collision entre `CREATION` et son propre préfixe partagé avec
`CREATION_NOM_PROJET`/etc.

Résolution robuste du chemin `openssl` (`_resoudre_openssl`, point
d'attention hérité de #557 puisque #558 n'était pas encore mergé au moment
de cette tâche) : PATH → installation manuelle Windows
(`C:\Program Files\OpenSSL-Win64\bin\openssl.exe`, pas sur le PATH par
défaut sur CCW) → repli `usr\bin` de Git pour Windows — dupliqué en Python
plutôt que réutilisé depuis `Resoudre-OpenSSL` côté PowerShell
(`provisionner.ps1`, #554) : pas de dot-sourcing PowerShell depuis Python,
et un simple calcul de chemin ne justifie pas d'exécuter un script externe.

Retrait immédiat des deux tokens chiffrés du corps GitHub (`gh issue edit
--body-file`, remplacés par `<retiré après application>`) DÈS que les
valeurs sont en mémoire — avant même la tentative de déchiffrement — pour
limiter le temps d'exposition résiduel (§2.4 de #554). Fichier de valeurs
temporaire supprimé en deux lignes de défense (le `finally` PowerShell déjà
en place côté `finaliser_projet_ccw_auto.ps1`, PUIS un nettoyage Python en
repli). Compte-rendu + fermeture si succès (codes 0/2), `needs-human` + log
complet en commentaire si échec — un champ manquant est traité comme une
erreur de configuration définitive (aucun script PowerShell ni
déchiffrement tenté).

Testé sans vraie issue GitHub ni machine CCW réelle (sur le modèle du test
`SOUS_DOSSIER` de #550) : `tests/test_creation_bootstrap_ccw_556.py`, 15
scénarios — extraction/détection, non-collision `CREATION`/
`CREATION_NOM_PROJET`, retrait des tokens, résolution `openssl` (3 replis),
chiffrement/déchiffrement RÉEL via un openssl local (RSA 3072 généré à la
volée), chemin complet succès/champ manquant/dry-run (faux `gh` et faux
`powershell` sur le `PATH`), et un scénario bout en bout via `traiter_issue`
vérifiant qu'un faux `claude` marqueur n'est jamais touché.

Documenté en détail dans `BRIDGE_AGENT_DOC.md` §16.6 (nouvelle
sous-section), à l'intention du formulaire web à venir (3/3, #559 ou
suivant — non traité ici, `new_issue.py` non touché).

## 22 septembre 2026 — issue #584

Verrou anti-collision `REP_TRAVAIL` (`watcher.py`, #189/#322) : filet de
sécurité complémentaire contre un verrou orphelin. Incident réel : issue
#583 (canal unifié for-windows, mode_write) bloquée 48 minutes
(12:48–13:36), chaque cycle du watcher affichant « un autre traitement
détient déjà le verrou sur C:\CCW_Share ». Hypothèse posée dans #584 (un
chemin de sortie anticipée de `_traiter_issue_synchrone` — refus précoce,
avant tout travail réel — ne relâcherait pas le verrou faute de
`try`/`finally` symétrique) vérifiée par lecture de code et **INFIRMÉE** :
le `try` qui enveloppe tout le corps de `_traiter_issue_synchrone`, verrou
compris, existe depuis l'introduction même du mécanisme (issue #189,
2026-07-20, commit `6a91a0a`) et son `finally` (`liberer_verrou`) couvre
déjà tous les chemins de sortie ajoutés depuis — succès, échec après
tentative(s), abandon définitif (`needs-human`), et refus précoce (claude
répond ❌ en quelques secondes, exit code 0, avant tout travail réel).
Confirmé par deux nouveaux scénarios de `tests/test_verrou_refus_precoce_584.py`
(`scenario_refus_precoce_libere_verrou`,
`scenario_echec_rapide_sans_travail_libere_verrou`) : appel direct de
`_traiter_issue_synchrone` avec un faux `claude` répondant respectivement
❌ en exit 0 et en échec non-zéro immédiat — verrou absent après coup dans
les deux cas.

Cause réelle la plus probable de l'incident, en revanche : un watcher tué
BRUTALEMENT (crash, `kill -9`, redémarrage de service — cohérent avec
« erreur de conception de l'issue elle-même, corrigée après coup côté
Alain » évoqué dans #584) pendant qu'il détenait le verrou. Aucun
`try`/`finally` Python ne survit à un `kill -9`, sur aucune plateforme :
c'est le rôle du filet de sécurité existant par péremption par ancienneté
(issue #322, `acquerir_verrou`) — mais celui-ci se calcule à partir de
`max_essais × (TIMEOUT_projet + pause) + marge`, potentiellement des
dizaines de minutes pour un projet à `TIMEOUT` élevé (1800 s dans #583),
ce qui correspond à l'ordre de grandeur du blocage observé.

Nouveau filet complémentaire, plus rapide, dans `acquerir_verrou`
(`watcher.py`) : ajout de `_pid_vivant(pid)` (sonde cross-plateforme,
lecture seule — POSIX `os.kill(pid, 0)`, Windows `OpenProcess` avec le
droit minimal `PROCESS_QUERY_LIMITED_INFORMATION`, même pattern déjà en
place pour l'objet Job Windows de #249) et `_lire_pid_verrou(verrou)`
(lit le champ `pid=<n>` du fichier verrou — le PID du **watcher**, écrit
inconditionnellement dès la création du verrou, à ne pas confondre avec
`claude_pgid=<n>` qui n'arrive qu'après le lancement de claude, #322). Si
la péremption par ancienneté n'a pas encore tranché ET que le PID
propriétaire est confirmé mort, le verrou est repris **immédiatement**
(nouveau log dédié « Verrou orphelin sur ... — repris immédiatement »),
sans attendre l'écoulement de la péremption par ancienneté — corrige
directement le délai de #583. Asymétrie volontaire documentée sur
`_pid_vivant` : un PID introuvable est un fait certain (aucun faux négatif
possible), mais un PID trouvé vivant ne prouve pas qu'il s'agit encore du
même process (réutilisation de PID par l'OS, notamment après un temps long
ou un reboot) — dans le doute (PID vivant, sonde en échec, plateforme non
gérée), la fonction répond `True` et l'appelant retombe sur le critère
d'ancienneté existant : ce filet ne peut donc jamais rendre un verrou
encore valide plus fragile qu'avant #584. Le nettoyage de l'éventuel
`claude` orphelin (pgid stocké, POSIX uniquement, #322) reste appliqué à
l'identique dans les deux cas de reprise. Deux scénarios supplémentaires
dans `tests/test_verrou_refus_precoce_584.py`
(`scenario_pid_mort_repris_immediatement`,
`scenario_pid_vivant_reste_bloque`) : verrou frais (donc très loin de la
péremption par ancienneté) avec PID propriétaire confirmé mort → repris
immédiatement ; même verrou frais avec PID propriétaire vivant (le
process du test lui-même) → reste bloquant, sans régression.

Documentation : section « Parallélisation mode_write via git worktrees »
de `BRIDGE_AGENT_DOC.md` complétée par deux nouvelles puces (libération
garantie du verrou quel que soit le chemin de sortie ; filet de sécurité à
deux niveaux) ; §16.4 « Interrompre une issue CCW coincée » (procédure
manuelle historique pour ce même symptôme, issue #287) mis à jour pour
signaler l'atténuation automatique apportée par #584, la procédure
manuelle restant le repli si la sonde PID ne peut pas conclure (PID
recyclé par l'OS). Pied de page de `BRIDGE_AGENT_DOC.md` glissé d'un cran
en conséquence (§10) — l'entrée #540 (couleur d'accent des projets) en
sort, elle reste disponible ci-dessous.

## 20 septembre 2026 — issue #577

Section « Parallélisation mode_write via git worktrees » (#337) de
`BRIDGE_AGENT_DOC.md` : isolation de `REP_TRAVAIL` vis-à-vis d'Alain
désormais **systématique**, y compris à `MAX_WRITE_PARALLELE = 1` (issue
#577). Incident réel ayant motivé ce changement, sur `relecture_bridge`
(`MAX_WRITE_PARALLELE=1`) : Alain a fait un `git commit`/`git stash` manuel
dans `REP_TRAVAIL` pendant qu'une issue `mode_write` y travaillait
directement (comportement d'avant #577, gaté par `CFG.max_write_parallele
> 1`) — collision directe, une modification manuelle temporairement
effacée, récupérée de justesse depuis un commit orphelin. `watcher.py`
(`traiter_issue`) découple désormais explicitement les deux besoins que le
couplage précédent confondait : `MAX_WRITE_PARALLELE` continue de piloter
uniquement la parallélisation **entre** tâches CCL (thread principal vs
threads dédiés, utilité réelle seulement `> 1`) ; l'isolation via worktree,
elle, s'applique dans tous les cas. À `MAX_WRITE_PARALLELE ≤ 1`,
`_creer_worktree(numero)` est maintenant appelée avant
`_traiter_issue_synchrone`, celle-ci restant appelée directement (aucun
`threading.Thread`, comportement séquentiel historique préservé) — mais
désormais avec `chemin_worktree` renseigné au lieu de `None`. Repli propre
sur `REP_TRAVAIL` si la création du worktree échoue (chemin/branche déjà
pris), comme pour le cas parallélisé. Nettoyage/traçabilité déjà en place
(alerte d'accumulation de worktrees #432, comptage `MAX_WRITE_PARALLELE`
via `needs-human` #576) inchangés — ces worktrees « solo » sont
indiscernables des worktrees créés en parallélisation, aucun traitement
spécial requis. `tests/test_worktree_parallelisation_337.py` étendu : la
scénario de non-régression à `MAX_WRITE_PARALLELE=1` devient un scénario
d'isolation (worktree utilisé, `REP_TRAVAIL` inchangé — même HEAD, aucun
fichier ajouté, aucun thread créé) ; nouveau scénario couvrant le repli sur
`REP_TRAVAIL` si la création du worktree échoue à `MAX_WRITE_PARALLELE=1`.

## 18 septembre 2026 — issue #571

§2 « Projets actifs » et §7 « Périmètre par projet » de
`BRIDGE_AGENT_DOC.md` n'étaient maintenus qu'à la main, indépendamment des
`configs/*.conf` réellement lus par `watcher.py` — source de vérité
fonctionnelle (`NOM`/`DEPOT`/`REP_TRAVAIL`/`PERIMETRE`). Toute divergence
(création, suppression, renommage d'un projet oublié dans un des
tableaux) pouvait se reproduire, et s'était reproduite : `testccwprojet`
(projet de test entièrement nettoyé — dépôt GitHub, service CCW, `.conf`
local, entrées de `reinstaller_projets_ccw.ps1`) restait visible dans ces
deux tableaux.

Nouveau script `regenerer_tableaux_projets.py` (racine) : scanne
`configs/*.conf`, ignore les fichiers sans champ `NOM` (ex.
`configs/ccw_ssh.conf`, config technique de connexion SSH, pas un projet
watcher), et remplace intégralement le contenu des deux tableaux entre
des marqueurs HTML dédiés (`<!-- DEBUT:TABLEAU_PROJETS_ACTIFS -->`/
`<!-- DEBUT:TABLEAU_PERIMETRE_PROJETS -->` + `FIN:` correspondants,
ajoutés dans `BRIDGE_AGENT_DOC.md`) — jamais d'édition manuelle. Projets
triés par ordre alphabétique du `NOM` (l'ordre chronologique d'ajout
historique n'est pas reconstituable depuis le disque) ; effet de bord
assumé, la casse affichée suit désormais celle du `NOM` du `.conf`
(`apiselect`, en minuscules, remplace l'ancien `ApiSelect` du tableau —
qui ne correspondait à aucun champ réel).

`nouveau_projet.py::mettre_a_jour_doc()` (route Flask) et `etape_doc()`
(CLI interactif) dupliquaient chacun leur propre logique d'insertion de
ligne (`_inserer_ligne_tableau`, `_afficher_rep`) — les deux délèguent
maintenant à `regenerer_tableaux_projets.regenerer()`, un seul mécanisme
écrit désormais dans ces tableaux ; helpers dupliqués supprimés, ainsi
que `MOIS_FR`/`from datetime import date`, devenus inutiles dans
`nouveau_projet.py`. Le script reste aussi utilisable seul et à la
demande (`python3 regenerer_tableaux_projets.py`, sans argument) — la
commande à relancer après un nettoyage manuel de projet (pas de flux de
suppression automatisé aujourd'hui) pour resynchroniser la doc avec la
réalité du disque ; conséquence directe, testé en simulant un cycle
création/suppression d'un `.conf` de test, `testccwprojet` disparaît des
deux tableaux — de même que `relecture_bridge`, ajouté au commit
précédent (§2/§7) mais sans `configs/relecture_bridge.conf` présent sur
ce disque : ⚠️ à vérifier par Alain (projet réellement sans watcher
dédié, ou `.conf` restant à créer — CCL n'a pas le droit de créer/modifier
`configs/*.conf`).

Piège évité en cours de route (documenté en §10 de `BRIDGE_AGENT_DOC.md`,
déjà rencontré à l'issue #268) : le premier essai de mise à jour
automatique de la date de pied de page utilisait un `re.sub` sur le texte
entier du fichier, qui a corrompu l'exemple donné en §10
(`` *Dernière mise à jour : <date> — ...* ``) au lieu du vrai pied de
page en fin de fichier — corrigé en ne substituant que sur la ligne qui
**commence** par le marqueur (même garde-fou que l'ancien code de
`nouveau_projet.py`), avec test de non-régression manuel (relecture du
diff avant/après).

Tableau §7 de `provisioning/windows/REINSTALLATION_CCW.md` (étape 7,
recréation des services CCW dédiés) : choix documenté de le laisser **en
dehors** de ce mécanisme, pas appliqué silencieusement. Ce n'est pas la
même liste : un sous-ensemble des projets (ceux avec un service Windows
dédié), décision manuelle indépendante des `.conf` Linux, dont la source
de vérité déclarée reste déjà le tableau `$Projets` de
`reinstaller_projets_ccw.ps1` (issue #552) — note ajoutée dans
`REINSTALLATION_CCW.md` pour expliciter cette distinction plutôt que de
laisser deviner pourquoi ce tableau-ci échappe à la régénération.

## 14 septembre 2026 — issue #542

Mode lecture bloqué sur des commandes nécessitant une approbation
interactive impossible en session non-interactive (issue #542, constaté
sur CCW via l'issue de diagnostic #541 : `git fetch`/`git pull` et
`Add-Type -AssemblyName ...` refusés par Claude Code avec « This command
requires approval »). Confirmé dans le code (`lancer_claude`) :
`MODE_LECTURE` n'a jamais `--dangerously-skip-permissions` (réservé à
`mode_write`/`mode_scratch`) — reproduit à l'identique sur CCL avec le CLI
`claude` nu (`git -C ... fetch` bloqué avec le même message), donc bien un
bug partagé par les deux plateformes (`watcher.py` commun), pas spécifique
à CCW/Windows.

Plutôt que d'ajouter `--dangerously-skip-permissions` en lecture seule (ce
qui désarmerait toutes les protections de Claude Code sans le filet de
sécurité technique dont bénéficie la lecture active, empreinte
avant/après), ajout d'une allowlist fine via `--allowedTools` — mécanisme
natif de Claude Code qui débloque des commandes précises sans toucher au
reste : `git fetch` (jamais d'écriture dans l'arbre de travail),
`git pull --ff-only` (échoue plutôt que de merger — même opération que le
`git pull --ff-only` déjà fait automatiquement par le watcher en début de
cycle sur `REP_TRAVAIL`) et `Add-Type -AssemblyName` côté CCW (charge un
assembly .NET nommé, sans exécuter de code arbitraire —
`Add-Type -TypeDefinition`, qui compile du C#, reste volontairement hors
liste). Nouvelle constante `OUTILS_LECTURE_AUTORISES` dans `watcher.py`,
ajoutée à `cmd` uniquement en `MODE_LECTURE`. `git status`/`log`/`diff`/
`show` n'ont pas eu besoin d'y être ajoutés : déjà autorisés sans
approbation par l'heuristique interne de Claude Code (vérifié).

Vérification de bout en bout via `lancer_claude` en conditions réelles
(pas seulement `claude --help`) : `git fetch --dry-run` + `git pull
--ff-only` s'exécutent sans blocage en mode lecture (résultat renvoyé
normalement) ; une tentative d'écriture hors allowlist (redirection shell
vers un fichier du projet) reste bloquée par le sandbox, confirmant que le
périmètre d'écriture de la lecture seule n'a pas été élargi. Le cas
`Add-Type -AssemblyName` (spécifique PowerShell/CCW) n'a pas pu être
vérifié en conditions réelles faute d'environnement Windows disponible ici
— à confirmer côté CCW à l'occasion d'une prochaine tâche PowerShell en
lecture seule.

## 13 septembre 2026 — issue #540

Recyclage de la couleur des projets à l'arrêt (`ecole`, `ff_galerie`) vers
un gris neutre partagé, pour libérer leur ancienne couleur dédiée dans une
palette déjà contrainte (#539 : combinaison distance CIE76 + écart de
teinte Lab, seulement 5 couleurs libres avant cette issue).

Nouvelle constante `COULEUR_PROJET_INACTIF = "#767676"` définie à deux
endroits (`nouveau_projet.py` et `static/js/app.js`, pas de mécanisme de
partage de constantes entre les deux) : contraste texte noir 4,62:1
(`_contraste_avec_noir(0, 0, 46)`), au-dessus du seuil `SEUIL_CONTRASTE_NOIR`
(4,5:1) commun aux couleurs actives — sans contrainte de saturation 100% ni
de distance/teinte Lab, le but étant justement de signaler visuellement
l'absence d'identité propre.

Traitement volontairement ASYMÉTRIQUE entre les deux fichiers, vérifié
concrètement plutôt que supposé :
- `nouveau_projet.py` : `ecole` et `ff_galerie` **retirées** de
  `COULEURS_PROJETS_EXISTANTS` (pas remplacées par le gris). Ce dictionnaire
  est passé en `couleurs_a_eviter` à `generer_palette()`, qui compare les
  couleurs par angle de teinte Lab (`_teinte_lab`) ; un gris (saturation 0)
  a un a\*/b\* quasi nul, donc un angle `atan2(0,0)` dégénéré à 0°, qui
  entre en collision avec l'exclusion de teinte prévue pour les rouges et
  fait échouer l'assertion de fin de `generer_palette()` — reproduit
  concrètement en testant les deux variantes (retrait vs. remplacement par
  le gris) avant de choisir. Les retirer suffit et n'a pas cet effet de
  bord : `couleurs_disponibles()` passe de 5 à 6 couleurs proposées à un
  futur projet, confirmant que l'ancienne couleur dédiée est bien recyclée.
- `static/js/app.js` : `ecole` et `ff_galerie` restent des clés de
  `COULEURS_PROJET` (seule source de vérité pour l'affichage, y compris des
  projets à l'arrêt), simplement avec la valeur `COULEUR_PROJET_INACTIF` à
  la place de leur ancienne teinte dédiée.

Documentation : sous-section « Couleur d'accent des projets » de
`BRIDGE_AGENT_DOC.md` complétée d'une procédure de recyclage réutilisable
pour un futur projet mis à l'arrêt (retrait côté Python, remplacement de la
valeur côté JS, pourquoi ce n'est pas symétrique).
## 13 septembre 2026 — issue #539

Suite retour d'usage sur #535 : 3 paires de couleurs de projet restaient
visuellement trop proches malgré une distance CIE76 au-dessus du seuil de
garde de 15 posé en #535 — `alchess`/`rummikub`, `ecole`/`chesscoach`,
`actualise`/`gestionmail`.

**Diagnostic (point 1 de l'issue)** : les couleurs réellement en usage pour
`alchess`/`rummikub` et `ecole`/`chesscoach` ont une distance CIE76 de 56 et
52 — largement AU-DESSUS du seuil de 15, pas « de justesse » comme supposé.
La vraie cause : leur écart d'angle de teinte dans le plan Lab a\*/b\* n'est
que de 1,6° et 0,4° — ces couleurs ne diffèrent quasiment qu'en clarté/chroma,
pas en teinte. CIE76 (distance euclidienne L/a\*/b\*) traite cet écart comme
n'importe quel autre, alors que l'œil, sur une petite pastille, identifie
d'abord la teinte : deux nuances d'une même teinte se lisent comme UNE seule
couleur, pas deux. `actualise`/`gestionmail` n'a pas pu être mesurée sur la
couleur réelle (gestionmail est un projet créé après #535, sa couleur ne vit
que dans `configs/gestionmail.conf`, hors périmètre de ce worktree et de
toute façon jamais modifiable par CCL/CCW) — mais le même mécanisme est en
cause : `actualise` (ancienne valeur, teinte Lab ≈292°) se trouvait dans la
même zone bleu-violet que `ff_galerie` (285,5°), `gestionmail` (candidat le
plus proche de la palette de l'époque : `#9191FF`, ≈296°) et `chesscoach`
(318,3°).

**Correction (points 2 et 3)** : `nouveau_projet.py` — ajout d'un second seuil
de garde `SEUIL_ECART_TEINTE_MIN` (15°, écart minimal d'angle de teinte Lab
entre deux couleurs de la palette), complémentaire de `SEUIL_DISTANCE_MIN`
(remonté 15→20, défense en profondeur mais insuffisant seul ici : 56 et 52
sont déjà loin au-dessus). `generer_palette()` vérifie désormais les deux
seuils, par construction (filtrage des candidats) ET par assertion finale.
Correction ciblée de 4 couleurs seulement dans `COULEURS_PROJETS_EXISTANTS`
(les 7 autres restent inchangées, même esprit que la correction #534
ecole/ff_galerie) :
- `alchess` `#00FF00`→`#00D68F` (pas de champ COULEUR persisté en `.conf`,
  contrairement à `rummikub` → conservée)
- `ecole` `#DE85FF`→`#CC7400` (pas de champ COULEUR persisté, contrairement à
  `chesscoach` → conservée ; nouvelle teinte ambre/moutarde, clin d'œil à la
  couleur qu'ecole portait déjà entre #534 et #535)
- `actualise` `#086BFF`→`#009DD6` (seul levier disponible côté code puisque
  gestionmail — l'autre membre de la paire — n'est pas modifiable ; nouvelle
  teinte délibérément écartée de toute la zone bleu-violet 197°-320°)
- `bloc_score` `#FFB0AB`→`#FF8595` : 4e paire découverte en appliquant le
  nouveau seuil (non signalée dans l'issue) avec `bridge_agent` (écart de
  teinte 13,2°, sous le nouveau plancher de 15°) — `bridge_agent` non
  retouché, nouvelle teinte toujours rose/saumon pâle.

Toutes les paires (11 couleurs figées + palette régénérée) validées sans
violation par script (120 paires testées, contraste texte noir >= 4,5:1
conservé partout). `static/js/app.js` (`COULEURS_PROJET`) mis à jour en
synchro.

**Mécanisme de sélection pour les futurs projets (point 4)** :
`generer_palette()` accepte désormais un paramètre `couleurs_a_eviter`
(passé avec `COULEURS_PROJETS_EXISTANTS`) et l'utilise comme réservation
initiale de l'algorithme glouton — pas seulement en post-filtrage comme le
faisait déjà `couleurs_utilisees()`. Sans ce paramètre, la garantie de
distance/teinte ne portait que sur les couleurs générées ENTRE ELLES, jamais
sur les 11 couleurs gelées en dur : c'est exactement ce trou qui avait laissé
passer la collision `actualise`/`gestionmail` (gestionmail avait pris une
couleur de la palette, valide par rapport aux autres couleurs générées, mais
jamais vérifiée par rapport à `actualise`). Avec ce paramètre, toute couleur
encore proposée à un futur projet est garantie distincte de TOUS les projets
existants. Conséquence attendue : `NB_COULEURS_PALETTE` (30 demandées) ne
produit plus que 5 couleurs effectivement disponibles au-delà des 11
historiques (contre 40 avant #539) — la combinaison seuil de distance +
seuil de teinte limite mécaniquement le nombre de couleurs vraiment
distinctes sur le cercle chromatique ; à surveiller si de nombreux nouveaux
projets sont créés.

**Point d'attention laissé à Alain** : la couleur réelle de
`configs/gestionmail.conf` n'a pas pu être lue (hors périmètre du worktree
`/home/alain/bridge_agent-issue539`, et modification de `configs/*.conf`
interdite à CCL/CCW dans tous les cas) ni donc revérifiée contre la nouvelle
valeur d'`actualise`. À vérifier manuellement ; si elle s'avère encore trop
proche d'une des 11 couleurs figées (ou d'une future couleur de
`PALETTE_COULEURS`), seule une modification manuelle du `.conf` par Alain
peut la corriger.

## 11 septembre 2026 — issue #528

`creer_depot()` (`nouveau_projet.py`) n'était plus systématiquement `--public`
codé en dur : nouveau paramètre `public: bool = True` déterminant le flag
`gh repo create` (`--public`/`--private`), défaut cohérent avec le
comportement historique. Exposé dans les deux points d'entrée existants :
CLI (`etape_depot()`, question « Dépôt public (non = privé) » juste après la
confirmation de création) et formulaire web (case à cocher « Dépôt public »
dans `templates/index.html`, visible seulement quand le dépôt cible n'existe
pas encore, comme la case « Créer le dépôt » dont elle dépend) → transmis à
`app/nouveau_projet.py`/`creer_projet()` puis à `creer_depot()`. Aucune étape
ultérieure (`initialiser_git()`, clonage, remote, push) ne suppose un accès
public : tout passe par `gh`/`git` en HTTPS authentifié via `GH_TOKEN`
(`_url_https()`, §9), donc un dépôt privé fonctionne à l'identique côté
interface — seule condition, que ce token ait les permissions nécessaires
sur ce dépôt. Commentaires/messages qui présupposaient un dépôt public
(docstrings, messages CLI, encarts web) mis à jour en conséquence. §13 de la
doc complété.

## 7 septembre 2026 — issue #521

Traçabilité minimale sur `logs/historique_durees.json` et
`logs/etat_timeout.json`, pour diagnostiquer une future perte de données
comme celle du 7 septembre 2026 restée inexpliquée faute de preuve (fichiers
gitignorés, aucun historique git natif).
- Approche retenue (parmi les deux esquissées dans l'issue) : un journal
  séparé append-only, plutôt qu'une exception ciblée au `.gitignore` de
  `logs/` — `historique_durees.json` grossit à chaque issue close
  (cf. `scripts/archiver_historique.py`), le suivre en git alourdirait
  chaque commit de sauvegarde CCL sans rapport avec la tâche en cours.
- `watcher.py` : nouveau `logs/journal_ecritures_historique.jsonl` (JSON
  Lines, déjà couvert par le `.gitignore` existant de `logs/`) via
  `_journaliser_ecriture` (nouvelle fonction). Une ligne par écriture
  significative : `nb_avant`/`nb_apres` (nombre d'entrées), taille en octets
  avant/après, `operation`, et `reinitialise_corruption=true` si l'écriture
  repart d'un JSON illisible (la signature exacte d'une perte de données
  silencieuse — jusqu'ici, `enregistrer_duree` réinitialisait déjà
  discrètement l'historique à `[]` dans ce cas, sans laisser aucune trace).
  Appelé depuis `enregistrer_duree` (`operation="cloture_issue"`,
  `historique_durees.json`) et depuis `_maj_etat_json` pour
  `etat_timeout.json` uniquement (`operation="calibration_timeout"`,
  nombre de combinaisons avant/après) — `etat_ambiance.json` non instrumenté
  (deux clés fixes `F_reseau`/`F_local`, jamais perdues de la même façon,
  hors du périmètre demandé par l'issue).
- `scripts/archiver_historique.py` : écrit aussi dans ce même journal
  (`operation="archivage_manuel"`, nouvelle fonction locale
  `_journaliser_archivage`, sans importer `watcher.py` — cohérent avec le
  découplage volontaire du script) lors d'une exécution réelle (jamais en
  `--dry-run`). But : qu'une réduction volontaire et attendue du fichier
  (archivage manuel par Alain) ne soit jamais confondue, à la lecture du
  journal, avec une chute inexpliquée.
- `BRIDGE_AGENT_DOC.md` (§19.3, §19.7) : documentation du nouveau journal et
  de son rôle diagnostique.
- Aucun test dédié ajouté : vérification manuelle (écritures normales,
  simulation d'une corruption suivie d'une réinitialisation, exécution de
  `archiver_historique.py`) dans un dossier temporaire isolé, hors du
  périmètre du projet — cf. rapport de clôture de l'issue.

## 2 septembre 2026 — issue #516

Champ `RELANCE` dans `issues_inbox/` : corriger/relancer une issue
`needs-human` sans repasser par une édition manuelle sur GitHub. Jusqu'ici,
ajuster un `TIMEOUT` trop court après un échec par dépassement obligeait à
sortir du flux `issues_inbox` — redéposer un `.txt` avec le même titre
échouait systématiquement (anti-doublon §3.4, qui rejette tout titre déjà
porté par une issue OUVERTE, `needs-human` incluse).
- `scripts/watcher_issues_inbox.py` : nouveau champ d'en-tête optionnel
  `| RELANCE | #N |` (en cohérence avec `SUITE_DE`, §6). Présent, il
  détourne tout le bloc vers la correction de l'issue #N déjà ouverte —
  aucune création, anti-doublon court-circuité (n'a de sens que pour une
  création). Validation avant modification (`valider_relance`,
  `_recuperer_issue`) : `PROJET` résout le dépôt cible, `RELANCE` doit être
  un numéro exploitable, `gh issue view --repo` confirme l'existence et
  l'appartenance au bon dépôt, l'issue doit être OUVERTE — sinon rejet vers
  `rejected/`, même mécanique que les rejets existants. Champs corrigibles
  dans le corps : `TIMEOUT` et `MODELE` uniquement (`_fusionner_entete`/
  `_maj_ligne_entete` — corrige une ligne déjà présente, n'en insère jamais
  une nouvelle). `MODE` est exclu (le mode réel est armé par le label GitHub
  `mode_write`/`mode_scratch`, pas par le texte du corps — le
  resynchroniser depuis ce chemin est jugé hors-scope pour cette première
  itération) ; `LABELS` aussi (n'apparaît jamais dans le corps).
- `app/interruption.py` : logique de `route_relancer()` (bouton
  « 🔄 Relancer », issue #460) extraite dans `relancer_issue(depot, numero,
  commentaire=...)`, réutilisée telle quelle par le champ `RELANCE` — aucun
  retrait de label / pose de commentaire dupliqué entre les deux flux. Le
  commentaire posté depuis `issues_inbox/` mentionne explicitement RELANCE,
  résume les champs corrigés et reprend le texte libre éventuel du fichier
  déposé.
- `BRIDGE_AGENT_DOC.md` : nouveau §3.14, ligne `RELANCE` ajoutée au tableau
  §6.
- `tests/test_champ_relance_516.py` (nouveau) : extraction du champ,
  parsing du numéro, fusion des champs corrigibles (jamais d'insertion d'un
  champ absent), chemin complet `_traiter_relance` (succès, issue fermée,
  numéro invalide) — tous les appels `gh` substitués, aucun accès réseau.
- Formulaire web (`new_issue.py`) volontairement non modifié : il sert à
  **créer** des issues et dispose déjà d'un chemin dédié pour cibler une
  issue existante (bouton « 🔄 Relancer ») — dupliquer `RELANCE` là
  n'apporterait rien.

## 30 août 2026 — issue #509

Panneau Infrastructure — bouton « Retirer needs-human » sur l'issue
sélectionnée : demande déjà entièrement couverte par l'issue #460
(commit `8dec213`, fusionné dans `master` avant #509). Vérification faite
que le bouton « 🔄 Relancer » de `#pl-zone-actions`
(`rendrePanneauLateralActions()`, `static/js/app.js`) remplit exactement
le besoin décrit : visible uniquement quand l'issue sélectionnée porte le
label `needs-human` et est ouverte, retire ce label via `gh issue edit
--remove-label` (route `POST /relancer-issue`,
`app/interruption.py::route_relancer`, même mécanisme `--add-label`/
`--remove-label` que `app/issues.py::modifier_label_notif`), ne ferme pas
l'issue, poste un commentaire de trace, puis rafraîchit la liste et le
détail sans rechargement manuel complet. Aucune modification de code
nécessaire.
- `BRIDGE_AGENT_DOC.md` : ajout de la sous-section « Relancer une issue
  bloquée en `needs-human` (issue #460, cf. #509) » (juste après
  « Interrompre une issue bloquée »), qui manquait — seul point réellement
  manquant identifié pour cette issue.

## #507 — CONTEXTE.md : correction de deux mentions obsolètes de "VM Windows"

`CONTEXTE.md` mentionnait encore « VM Windows » à deux endroits (description
du module `app/ccw` et entrée changelog §16), alors que la migration vers un
PC fixe physique est actée depuis longtemps (`BRIDGE_AGENT_DOC.md` §16,
issue #446). Remplacé par « PC Windows physique », cohérent avec le
vocabulaire de `BRIDGE_AGENT_DOC.md`. Vérifié qu'aucune autre mention de VM
ne subsiste dans le fichier.

## #506 — eval-expiration.json : correction date d'installation Windows PC fixe (2026-08-30)

`provisioning/windows/eval-expiration.json` contenait déjà `date_installation:
2026-08-17` / `date_expiration: 2026-11-15` (mis à jour par le fix #452, le
2026-08-18) — pas les valeurs `2026-07-19`/`2026-10-17` que l'issue supposait.
La mesure fraîche du 30 août 2026 fournie dans l'issue (`GracePeriodRemaining`
= 111244 min ≈ 77,25 j restants) recalcule une expiration au **2026-11-15**
et une installation au **2026-08-17** — exactement les valeurs déjà en place.
Aucune modification du JSON n'était donc nécessaire.

En revanche, `BRIDGE_AGENT_DOC.md` §16.1 (tableau « Repères de dates »)
n'avait pas été mis à jour lors du fix #452 et affichait encore les
anciennes dates de la VM. Corrigé :
- « Date d'installation Windows » : 2026-07-19 → **2026-08-17**
- « Expiration éval Windows (90 j) » : 2026-10-17 → **2026-11-15**

Non touché (hors périmètre de l'issue) :
- §16, tableau `provisioning/windows/` (ligne `eval-expiration.json`) :
  mentions 2026-07-19/2026-10-17 explicitement présentées comme historique
  de l'ancienne VM VirtualBox (issue #167), conservées telles quelles.
- §16.1, ligne « Expiration token GitHub » (≈ 2026-10-17) : concerne
  l'expiration d'un token GitHub fine-grained réel, non recalculable depuis
  la mesure Windows fournie — signalé pour vérification manuelle éventuelle,
  non modifié.

## #501 — finaliser_projet_ccw.ps1 : clarification du prompt de confirmation du token

Le message `Read-Host 'Appuie sur Entrée une fois le token créé et copié'` prêtait à
confusion : il pouvait être lu comme une demande de coller le token à cet endroit,
alors qu'il ne fait qu'attendre une touche Entrée pour continuer — le vrai collage
du token a lieu juste après, dans `mettre_a_jour_tokens_ccw.ps1` (« Collez la valeur
de GH_TOKEN »). Un utilisateur a déjà collé son token par erreur à cette invite.

Reformulé en : `'Ne colle RIEN ici : une fois le token créé et copié, appuie juste
sur Entrée pour continuer (le collage se fera à l'étape suivante)'`.

Le script personnel `creer_projet_ccw_complet.ps1` (hors dépôt officiel) n'est pas
accessible depuis ce worktree — la même formulation cohérente y est recommandée
manuellement si un message similaire y existe.

## 18 août 2026 — issue #454

FEATURE — Bandeau d'avertissement d'échéance de l'éval Windows CCW dans
`new_issue.py`.
- `app/eval_windows.py` (nouveau) : `etat_eval_windows()` lit
  `provisioning/windows/eval-expiration.json`, recalcule la date
  d'expiration (`date_installation` + `eval_jours`, même logique que
  `provisioning/windows/verifier_expiration_ccw.py`) et retourne `None`
  si le fichier est absent/invalide ou si l'échéance est encore lointaine
  (> 14 jours), sinon un état `{jours_restants, date_expiration, niveau,
  message}` avec `niveau` = `orange` (≤ 14 j) ou `rouge` (≤ 5 j ou
  échéance dépassée).
- `app/vues.py` : la route `index()` passe `eval_windows=etat_eval_windows()`
  au gabarit.
- `templates/index.html` : bandeau `{% if eval_windows %}` inséré juste
  après l'en-tête, en dehors des panneaux d'onglets → visible sur tous
  les onglets sans dupliquer le HTML.
- `static/css/style.css` : styles `.bandeau-eval-windows.orange` (fond
  `#fff3cd`) et `.rouge` (fond `#f8d7da`), cohérents avec les couleurs
  d'alerte déjà utilisées ailleurs dans l'interface.
- Vérifié par test manuel (`create_app()` + `test_client`) avec état
  forcé orange/rouge/absent : bandeau présent avec le bon texte et la
  bonne classe, absent quand l'échéance est lointaine (cas réel actuel :
  89 jours restants au 18/08/2026) ou quand le fichier est absent/invalide.

## 18 août 2026 — issue #452

CONFIG — `provisioning/windows/eval-expiration.json` mis à jour pour
refléter l'échéance réelle du PC fixe physique (remplaçant l'ancienne VM
VirtualBox, cf. #449/#450), installé le 17 août 2026.
- `date_installation` : `2026-07-19` → `2026-08-17`.
- `date_expiration` : `2026-10-17` → `2026-11-15` (date_installation +
  eval_jours = 90 jours, conforme à la note du fichier).

## 18 août 2026 — issue #451

DOC — nouveau fichier `provisioning/windows/REINSTALLATION_CCW.md` :
procédure complète de réinstallation du PC fixe CCW, aux côtés des scripts
qu'elle utilise (`autounattend.xml`, `provisionner.ps1`,
`mettre_a_jour_tokens_ccw.ps1`), plutôt que dans `BRIDGE_AGENT_DOC.md` qui
est destiné aux agents CCL/CCW et non à la procédure d'installation
Windows. Couvre dans l'ordre : réinstallation Windows via
`autounattend.xml`, configuration SSH (`configurer_ssh_ccw.ps1`),
vérification de la connexion SSH depuis CCL, provisioning logiciel
(`provisionner.ps1`), topic ntfy + tokens
(`mettre_a_jour_tokens_ccw.ps1`), vérification du service `CCW-Watcher`.
Précise que la clé privée CCL (`~/.ssh/ccl_ccw`) reste sur le ThinkPad
entre les réinstallations — seule la clé publique est à réinstaller sur le
nouveau Windows.
- `BRIDGE_AGENT_DOC.md` : §16 complété d'une ligne de référence vers ce
  nouveau fichier.

**Point d'attention signalé (pas corrigé, hors périmètre de cette
issue) :** `configurer_ssh_ccw.ps1`, référencé à l'étape 2 de la
procédure, n'existe pas dans `provisioning/windows/` au moment de la
rédaction — il devra être créé (script PowerShell côté Windows qui active
OpenSSH Server et installe la clé publique fournie dans
`authorized_keys`) avant que l'étape 2 soit exécutable telle quelle. Une
note l'indique en bas du nouveau fichier.

## 7 septembre 2026 — issue #518

DOC — retrait de toute mention du copier-coller comme méthode de création
d'issue à partir de contenu produit par Claude Chat, dans
`BRIDGE_AGENT_DOC.md`. Depuis #483, Claude Chat ne doit produire que des
fichiers `.txt` déposés dans `issues_inbox/` (§3) ; la doc présentait
encore, notamment au §20, le copier-coller dans le formulaire web comme un
usage normal pour du contenu de Claude Chat.
- §20 : le bloc « Format du corps pour copier-coller depuis Claude Chat »
  et son exemple sont reformulés en « Format du corps reconnu par le
  formulaire » — présenté comme un format de saisie manuelle (Alain) plutôt
  que comme une cible de copier-coller. « Envoi en lot (plusieurs issues
  d'un seul copier-coller) » renommé « Envoi en lot (plusieurs issues dans
  un même corps) ». Le bloc « Convention de présentation côté Claude Chat »
  (issues #153/#443) devient « Regroupement des blocs pour le mode lot » et
  précise explicitement que Claude Chat ne doit plus jamais produire de
  texte destiné à être copié-collé dans ce formulaire. Mentions résiduelles
  de « corps collé » reformulées en « corps du formulaire »/« corps saisi
  dans le champ ».
- §11 (conventions de code) : la règle « Alain colle le tout dans le champ
  Corps de new_issue.py — un seul copier-coller » remplacée par un renvoi
  au flux `issues_inbox/` (§3).
- §3.3 : « Même format qu'une issue produite par Claude Chat pour le
  formulaire web (§20) » reformulé en « Même format que celui reconnu par
  le formulaire web (§20) », pour ne plus laisser entendre que Claude Chat
  produit du contenu pour ce formulaire.
- Usages légitimes du formulaire web laissés inchangés : aperçu de la
  commande `gh issue create` avant envoi, création manuelle par Alain
  directement depuis l'interface, repli si le watcher `issues_inbox` est
  indisponible.
- Pied de page de `BRIDGE_AGENT_DOC.md` mis à jour (glissement des trois
  dernières entrées d'un cran, la plus ancienne sort du pied de page).

## 25 août 2026 — issue #483

Watcher `issues_inbox` centralisé + onglet « Résultats inbox » : nouveau
flux de création d'issues sans passage par le formulaire web. La
volumétrie d'issues créées à la main (copier-coller depuis Claude Chat
dans `new_issue.py`) montait et demandait des allers-retours ; ce watcher
automatise le dépôt → création → nettoyage.
- `scripts/watcher_issues_inbox.py` (nouveau) : scrute
  `~/Bridge_Agent/issues_inbox/` en continu (polling, 5s par défaut),
  parse l'en-tête de chaque fichier `.txt` (`PROJET`, `TIMEOUT`, `MODELE`,
  `MODE`, `LABELS`, `#Titre:` — mêmes regex que `static/js/app.js`), valide
  (`PROJET` existe dans `configs/`, titre non vide, `MODELE`/`TIMEOUT`
  bien formés si fournis), crée l'issue via `gh issue create` (même
  format de body/labels que `app/issues.py`), supprime le fichier traité.
  Fichier invalide ou échec de `gh` → déplacé vers `issues_inbox/rejected/`
  (suffixe `__REJETE-<motif>`), jamais retraité automatiquement. Ignore un
  fichier modifié il y a moins d'1s (protection contre une lecture en
  cours d'écriture). Dossiers `issues_inbox/` et `issues_inbox/rejected/`
  créés automatiquement au premier lancement. Config optionnelle
  `configs/watcher_issues_inbox.conf` (non créée par CCL — garde-fou §11 :
  CCL ne modifie/crée jamais `configs/*.conf`, à créer à la main par Alain
  s'il veut surcharger les défauts).
- Journalisation : `logs/issues_inbox.log`, une ligne par traitement
  (`<horodatage> | <projet> | OK|REJECTED | <titre>`), rotation par
  **nombre de lignes** (défaut 50 — distincte de la rotation par taille
  des autres watchers).
- `app/issues_inbox.py` (nouveau) : route `GET /issues-inbox/etat`, pure
  lecture disque (aucun appel `gh`) — renvoie l'état de `rejected/`
  (déclenche l'alarme) et les dernières lignes du log (historique
  informatif, sans effet sur l'alarme).
- `templates/index.html` / `static/js/app.js` / `static/css/style.css` :
  nouvel onglet « Résultats inbox », badge 🚨 clignotant sur l'onglet
  piloté **uniquement** par la présence de fichiers dans
  `issues_inbox/rejected/` (jamais par un parsing de log), tableau des
  fichiers rejetés (nom + date), historique de log affiché à titre
  informatif, rafraîchissement en polling continu (7s, indépendant de
  l'onglet actif) + bouton « Rafraîchir ».
- `.gitignore` : ajout de `issues_inbox/` (état transitoire, pas du code).
- `BRIDGE_AGENT_DOC.md` : nouveau §20 « Watcher `issues_inbox` centralisé »
  (structure disque, format de fichier, validation, journalisation,
  concurrence, config, onglet web, workflow utilisateur final) ; §10
  (structure du dépôt) complété avec `app/issues_inbox.py` et
  `issues_inbox/`. Pied de page mis à jour (glissement des trois dernières
  entrées d'un cran, la plus ancienne — #435 — sort du pied de page).

## 13 août 2026 — issue #443

DOC — extension de la convention de présentation des issues (issue #153)
au cas mono-issue. Le §3 de `BRIDGE_AGENT_DOC.md` ne formulait la règle du
bloc de code unique que pour le mode lot ; en pratique Claude Chat enveloppe
aussi une issue unique dans un bloc de code afin qu'Alain puisse utiliser le
bouton copier du bloc, mais ce n'était pas explicite dans la doc.
- `BRIDGE_AGENT_DOC.md` : §3 « Convention de présentation côté Claude Chat
  (issue #153) » complétée pour couvrir explicitement le cas mono-issue —
  une issue unique est elle aussi présentée dans un bloc de code, pas
  seulement un lot de plusieurs issues.
- `BRIDGE_AGENT_DOC.md` : §11 « Conventions de code », bullet « Issues »,
  précise désormais que le corps est toujours présenté dans un bloc de
  code, qu'il s'agisse d'une issue seule ou d'un lot.
- Pied de page mis à jour (glissement des trois dernières entrées d'un
  cran).

## 10 août 2026 — issue #434

Champ `COMPLEXITE` dans les issues : 4e dimension de la clé EWMA de
calibration TIMEOUT. La clé `projet|TYPE|mode` mélangeait des populations
incompatibles (ex. une issue de doc de 250s et une refonte de 1800s dans
la même case).
- `watcher.py` : nouvelle fonction `extraire_complexite(body)` (même
  pattern que `extraire_timeout`/`extraire_modele`) — lit `| COMPLEXITE |
  ... |` dans l'en-tête, valeurs reconnues `rapide`/`court`/`normal`/`lourd`
  (insensible à la casse), toute valeur non reconnue ou champ absent →
  `normal`. `_cle_combinaison()` prend désormais un 4e paramètre
  `complexite` et produit `f"{projet}|{type_issue}|{mode}|{complexite}"`
  au lieu de `f"{projet}|{type_issue}|{mode}"`. `maj_calibration_timeout()`
  et `lire_timeout_suggere()` reçoivent un nouveau paramètre optionnel
  `complexite` (défaut `"normal"`) répercuté dans la clé ; les trois sites
  d'appel (succès, tentative expirée, échec définitif) calculent
  `extraire_complexite(body)` au même endroit que `deduire_type_issue`/
  `_etiquette_calibration` et le transmettent. Nouvelles clés distinctes
  par complexité — l'historique existant (sans ce champ) n'est pas
  affecté, recalibration progressive.
- `consignes/globales.md` : nouvelle consigne demandant à CCL/CCW d'inclure
  `| COMPLEXITE | <niveau> |` dans l'en-tête de toute issue chef/ouvrier
  qu'il crée lui-même. Ne concerne pas les issues rédigées par Claude
  Chat — géré côté doc/prompt, hors de ce fichier.
- `BRIDGE_AGENT_DOC.md` : §6 (table des champs spéciaux) documente le
  nouveau champ `COMPLEXITE` ; §19.1 et §19.3 (calibration TIMEOUT)
  mentionnent son rôle de 4e dimension de la clé EWMA et le changement de
  format de la clé dans `etat_timeout.json`.

## 10 août 2026 — issue #432

Alerte accumulation de worktrees : depuis l'issue #337, les worktrees
créés pour la parallélisation mode_write ne sont jamais supprimés
automatiquement (nettoyage manuel par Alain) et pouvaient s'accumuler
silencieusement, sans aucun signal.
- `watcher.py` : nouvelle fonction `_lister_worktrees_secondaires()`
  (parse `git worktree list --porcelain` dans `REP_TRAVAIL`, exclut le
  worktree principal) et `verifier_accumulation_worktrees()`, appelée en
  début de chaque cycle de polling juste après `rafraichir_depot()`
  (`git pull --ff-only`). Au-delà de `SEUIL_ALERTE_WORKTREES` worktrees
  secondaires actifs (nouvelle clé `.conf`, entier, défaut **3**),
  émet un `log.warning` listant chemin + branche de chacun — visible
  dans l'onglet Journal watcher de l'interface. En dessous du seuil,
  silence total ; clé absente du `.conf` → défaut 3, aucune erreur.
  Pas de notification ntfy/bureau, volontairement — un warning dans le
  log suffit.
- `WORKTREES.md` (§5) et `BRIDGE_AGENT_DOC.md` (§13, sous-section
  parallélisation mode_write) documentent le mécanisme ; la limite
  « pas d'alerte sur l'accumulation de worktrees » de `WORKTREES.md`
  §5 est levée.

## 8 août 2026 — issue #401

Onglet Résultats : les titres des issues ne s'alignaient pas horizontalement,
la zone d'icônes à gauche (case à cocher, pastille, badges Diff/All, etc.)
ayant une largeur variable selon le nombre d'icônes présents sur chaque ligne.
- `static/css/style.css` : `.ligne-issue .ligne-gauche` (préfixe type/OS +
  badges ✏️/✅/⚠️/○/Diff/All + pastille projet) reçoit un `min-width:130px`
  — largeur fixe couvrant le cas le plus chargé (chef/ouvrier + for-windows +
  mode_write+done+Diff+All), tous les titres démarrent désormais à la même
  position, les icônes restant alignées à gauche (flex-start).

## 7 août 2026 — issue #389

Fix `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x82` lors de la
finalisation d'un projet CCW : la sortie de `powershell.exe` exécuté dans
la VM invitée est encodée en CP1252 (page de code Windows par défaut), pas
en UTF-8.
- `app/ccw.py` : `_executer_ps` et `_executer_commande_ps` (même schéma —
  toutes deux lancent `powershell.exe` via `guestcontrol run`) décodent
  désormais `stdout`/`stderr` en `encoding="cp1252"` avec `errors="replace"`
  en filet de sécurité, au lieu de `text=True` (UTF-8 implicite côté hôte
  Linux). `_copier` (guestcontrol `copyto`, ne lance aucun processus dans
  la VM) n'était pas concernée, laissée inchangée.

## 6 août 2026 — issue #384

Panneau flottant actions : toggles `notif_pc`/`notif_gsm`/`notif_tous` sur
l'issue sélectionnée, sans passer par GitHub — ces labels peuvent être
modifiés pendant le traitement, le watcher les relit au moment de la
clôture.
- Nouvelle route `POST /modifier-label-notif` (`app/issues.py`,
  `modifier_label_notif`) : `gh issue edit --add-label`/`--remove-label`
  selon `actif`, whitelist stricte sur `notif_pc`/`notif_gsm`/`notif_tous`
  (constantes `LABEL_NOTIF_*` de `watcher.py`, réutilisées telles quelles) —
  aucun autre label ne peut être modifié via cette route. Protégée par
  `login_requis`, enregistrée dans `app/__init__.py`.
- `rendrePanneauLateralActions()` (`static/js/app.js`) : bloc « 🔔
  Notifications » (3 checkboxes) inséré sous le mode de l'issue, affiché
  seulement si l'issue est interrompible (ouverte, ni `done` ni
  `needs-human` — même condition que les boutons d'interruption). État
  initial coché/décoché lu depuis `listeIssuesResultats`. Au clic :
  appel `/modifier-label-notif`, mise à jour locale de
  `listeIssuesResultats` + re-rendu du panneau si succès ; en cas
  d'échec, la checkbox revient à son état précédent et un message
  d'erreur discret (`#pl-notif-erreur`, sans `alert()`) s'affiche puis
  s'efface après 4 s.
- CSS : `.pl-notifs`/`.pl-notifs-titre`/`.pl-notif-ligne`/`.pl-notif-erreur`
  (`static/css/style.css`).

## 6 août 2026 — issue #383

Correctif suite #381/#382 : les pastilles de notification des boutons de
filtre projet comptaient les issues **OPEN** ni `done` ni `needs-human`
(état GitHub), au lieu des issues **décochées** localement — la case à
cocher libre (issue #154), persistée en `localStorage` via
`cleCocheResultat`/`estResultatCoche`, indépendante de l'état GitHub.
- `majPastillesFiltres()` : remplacement du filtre `state`/labels
  (`OPEN`/`done`/`needs-human`) par `estResultatCoche(it.projet, it.number)`
  — une issue est comptée si elle n'est PAS cochée, quel que soit son état
  GitHub. Le filtre GitHub est supprimé entièrement (une issue décochée
  reste décochée quel que soit son état). La portée courante
  (`limiteIssuesProjet()`, issue #382) est conservée inchangée.
- Effet de bord nécessaire : ni `basculerCocheResultat()` (case individuelle)
  ni `cocherToutesVisibles()` (bouton « Tout cocher ») n'appelaient
  `majPastillesFiltres()` — sans ce fix, une pastille basée sur les cases
  restait figée jusqu'au prochain rendu complet de la liste après un clic
  sur une case. Ajout de l'appel dans les deux fonctions pour un
  rafraîchissement immédiat.
- Fichier touché : `static/js/app.js` (`majPastillesFiltres`,
  `basculerCocheResultat`, `cocherToutesVisibles`).

## 6 août 2026 — issue #382

Correctif suite #381 : les pastilles de notification des boutons de filtre
projet ne respectaient pas la portée courante.
- Investigation des deux causes suspectées par l'issue : l'attribut
  `data-projet` posé sur `.filtre-projet` (`construireBoutonsFiltre`) et
  l'ordre d'appel de `majPastillesFiltres()` après le peuplement de
  `listeIssuesResultats` (`appliquerListeIssues`, `rendreListeIssues`,
  `remplacerLigneIssue`) étaient déjà corrects — aucune des deux ne causait
  l'absence de pastilles.
- **Cause réelle** : `majPastillesFiltres()` comptait sur la totalité de
  `listeIssuesResultats`, sans tenir compte de la portée du champ
  « par projet : N » (`limiteIssuesProjet()`) — un compte pouvant dépasser ce
  que l'utilisateur voit réellement dans la liste dès que N est abaissé sans
  cliquer sur ↻ (la saisie seule n'invalide que le cache, pas les données déjà
  en mémoire). Le comptage se limite désormais aux N premières issues de
  chaque projet (même lecture de la limite que le téléchargement), avant
  d'appliquer le filtre ouvert/ni-done/ni-needs-human.
- Fichier touché : `static/js/app.js` (`majPastillesFiltres`).

## 6 août 2026 — issue #381

Améliorations de confort du panneau flottant (suite #380), sans changement
de layout ni de mécanique existante :
- **Monitoring watchers CCL** (`rendrePanneauLateralMonitoring`) : bouton
  global renommé « ↺ Relancer tous les éteints » → « ▶ Lancer les éteints »
  + nouveau bouton « ↺ Relancer tous les CCL » (`sidebarRelancerTousCCL`) qui
  relance TOUS les watchers CCL, actifs ou éteints — même mécanique que
  `sidebarRelancerTousEteints` mais sans filtrer sur l'état. Les deux boutons
  sont côte à côte (`.pl-boutons-ccl`).
- **Résumé par projet** (`resumeProjetMonitoring`) : sous chaque watcher CCL,
  une ligne « X en cours, Y en file » (`.pl-sous-projet`) — calculée
  uniquement depuis les données déjà en mémoire (`listeIssuesResultats` +
  `timingIssues`), sans nouveau fetch réseau automatique (pour ne pas
  reproduire la surconsommation de quota gh déjà corrigée par l'issue #270).
  Horodatage « Mis à jour à HH:MM:SS » ajouté en bas du monitoring.
- **Zone actions** (`rendrePanneauLateralActions`) : mode de l'issue
  sélectionnée affiché en haut (« 📖 Lecture seule » / « ✏️ Lecture active » /
  « ⚠️ Écriture », `libelleModeIssue`, lu depuis les labels via
  `modeEcritureDepuisLabels`) ; nouveau bouton « ⛔ Interrompre et relancer
  (watcher CCL/CCW) » (`interrompreEtRelancer`) qui enchaîne `/interrompre`
  puis la relance du watcher adapté au label de l'issue (for-linux → CCL,
  for-windows → CCW) — l'ancien bouton « ⛔ Interrompre l'issue » reste en
  dessous ; nouveau bouton « ✖ Fermer l'issue » quand l'issue porte le label
  `needs-human`, réutilisant exactement la route `/fermer-issue` déjà câblée
  par `fermerIssue()` dans le détail. `interrompreIssue()` retourne désormais
  un booléen de succès (annulation/échec → false) pour permettre à
  `interrompreEtRelancer()` de savoir s'il doit enchaîner sur la relance.
- **Pastilles de notification** (`majPastillesFiltres`) sur les boutons de
  filtre projet (`.filtres-projets`) : petit badge rouge (`.pastille-notif`)
  affichant le nombre d'issues ouvertes ni `done` ni `needs-human` du projet,
  visible même quand son filtre est masqué. Calcul purement local depuis
  `listeIssuesResultats`, rafraîchi à chaque (re)rendu de la liste
  (`rendreListeIssues`, `remplacerLigneIssue`, `construireBoutonsFiltre`).
- **Bouton « ✓ Cocher tout »** (`cocherToutesVisibles`) dans la barre de
  filtres, à côté du bouton rafraîchir : coche toutes les issues actuellement
  visibles (projet filtré, ou tous si filtre « Tous »), en réutilisant le
  mécanisme de case à cocher existant (issue #154, localStorage +
  `.resultat-traite`).
- Fichiers touchés : `static/js/app.js`, `static/css/style.css`.

## 6 août 2026 — issue #380

Refonte du panneau latéral de l'onglet Résultats (#375/#376/#377) en
**panneau flottant** (`position:fixed`, `.panneau-lateral`,
`static/css/style.css`), lisible et extensible :
- **Layout** : l'ancien layout flex `.resultats-layout` / `.resultats-liste-col`
  (colonne fixe 280px) est retiré — la liste des issues reprend toute la
  largeur. Le panneau devient un overlay ~360px, max-height 80vh scrollable,
  ombre portée, coin haut-droit. Nouveau bouton toggle fixe `#pl-toggle`
  (« 📊 Infrastructure », `basculerPanneauLateral`) toujours visible dans
  l'onglet, qui ouvre/ferme le panneau. Ouvert par défaut à chaque entrée
  dans l'onglet (`ouvrirPanneauLateralParDefaut`), sauf écran étroit
  (< 900px) où il reste fermé par défaut.
- **Monitoring lisible** (`rendrePanneauLateralMonitoring`, `static/js/app.js`) :
  fini les pastilles colorées par projet, illisibles en 280px — chaque
  watcher CCL a désormais sa propre ligne (`🟢`/`⚫` + nom + bouton individuel
  « ▶ Lancer » ou « ↺ Relancer », noir et blanc, sans couleur projet), même
  format pour les services CCW connus. VM CCW en ligne unique
  (« 🟢 VM allumée » / « 🔴 VM éteinte » + bouton Démarrer si éteinte). Bouton
  « ↺ Relancer tous les éteints » conservé si au moins un watcher CCL est
  éteint. Fonctions `pastillesInline`/`couleurEtatCcw` (obsolètes) retirées.
- **Zone réservée** `#pl-zone-extras` (`.pl-zone-extras`, vide, s'efface via
  `:empty` tant qu'inutilisée) ajoutée entre le monitoring et les actions
  contextuelles, prête à accueillir de futurs boutons sans restructurer le
  panneau — non remplie par cette issue.
- Zone actions contextuelles (`rendrePanneauLateralActions`) inchangée sur le
  fond, seule sa position dans le panneau flottant change.
- CSS : classes `.pl-chip`/`.pl-chips`/`.pl-dot`/`.pl-etat`/`.pl-synthese`
  devenues inutiles retirées, remplacées par `.pl-ligne`/`.pl-ligne-libelle`/
  `.pl-btn-mini`.

## 6 août 2026 — issue #377

Panneau latéral de l'onglet Résultats (#375/#376) : les deux états
mutuellement exclusifs (monitoring OU actions) deviennent **deux zones
empilées non exclusives**, chacune dans son propre conteneur DOM
(`#pl-zone-monitoring` / `#pl-zone-actions`, sous `#panneau-lateral-resultats`,
`templates/index.html`) :
- **Zone haute — monitoring, toujours visible**, même issue sélectionnée
  (`rendrePanneauLateralMonitoring`, `static/js/app.js`) : VM CCW inchangée ;
  watchers CCL désormais colorés **par projet** (`couleurProjetResultats`,
  et non plus vert/rouge générique — pastille sombre `#33322f` = éteint,
  couleur vive du projet = actif) avec un nouveau bouton « ↺ Relancer tous les
  éteints » (`sidebarRelancerTousEteints`) qui relit `/watchers` au clic puis
  relance séquentiellement, un par un via `/lancer-watcher`, chaque watcher
  éteint (une relance en échec n'interrompt pas les suivantes) ; services CCW
  inchangés. Le détail par projet (`.pl-projet`, pid, état CCW ligne par
  ligne) est retiré : redondant avec les pastilles par projet ci-dessus et
  avec la pastille projet désormais sur chaque ligne de résultat (voir
  ci-dessous).
- **Zone basse — actions contextuelles, visible uniquement si une issue est
  sélectionnée** (`rendrePanneauLateralActions`), avec un séparateur
  `<hr class="pl-sep">` et un titre unique « Actions — `<projet>` #`<numero>` »
  (fusion de l'ancien titre + de la référence séparée). Se vide (donc
  disparaît entièrement, séparateur compris) dès qu'aucune ligne n'est
  sélectionnée, au lieu de remplacer le monitoring. Boutons inchangés sur le
  fond (relancer watcher CCL, interrompre l'issue si ouverte et ni `done` ni
  `needs-human`, relancer watcher CCW, verrous CCW désactivé en attendant
  #378), icône de relance alignée sur celle du monitoring (« ↺ » au lieu de
  « 🔁 »).
- `rafraichirPanneauLateralResultats()` rend désormais TOUJOURS le monitoring
  puis (re)rend/vide les actions, au lieu de choisir l'un OU l'autre — appelé
  sans changement par le SSE `fin_issue`, l'intervalle 30s et chaque
  changement de sélection de ligne.

La pastille colorée de projet sur chaque ligne de résultat
(`.pastille-ligne`, `construireLigneIssueDOM`) existait déjà (issue #66,
héritée de l'extraction du frontend) et couvrait déjà le besoin exprimé par
cette issue pour le filtre « Tous » — aucune modification nécessaire sur ce
point, vérifié seulement.

CSS (`static/css/style.css`) : classes `.pl-projet`, `.pl-projet-nom` et
`.pl-issue-ref` retirées (plus aucun appelant après la restructuration) ;
`.pl-synthese`, `.pl-chips`, `.pl-btn-vm`, `.pl-sep`, `.pl-actions`
inchangées, réutilisées telles quelles par les deux zones.

## 6 août 2026 — issue #376

Panneau monitoring de l'onglet Résultats (`rendrePanneauLateralMonitoring`,
`static/js/app.js`) : ajout d'une **vue synthétique de l'infrastructure** en
tête du panneau, avant le détail par projet (inchangé, désormais sous un
séparateur `<hr class="pl-sep">` titré « Détail par projet »). Trois blocs de
résumé, dans un encadré `.pl-synthese` :
- **VM CCW** — état allumée (pastille verte) / éteinte (rouge) / inconnu
  (gris), lu via l'endpoint existant `/ccw/vm-statut` (VBoxManage local, pas de
  guestcontrol) fetché en parallèle de `/watchers` (`Promise.all`). Si la VM est
  éteinte, un bouton « ▶ Démarrer la VM » appelle `/ccw/demarrer-vm`
  (`sidebarDemarrerVm`, même endpoint que le bouton de l'onglet CCW) puis
  re-rend le panneau.
- **Watchers CCL** — une ligne « N/M watchers CCL actifs » + liste inline des
  projets actifs (pastille verte) et éteints (rouge), sans répéter le détail du
  dessous (`pastillesInline`, `.pl-chips`).
- **Services CCW** — affiché seulement si `ccwProjetsConnus` est non vide :
  « N/M services CCW running » + liste inline ; sinon le lien « Vérifier les
  services CCW » existant. Le lien « Actualiser les services CCW » (cas connu)
  reste sous le détail.

Nouvelles classes CSS `.pl-synthese`, `.pl-resume-titre`, `.pl-chips`,
`.pl-chip`, `.pl-btn-vm`, `.pl-sep` (`static/css/style.css`). Aucun nouveau
polling réseau : la synthèse réutilise les fetchs locaux déjà en place et
`ccwProjetsConnus` (alimenté uniquement à la demande par `ccwChargerProjets`).

## 6 août 2026 — issue #375

Onglet Résultats : panneau latéral droit (~280px, scrollable, repasse sous la
liste en écran étroit) ajouté à droite de la liste des issues
(`.resultats-layout` / `.resultats-liste-col` / `.panneau-lateral`), qui
utilisait mal l'espace disponible dans la fenêtre (`.fenetre` élargie
860→1160px pour l'accueillir sans écraser la liste). Deux états, pilotés par
la sélection de ligne existante (`selectionnerLigne`) :
- **Aucune issue sélectionnée** : monitoring passif, tous les projets actifs —
  watcher CCL (actif/pid via `/watchers`, appel Flask local) et watcher CCW
  (état NSSM) pour les projets ayant un service CCW connu. Rafraîchi toutes
  les 30s et à chaque événement SSE `fin_issue` (#350), sans appel GitHub
  supplémentaire.
- **Issue sélectionnée** : actions contextuelles — relancer le watcher CCL
  (`/lancer-watcher`, comme l'onglet Watchers), interrompre l'issue (bouton
  identique à celui du détail, `/interrompre`, affiché seulement si l'issue
  est ouverte et ni `done` ni `needs-human`), relancer le watcher CCW
  (`ccwRedemarrerProjet`, réutilisée telle quelle depuis l'onglet CCW) et un
  emplacement pour « Nettoyer verrous CCW + redémarrer », désactivé en
  attendant l'issue #378 — ces deux derniers boutons seulement si le projet a
  un service CCW connu.
- L'état des services CCW (`ccwProjetsConnus`) n'est JAMAIS interrogé
  directement par ce panneau (guestcontrol coûteux) : il ne fait que lire le
  résultat du dernier appel à `ccwChargerProjets()` (onglet CCW ou lien
  manuel « Vérifier les services CCW » du panneau) — aucun nouveau polling.
- Aucune route Flask ajoutée : tout reprend les endpoints existants
  (`/watchers`, `/lancer-watcher`, `/interrompre`, `/ccw/projets`,
  `/ccw/redemarrer-projet`).

## 3 août 2026 — issue #370

Script PowerShell `surveiller_builds.ps1` (issu d'une session Claude Chat
précédente) committé dans `provisioning/windows/` : surveille en temps réel,
pendant un build CCW (PyInstaller/ISCC), les processus de build et la
croissance du dossier de sortie (taille + delta par passage et depuis le
début). Paramètre `-Dossier` obligatoire, `-Processus` et
`-IntervalleSecondes` optionnels. Documenté au §16 de `BRIDGE_AGENT_DOC.md`
(tableau de provisioning), avec la note que le nom de process Claude Code
(`claude` par défaut) reste à confirmer via `Get-Process` pendant un build
réel.

## 3 août 2026 — issue #352

Le POST `/notifier-fin-issue` (#350) était déclenché via `notifications.bip()`,
donc uniquement pour les issues portant un label `notif_pc`/`notif_gsm`/
`notif_tous` — le rafraîchissement SSE de l'onglet Résultats restait soumis
au ↻ manuel pour toutes les autres. Il doit être universel, indépendamment
des labels notif.

- `watcher.py` : import direct de `scripts/traitement_fin.py` (ajout de
  `scripts/` au `sys.path`, ce dossier n'étant pas un package) et nouvelle
  enveloppe `notifier_fin_sse(numero)` qui appelle
  `traitement_fin.notifier_fin_issue(CFG.nom, numero)` sans passer par
  `notifier()`/`bip()` — donc sans dépendre des labels `notif_*`. Appelée
  dans `_traiter_issue_synchrone` aux trois points de fin définitive d'une
  issue : succès, échec définitif (garde-fou lecture active niveau 2, issue
  #327), échec définitif après épuisement des tentatives (`max_essais`, non
  critique). Non appelée sur les fins non définitives (retry différé d'une
  issue critique, commentaire de résultat non posté) — l'issue reste ouverte
  et sera retraitée.
- Le bip et les labels `notif_*` restent inchangés — seul le POST est
  découplé, comme demandé par l'issue.

## 3 août 2026 — issue #350

Renommage de `scripts/bip.py` en `scripts/traitement_fin.py` et ajout d'un
canal SSE de rafraîchissement instantané (< 1 s) de l'onglet Résultats, sans
polling supplémentaire.

- `scripts/traitement_fin.py` : après le bip habituel, POST **best-effort**
  (timeout 1 s, échec silencieux si `new_issue.py` n'est pas lancé) vers
  `http://localhost:5100/notifier-fin-issue` avec `{"projet": ..., "numero": ...}`,
  lus depuis deux nouveaux arguments CLI `--projet`/`--numero`. La clé de
  config reste `SCRIPT_BIP` (renommer la clé impliquerait de modifier les
  `configs/*.conf` gitignorés, hors périmètre agent) — **Alain doit mettre à
  jour manuellement le chemin dans ses `configs/*.conf` existants**
  (`.../scripts/bip.py` → `.../scripts/traitement_fin.py`).
- `notifications.py` (`bip()`/`notifier()`) et les enveloppes correspondantes
  de `watcher.py` et `app/notifications_poller.py` : ajout d'un paramètre
  `numero` transmis en CLI au script, pour que le POST identifie précisément
  l'issue concernée. Comme le bip lui-même, ce déclenchement reste opt-in via
  les labels `notif_*` — sans label, la ligne reste soumise au ↻ manuel ou au
  fetch post-TIMEOUT de #334.
- `app/fin_issue.py` (nouveau module) : route `POST /notifier-fin-issue`
  (sans authentification, appelée par le script local) qui pousse un
  événement SSE `event: fin_issue\ndata: {"projet": ..., "numero": ...}` à
  tous les onglets Résultats ouverts, et route `GET /stream` (protégée par
  `login_requis`) qui les diffuse — une `queue.Queue` par connexion active
  (ajoutée/retirée de `app.config["FIN_ISSUE_ABONNES"]`), pas de broadcast
  global, car plusieurs onglets peuvent être ouverts simultanément. Ping
  `: ping\n\n` toutes les 30 s pour maintenir la connexion ; nettoyage propre
  de l'abonné à la déconnexion (`GeneratorExit`).
- `static/js/app.js` : `demarrerStreamFinIssue()`/`arreterStreamFinIssue()`
  ouvrent/ferment un `EventSource('/stream')` à l'entrée/sortie de l'onglet
  Résultats (`basculerOnglet`). Sur réception d'un événement `fin_issue` dont
  le numéro figure dans `listeIssuesResultats`, réutilise directement
  `verifierIssueApresDepassement()` (issue #334) — même fetch de vérification,
  même `remplacerLigneIssue()`, sans dupliquer la logique. Reconnexion
  automatique gérée nativement par `EventSource`.
- `BRIDGE_AGENT_DOC.md` : §17 mis à jour (mentions de `bip.py` →
  `traitement_fin.py`), nouvelle sous-section 17.3 documentant le mécanisme
  SSE complet.
- Testé sans `new_issue.py` lancé (bip normal, POST en échec silencieux,
  aucune exception) et avec un client de test Flask (`app.test_client()`) :
  `POST /notifier-fin-issue` livre bien l'événement à une connexion
  `GET /stream` active, et la liste des abonnés est correctement nettoyée à
  la déconnexion.

## 2 août 2026 — issue #343

`WORKTREES.md` §3 « Workflow normal d'Alain » (étape 3) et §4
« Procédures de récupération » : précisions suite à un cas vécu lors du
premier workflow complet avec worktrees (issues #340/#341, session du
02/08/2026) — `fusionner_changelog.py` lancé depuis `master` avant le
merge n'a rien trouvé, car le script scanne la racine du dépôt qu'on lui
indique et `CHANGELOG-341.md` n'existait alors qu'à la racine du
worktree ; le fichier s'est donc retrouvé dans `master` via le merge
sans être intégré, nécessitant un commit de rattrapage. L'étape 3
documente désormais l'ordre impératif (script avant merge) et deux
méthodes : lancer `--repo .` depuis le worktree lui-même (recommandé),
ou copier `CHANGELOG-<N>.md` dans master avant de fusionner depuis
`REP_TRAVAIL`. Le §4 précise la procédure de rattrapage si le merge a
eu lieu avant le script (relancer le script depuis `REP_TRAVAIL`,
vérifier `git diff CHANGELOG.md`, committer).

## 2 août 2026 — issue #341

Ajout dans `TACHES.md`, juste après le bloc d'en-tête, d'une section
« Worktrees en production — points de surveillance » listant les deux
limites connues restantes après correction de #340 : pas d'alerte sur
l'accumulation de worktrees (nettoyage manuel requis) et
`issues_en_cours` sans verrou explicite inter-process.

## 2 août 2026 — issue #342

§11 « Conventions de code » de `BRIDGE_AGENT_DOC.md` : deux notes ajoutées
pour informer les projets utilisant Bridge_Agent des conséquences
pratiques de la parallélisation `mode_write` par worktrees (issue #337),
jusqu'ici documentée uniquement pour l'infrastructure elle-même (§13 du
DOC, `WORKTREES.md`). Première note : deux issues `mode_write` touchant
les mêmes fichiers ou zones de code peuvent désormais générer un conflit
de merge à résoudre manuellement — recommandation de scoper chaque issue
sur un périmètre de fichiers aussi distinct que possible. Deuxième note :
le workflow de vérification/push d'Alain inclut désormais deux étapes
supplémentaires après une ou plusieurs issues `mode_write` en parallèle —
`git worktree list` pour repérer les worktrees à traiter,
`python3 scripts/fusionner_changelog.py` avant tout merge ou push (intègre
les `CHANGELOG-N.md` des worktrees dans `CHANGELOG.md`), puis merge manuel
de chaque branche `worktree-issue-<N>` et nettoyage
(`git worktree remove` + `git branch -d`) ; renvoi vers `WORKTREES.md` pour
le détail complet plutôt qu'une duplication intégrale. Pied de page du DOC
mis à jour en conséquence (glissement des trois entrées, #327 sort du pied
de page).

## 2 août 2026 — issue #340

Suite #338 : le bouton ⛔ « Interrompre » (`app/interruption.py::interrompre_linux()`)
nettoie désormais aussi les verrous des worktrees actifs, pas seulement
celui de `REP_TRAVAIL`. Nouvelle fonction `_lister_worktrees_actifs()` :
scanne le répertoire parent de `REP_TRAVAIL` à la recherche de
répertoires frères `<NOM_PROJET>-issue<N>` (même convention que
`_chemin_worktree` dans `watcher.py`) ; pour chacun, le chemin de verrou
est recalculé via `_chemin_verrou()` (déjà importé de `watcher.py`) et le
fichier `.lock` supprimé s'il existe — uniquement une fois l'arbre de
process confirmé mort, même garde-fou que pour le verrou de
`REP_TRAVAIL`. Ces suppressions apparaissent dans le rapport de statut
renvoyé à l'interface (une étape `suppression_verrou_worktree_<nom>` par
worktree détecté, ou `suppression_verrous_worktrees` en `rien_a_faire`
si aucun). `WORKTREES.md` §4 mis à jour : la limite « verrou non libéré »
documentée depuis #338 est corrigée, plus besoin d'intervention manuelle
après un « Interrompre » pendant qu'un worktree tournait.

## 2 août 2026 — issue #339

Nettoyage de `TACHES.md` : suppression de trois items devenus obsolètes.
« Parallélisation en mode_write via git worktrees » est implémenté depuis
l'issue #337. « Rafraîchir une seule fois la ligne d'une issue quand son
décompte atteint zéro » est implémenté depuis l'issue #334. « Concurrence
limitée aux issues mode_lecture » est abandonné : le cas d'usage est trop
rare pour justifier une implémentation séparée, et le sujet sera
naturellement couvert par le système de worktrees si le besoin se
confirme. Restent inchangés : « Projet dédié à la communication CCL ↔
CCW » et « Calibration automatique du TIMEOUT — trois défauts à
corriger ».

## 2 août 2026 — issue #338

Documentation dédiée à la parallélisation mode_write via git worktrees
(#337) : nouveau fichier `WORKTREES.md` à la racine du dépôt, distinct de
`BRIDGE_AGENT_DOC.md` (manuel commun à tous les projets) pour ne pas
l'alourdir d'internals d'infrastructure. Couvre le pourquoi du mécanisme,
son design (`MAX_WRITE_PARALLELE`, premier slot sans worktree, verrou par
chemin de travail effectif, auto-extinction différée), le workflow normal
d'Alain (création d'issues, `git worktree list`, `fusionner_changelog.py`
avant merge, merge manuel branche par branche, nettoyage
`git worktree remove` + `git branch -d`), les procédures de récupération
(worktree orphelin, verrou non libéré — y compris la limite du bouton
« Interrompre », qui ne nettoie que le verrou de `REP_TRAVAIL` et pas ceux
des worktrees actifs —, `CHANGELOG-N.md` oublié, conflit de merge) et les
limites connues (`issues_en_cours` sans verrou explicite, pas d'alerte sur
l'accumulation de worktrees, `mode_lecture`/`mode_scratch` non
parallélisés). `BRIDGE_AGENT_DOC.md` §13 pointe désormais vers ce nouveau
fichier juste sous sa sous-section worktrees existante.

## 2 août 2026 — issue #337

Parallélisation des issues `mode_write` via `git worktree` : `watcher.py`
peut désormais traiter plusieurs tâches d'écriture **en parallèle**, chacune
dans un répertoire isolé sur sa propre branche, au lieu du traitement
strictement séquentiel historique. Les issues `mode_lecture`/`mode_scratch`
restent traitées séquentiellement dans `REP_TRAVAIL`, inchangées.

- Nouvelle clé `.conf` `MAX_WRITE_PARALLELE` (entier, défaut `2`) : nombre
  maximum de tâches `mode_write` concurrentes. `1` (ou `0`) = comportement
  séquentiel historique intégral, aucun thread ni worktree créé.
- `traiter_issue` (nouveau point d'entrée public) décide, pour chaque issue
  `mode_write` prête, entre traitement séquentiel classique et
  parallélisation : la première tâche détectée sans autre `mode_write` déjà
  en cours est dispatchée dans un thread ciblant `REP_TRAVAIL` directement
  (sans worktree, nécessaire pour que la boucle principale reste libre de
  détecter une deuxième tâche pendant que la première tourne) ; les
  suivantes, sous `MAX_WRITE_PARALLELE`, obtiennent chacune un worktree
  dédié (`<REP_TRAVAIL>/../<PROJET>-issue<N>`, branche
  `worktree-issue-<N>`, créés via `git worktree add`). Le corps de
  traitement existant (`_traiter_issue_synchrone`) est inchangé, à
  l'exception du chemin de travail effectif qu'il reçoit désormais en
  paramètre.
- Liste thread-safe (`threading.Lock` + liste) des tâches `mode_write`
  actuellement en thread (numéro, chemin du worktree ou `None`, thread
  Python), purgée des threads terminés à chaque décision de dispatch et en
  tête de boucle principale.
- Garde-fous à la création du worktree : chemin ou branche déjà existants,
  ou tout autre échec de `git worktree add` → repli propre sur le
  traitement séquentiel (l'issue attend qu'un slot se libère), jamais
  d'exception propagée.
- `lancer_claude` reçoit `chemin_worktree` : injecte dans le prompt, en
  worktree uniquement, un bloc d'avertissement (chemin, branche, consigne
  d'écrire l'entrée changelog dans `CHANGELOG-<N>.md` plutôt que
  `CHANGELOG.md` — voir `scripts/fusionner_changelog.py`, issue #336).
  Toutes les opérations déjà paramétrées par `cwd`/`perimetre` (backup,
  clause de périmètre du prompt, opérations git de garde-fou) reçoivent
  déjà le chemin de travail effectif (worktree ou `REP_TRAVAIL`) — aucun
  changement de signature nécessaire sur ces fonctions.
- Verrou anti-collision (#189/#322) posé par le chemin de travail effectif
  de la tâche (`REP_TRAVAIL` ou le worktree), et non plus systématiquement
  par `REP_TRAVAIL` seul : deux worktrees du même projet obtiennent deux
  verrous distincts et tournent sans s'attendre l'un l'autre.
- Fin de tâche en worktree : **aucune suppression automatique** (ni
  `git worktree remove`, ni suppression de branche) — Alain merge et pousse
  manuellement une fois le travail relu. Numéro d'issue, chemin du worktree
  et branche journalisés clairement.
- Auto-extinction (#199/#200) : ne se déclenche plus tant qu'un thread
  `mode_write` tourne encore, même au-delà de `DELAI_INACTIVITE_MIN` —
  réévaluée à chaque cycle.
- `BRIDGE_AGENT_DOC.md` §13 documente le mécanisme et `MAX_WRITE_PARALLELE`.
- Test de non-régression `tests/test_worktree_parallelisation_337.py` :
  nommage chemin/branche, création + replis (chemin/branche déjà pris),
  purge des threads terminés, scénario de bout en bout à deux issues
  `mode_write` concurrentes (première dans `REP_TRAVAIL`, seconde dans un
  worktree dédié, worktree conservé après coup), et non-régression avec
  `MAX_WRITE_PARALLELE = 1`.

## 2 août 2026 — issue #336

Création de `scripts/fusionner_changelog.py`, en préparation du futur
système de worktrees : quand CCL travaillera dans un répertoire isolé, il
écrira son entrée CHANGELOG dans `CHANGELOG-<N>.md` (N = numéro de l'issue)
plutôt que dans `CHANGELOG.md` directement, pour éviter les conflits
systématiques sur ce fichier unique quand plusieurs issues mode_write
tournent en parallèle. Ce script fusionne ces fichiers dans `CHANGELOG.md`
avant le push d'Alain.

- Scanne la racine du dépôt (`--repo`, défaut `.`) à la recherche de
  fichiers `CHANGELOG-<N>.md`, les trie par N décroissant (plus récent en
  tête, cohérent avec la convention de `CHANGELOG.md`, issue #252), et
  insère leur contenu tel quel en tête de `CHANGELOG.md`, juste après
  l'en-tête fixe (jusqu'à la ligne vide qui suit « Convention d'ajout :
  ... »). Les fichiers traités sont ensuite supprimés.
- Aucun `CHANGELOG-<N>.md` trouvé : message et sortie propre (code 0),
  `CHANGELOG.md` laissé inchangé — propriété qui rend une seconde exécution
  sans nouveaux fichiers idempotente de fait, puisque les sources du
  premier passage ont déjà été supprimées. Vérifié par test manuel (fichiers
  factices `CHANGELOG-338.md`/`CHANGELOG-340.md` dans un dépôt temporaire,
  hors du dépôt réel) : fusion correcte dans l'ordre #340 puis #338,
  suppression des fichiers sources, relance sans effet.
- Pas encore appelé automatiquement par `watcher.py` — le système de
  worktrees qui produira des `CHANGELOG-<N>.md` n'existe pas encore ;
  lancement manuel uniquement pour l'instant.

## 2 août 2026 — issue #335

Correction du radio Mode qui restait parfois figé sur « Lecture seule » après
un collage, alors que le corps collé portait bien `| MODE | écriture |` —
symptôme intermittent, corrigé par un simple F5 puis re-collage (observé à la
suite des issues #157 et suivantes).

- Cause racine : `viderFormulaire()` (appelée après chaque envoi réussi) remet
  le radio Mode sur *lecture* mais ne réinitialisait pas `dernierModeAutoDetecte`,
  la variable de garde de `detecterModeDansCorps()` (#326) qui évite de réécraser
  un choix manuel quand « rien de neuf » n'est détecté dans le corps. Si le
  corps collé ensuite portait le MÊME MODE que la détection précédente,
  `detecterModeDansCorps` voyait `valeurDetectee === dernierModeAutoDetecte` et
  ne touchait plus au radio — qui restait donc sur *lecture*, alors que ce
  n'était pas un choix manuel d'Alain mais le défaut posé de force par
  `viderFormulaire()` (qui vide aussi le corps par affectation directe de
  `.value`, sans déclencher d'événement `input`, donc sans repasser par la
  détection). Un rafraîchissement de page réinitialise cette variable JS à
  `null`, ce qui « corrigeait » silencieusement le symptôme au collage suivant.
- `static/js/app.js` (`viderFormulaire`) : ajout de `dernierModeAutoDetecte =
  null;` juste après la remise à *lecture* du radio, pour que le prochain
  collage soit toujours traité comme une détection neuve, quelle que soit la
  valeur MODE précédemment vue dans la session.
- Non modifié : `detecterProjetDansCorps`/`detecterTimeoutDansCorps`
  partagent le même schéma de garde-fou (`dernierProjetAutoDetecte`,
  `dernierTimeoutAutoDetecte`) et pourraient présenter la même faille — hors
  périmètre de cette issue, à traiter séparément si observé en pratique.

## 2 août 2026 — issue #334

Onglet Résultats : fetch unique de vérification 15s après le dépassement du
décompte TIMEOUT d'une issue — le watcher a besoin de quelques secondes après
son TIMEOUT pour poster le diagnostic et fermer l'issue ; jusqu'ici, la ligne
restait figée sur « ⌛ 0s — budget épuisé » même une fois l'issue close côté
serveur, jusqu'au prochain ↻ manuel. L'idée du `TACHES.md` (fetch au décompte
UI/médiane) est abandonnée au profit du décompte TIMEOUT réel, déjà présent
côté client, comme déclencheur — plus simple et plus fiable. Zéro polling
ajouté : un seul appel réseau par issue, une seule fois.

- `static/js/app.js` : dès que `formaterBadgeTempsRestant()` atteint la
  branche « budget épuisé », `programmerFetchDepassement()` pose un unique
  `setTimeout` de 15s (`DELAI_FETCH_DEPASSEMENT_MS`) qui appelle
  `verifierIssueApresDepassement()` — fetch de `/issue/<projet>/<numero>`
  (route existante). Un `Set` (`issuesFetchDepassementProgrammees`) garde-fou
  garantit une seule programmation par issue, même si le composant est
  rendu plusieurs fois (rendu de liste, tick/s de `majBadgesTempsRestant`).
- Issue fermée (`done`/`needs-human`) au moment du fetch : la ligne est mise
  à jour normalement (badge terminal, retrait du décompte), comme un ↻
  manuel restreint à cette seule ligne — nouvelle fonction
  `remplacerLigneIssue()`, qui reconstruit la ligne DOM via
  `construireLigneIssueDOM()` et rebranche ses gestes (clic/ctrl+clic/
  double-clic) via `brancherEvenementsLigneIssue()`, extraite de
  `rendreListeIssues()` pour être partagée sans dupliquer le câblage.
- Issue encore ouverte au moment du fetch (cas marginal de timing) : le
  badge devient « ⌛ dépassement — rafraîchir ↻ » (mémorisé dans le Set
  `issuesDepassementVerifie`, relu par `formaterBadgeTempsRestant`) et
  aucun autre fetch automatique n'est reprogrammé pour cette issue.

## 2 août 2026 — issue #333

Documentation : les deux boutons ⛔ « Interrompre » (CCL et CCW, issue
#323) sont désormais implémentés et fonctionnels — mise à jour de
`BRIDGE_AGENT_DOC.md` en conséquence, plus de renvoi mort vers
`TACHES.md`.

- `BRIDGE_AGENT_DOC.md`, §16.4 « Interrompre une issue CCW coincée » : la
  Note « un bouton [...] est prévu [...] (voir `TACHES.md`) » est
  remplacée par une description au présent de `interrompre_windows()`
  (`app/interruption.py`) : copie et exécution à distance (`VBoxManage
  guestcontrol`) de `provisioning/windows/interrompre_projet_ccw.ps1` —
  arrêt du service NSSM, vérification bornée (~5 s) que l'arbre de
  process est mort, suppression conditionnelle des `.lock` de
  `<RepDepot>\logs\verrous\`, label `needs-human` + commentaire de
  traçabilité systématiques, watcher jamais relancé automatiquement.
- `BRIDGE_AGENT_DOC.md`, §13 « Commandes utiles » : nouvelle sous-section
  « Interrompre une issue bloquée (issue #323, suite #320) », même niveau
  de détail que §16.4, pour le pendant côté CCL (`interrompre_linux()`) :
  arbre de process retrouvé par remontée `/proc/<pid>/status` (PPID),
  `SIGKILL`, attente de confirmation avant suppression du verrou —
  équivalent manuel (`kill -9` + suppression du `.lock`) inclus.
- `BRIDGE_AGENT_DOC.md`, pied de page : ligne « Dernière mise à jour »
  mise à jour (nouvelle entrée en tête, l'entrée #318 sort).
- Aucun changement de code — documentation uniquement.

## 2 août 2026 — issue #332

Le bouton « ⛔ Interrompre cette issue » (#323) tue par SIGKILL sans
prévenir que, si l'issue écrivait, le working tree du projet peut rester
PARTIEL (fichier à moitié écrit, backup présent sans le fix) — rien n'est
perdu ni poussé, mais l'état n'est pas nettoyé automatiquement et il faut
l'inspecter avant de relancer quoi que ce soit dessus.

- `static/js/app.js` — `interrompreIssue` : nouvelle `modeEcritureDepuisLabels`
  (mêmes labels que le pastillage `prefixeIssue`, ligne ~606, étendue à
  `mode_scratch`) détecte si l'issue écrivait (`mode_write` → 'ecriture',
  `mode_scratch` → 'lecture_active', aucun des deux → lecture seule, pas
  d'avertissement). Nouvelle `avertissementWorkingTree` formule le message
  (texte différent pour écriture pleine et pour lecture active — nuance :
  le garde-fou de restauration #327 tourne APRÈS claude, donc peut ne pas
  s'être exécuté avant un kill en pleine lecture active).
- Confirmation AVANT le kill (`confirm()`) : enrichie avec l'avertissement
  quand l'issue écrit — dernier moment pour renoncer. Comportement
  inchangé pour une issue en lecture seule.
- Modal de résultat APRÈS (`ouvrirModalInterrompre`, `modal-interrompre-rappel`) :
  reçoit désormais l'avertissement en paramètre et l'ajoute au rappel
  existant (relance manuelle du watcher) — `git status` dans le projet,
  annuler/repartir du commit `avant-XXX`, ne pas relancer d'issue sur ce
  projet avant working tree propre.

## 2 août 2026 — issue #330

Documentation du champ d'en-tête `MODE`, jusqu'ici absent de
`BRIDGE_AGENT_DOC.md` alors qu'il est auto-détecté depuis #326.

- **§3** — ajout de `MODE` à la liste des champs d'en-tête optionnels
  reconnus, avec un paragraphe dédié : `| MODE | … |` est détecté par
  `new_issue.py` (`detecterModeDansCorps`) exactement comme
  `TIMEOUT`/`PROJET`/`MODELE` — pré-sélectionne le radio Mode du
  formulaire puis la ligne est retirée du corps collé. Reconnaissance
  tolérante (insensible casse/accents, plusieurs libellés par valeur) et
  défaut LECTURE si le champ est absent ou non reconnu.
- **§6** — ajout d'une ligne `MODE` au tableau des champs spéciaux :
  valeurs `lecture`/`écriture`, effet (arme ou non le label `mode_write`
  via le radio du formulaire), renvoi au §5 pour le comportement des
  modes.
- **Ligne ~172 (§3, envoi en lot)** — précision : en mono-issue `MODE`
  est auto-détecté depuis l'en-tête du bloc, alors qu'en mode lot il
  reste commun à tout le lot (choisi une fois au radio du formulaire,
  jamais lu bloc par bloc).
- Volontairement **hors périmètre** : la troisième valeur (« lecture
  active » / `mode_scratch`) n'est PAS ajoutée à ces deux endroits — elle
  reste documentée uniquement au §5 (issue #327), car cette issue ne
  documente que les deux valeurs fonctionnelles au sens de la détection
  `new_issue.py`/formulaire.
- Pied de page de `BRIDGE_AGENT_DOC.md` mis à jour selon la convention
  §10 (nouvelle entrée en tête, glissement des deux précédentes ; l'entrée
  #299 sort du pied de page — déjà disponible dans `CHANGELOG.md`).

## 2 août 2026 — issue #327

Implémentation du mode « lecture active » (`mode_scratch`) côté
`watcher.py` — préparé formulaire/en-tête par #326, resté volontairement
inactif (une issue `mode_scratch` sans `mode_write` était traitée comme
lecture seule). Écriture confinée pour les outils d'analyse qui exigent un
vrai fichier de config sur disque (linters, eslint flat config ≥ 9, ...),
impossible à satisfaire en lecture seule.

**Mode à trois valeurs, plus un booléen empilé.** `autoriser_ecriture: bool`
pilotait CINQ points de décision (flag `--dangerously-skip-permissions`,
bloc de garde-fou du prompt, backup, garde-fou `configs/*.conf` #318,
étiquette de calibration TIMEOUT) — insuffisant pour un 3e mode. Remplacé
par `MODE_LECTURE`/`MODE_LECTURE_ACTIVE`/`MODE_ECRITURE` (nouvelle constante
`LABEL_SCRATCH = "mode_scratch"`), déduits des labels par la nouvelle
`_deduire_mode` (priorité `mode_write` > `mode_scratch` > lecture seule par
défaut) et lus par les cinq points ci-dessus — un futur 4e mode n'ajoutera
qu'une valeur, pas cinq retouches éparses. `lancer_claude` prend désormais
`mode` (plus `autoriser_ecriture`) et `chemin_scratch` ; les deux tests
existants qui l'appelaient directement (`test_nettoyage_arbre_247.py`,
`test_orphelin_verrou_perime_322.py`) sont mis à jour en conséquence.

**Chemin scratch** : `/tmp/bridge_scratch_<projet>/` (`<projet>` = `CFG.nom`,
validé strictement — aucun `../`, aucun séparateur de chemin — jamais dérivé
d'une valeur fournie par l'issue). Créé par le watcher juste avant le
premier lancement de claude en lecture active, supprimé dans un `finally`
(succès/échec/timeout confondus, même esprit que `_nettoyer_arbre_claude`).

**Défense en profondeur, niveau 1 + niveau 2** (même schéma que le
garde-fou `configs/*.conf`, #318) :
- **Niveau 1 (prompt)** : nouveau bloc de garde-fou dédié dans
  `lancer_claude`, distinct des deux blocs existants — chemin scratch exact,
  interdiction d'écrire ailleurs (notamment REP_TRAVAIL), interdiction de
  `git commit`/`git push`/commande destructrice, rappel que le scratch est
  éphémère et que le livrable reste un rapport de lecture.
  `--dangerously-skip-permissions` est ajouté (la lecture active doit
  pouvoir écrire dans le scratch), désarmant les mêmes protections claude
  que l'écriture libre — d'où le niveau 2.
- **Niveau 2 (détection technique a posteriori)** : nouvelles
  `_statut_git_rep_travail`/`_restaurer_rep_travail_modifie`, sur le modèle
  de `_empreinte_configs`/`_restaurer_configs_modifies` (#318) — empreinte de
  `git status --porcelain -uall` sur REP_TRAVAIL avant la première tentative,
  comparée après chaque tentative. Toute écriture détectée (fichier modifié,
  neuf ou supprimé) est restaurée (`git checkout`/`git clean` ciblés) et
  l'issue est marquée en échec définitif (`needs-human`, pas de nouvelle
  tentative) avec un message explicite. Le scratch (`/tmp`, hors REP_TRAVAIL)
  n'apparaît jamais dans cette empreinte par construction, donc n'est jamais
  emporté par la restauration.

**Backup et garde-fou configs** : aucun backup projet en lecture active
(comme la lecture seule — le filet est le niveau 2, pas un commit de
sauvegarde). Le garde-fou technique `configs/*.conf` (#318) est étendu : il
s'armait uniquement en mode écriture, il couvre désormais aussi la lecture
active (`mode != MODE_LECTURE`), cohérent avec le fait que ce mode arme
aussi `--dangerously-skip-permissions`.

**Calibration (§19)** : nouvelle étiquette `"scratch"` (fonction
`_etiquette_calibration`), distincte de `"read"`/`"write"`, appliquée aux
trois points de calibration (succès, timeout, échec définitif) —
`etat_timeout.json` et `historique_durees.json` gagnent une population
`projet|TYPE|scratch` propre, pour ne pas refaire le mélange de populations
que #326 avait corrigé côté UI. `app/issues.py` (estimation de durée d'une
issue ouverte, badge de progression) mis à jour en cohérence : `mode_scratch`
y était jusqu'ici classé à tort dans la population `"read"`.

`templates/index.html` : le radio « Lecture active » n'est plus marqué
« réservé » (le mode est désormais fonctionnel) ; `app/issues.py` (table
`MODES`) et le commentaire près de `LABEL_ECRITURE`/`LABEL_SCRATCH` dans
`watcher.py` mis à jour en conséquence.

Tests (`tests/test_lecture_active_327.py`, faux `claude` **et** faux `gh`,
aucun appel réseau) : déduction du mode depuis les labels (les quatre cas,
priorité `mode_write` > `mode_scratch`) ; validation stricte de
`_chemin_scratch` ; traitement complet (`traiter_issue`) d'une lecture
active qui n'écrit que dans le scratch → succès, REP_TRAVAIL inchangé,
scratch nettoyé ; traitement complet d'une lecture active qui écrit dans le
projet hors scratch → détecté, restauré (fichier modifié restauré à son
contenu d'origine, fichier neuf supprimé), `needs-human` posé, jamais
`done`.

`TACHES.md` : entrée « mode_scratch » retirée (implémentée).

## 2 août 2026 — issue #326

Détection automatique du MODE dans l'en-tête + mode à valeurs extensibles,
préparation lecture active/mode_scratch (issue #326). Deux problèmes réglés
ensemble : (1) contrairement à TIMEOUT/PROJET/titre, le champ `| MODE | … |`
était GÉNÉRÉ à l'envoi mais jamais LU depuis le corps collé — Alain cochait
« écriture » à la main par habitude même pour des tâches en réalité en
lecture seule, ce qui rangeait des lectures dans la population « write » et
faussait la calibration TIMEOUT (§19, clé projet|TYPE|mode) ; (2) le mode
était un booléen en dur (`autoriser_ecriture` déduit du seul label
`mode_write`), incapable de porter un futur 3e mode.

Frontend (`static/js/app.js`) : nouveau `detecterModeDansCorps`, calqué sur
`detecterTimeoutDansCorps`, branché sur l'input du corps — lit `| MODE | … |`
via `lireChampEntete` (aucune regex dupliquée), reconnaît la valeur de façon
tolérante (casse/accents, plusieurs libellés par mode : « écriture »/
« write »/`mode_write` ; « lecture active »/« scratch »/`mode_scratch` ;
« lecture »/« lecture seule »/« read »/`mode_read`), coche le bon radio,
retire la ligne MODE du corps (comme TIMEOUT/PROJET) et met à jour la
couleur du bouton d'envoi. **MODE absent ou non reconnu → LECTURE forcée**
(défaut sûr, cohérent avec le reset après envoi). Neutralisé en mode lot
(le MODE reste commun à tout le lot, DOC §3, inchangé).

`templates/index.html` : 3e radio `lecture_active` entre lecture et
écriture (ordre du moins au plus permissif), badge « scratch (mode_scratch,
réservé) » + tooltip précisant que ce mode n'est pas encore fonctionnel côté
watcher. Bouton d'envoi à 3 couleurs (`COULEURS_MODE`) : lecture → noir,
lecture active → bleu, écriture → rouge (inchangé, réservé à l'écriture
pleine, la plus risquée).

`app/issues.py` : nouvelle table `MODES` ({valeur radio → (libellé
français, label GitHub)}) lue à la fois par `construire_body` (champ
`| MODE | … |`) et `construire_labels` (pose du label technique) — remplace
les deux tests booléens en dur (`"ÉCRITURE" if mode == "ecriture" …` /
`if mode == "ecriture": labels.append("mode_write")`). Un futur 4e mode ne
demande qu'une ligne dans cette table.

**`mode_scratch` reste RÉSERVÉ, watcher.py non touché** : cette issue ne
porte pas l'implémentation de la lecture active côté watcher (issue séparée
à venir) — juste documenté (commentaire près de `LABEL_ECRITURE`) qu'une
issue portant `mode_scratch` sans `mode_write` est traitée comme lecture
seule par le watcher actuel (`autoriser_ecriture` ne teste que
`LABEL_ECRITURE`), comportement sûr. Backlog `TACHES.md` renommé en
cohérence (`mode_tmp_write` → `mode_scratch`, vocabulaire retenu par #326).

## 2 août 2026 — issue #325

Retrait de `TACHES.md` de l'entrée backlog « Bouton Interrompre dans
l'onglet CCW » (procédure manuelle nssm restart + suppression des
`.lock`), désormais implémentée — et dépassée — par #323 (suite #320) :
le bouton « ⛔ Interrompre cette issue » a été ajouté dans l'onglet
Résultats, pas l'onglet CCW, et couvre CCL comme CCW. Même convention de
retrait que #317 (retiré par #321) et les entrées PERIMETRE (#319) :
suppression pure de la section obsolète, rien d'autre touché.

## 2 août 2026 — issue #324

Ajout au backlog `TACHES.md` d'une entrée (pas d'implémentation) :
« Rafraîchir une seule fois la ligne d'une issue quand son décompte atteint
zéro ». Née d'une session où le décompte figé côté navigateur
(`majBadgesTempsRestant`, jamais re-fetché depuis #270) a fait douter à
répétition de l'état réel d'issues déjà closes (#320/#322/#323). Idée :
au passage à « ⌛ 0s — budget épuisé », déclencher UN SEUL fetch ciblé de
l'issue via la route existante `/issue/<projet>/<numero>` (`issue_detail`)
plutôt qu'un re-fetch périodique de toutes les issues comme avant #270 —
distinction explicitée dans l'entrée pour qu'une future implémentation ne
réintroduise pas le polling banni par #270 (~3840 pts/h de quota GraphQL,
cf. #263). Point de conception laissé ouvert : comportement au dépassement
légitime (re-fetch à intervalle long vs. badge « rafraîchir » manuel), avec
anti-abus à prévoir si l'option de re-fetch est retenue.

## 2 août 2026 — issue #323 (suite #320)

Bouton **« ⛔ Interrompre cette issue »** dans l'onglet Résultats, sur toute
issue ouverte ni `done` ni `needs-human` — remplace l'intervention manuelle
hors interface (kill + nettoyage de verrou à la main) qu'exigeait jusqu'ici
un watcher bloqué (verrou orphelin, process pendu). Reprise de #320,
abandonnée 3 fois faute de `TIMEOUT` suffisant (600s ne couvrait pas
`watcher.py` + route Flask + logique CCW + modal front) ; `TIMEOUT` porté à
1800s pour cette reprise. **Contrainte centrale** : interrompre UNE issue ne
sacrifie jamais les autres issues en file pour le même watcher — elles
restent ouvertes sur GitHub, simplement en attente d'une relance MANUELLE
(bouton « Lancer watcher » côté CCL, onglet CCW côté CCW-Watcher ; aucun
rallumage automatique ici, à la différence de #202).

- Nouvelle route **`POST /interrompre`** (`app/interruption.py`) : reçoit
  `{depot, numero, labels}`, résout le projet via `projet_par_depot` (nouveau
  dans `app/projets.py`) — **toujours par le champ DEPOT du `.conf`**, jamais
  déduit du nom projet ni du basename de `REP_TRAVAIL` (trois clés distinctes
  qui peuvent diverger, ex. projet « echecs » / dépôt `AlChess` / répertoire
  `~/NicLink`). Chaque étape renvoie un statut à **trois valeurs**
  (`succes`/`rien_a_faire`/`echec`) + message ; une étape en échec n'arrête
  pas les suivantes, sauf la suppression du verrou, volontairement **sautée**
  si l'arbre de process n'est pas confirmé mort. Statut global dérivé : `ok`
  / `succes_partiel` / `echec_critique` (arbre non tué → lock **non**
  nettoyé, pour ne jamais risquer un double traitement). Label `needs-human`
  + commentaire `⛔ Interrompu via new_issue.py` posés dans TOUS les cas
  (sortie du circuit + trace), avant même le résultat des étapes techniques.
  - **for-linux** : arbre de process du watcher (`logs/watcher-<nom>.pid` +
    toute sa descendance, dont l'éventuel claude en session séparée,
    §13/#247) énuméré par **remontée `/proc` via PPID** — jamais par nom
    d'exécutable — puis `SIGKILL`, attente bornée (~5s) de disparition
    effective avant de supprimer le verrou par **nom exact**
    (`watcher._chemin_verrou` réutilisée telle quelle, jamais redupliquée),
    puis re-vérification (verrou frais réapparu → signalé comme course #202
    probable, jamais resupprimé en boucle). Piège découvert en testant :
    le process watcher est un enfant DIRECT du process Flask
    (`app/watchers.py:demarrer_watcher`) jamais attendu (`wait()`) — après
    `SIGKILL` il reste **zombie** et `os.kill(pid, 0)` le signale encore
    vivant indéfiniment ; `_reaper_best_effort` (`os.waitpid(..., WNOHANG)`)
    corrige ce faux positif. `FileNotFoundError` sur le verrou = `rien_a_faire`
    (libéré normalement), pas un échec.
  - **for-windows** : nouveau script `provisioning/windows/
    interrompre_projet_ccw.ps1` (poussé + exécuté via guestcontrol, pattern
    `app/ccw.py` — service et répertoire du projet résolus dynamiquement via
    `_lister_projets_vm`, jamais codés en dur malgré l'exemple `CCW-Watcher`
    / `C:\CCW\Bridge_Agent` de l'issue) : arrêt du service NSSM, vérification
    + kill ciblé de l'arbre resté vivant (remontée par `ParentProcessId`,
    même logique PPID que côté Linux), suppression des `.lock` du dossier
    `logs\verrous` du projet **seulement** si l'arbre est confirmé mort.
    Non exécuté contre une VM réelle (pas d'environnement CCW disponible ici
    — comme `finaliser_projet_ccw.ps1` en son temps).
- `templates/index.html` / `static/js/app.js` : bouton `interrompreIssue()`
  dans `construireHtmlIssue` (dépôt lu depuis le `<select id="projet">`
  peuplé côté serveur « nom — depot », jamais déduit du nom ; labels lus
  depuis le cache localStorage du détail déjà affiché). Modal dédiée
  (`#modal-interrompre`) détaillant **chaque étape** (statut + message), pas
  seulement le résultat global, avec rappel de la relance manuelle adapté à
  l'agent (CCL vs CCW) et alerte explicite en cas de `succes_partiel` /
  `echec_critique` (« vérifier avec ps/Gestionnaire des tâches avant de
  relancer »). Avertissement discret si la VM CCW n'est pas démarrée
  (`vm_running` dans la réponse).
- Testé (hors modal/CCW, sans VM disponible) : arbre de process réel
  (`sh` + enfant `sleep`) tué + confirmé mort + verrou nommé supprimé +
  re-vérifié ; cas `rien_a_faire` (aucun watcher, aucun verrou) ;
  `projet_par_depot` contre les `.conf` réels du dépôt.

## 2 août 2026 — issue #322

Dernier trou résiduel du cycle de vie verrou/claude comblé : si le watcher
meurt BRUTALEMENT (kill -9, coupure de courant, plantage Python non
capturé) pendant qu'un claude tourne, aucun `finally` ne s'exécute — le
claude devient orphelin ET le verrou reste posé. Au démarrage suivant, le
watcher voyait ce verrou, le déclarait périmé et le REPRENAIT sans
vérifier qu'un claude orphelin de l'ancien contexte tournait encore,
risquant de lancer un second claude dans le même `REP_TRAVAIL` pendant que
l'orphelin y écrivait toujours (le périmètre empêche de sortir du dossier,
pas deux process d'y entrer en collision). Fermé PAR CONSTRUCTION, au seul
moment qui compte (la reprise d'un verrou périmé) — pas par une
surveillance externe (cron), aveugle quand le watcher est éteint.

- `watcher.py` :
  - `lancer_claude` accepte un paramètre `verrou` optionnel ; une fois le
    `Popen` du claude réussi, `_maj_verrou_pgid` consigne son pgid
    (== pid, `start_new_session=True`) dans le fichier verrou via un
    nouveau champ `claude_pgid=<n>`, en préservant les champs existants
    (`pid=`/`projet=`/`rep=`). Le verrou est posé par `acquerir_verrou`
    AVANT le lancement de claude : le pgid n'est donc connu qu'après le
    `Popen`, d'où cette mise à jour a posteriori plutôt qu'à la pose.
  - `_lire_pgid_verrou` : lit ce champ, `None` si absent (ancien format,
    ou watcher mort avant même le lancement de claude) — traité sans
    erreur, aucun kill tenté dans ce cas.
  - `_nettoyer_orphelin_verrou_perime` (appelée depuis `acquerir_verrou`,
    juste avant `verrou.unlink()`, uniquement sur la branche verrou
    PÉRIMÉ) : garde-fou anti-reboot à trois conditions cumulées avant
    tout kill — verrou périmé (déjà garanti par l'appelant), un process
    de ce pgid existe encore (`_lister_processus_pgid`, réutilisée telle
    quelle), et sa ligne de commande contient bien « claude » (identifier
    par ce que le process EST, jamais tuer aveuglément, même esprit que
    #247 point 4). Si les trois sont réunies : `os.killpg(pgid,
    SIGKILL)` sur ce seul groupe, un `log.warning` par process tué
    (PID + ligne de commande), attente bornée (5s) de la disparition
    effective. Un pgid mort ou recyclé après un reboot (PID/pgid
    réattribués) ne provoque aucun kill. POSIX uniquement, gardé par
    `os.name != "nt"` côté appelant (sous Windows, objet Job — pas de
    pgid, la question ne se pose pas dans les mêmes termes).
    Best-effort strict, comme `_nettoyer_arbre_claude` (#249) : toute la
    logique est enveloppée dans un garde-fou total (`_lister_processus_
    pgid` peut lever `OSError`, `os.killpg` une `PermissionError`) — une
    erreur du nettoyage journalise et laisse la reprise du verrou suivre
    son cours normal, jamais de remontée qui ferait échouer l'acquisition
    du verrou ni le traitement de l'issue.
  - `traiter_issue` : passe désormais le verrou courant à `lancer_claude`.
- `tests/test_orphelin_verrou_perime_322.py` (nouveau, sur le modèle de
  `tests/test_nettoyage_arbre_247.py`) : orphelin réellement tué à la
  reprise d'un verrou périmé (et journalisé) ; garde-fou anti-reboot sur
  pgid vivant mais pas un claude, et sur pgid mort/recyclé — aucun kill
  dans ces deux cas ; verrou d'ancien format (sans `claude_pgid`) repris
  sans erreur ; `lancer_claude` consigne bien le pgid dans le verrou
  fourni.

## 2 août 2026 — issue #321

Champ de recherche par TITRE dans l'onglet Résultats de `new_issue.py`,
répondant au backlog ouvert par #317 suite au doublon #315/#316 — sous
une forme différente de l'idée initiale (titre ET corps) : décision de
#321 de rester sur le titre seul, plus rapide et suffisant pour
retrouver un sujet déjà traité. Entrée backlog correspondante retirée
de `TACHES.md`.

- `app/issues.py` : nouvelle route `recherche_issues` (une par projet,
  comme `issues_liste`) — `gh issue list --state all --limit <portée>`
  (state `all` : on cherche justement une issue déjà fermée/done),
  `--limit` réutilisant `_limite_issues_requete`/`LIMITE_ISSUES_MIN`/
  `LIMITE_ISSUES_MAX` sans dupliquer de borne. Filtrage sur le titre
  uniquement, insensible casse+accents via `_normaliser_recherche`
  (NFKD + suppression des diacritiques + casefold). Même gestion
  d'erreur (timeout/gh introuvable/returncode) qu'`issues_liste`.
- `app/__init__.py` : route `/recherche-issues/<nom_projet>`.
- `static/js/app.js` : champ texte + champ « portée » (défaut 15/projet,
  borné à `LIMITE_ISSUES_MAX`, réglage DISTINCT de la limite d'affichage
  de l'onglet) dans la barre de contrôles, déclenchement au clic (ou
  Entrée) uniquement — jamais à la frappe, cohérent avec #270. La
  recherche porte sur les projets actuellement sélectionnés dans les
  filtres (un appel `gh` par projet, portée non cumulative), ratisse
  toute la portée sans s'arrêter au premier match, respecte le filtre
  « 👷 Ouvriers », et agrège les échecs par projet sans annuler les
  autres. `construireLigneIssueDOM` extrait de `rendreListeIssues` pour
  être partagée avec la nouvelle fenêtre de résultats, qui réutilise
  telles quelles `copierReponseDepuisBadge`/`copierDiffDepuisBadge`/
  `copierToutEtDiffDepuisBadge` (badges ✅/Diff/All) et une nouvelle
  `afficherIssueRecherche` (double-clic) chargeant dans sa PROPRE zone
  de détail (`#zone-issue-recherche`), autonome de celle de l'onglet —
  plusieurs corps peuvent s'enchaîner sans se fermer mutuellement.
  `demarrerRedimTitre`/`finRedimTitre` adaptés pour redimensionner la
  colonne titre de la fenêtre indépendamment de celle de l'onglet, sans
  persister ce redimensionnement en localStorage.
- `templates/index.html` : barre de recherche statique dans l'onglet
  Résultats + modal `#modal-recherche-titre` (liste + zone de détail
  propres, bouton Fermer).
- `static/css/style.css` : styles de la barre et du modal.
- `TACHES.md` : retrait de l'entrée de backlog « Champ de recherche
  texte dans l'onglet Résultats » (#317), désormais implémentée.

La limite d'affichage par défaut de l'onglet (`LIMITE_ISSUES_DEFAUT`,
30) reste inchangée — le 15 par défaut ne concerne que la portée de
recherche, un réglage distinct.

## 2 août 2026 — issue #319

`TACHES.md` : retrait de l'entrée de backlog « Garde-fou technique sur
la modification de PERIMETRE » (diagnostic du 31/07/2026, issue #298),
désormais implémentée — sous une forme différente de l'idée initiale
(détection/confirmation) : décision finale du 02/08/2026 d'interdire
purement et simplement toute modification de `configs/*.conf` par
CCL/CCW (issue #318, commit 65e81c5). Suppression simple, même
convention que les issues #310/#312. Reste du fichier inchangé,
notamment « Champ de recherche texte dans l'onglet Résultats de
new_issue.py » (#317), toujours en attente sans implémentation.

## 2 août 2026 — issue #318

Interdiction totale de modification de `configs/*.conf` par CCL/CCW, y
compris en mode_write (diagnostic #298, décision du 02/08/2026 : pas de
mécanisme de détection/confirmation, interdiction pure et simple —
seul Alain modifie ces fichiers à la main ou via l'onglet Configuration
de `new_issue.py`).

- `consignes/globales.md` : nouvelle règle explicite — CCL/CCW ne
  modifie JAMAIS `configs/*.conf`, même si une issue le demande en
  toutes lettres ; en cas de demande de ce type, refuser cette partie
  de la tâche, l'expliquer dans le rapport de clôture, ne rien
  committer sur ce point.
- `watcher.py` : garde-fou technique en deux temps.
  - `_detecter_demande_modif_configs` : repérage best-effort (regex sur
    un chemin `configs/*.conf` dans le corps) juste avant le lancement
    de claude en mode_write — purement informatif (WARNING journalisé),
    ne bloque rien.
  - `_empreinte_configs` / `_restaurer_configs_modifies` : instantané
    intégral (contenu brut) de `configs/*.conf` pris une seule fois
    avant la première tentative de `traiter_issue`, comparé après
    CHAQUE tentative (succès ou échec). Toute modification, création ou
    suppression détectée est annulée automatiquement (restauration du
    contenu d'origine, ou suppression d'un fichier apparu), avec un
    WARNING explicite par fichier concerné — sans jamais faire échouer
    le reste du traitement de l'issue (best-effort, aucune exception
    propagée). `configs/` est commun à tous les projets (partagé par ce
    `watcher.py`), donc l'ensemble du dossier est protégé, pas
    seulement le `.conf` du projet en cours de traitement.
- `BRIDGE_AGENT_DOC.md` (§12) : le paragraphe « Exception » sur
  `configs/*.conf` précise désormais que cette exception vaut
  uniquement pour Alain (à la main ou via l'onglet Configuration),
  jamais pour CCL/CCW, même en mode_write, et renvoie vers le
  garde-fou technique de `watcher.py`.

## 2 août 2026 — issue #315

`BUILD_WINDOWS_CCW.md` : ajout de la checklist Rummikub (build validé),
insérée avant l'entrée Scrabble (plus récente en premier) — clone
`Z:\CCW\rummikub`, script `build\rebuild_rummikub.bat` (6 étapes),
`rummikub.spec` en liste explicite des `datas` (`src/rummikub/ui/web/`,
aucun `collect_tree` en bloc), TIMEOUT de référence 1200s (build réel
~333s), et les deux garde-fous de taille distincts introduits par
l'issue #57 (dist non compressé vs installeur compressé étant deux
grandeurs différentes) : `dist\Rummikub\` non compressé 28 712 051
octets (~28,7 Mo, fourchette 20-45 Mo) et `Rummikub-Setup.exe`
compressé 12 778 092 octets (~12,18 Mo, fourchette 5-25 Mo).

## 2 août 2026 — issue #314

`BRIDGE_AGENT_DOC.md` (§12.1, juste après le tableau des trois couches
de consignes) : ajout d'un renvoi explicite pour un Claude en
conversation (celui qui rédige une issue avant envoi, ex.
ClaudeRummikub) vers `consignes/globales.md` via `curl`, sur le même
modèle que le renvoi déjà existant vers `BRIDGE_AGENT_DOC.md` lui-même
(§9). Jusqu'ici le tableau décrivait l'injection automatique par
`watcher.py` à l'exécution (CCL/CCW) sans jamais pointer un Claude en
conversation vers le contenu réel de `globales.md` — notamment le
garde-fou backup/reset ajouté par l'issue #313, invisible avant que
l'issue parte à l'exécution.

## 2 août 2026 — issue #313

`consignes/globales.md` : ajout de deux garde-fous mutualisés à tous les
projets (injection automatique, aucune modification de `CONTEXTE.md` par
projet nécessaire). (1) Garde-fou backup/reset : le commit de sauvegarde
(`git add -A`) peut faire passer sous suivi git des dossiers auparavant
non trackés (ex. `.tools/`, `installeur/output/`) ; si le script exécuté
ensuite se termine par une opération git destructive (`reset --hard`,
`clean -fd`), ces dossiers seraient effacés du disque — vérifier via
`git status`/`git show --stat` et détracker (`git rm --cached`) avant de
lancer un tel script. Problème constaté et corrigé au cas par cas sur
Scrabble et Rummikub (issues #306, #311). (2) Renvoi vers
`BUILD_WINDOWS_CCW.md` (dépôt bridge_agent, racine) avant de proposer une
issue de build ou de modification de pipeline sur un projet ayant un
script de build Windows (PyInstaller/Inno Setup) — documente le pattern
de staging local et l'extension du PÉRIMÈTRE associée (issue #297/#299).

## 2 août 2026 — issue #312

`TACHES.md` : retrait des trois entrées de backlog désormais
implémentées — « Capture stderr CCL dans watcher.py » et « Vérification
pre-flight de la validité du token CCL » (issue #309, commit bcd3a11)
et « Archivage de logs/historique_durees.json » (issue #310, commit
6df2f44). Suppression simple, sans section « Terminé » : c'est déjà la
convention établie pour ce fichier (cf. commit dcecb85). Reste du
fichier inchangé, notamment « Garde-fou technique sur la modification
de PERIMETRE » (#298) et « Concurrence limitée aux issues mode_lecture »,
toujours en attente sans implémentation.

## 2 août 2026 — issue #310

Nouveau script `scripts/archiver_historique.py`, lancement manuel
uniquement — jamais appelé par `watcher.py` (issue #310) — pour purger
`logs/historique_durees.json`, qui accumule toutes les entrées depuis
mai 2026 sans purge et grossit à chaque clôture d'issue. Diagnostic
préalable (lecture du code, pas de conséquence sur ce script) :
`maj_calibration_timeout` (EWMA, calibration TIMEOUT réelle, issue
#221, `watcher.py`) est purement incrémentale et ne lit/écrit jamais
`historique_durees.json` (seulement `etat_timeout.json` et
`etat_ambiance.json`) — l'archivage n'a donc aucun impact sur elle ;
`estimer_duree` (badge de fiabilité à la création d'une issue, issue
#108, `app/issues.py`) recalcule en revanche une médiane à partir de
tout l'historique transmis, filtré par projet/type/mode, donc un
archivage réduit potentiellement le nombre d'échantillons par
catégorie.

Fonctionnement : pour chaque combinaison (projet, type, mode), les
`--n-min` entrées les plus récentes (défaut 20) sont TOUJOURS
conservées quelle que soit leur ancienneté ; au-delà de ce plancher,
les entrées antérieures à `--seuil-mois` (défaut 6) sont déplacées
vers `logs/historique_durees_archive_<année>.json` (une entrée va
dans le fichier de SON année ; fusion avec l'archive existante si déjà
présente). Les entrées à date illisible/absente sont conservées par
prudence, jamais archivées. N_MIN_DEFAUT = 20 choisi en cohérence avec
`SEUIL_ESTIM_SUR = 15` (`app/issues.py`) : une catégorie déjà au badge
"sûr" (vert, n > 15) avant archivage y reste après, avec une marge de
confort de 5. Le rapport console liste, par catégorie, le nombre total
avant, archivé et conservé, avec une alerte si une catégorie repasse
sous le seuil "sûr". `--dry-run` simule sans rien écrire. Écriture
atomique (`tempfile` + `os.replace`, même motif que `watcher.py`) ;
`etat_timeout.json` et `etat_ambiance.json` ne sont ni lus ni écrits
par ce script.

Testé sur une copie temporaire (`/tmp`, hors dépôt) avec des seuils
réduits pour valider le mécanisme (archivage, fusion sur double
exécution, conservation du total d'entrées) avant exécution réelle sur
`logs/historique_durees.json` : avec les valeurs par défaut (6 mois),
aucune entrée n'est encore assez ancienne (données depuis le
24/05/2026 seulement) — 774 entrées conservées, 0 archivée, fichier
inchangé après exécution. `etat_timeout.json` vérifié inchangé (même
empreinte MD5) ; `etat_ambiance.json` n'existe pas encore sur cette
machine et n'a pas été créé par ce script.

## 2 août 2026 — issue #309

Diagnostic CCL amélioré dans `watcher.py`, zone `lancer_claude()` (issue
#309) — suite à l'incident #279 où plusieurs issues avaient échoué en
~1,2s avec le message générique "Erreur inconnue" (cause réelle : token
CCL expiré), sans aucune indication exploitable dans le log. Deux ajouts
dans la même zone de code : **A)** capture stderr — au retour de
`communicate()`, si le process claude échoue (code de retour non nul),
les 2000 premiers caractères de son stderr sont journalisés en WARNING
(`_extrait_stderr`, tronque avec mention du nombre total de caractères
au-delà de cette limite, pour éviter un dump de plusieurs Mo tout en
gardant de quoi diagnostiquer une panne d'auth/réseau) ; **B)**
vérification pre-flight du token — nouvelle fonction
`verifier_preflight_token()`, appelée une seule fois par issue dans
`traiter_issue()` juste avant la boucle de tentatives (pas à chaque
tentative), qui lance un `claude --print` court (stdin vide, timeout 5s)
et recherche dans stdout+stderr des signatures d'authentification
manquante/expirée (`SIGNATURES_TOKEN_EXPIRE` : "not logged in", "/login",
"invalid api key", etc.) ; si détecté, WARNING explicite invitant à
relancer `claude` interactivement et taper `/login`. Choix délibéré de
passer une entrée vide via **stdin** plutôt que l'exemple littéral de
l'issue (`claude -p ""`) : un argument positionnel vide est rejeté
immédiatement par la validation d'arguments du CLI ("Input must be
provided...") AVANT toute vérification d'authentification, quel que
soit l'état du token — inutilisable comme sonde ; passé en stdin, l'appel
atteint bien le contrôle d'authentification. Le pre-flight ne bloque
jamais le traitement (toute exception — timeout, `claude` introuvable —
est avalée silencieusement, aucune tentative n'est empêchée) et est
sauté en dry-run. Comportement nominal (issues qui réussissent) inchangé
: vérifié par exécution manuelle de `verifier_preflight_token()` sur
l'environnement courant (aucune exception, aucun faux positif avec un
token valide) et simulation d'un échec de process (stderr correctement
tronqué et journalisé). Commit local, pas de push.

## 1er août 2026 — issue #299

Crée `BUILD_WINDOWS_CCW.md` à la racine du dépôt (issue #299), dédié au
contenu spécifique-projet des builds Windows délégués à CCW — jusqu'ici en
voie d'accumulation dans `BRIDGE_AGENT_DOC.md` (§16.3) à chaque nouveau
projet buildé (Scrabble déjà, Rummikub en préparation). Le fichier reprend
le pattern général de staging local documenté par l'issue #297 (corruption
de fichiers sur `\\VBOXSVR\CCW_Share`, contournement via
`C:\Temp\<Projet>Build`, extension obligatoire du `PERIMETRE` dans
`configs\ccw.conf`), ajoute une checklist type à remplir par projet
buildé (clone CCW, script de build, `.spec` — datas explicites ou
`collect_tree` en bloc avec mise en garde suite à l'incident dump
wiktionnaire 8,2 Go sur Scrabble du 31/07/2026 —, TIMEOUT de référence,
taille/hash de l'artefact final), et une première entrée déjà remplie
pour Scrabble (`Z:\CCW\scrabble`, `build\rebuild_scrabble.bat` en 7
étapes fix #338, `scrabble.spec` corrigé en liste explicite, TIMEOUT
1200s, installeur de référence 26 546 846 octets, SHA256
`d52e101f8758a1b107011adf0bc1a04102bce48d3283248650019ba101ef3254`).
En contrepartie, la note « staging local » ajoutée au §16.3 de
`BRIDGE_AGENT_DOC.md` par l'issue #297 est remplacée par un renvoi de
deux lignes vers ce nouveau fichier ; pied de page de `BRIDGE_AGENT_DOC.md`
glissé (#299 en tête, #287 conservée, #297 conservée en dernière position
avec note du remplacement, #285 sorti).

## 31 juillet 2026 — issue #297

Documente au §16.3 « Procédure — builder un projet Windows » de `BRIDGE_AGENT_DOC.md` le pattern de staging local pour les builds Windows CCW (issue #297), jusqu'ici décrit uniquement dans le `CONTEXTE.md` propre au projet Scrabble et donc invisible pour toute autre instance CCL/CCW ayant le même besoin (ex. Rummikub, même stack PyInstaller + Inno Setup, prévoit ce pattern dès son premier script de build). Contexte : diagnostic du 31/07/2026 sur Scrabble — les builds PyInstaller + Inno Setup produisaient des fichiers tronqués/corrompus lorsqu'ils tournaient directement sur le partage VirtualBox `\\VBOXSVR\CCW_Share` (fix #338). Nouvelle note ajoutée juste après le paragraphe « Note safe.directory », avant la sous-section 16.4 : **contournement standard** — le script de build copie les sources vers un répertoire local à la VM (`C:\Temp\<Projet>Build` ou équivalent), construit entièrement là, puis ne recopie vers le partage que l'artefact final ; **conséquence obligatoire** — ajouter ce chemin local au `PERIMETRE` de `configs\ccw.conf` (liste séparée par virgules), sans quoi CCW refuse à juste titre d'en sortir et bloque légitimement le build ; **rappel** — avant d'ajouter un nouveau projet à builder sous Windows, vérifier si son script de build suit déjà ce schéma et, si oui, étendre le `PERIMETRE` en conséquence. Pied de page de `BRIDGE_AGENT_DOC.md` glissé (issue #297 en tête, #287 et #285 conservées comme les deux entrées les plus récentes parmi les issues modifiant cette doc, #281 sorti). Aucun fichier `.py`/`.js` modifié (documentation seule), aucune section renumérotée.

## 30 juillet 2026 — issue #287

Documente au §16 « Agent Windows CCW » de `BRIDGE_AGENT_DOC.md` la procédure d'interruption d'une issue CCW coincée (issue #287), jusqu'ici purement manuelle et non écrite nulle part. Nouvelle sous-section **16.4 « Interrompre une issue CCW coincée »** insérée après la note sur `safe.directory` (fin du §16), avant le §17 : **symptôme** — le watcher `CCW-Watcher` détecte bien l'issue à chaque cycle mais log en boucle, sans jamais progresser, « Issue différée : un autre traitement détient déjà le verrou sur `\\VBOXSVR\CCW_Share\` » ; **cause** — un fichier verrou laissé dans `C:\CCW\Bridge_Agent\logs\verrous\` n'a pas été nettoyé (process tué brutalement, ou redémarrage NSSM du service sans libération propre du verrou en cours), le watcher refusant alors de retraiter l'issue tant que ce fichier existe, même après redémarrage ; **procédure manuelle** en deux étapes — `nssm restart CCW-Watcher` (nécessaire mais pas suffisant seul), puis lister et supprimer le(s) fichier(s) `.lock` restant(s) dans `C:\CCW\Bridge_Agent\logs\verrous\` via `Get-ChildItem ... -Filter "*.lock"` et `Remove-Item` ; **note** — un bouton « Interrompre » dans l'onglet CCW de `new_issue.py` est prévu pour automatiser cette procédure à distance depuis Linux (voir `TACHES.md`, backlog ajouté par l'issue précédente be4cae0). Pied de page de `BRIDGE_AGENT_DOC.md` glissé (issue #287 en tête, #285 et #281 conservées comme les deux entrées les plus récentes parmi les issues modifiant cette doc, #279 sorti). Aucun fichier `.py`/`.js` modifié (documentation seule), aucune section renumérotée.

## 30 juillet 2026 — issue #285

Documente au §3 « Créer une issue — la méthode normale » de `BRIDGE_AGENT_DOC.md` le comportement exact du bouton **« Aperçu de la commande »** de l'onglet Nouvelle issue (issue #285), jusqu'ici non décrit malgré sa présence de longue date dans le formulaire. Nouveau paragraphe inséré juste après la description du lancement (`new_issue.py`/`lancer_new_issue.sh`) et avant le « Format du corps pour copier-coller » : le bouton appelle la route `/apercu` (fonction `apercu()` de `app/issues.py`), qui construit à partir des champs actuellement remplis dans le formulaire la commande `gh issue create` exacte qui serait exécutée (dépôt, titre, labels, `--body-file`), suivie en commentaire du corps complet qui serait envoyé, renvoyée en JSON. `afficherApercu()` (`static/js/app.js`) affiche ce texte tel quel dans la zone `zone-apercu` sous le formulaire. Point clé : c'est un aperçu pur — aucune issue n'est créée, aucune commande n'est réellement exécutée, rien n'est modifié tant que le bouton d'envoi n'est pas cliqué séparément. Pied de page de `BRIDGE_AGENT_DOC.md` glissé (issue #285 en tête, #281 et #279 conservées comme les deux entrées les plus récentes parmi les issues modifiant cette doc, #268 sorti). Aucun fichier `.py`/`.js` modifié (documentation seule), aucune section renumérotée.

## 30 juillet 2026 — issue #281

Ajoute au §11 « Conventions de code » de `BRIDGE_AGENT_DOC.md` le paragraphe **« Niveau de détail des issues »** (issue #281), en réponse à une tendance observée chez Claude Chat à rédiger du code complet dans le corps des issues (blocs Avant/Après, implémentations entières) alors que CCL est capable de lire les fichiers source et d'implémenter lui-même à partir d'une description claire. La règle posée : Claude Chat décrit le problème, la cause et l'intention du fix, sans rédiger le code complet — CCL fait l'implémentation. **Exception tolérée** : un snippet de 1-2 lignes si la syntaxe est non-triviale ou si l'intention serait ambiguë sans exemple. **Mauvais exemple** donné : fournir les trois méthodes complètes Avant/Après pour un fix pywebview de navigation différée. **Bon exemple** : « Dans `api.py`, pour les trois méthodes de navigation, différer l'appel dans un thread daemon avec `time.sleep(0.05)` avant de naviguer. » Pied de page de `BRIDGE_AGENT_DOC.md` glissé (issue #281 en tête, #279 et #268 conservées comme les deux entrées les plus récentes parmi les issues modifiant cette doc, #263 sorti). Aucun fichier `.py` modifié, aucune section renumérotée.

## 30 juillet 2026 — issue #279

Documente dans §13 de `BRIDGE_AGENT_DOC.md` le diagnostic du symptôme « Erreur inconnue » observé la nuit du 29/07/2026 (issue #279) : plusieurs issues avaient échoué en ~1,2 s, 3 tentatives et passe diagnostique comprises, le message générique masquant totalement la cause réelle — une session CCL expirée. Nouveau bloc **« Diagnostic — CCL ne démarre pas »** ajouté en fin de §13 (après le paragraphe sur les services systemd abandonnés) : **symptôme** (échec quasi immédiat sur toutes les issues → cause systémique, pas liée au contenu d'une tâche précise) ; **première vérification** (`claude -p "test" 2>&1` — une réponse « Not logged in » signe un token de session CCL expiré) ; **résolution** (lancer `claude` en session interactive, puis taper `/login`) ; **autres causes possibles** (réseau indisponible/DNS, installation `claude` corrompue) ; et le **critère de distinction** entre ces causes par le temps d'échec — un token expiré échoue en moins de 2 secondes (observé le 29/07/2026), un problème réseau échoue en général bien plus tard, proche du `TIMEOUT` configuré dans l'en-tête de l'issue (l'appel reste bloqué à attendre une réponse qui ne vient jamais). Pied de page de `BRIDGE_AGENT_DOC.md` glissé (issue #279 en tête, #268 et #263 conservées comme les deux entrées les plus récentes parmi les issues modifiant cette doc, #257 sorti). Aucun fichier `.py` modifié, aucune section renumérotée.

## 29 juillet 2026 — issue #272

Consignation dans `TACHES.md` de deux sujets diagnostiqués en conversation le 29/07/2026 (issue #272), qui auraient été perdus à la fermeture du fil sans cette entrée : tous deux relèvent du backlog (pistes à mûrir, aucun développement lancé). Ajoutées en tête du fichier, avant « Concurrence limitée aux issues mode_lecture », les entrées existantes n'ont pas été modifiées. **Entrée 1 — calibration automatique du TIMEOUT (§19), trois défauts** : (1) `_detecter_tag_reseau()` retourne toujours `None`, donc le facteur d'ambiance `F` (F_reseau/F_local) n'influence jamais la suggestion malgré la formule qui le prévoit ; (2) même corrigé, `maj_calibration_timeout` retomberait toujours sur `F_local` par défaut sans lire le tag — bug distinct du premier ; (3) la clé `projet|TYPE|mode` mélange des populations de durée incompatibles (une doc de 250s et une refonte avec tests de 1800s dans la même case), produisant des suggestions sans sens (observé : 2794s suggérés pour une issue ayant pris 351s). Piste retenue : séparer le coût de la TÂCHE (proxy : le TIMEOUT déclaré en en-tête, que Claude Chat estime déjà à la rédaction) de l'état de la MACHINE (latence réseau mesurée au démarrage, pour enfin alimenter `tag_reseau`), en conservant une composition en PRODUIT et non en somme. **Entrée 2 — archivage de `logs/historique_durees.json`** : 682 entrées, 112 Ko au 29/07/2026, jamais purgé depuis mai ; les 13 entrées `ff_galerie` (projet piloté par EmailJS, pas d'usage bridge réel) ne polluent aucun calcul mais brouillent la lecture manuelle. Point de vigilance impératif pour toute implémentation future : ne pas archiver naïvement par mois — l'EWMA de calibration a une demi-vie de 15 issues, une bascule mensuelle repartirait de zéro à chaque mois pour les projets les plus actifs. Aucune urgence à 112 Ko ; à traiter avant plusieurs Mo. `BRIDGE_AGENT_DOC.md` non modifié par cette issue (aucune section ne couvre `TACHES.md`), donc pied de page non glissé (condition de #10 non remplie).

## 29 juillet 2026 — issue #271

Résultats : nombre d'issues chargées par projet rendu configurable (issue #271), pour accélérer le bouton rafraîchir et réduire le volume rapatrié — jusqu'ici `issues_liste()` (`app/issues.py`) appelait `gh issue list --limit 30` en dur, **par projet** (jusqu'à 240 issues téléchargées avec 8 projets), alors que l'affichage était déjà plafonné par le quota adaptatif d'`appliquerFiltresListe()` (issue #136). **Backend** : `issues_liste()` accepte désormais un paramètre de requête optionnel `limite` (`_limite_issues_requete()`), entier borné entre 1 et 50 — toute valeur absente, non entière ou hors bornes retombe sur 30 (`LIMITE_ISSUES_DEFAUT`), comportement strictement inchangé pour tout appelant qui ne passe pas le paramètre (vérifié : `?limite=5`→5, `?limite=999`→50, `?limite=0`→1, `?limite=abc`→30, absent→30, via `test_client()` bout-en-bout contre `gh` réel). **Frontend** (`static/js/app.js`, `static/css/style.css`) : champ numérique `#limite-issues-projet` ajouté dans la ligne de filtres, juste avant le bouton rafraîchir, `title` explicite (« Nombre d'issues chargées par projet (pas un total). Ex. 5 → 5 issues par projet affiché. ») pour éviter la confusion nombre-par-projet / total — un total obligerait à diviser par le nombre de projets actifs, qui change à chaque clic sur un filtre. Persisté dans `localStorage` (`bridge_limite_issues_projet`), défaut **5** (besoin réel dans 70% des cas d'après l'issue, et non 30 : l'ancienne valeur reste atteignable en remontant le champ). `chargerListeIssues()` transmet la valeur courante (`limiteIssuesProjet()`) à chaque appel `/issues-liste/<projet>`. Changer la valeur du champ ne déclenche **aucun** rechargement automatique (cohérent avec la décision de #270) : seul le bouton rafraîchir applique la nouvelle limite ; en revanche `changerLimiteIssuesProjet()` invalide immédiatement `CLE_CACHE_ISSUES`, sans quoi un cache constitué à l'ancienne limite continuerait d'afficher une profondeur d'historique incohérente avec le réglage visible. Quota adaptatif de #136 (`appliquerFiltresListe()`) **non touché** : les deux mécanismes sont complémentaires (celui-ci plafonne ce qui est TÉLÉCHARGÉ, celui-là ce qui est MONTRÉ) ; commentaire ajouté pour expliciter que si la limite de téléchargement est plus basse que le quota d'affichage, ce dernier n'a simplement rien de plus à masquer — sans conséquence. **Mesure du coût GraphQL** (méthode #263 : deux `gh api rate_limit` encadrant un appel isolé de `gh issue list --json ...`, 3 répétitions, delta minimal retenu) sur `--limit 30/10/5` : les trois deltas minimaux mesurés valent **1 point** (identique au coût unitaire déjà mesuré par #263 pour cet appel) — résultat inattendu : le coût GraphQL par appel ne varie PAS avec `--limit` dans la plage testée, contrairement à l'intuition de l'issue ; le gain réel n'est donc pas une réduction du quota GraphQL (le nombre d'appels — un par projet — reste le facteur dominant, inchangé par cette issue) mais une réduction du volume de données transférées/parsées (23 113 → 3 445 octets entre `--limit 30` et `--limit 5` sur ce dépôt, soit -85%), donc du temps de traitement `gh`/JS et du risque de timeout sur un historique profond. Détail complet et tableau des mesures dans le rapport de clôture de l'issue #271 (non dupliqué ici). Route `/issues-liste/<projet>` non documentée dans `BRIDGE_AGENT_DOC.md` (aucune section ne la décrit) : aucune mise à jour de ce fichier, pied de page non glissé (condition de #10 non remplie — cette issue ne modifie pas `BRIDGE_AGENT_DOC.md`).

## 29 juillet 2026 — issue #270

Badges de temps restant : suppression du rafraîchissement périodique (issue #270, remplace #269 fermée sans correctif — mesure infaisable dans le TIMEOUT, décisions non tranchées). `intervalFetchTiming` (re-fetch de `/issues-en-attente/<projet>` toutes les 15s pour tous les projets configurés, ~3840 pts/h mesurés par #263, premier poste de consommation du quota GraphQL) supprimé ; `intervalTempsRestant` conservé (décompte purement client, recalcul chaque seconde, sans coût réseau). `chargerTimingIssues()` n'est plus appelée qu'au chargement initial de l'onglet Résultats et depuis `rafraichirResultats()` (bouton rafraîchir), pour qu'un seul geste mette à jour liste ET badges. Décision sur le décompte (point 3 de #269, laissé en suspens) : une fois le budget total épuisé, le badge se fige à « ⌛ 0s — budget épuisé » au lieu d'un compteur de dépassement qui grossissait indéfiniment (`⌛ dépassement +Xs`) — jamais de valeur négative, jamais de message spéculatif du type « terminé ? » (l'état réel n'est pas connu sans re-fetch), badge visible jusqu'au prochain rafraîchissement manuel. Retrait de deux résidus d'une tentative précédente non commitée proprement : un `console.error('[DEBUG-269-TRACE]', …)` dans `chargerTimingIssues()` et un bloc `<script>` de harnais temporaire dans `templates/index.html` (auto-bascule vers l'onglet Résultats après 800ms) qui portait lui-même la mention « à retirer avant commit ». Second appelant de `/issues-en-attente` (~ligne 2735, garde-fou avant l'envoi d'une nouvelle issue) : hors périmètre de cette issue, laissé strictement tel quel. Aucune mesure de gain (hors périmètre, cf. #269 : nécessite un navigateur ouvert 5+ minutes, invérifiable depuis l'agent) — à faire par Alain avec `scripts/mesurer_api.py`.

## 29 juillet 2026 — issue #268

Corrige la corruption du § 10 provoquée par #263 (issue #268) : l'entrée de #263, destinée au vrai pied de page (dernière ligne du fichier), avait été insérée à la place du `<date> — ...` du modèle explicatif du §10 — remplacement effectué sur la première occurrence de « Dernière mise à jour » dans le fichier, qui est cet exemple, pas le pied de page situé bien plus bas. Deux dégâts cumulés : le §10 affichait un modèle cassé (phrase du point 2 disloquée par le texte de #263 inséré en son milieu) et le vrai pied de page n'avait PAS reçu l'entrée de #263 — il avait seulement perdu #252, passant de trois entrées (#257, #253, #252) à deux (#257, #253), contredisant le rapport de clôture de #263 qui affirmait à tort « Footer glissé (#263 en tête, #257 et #253 conservées, #252 sorti) ». **Correctifs** : (1) §10 restauré au mot près dans son état d'origine (`*Dernière mise à jour : <date> — ...*`) ; (2) pied de page reconstruit avec l'entrée #263 en tête suivie de #257 et #253 (les trois entrées les plus récentes parmi les issues modifiant cette doc), puis complété dans la même opération par cette propre entrée #268, faisant sortir #253 ; (3) garde-fou ajouté au §10 (nouveau point 3) : le format n'apparaît qu'à la toute dernière ligne du fichier, une recherche sur « Dernière mise à jour » remontant d'abord l'exemple du §10 — toujours viser la fin du fichier, jamais la première occurrence. **Test (point 4)** : regex de `nouveau_projet.py` (`(\*Dernière mise à jour : )[^—]*( —)`) rejouée réellement (`re.sub`) contre la première ligne du pied de page corrigé — match confirmé, substitution de la date vérifiée avec succès. Aucun fichier `.py` modifié, aucune section renumérotée.

## 28 juillet 2026 — issue #263

Mesure et attribution de la consommation du quota GraphQL GitHub (issue #263, suite à l'épuisement complet du 28/07 vers 3h — 5000/5000, `remaining: 0`) — aucun correctif, mesure seule. Ajout de `scripts/mesurer_api.py` : échantillonne `gh api rate_limit` (REST, **gratuit** — vérifié empiriquement par une rafale de 40 appels sans effet sur `graphql.used`) à intervalle réglable et journalise dans `logs/mesure_api.csv` (déjà gitignoré via la règle `logs/`), arrêtable par Ctrl+C sans perte. **Coûts unitaires mesurés** (delta minimal sur 2-5 répétitions, pour s'affranchir du bruit de fond) : `gh issue list --json ...` (l'appel du polling) = 1 point, `gh issue view --json comments` = 2, `gh issue comment` = 2, `gh issue edit --add-label` = 3, `gh issue close` = 2 (plancher, variance 2-4). **Résultat principal, inattendu** : sur la fenêtre mesurée (baseline ≈ 4045 points/heure, 1 seul watcher CCL actif), la première cause identifiée n'est ni la boucle CCW, ni le délai d'inactivité de 20 min, ni le polling à 10s des watchers (chacun ≈ 360 points/heure, confirmé par calcul coût-unitaire × fréquence) — c'est **l'interface web laissée ouverte dans un navigateur** : `/issues-en-attente/<projet>` interroge deux fois (labels for-linux ET for-windows) CHAQUE projet configuré toutes les ~15s pour rafraîchir les badges du sélecteur, soit environ 3840 points/heure à elle seule avec les 8 projets actuels — avant même qu'un watcher ou le poller de notifications (`app/notifications_poller.py`, ≈ 960 points/heure pour 8 projets) n'entre en jeu. Protocole en phases A-D adapté : la phase « tout arrêté » n'a pas pu être mesurée en conditions réelles (le watcher CCL traitant cette issue de mesure, et `new_issue.py` dont il dépend, ne peuvent pas être arrêtés depuis CCL sans interrompre l'exécution en cours — même limite que le watcher CCW, inaccessible depuis le ThinkPad) ; contournement par deux watchers de test supplémentaires (`rummikub`, `scrabble`, `--dry-run`, 0 issue en attente donc aucun risque d'exécution réelle) pour isoler la contribution marginale d'un watcher au repos. §13 de `BRIDGE_AGENT_DOC.md` complété avec la méthode reproductible ; pied de page glissé (issue #257 et #253 conservées, #252 sorti — déjà dans ce fichier). Classement des leviers correctifs et chiffres complets : rapport détaillé posté en commentaire de clôture de l'issue #263 (non dupliqué ici) — aucun changement de comportement du bridge n'a été apporté, les correctifs éventuels feront l'objet d'issues séparées.

## 28 juillet 2026 — issue #262

Transforme le bouton « Tous » de l'onglet Résultats en véritable interrupteur à deux états, après que #259 a établi que le comportement inconditionnel qu'il évoluait n'était pas un bug : le besoin réel est un basculement rapide entre « tout afficher » et « tout masquer », le bouton « Tous » et la case de marquage étant les deux gestes les plus fréquents de cet onglet (le détail d'une issue y est presque jamais consulté, cf. #261).

**Nouvelle fonction** : `reactiverTousLesFiltres()` renommée `basculerTousLesFiltres()` (`static/js/app.js`), commentaire d'en-tête réécrit pour décrire le toggle plutôt que la remise à zéro inconditionnelle. Règle : `noms.every(nom => projetsFiltresActifs.has(nom))` vrai (tout affiché) → passe à l'ensemble vide (tout masqué) ; faux (état partiel OU tout masqué) → passe à l'ensemble complet (tout affiché). Un seul état bascule vers « tout masqué », tout le reste revient à « tout affiché », conformément à l'énoncé.

**Garde-fou de #259** : supprimé purement et simplement (`if (!noms.length) return;`), sans réécriture ni remplacement — l'ensemble vide qu'il interdisait est désormais l'état « tout masqué », volontaire et légitime, exactement ce que la fonction doit pouvoir produire. Le garder aurait bloqué le nouveau comportement dans le cas `noms` vide (aucun projet configuré), un cas de toute façon sans conséquence réelle (aucun bouton projet à masquer).

**Persistance `localStorage`** (`CLE_FILTRES_RESULTATS`) : asymétrique, à dessein. Vers « tout affiché » → `localStorage.removeItem(...)`, comme avant #262 (retour au défaut — tout actif — au prochain chargement). Vers « tout masqué » → `sauvegarderFiltresProjets(noms)`, la même fonction qu'utilise déjà `basculerFiltreProjet()`, qui écrit `{nom: false, ...}` pour chaque projet : sans cette persistance explicite, un rechargement de page aurait silencieusement annulé le masquage volontaire (retour à tout affiché par défaut, cf. `restaurerFiltresProjets()`).

**État visible sur le bouton** : `majClassesBoutonsFiltre()` (qui ne traitait jusqu'ici que les boutons `[data-projet]`) traite désormais aussi `.filtre-projet.tous` — classe `inactif` (grisée, CSS déjà existante) et `title` reflétant l'action du **prochain** clic (« Tout masquer » quand tout est affiché, « Tout afficher » sinon), pas l'état courant. Effet de bord nécessaire : dans `construireBoutonsFiltre()`, l'appel à `majClassesBoutonsFiltre()` se faisait juste après la boucle des boutons projet, donc **avant** la création du bouton « Tous » — déplacé après sa création (juste avant le bouton rafraîchir), sinon la mise à jour de son état visuel n'aurait rien trouvé dans le DOM à la construction initiale ni après reconstruction de la ligne de filtres.

**Point 5 (cas limite tout masqué)** : `appliquerFiltresListe()` masque bien toutes les lignes (`projetVisible` faux pour tout projet quand l'ensemble est vide), `selectionnerPremiereVisible()` ne trouve aucune ligne visible et affiche proprement « Aucune issue à afficher », sans erreur. Défaut trouvé en vérifiant ce chemin : la ligne précédemment sélectionnée gardait sa classe `.selectionnee` (invisible mais toujours marquée) même masquée — au retour à « tout afficher », cette ligne redevenait visible et le code de resynchronisation (`if (!sel || sel.style.display === 'none')`), la trouvant déjà « sélectionnée » et visible, sautait la resélection : la zone de détail restait bloquée sur le message « Aucune issue à afficher » malgré une ligne visiblement en surbrillance. Ce chemin était déjà latent via `basculerFiltreProjet()` (désactiver le dernier projet actif un par un y menait aussi) mais quasi inatteignable en pratique ; le nouveau toggle le rend trivial (un clic). Corrigé dans `selectionnerPremiereVisible()` : la branche « aucune ligne visible » retire désormais aussi la classe `.selectionnee` de toute ligne qui la porterait encore et réinitialise `projetCourant`/`numeroCourant` (miroir du comportement déjà présent dans `selectionnerLigne()` pour son propre cas « aucune issue »). Effet : au retour à « tout afficher », plus aucune ligne ne porte `.selectionnee`, la resynchronisation se déclenche normalement et sélectionne proprement la première ligne visible.

**Point 6 (rechargement / reconstruction)** : vérifié par lecture du chemin d'appel — `appliquerListeIssues()` recalcule toujours `projetsFiltresActifs = restaurerFiltresProjets(noms)` avant `construireBoutonsFiltre(noms)`, aussi bien au chargement initial qu'à toute reconstruction (ajout de projet). Après un masquage total persisté, un rechargement restaure bien un ensemble vide (chaque projet marqué `false` dans l'état sauvegardé) : le bouton affiche correctement l'état « inactif »/« Tout afficher » dès la construction, premier clic correct. Ajout d'un nouveau projet pendant un masquage total : ce projet, absent de l'état `localStorage` sauvegardé, est actif par défaut (`etat[nom] !== false` vrai pour une clé absente) — l'ensemble devient donc partiel plutôt que resté totalement vide ; le bouton reflète alors correctement « Tout afficher » (état partiel), et un premier clic affiche bien tout, conformément à la règle générale (tout état partiel bascule vers tout affiché).

**Vérification** : `node --check static/js/app.js` → OK. Vérifications des points 5 et 6 faites par relecture attentive du chemin d'exécution réel du fichier (accès à un bac à sable DOM complet non disponible dans cette session — le fichier charge de nombreux `document.getElementById(...).addEventListener` en haut niveau, un stub minimal aurait été trompeur) ; le raisonnement s'appuie sur le code effectivement livré, ligne par ligne, pas sur une hypothèse.

## 28 juillet 2026 — issue #261

Dans l'onglet Résultats, `afficherIssue()` (`static/js/app.js`) lançait un `fetch('/issue/<projet>/<numero>')` systématique — y compris pour un clic simple réflexe (sélectionner une ligne sans vouloir lire son détail) et pour la sélection automatique (`selectionnerPremiereVisible()`, déclenchée à l'ouverture de l'onglet, à chaque changement de filtre projet, après « Tous » et après chaque rafraîchissement de liste). Le TTL du cache `localStorage` (issue #52) ne dispensait que l'affichage immédiat : le fetch d'arrière-plan partait quand même. Dans l'usage réel, ce détail n'est presque jamais consulté ; chaque clic réflexe et chaque changement de filtre coûtaient donc un aller-retour GitHub inutile — autant d'occasions d'erreur/lenteur sur un réseau instable (issue #261).

**Solution retenue** : séparation stricte sélection / chargement. Nouvelle `selectionnerLigne(nom, numero)` — met en évidence la ligne (classe `.selectionnee`), mémorise `projetCourant`/`numeroCourant`, affiche un état neutre (« Double-cliquez une issue pour afficher son détail. ») dans `#zone-issue`, **sans fetch**. `afficherIssue()` (comportement de fetch/cache inchangé) délègue désormais la partie sélection à `selectionnerLigne()` et ne s'en distingue plus que par le chargement effectif. `selectionnerPremiereVisible()` appelle `selectionnerLigne()` au lieu de `afficherIssue()` : la sélection automatique ne charge donc plus rien. Sur chaque ligne, `onclick` (clic simple) appelle `selectionnerLigne()` ; un nouveau `ondblclick` appelle `afficherIssue()` — seul geste, avec le Ctrl+clic (identique à avant, demande explicite de détail + défilement vers le résultat CCL), qui charge encore. `title="Double-cliquez pour afficher le détail de cette issue"` posé sur chaque ligne pour rendre le geste découvrable (point 6).

**Bouton rafraîchir (issue #56, point 4)** : `rafraichirResultats()` mémorisait `projetCourant`/`numeroCourant` avant rechargement pour rouvrir l'issue affichée — mais ces variables sont désormais renseignées même par une simple sélection, jamais chargée. Nouveau drapeau `detailCourantCharge` (true uniquement après un chargement réel via `afficherIssue()`, remis à `false` par `selectionnerLigne()`) : `rafraichirResultats()` ne recharge le détail après rafraîchissement que si `detailCourantCharge` valait `true` juste avant — sinon, aucune issue n'ayant été explicitement ouverte, rien n'est chargé de force.

**Non modifié** : la checkbox de marquage, les badges « ✅ »/« Diff »/« All » (fetch à la demande explicite, inchangés), le filtrage par projet, `annulerIssue()`/`fermerIssue()` (leurs boutons ne sont rendus que dans une issue déjà explicitement chargée — rappeler le détail après leur action reste la continuation directe d'un geste explicite, pas un chargement réflexe). Aucune sélection au clavier n'existe dans ce fichier pour la liste des issues (point 7 : rien à adapter).

**Vérification** : `node --check static/js/app.js` → OK. Comportement rejoué dans un bac à sable Node (`vm`, mêmes stubs DOM/localStorage/fetch que pour #259) chargeant le fichier réel tel quel : sélection automatique et clic simple → zéro appel `fetch('/issue/...')` ; double-clic → exactement un appel ; `rafraichirResultats()` après une simple sélection → zéro appel ; après un double-clic préalable → un appel. Script de vérification non persisté (ad hoc, comme pour #259).

## 28 juillet 2026 — issue #260

Corrige la façon dont `initialiser_git()` (`nouveau_projet.py`) détecte le contenu préexistant d'un `REP_TRAVAIL` non versionné, en la faisant porter sur ce que git suivrait réellement plutôt que sur le contenu brut du disque (issue #260, suite #258). **Défaut** : `_fichiers_preexistants()` (livrée par #258) listait le répertoire via `rglob("*")` **avant** toute écriture — choix délibéré pour que le futur `.gitignore` ne fausse pas le constat — mais comptait de ce fait aussi tout ce que ce même `.gitignore` exclurait. Le cas typique d'un `REP_TRAVAIL` préexistant est un projet Python déjà commencé, contenant donc un `venv/` et des `__pycache__/` : le scan remontait alors potentiellement des milliers d'entrées, le compte-rendu annonçait un nombre de « fichiers préexistants » sans rapport avec la réalité, et le push était retenu pour des fichiers qui n'auraient de toute façon jamais été committés — un garde-fou qui se déclenche presque systématiquement pour de mauvaises raisons finit par être ignoré, ce qui annule le bénéfice recherché par #258. Point mineur de même famille : `rglob("*")` parcourait l'arborescence entière sans borne, au sein d'une requête Flask, alors que #258 venait précisément de poser des timeouts sur les appels git pour cette raison — un `venv/` volumineux aurait pu rendre la création anormalement lente.

**Solution retenue** : réordonnancement de `initialiser_git()` — `git init`, `remote add`, écriture du `.gitignore` minimal (comportement inchangé), PUIS `git add -A`, PUIS détection sur l'index réel (`git diff --cached --name-only`), PUIS commit. Nouvelle `_fichiers_suivis_preexistants(rep_path, git_runner)` remplace `_fichiers_preexistants()` (supprimée, aucune coexistence des deux mécanismes) : liste les fichiers indexés par `git add -A`, exclut ceux que le script crée lui-même (`CONTEXTE.md`, fichiers Specs, `.gitignore` — `FICHIERS_CREES_PAR_SCRIPT`, inchangée), triés, chemins relatifs. Un `venv/`/`__pycache__/` exclu par le `.gitignore` minimal n'atteint jamais l'index et ne compte donc plus comme contenu préexistant. Sémantique de sortie strictement conservée : `contenu_preexistant` (liste triée), `push_ok=None` en cas de retenue volontaire (distinct de `False` = échec réel), `commande_manuelle`, `detail` expliquant le pourquoi — seule la manière de constituer la liste change. `_fichiers_suivis_preexistants()` réutilise le `_git()` local de l'appelant (déjà borné par `TIMEOUT_GIT_LOCAL` et tolérant au dépassement) pour le `git diff --cached` : pas de second mécanisme de timeout à maintenir.

**Test** (`tests/test_init_git_local_258.py`) : scénario « contenu préexistant » (#258) inchangé, continue de passer. Nouveau scénario `scenario_venv_ignore_par_gitignore_pas_de_retenue` : répertoire non versionné contenant un `venv/lib/module.py` et un `__pycache__/module.cpython-311.pyc`, aucun fichier réellement suivi → `contenu_preexistant` vide et push tenté normalement (`push_ok:false`, dépôt distant inexistant — pas `None`). Vérifié comme échouant sur le code d'avant correction (`git stash` du seul `nouveau_projet.py`, test relancé : `venv/lib/module.py` et `__pycache__/module.cpython-311.pyc` remontaient tous les deux) puis passant sur le code corrigé. Les 4 autres scénarios de ce fichier ainsi que `test_nettoyage_arbre_247.py`, `test_auto_extinction_217.py`, `test_verification_commentaire_237.py` repassés sans régression.

**Doc** : §13 étape 5 reformulé — le garde-fou porte désormais explicitement sur les fichiers que git suivrait après `git add -A`, pas sur un inventaire brut du répertoire.

## 28 juillet 2026 — issue #259

Ajoute un garde-fou d'idempotence à `reactiverTousLesFiltres()` (bouton « Tous » de l'onglet Résultats, `static/js/app.js`), suite à un signalement de second clic masquant tous les projets (issue #259). **Diagnostic** : la piste envisagée (`nomsProjetsDisponibles()` retournant vide au second appel, faisant écrire un `Set` vide) ne s'est pas confirmée. `nomsProjetsDisponibles()` lit `[...document.getElementById('projet').options]` — le `<select>` global, peuplé une seule fois côté serveur par `lister_projets()` et jamais vidé/reconstruit côté client (seul `ajouterProjetAuSelecteur()` y ajoute une option, sans jamais en retirer) ; il est donc déjà indépendant de l'état d'affichage/filtre de l'onglet Résultats — `appliquerFiltresListe()` ne fait que masquer des LIGNES d'issues (`ligne.style.display`), jamais les options du select, et `localStorage.removeItem` ne touche pas non plus le DOM. Vérifié par exécution directe du fichier réel (`static/js/app.js` chargé tel quel dans un bac à sable `vm` Node, sans modification) : deux appels consécutifs à `reactiverTousLesFiltres()`, partant d'un état partiellement ou totalement désactivé, produisent chacun l'ensemble complet des projets — aucune régression vers un `Set` vide observée sur ce chemin. Seuls trois points du fichier réaffectent `projetsFiltresActifs` (déclaration initiale, `appliquerListeIssues()` via `restaurerFiltresProjets()`, et `reactiverTousLesFiltres()`) ; les deux derniers ont été rejoués sous test sans reproduire le symptôme. Le symptôme décrit (plus aucune issue affichée, récupérable seulement en recliquant chaque projet un par un) correspond en revanche exactement au comportement déjà connu et documenté de `basculerFiltreProjet()` lorsqu'on désactive le dernier projet actif restant (vérifié : le `Set` devient bien vide dans ce cas précis) — plausiblement la manipulation réellement en cause, plutôt qu'un second clic sur « Tous ».

**Solution retenue** : aucune correction de source nécessaire pour `nomsProjetsDisponibles()`, déjà appuyée sur une source stable. Garde-fou ajouté en second rideau dans `reactiverTousLesFiltres()` : si `nomsProjetsDisponibles()` retourne une liste vide (cas normalement inatteignable dans l'onglet Résultats, `chargerListeIssues()` court-circuitant déjà l'absence de projet), la fonction retourne immédiatement sans toucher à `projetsFiltresActifs` — état laissé inchangé plutôt que vidé. Vérifié par test direct (select vidé artificiellement) : l'état actif reste intact après le clic.

**Non modifié, signalé seulement (point 4)** : `basculerFiltreProjet()` désactivant le dernier projet actif produit bien un `Set` vide et un affichage sans aucune issue — confirmé par test. Comportement volontairement laissé tel quel : désactiver explicitement tous les projets un par un est une action délibérée de l'utilisateur, à la différence d'un second clic sur « Tous ».

**Vérifications (point 5)**, par exécution directe du fichier réel dans un bac à sable Node (`vm`) : **rechargement de page** — filtres partiellement désactivés puis persistés en `localStorage`, `appliquerListeIssues()` (chemin de chargement) restaure correctement l'état partiel, puis deux clics consécutifs sur « Tous » réactivent et maintiennent l'ensemble complet ; **reconstruction de la ligne de filtres** — ajout d'un projet au `<select>` puis `appliquerListeIssues()`/`construireBoutonsFiltre()` reconstruits, `nomsProjetsDisponibles()` inclut bien le nouveau projet, deux clics consécutifs sur « Tous » restent corrects et incluent le projet ajouté. `node --check static/js/app.js` → OK.

## 28 juillet 2026 — issue #258

Corrige deux défauts de `initialiser_git()` livrée par #257 : publication involontaire d'un répertoire préexistant, et absence de timeout sur les appels git (issue #258). **Défaut 1** : `creer_depot()` crée le dépôt GitHub en `--public`, et `initialiser_git()` fait `git add -A` puis pousse automatiquement — sans risque sur un répertoire neuf (cas nominal), mais si `REP_TRAVAIL` désigne un dossier **existant et non versionné** (cas explicitement couvert par le script, qui gère « création ET installation »), l'intégralité de son contenu était publiée sans confirmation ni aperçu ; le `.gitignore` minimal (`venv/`, `__pycache__/`, `*.pyc`, `*.log`, `.env`) ne protège que quelques cas. **Défaut 2** : `_git()` appelait `subprocess.run` sans `timeout=`, alors que le reste du code en pose un partout ailleurs (30s pour `commenter_issue`, 120s pour le push des pièces jointes) — un `git push` qui pend sur un réseau instable bloquait la requête Flask indéfiniment.

**Solution retenue — timeouts (point 1)** : `_git()` accepte désormais un `timeout` par appel, `TIMEOUT_GIT_LOCAL = 15` (secondes) pour `init`/`remote`/`add`/`commit`, `TIMEOUT_GIT_PUSH = 60` pour le push — seul appel réseau du lot, cohérent avec les timeouts déjà en place ailleurs. `subprocess.TimeoutExpired` est capturé et transformé en un `CompletedProcess` factice (`returncode=124`, `stderr` explicite) : le reste de la logique (qui ne fait déjà que tester `returncode != 0`) traite un timeout exactement comme un échec réseau ordinaire, sans exception qui remonterait et sans faire échouer la création — `commande_manuelle` renvoyée comme pour tout échec de push.

**Solution retenue — contenu préexistant (points 2/3)** : nouvelle `_fichiers_preexistants(rep_path)`, appelée AVANT toute écriture (avant que le futur `.gitignore` ne fausse le constat) : liste les fichiers du répertoire autres que ceux que le script crée lui-même (`CONTEXTE.md`, les 3 fichiers Specs MVC, `.gitignore` — constante `FICHIERS_CREES_PAR_SCRIPT`). Répertoire vide ou ne contenant que ces fichiers → comportement inchangé (init + commit + push automatiques). Contenu préexistant détecté → `git init`/remote/`.gitignore`/commit exécutés normalement, mais **le push n'est PAS déclenché** : `push_ok` reste `None` (distinct de `False`, qui signale un échec réel), nouveau champ `contenu_preexistant` (liste triée des chemins relatifs) renvoyé par `initialiser_git()` et propagé par `creer_projet()` (`git_contenu_preexistant`), `commande_manuelle` fournissant le `git push -u origin master` à lancer après relecture, et le `detail` explicitant pourquoi (dépôt public, contenu non relu) — pas un échec, une retenue volontaire.

**CLI** (`etape_git()`, résumé final de `main()`) : affiche la liste des fichiers préexistants détectés, tronquée à une dizaine (« … et N autre(s). »), et le message « push NON déclenché » distinct du message d'échec de push.

**Web** (`static/js/app.js`) : `afficherRappelProjet()` distingue désormais trois branches (déjà-git / poussé / **retenu volontairement** — contenu préexistant, avec la liste tronquée et l'explication « ce n'est pas un échec » — / échec de push), au lieu de fusionner la retenue volontaire avec l'échec de push comme le ferait un simple `else`.

**Doc** : §13 étape 5 réécrite en deux temps (push automatique si répertoire réellement vide ; garde-fou supplémentaire sinon) et complétée des deux timeouts. §18.2 : le paragraphe sur la seconde exception (#257) précisé — le raisonnement d'origine (« le dépôt distant vient d'être créé, rien à emporter ») est exact mais ne couvrait que le dépôt distant, pas le contenu local préexistant ; l'exception ne s'applique donc en pratique qu'aux répertoires réellement vides.

**Test** : nouveau `tests/test_init_git_local_258.py` (persisté — le test de #257 avait été fait sur des répertoires `/tmp` jetables puis supprimés, rien n'était resté sous `tests/`), quatre scénarios : répertoire neuf vide (comportement #257 inchangé, push tenté et échoue proprement sur un dépôt distant inexistant) ; déjà-git (strictement inchangé) ; contenu préexistant (issue #258 — `CONTEXTE.md` déjà présent n'est PAS compté, un fichier tiers l'est, aucun appel `git push` n'est tenté — vérifié en espionnant `subprocess.run` — et la commande manuelle est renvoyée) ; timeout de push (faux `git` en tête de `PATH` qui dort 2s sur `push` avec `TIMEOUT_GIT_PUSH` temporairement réduit à 0.3s — la création aboutit quand même, `push_ok:false`, pas d'exception). `python3 tests/test_init_git_local_258.py` → ✅ (4/4). Suites existantes repassées sans régression : `test_nettoyage_arbre_247.py`, `test_auto_extinction_217.py`, `test_verification_commentaire_237.py` → ✅. Aucune section renumérotée.

## 28 juillet 2026 — issue #257

Ajoute l'initialisation git du répertoire de travail à la création de projet, sans quoi le projet créé était inutilisable (issue #257). Contexte : `creer_projet()` (CLI et route Flask) créait le dépôt GitHub distant, le `.conf`, les labels, le répertoire de travail, `CONTEXTE.md` et mettait à jour la doc — mais ne faisait jamais `git init`/`git remote add` : aucun appel à `git` dans les 784 lignes du script, seule commande externe `gh`. Sur un projet réellement neuf (REP_TRAVAIL non versionné), `git pull --ff-only` en début de cycle du watcher échoue, et le commit de sauvegarde obligatoire avant toute modification en mode écriture ne peut pas s'exécuter — toute issue `mode_write` part en erreur. Cause probable : le script avait été écrit pour installer des dépôts déjà clonés de longue date, pas pour en créer de zéro ; le cas « projet neuf » n'avait jamais été parcouru jusqu'au bout avant `rummikub` (27 juillet 2026), initialisé à la main. **Aggravation** : après une création réussie, l'encart web `afficherRappelGit()` (`static/js/app.js`) affichait « ⚠ Action requise — pousser la doc sur GitHub » avec 3 commandes portant sur le dépôt **Bridge_Agent** (pousser `BRIDGE_AGENT_DOC.md`) — un encart « action requise » plein de commandes git juste après la création laissait croire à tort que rien d'autre n'était à faire, alors que deux étapes manquaient (init git + rédaction de `CONTEXTE.md`), non mentionnées nulle part.

**Solution retenue** : nouvelle étape « Dépôt git local » dans `creer_projet()` (`nouveau_projet.py`), entre « Fichiers contexte » et « Documentation », couvrant les deux cas : **déjà un dépôt git** (installation sur un projet existant, le cas de tous les projets actuels) → rien n'est fait, signalé « déjà un dépôt git — inchangé » ; **répertoire non versionné** (projet réellement neuf) → `git init -b master`, `git remote add origin` en **HTTPS** (`https://github.com/<owner>/<repo>.git`, jamais SSH — toute l'installation `gh` est en HTTPS), `.gitignore` minimal s'il est absent, commit initial, puis **push**. Nouvelle fonction `initialiser_git(rep, depot)`, réutilisée telle quelle par le CLI (`etape_git()`, avec confirmation comme les autres étapes, titre renuméroté « 8. » — Specs MVC en 7, doc en 9, résumé en 10) et par la route Flask (`creer_projet()`, sans confirmation individuelle, cohérent avec les autres étapes du flux web).

**Exception documentée à la règle « CCL/le script ne pousse jamais »** (issue #257, point 2) : ce push initial est déclenché par la création de projet elle-même, toujours à l'initiative d'Alain (terminal ou bouton web), jamais par un agent — même raisonnement que la route pièces jointes (§18.2, où une seconde exception du même type est désormais documentée explicitement). Un échec du push (réseau, droits) **ne fait pas échouer la création** : le commit reste local, `ok:true` mais `push_ok:false`, et une commande manuelle (`git push -u origin master`, ou la séquence complète si `git init` lui-même a échoué) est renvoyée dans `git_commande_manuelle` — affichée dans le récapitulatif CLI et dans un nouvel encart web dédié.

**Web** (`static/js/app.js`, `templates/index.html`, `static/css/style.css`) : nouvel encart `afficherRappelProjet()` (`#np-rappel-projet`, bordure bleue), **visuellement distinct** de l'encart existant `afficherRappelGit()` (bordure orange, dépôt Bridge_Agent uniquement, dont le titre est reformulé pour préciser « dépôt Bridge_Agent ») — c'est précisément la confusion entre les deux dépôts qui avait fait passer le problème inaperçu. Le nouvel encart rappelle systématiquement que `CONTEXTE.md` est créé **VIDE** (injecté dans chaque prompt CCL, plafonné à 4000 caractères) et affiche, le cas échéant, la commande git manuelle restante.

**Doc** : §13 « Commandes utiles » réécrit — décrivait auparavant seulement la commande de lancement sans aucune étape suivante ; détaille maintenant les 6 étapes réelles de bout en bout (dépôt GitHub, `.conf`, labels, contexte, **dépôt git local**, doc Bridge_Agent) et ce qui reste manuel dans tous les cas. §18.2 complété d'un paragraphe documentant cette seconde exception à la règle de push. Docstring d'en-tête de `nouveau_projet.py` mise à jour (« Zéro dépendance externe (stdlib + `gh`) » ne tenait plus, `git` est désormais requis pour le cas dépôt neuf).

**Test (point 6)** : sur des répertoires jetables sous `/tmp` (jamais de vrai dépôt GitHub créé, `depot_existe`/`creer_labels` court-circuités) : cas répertoire neuf → dépôt bien initialisé (`.git` présent, branche `master`, remote `origin` HTTPS correct, un commit), push échoue proprement (dépôt distant inexistant) sans faire échouer `creer_projet()` (`succes:true`), `git_commande_manuelle` renvoyée ; cas déjà-git → fichier préexistant intact, aucun remote ajouté, comportement strictement inchangé. Répertoires de test supprimés après vérification. Aucune section renumérotée.

## 27 juillet 2026 — issue #253

Étend la convention `CHANGELOG.md` à toute issue qui modifie le dépôt, pas seulement celles qui touchent la doc, et rattrape l'entrée manquante de #250 (issue #253, suite #252). Contexte : le texte introduit par #252 limitait l'obligation d'ajouter une entrée aux « issue[s] qui modifi[ent] cette doc » — restriction reconduisant, sous une autre forme, le trou que #240 avait dû combler à la main (issues #237/#238/#239, du code sans modification de doc, restées sans trace plusieurs jours) ; premier cas depuis #252 : #250 (correctif de contraste CSS pur, `static/css/style.css`) n'avait d'entrée ni dans `CHANGELOG.md` ni dans le pied de page, seulement dans l'historique git. **§10** reformulé : l'obligation d'ajouter une entrée en tête de `CHANGELOG.md` porte désormais sur **toute issue qui modifie le dépôt** (code, CSS, consignes, tests, documentation, quel que soit le fichier touché) ; le pied de page de cette doc reste, lui, réservé aux **trois entrées les plus récentes parmi les seules issues qui modifient cette doc elle-même** — comportement inchangé, une issue purement CSS comme #250 n'y figure donc pas. **Entrée rétroactive de #250** ajoutée dans `CHANGELOG.md`, à sa place chronologique (entre #252 et #251) : trois atténuations cumulées sur `.filtre-projet.inactif` (`opacity:.4` + fond `#f2f2f0` + texte `#999`) rendaient le nom des projets désélectionnés illisible (contraste `#999` sur `#f2f2f0` : 2,54:1, sous le seuil WCAG AA de 4,5:1, avant même l'effet de l'opacity) ; `opacity` globale supprimée — elle délavait aussi la pastille de couleur et l'emoji du bouton Ouvriers, pas seulement le texte — ne restent que fond et texte, `#5a5a5a` sur `#f2f2f0`, ratio 6,15:1. **Vérification des écarts (point 3)** : comparaison des numéros d'issue présents dans `CHANGELOG.md` à la liste des issues `done` fermées depuis #240 (13 issues, #240 à #252) — seules #241, #242 et #246 sont également absentes du changelog, mais légitimement : trois relances de build Windows Scrabble, `PROJET=bridge_agent` uniquement par la convention d'exception #233 pour les issues `for-windows`, ne modifiant aucun fichier du dépôt Bridge_Agent lui-même (build exécuté dans un partage CCW distinct) — hors du périmètre de la nouvelle règle, pas un oubli. Aucun autre écart trouvé. Aucune section renumérotée, aucun fichier `.py` modifié.

## 27 juillet 2026 — issue #252

Extrait l'historique du pied de page de `BRIDGE_AGENT_DOC.md` vers un `CHANGELOG.md` dédié (issue #252). Contexte : le pied de page (paragraphe « Dernière mise à jour : ... ») avait fini par contenir l'intégralité de l'historique du projet depuis l'issue #96, chaîné par 34 occurrences du connecteur « Précédemment » (suivi d'un tiret cadratin), soit 55523 caractères sur une seule ligne logique — coût de lecture (la doc est lue intégralement par Claude Chat à chaque conversation impliquant Bridge_Agent), coût d'écriture (chaque issue de doc réécrivait le bloc entier pour y insérer une entrée en tête), et risque de perte silencieuse (rien ne signalerait une troncature, un `git diff` sur une ligne de cette taille étant illisible). **Solution retenue** : nouveau fichier `CHANGELOG.md` à la racine du dépôt, contenant les 35 entrées historiques (de cette issue #252 jusqu'aux issues #135/#101/#97, suite #96) reformatées en sections `## <date> — issue #N`, contenu de chaque entrée repris **tel quel** — déplacement et reformatage, pas de résumé ni de réécriture. Extraction faite par script Python : séparation du pied de page d'origine sur la chaîne de connexion (« Précédemment » + tiret cadratin), avec vérification programmatique que la concaténation des segments reconstitue exactement le texte de départ (aucune perte possible) ; dates des 34 entrées antérieures (absentes du texte lui-même, seule la plus récente portait une date explicite) retrouvées sans ambiguïté via `git log` (recherche de `issue #N` dans les messages de commit, un seul jour de commit trouvé par numéro d'issue). Pied de page de `BRIDGE_AGENT_DOC.md` réduit aux **trois entrées les plus récentes** (celle-ci, #251, #249), suivies d'un renvoi vers `CHANGELOG.md` pour l'historique complet. **Vérification de non-perte (point 4)** : 34 occurrences du connecteur « Précédemment » avant modification, 35 entrées dans `CHANGELOG.md` après (34 + l'entrée « Dernière mise à jour » elle-même comptée à part) — décompte exact, aucun écart, confirmé avant livraison. **Vérification des dépendances (point 5)** : recherche de tout fichier s'appuyant sur le format du pied de page — une dépendance réelle trouvée dans `nouveau_projet.py` (deux occurrences, mise à jour de la date des projets §2/§7) : le script repère la ligne par `ligne.startswith("*Dernière mise à jour :")` puis remplace la date via le regex `(\*Dernière mise à jour : )[^—]*( —)`, insensible à tout ce qui suit le tiret cadratin — compatible tel quel avec le nouveau pied de page réduit, à condition que sa toute première ligne conserve exactement ce préfixe suivi d'un tiret cadratin juste après la date (vérifié, conservé sans changement). Aucun test (`tests/*.py`) ni aucun autre script ne référence ce pied de page ou la chaîne « Précédemment ». **§10** complété avec la nouvelle convention : toute issue modifiant la doc ajoute désormais son entrée en tête de `CHANGELOG.md` et fait glisser les trois entrées du pied de page (la plus ancienne des trois sortant du pied de page, elle reste disponible dans `CHANGELOG.md`). Aucune section renumérotée, aucun fichier `.py` modifié.

## 27 juillet 2026 — issue #250

Corrige le contraste illisible des pastilles de filtre projet désélectionnées (issue #250). Contexte : la règle `.filtre-projet.inactif` cumulait trois atténuations — `opacity:.4` global, fond `#f2f2f0`, texte `#999` — rendant le nom des projets désélectionnés difficile à lire, de façon inégale selon rendu/zoom du fait de l'`opacity` mêlée au fond de page sous-jacent ; contraste `#999999` sur `#f2f2f0` : 2,54:1, déjà sous le seuil WCAG AA (4,5:1) avant même l'effet de l'opacity. **Solution retenue** : suppression de l'`opacity` globale héritée de `.filtre-projet` — elle délavait aussi la pastille de couleur et l'emoji du bouton Ouvriers (`#filtre-ouvriers`, qui porte la même classe `.inactif` par défaut), pas seulement le texte du bouton ; ne restent atténués que le fond et le texte, ciblant uniquement ce qui doit l'être : `.filtre-projet.inactif{background:#f2f2f0;color:#5a5a5a}`. Contraste `#5a5a5a` sur `#f2f2f0` : 6,15:1, marge confortable au-dessus du seuil AA. La distinction sélectionné/désélectionné reste portée par trois signaux non corrélés — fond, texte, bordure (celle-ci retombant sur la valeur par défaut `1px solid #ccc`). Seul `static/css/style.css` modifié, aucun changement JS/HTML. Entrée ajoutée rétroactivement par l'issue #253 : cette issue, purement CSS, ne modifiait pas la doc et était donc restée hors du champ de la convention #252 alors en vigueur.

## 27 juillet 2026 — issue #251

Déclare restype/argtypes des appels ctypes kernel32 de l'objet Job Windows (issue #251, suite #249). Contexte : `_creer_job_windows_kill_on_close`/`_assigner_job_windows` appelaient `CreateJobObjectW`, `SetInformationJobObject`, `OpenProcess`, `AssignProcessToJobObject`, `CloseHandle` sans déclarer `restype`/`argtypes` — ctypes suppose alors par défaut un retour `c_int` (32 bits signés), alors que `CreateJobObjectW`/`OpenProcess` retournent un `HANDLE` (64 bits sur Windows x64) : le handle était donc tronqué silencieusement (fonctionnel en pratique tant que sa valeur reste petite, ce qui est le cas courant pour un handle noyau, mais rien ne le garantit), puis retronqué à chaque réutilisation en argument des appels suivants, eux aussi non déclarés — défaut structurellement invisible au test #249, qui mocke `ctypes.windll`. **Solution retenue** : nouvelle `_declarer_prototypes_kernel32_windows`, déclarant les cinq prototypes avec les types de `ctypes.wintypes` (`HANDLE`, `BOOL`, `DWORD`, `LPVOID`, `LPCWSTR`), appelée **une seule fois** à l'import du module sous la garde `if os.name == "nt":` — et non répétée à chaque appel, car le test `tests/test_nettoyage_arbre_windows_249.py` mocke `kernel32` par des méthodes liées Python (qui n'admettent pas l'affectation `.restype`/`.argtypes`) et ne force `os.name` qu'après l'import : une déclaration répétée aurait cassé ce mock. `python3 -c "import watcher"` vérifié toujours fonctionnel sous Linux (la garde empêche tout accès à `ctypes.windll`, absent hors Windows). **Point 2** : `_PROCESS_ALL_ACCESS = 0x1F0FFF` (valeur pré-Vista, toujours fonctionnelle) remplacé par les deux seuls droits documentés par Microsoft pour `AssignProcessToJobObject` — `PROCESS_SET_QUOTA | PROCESS_TERMINATE` (`_PROCESS_ACCES_JOB`). **Tests** : `tests/test_nettoyage_arbre_windows_249.py` et `tests/test_nettoyage_arbre_247.py` repassés sans modification (le mock ne traverse jamais la déclaration des prototypes, appelée seulement à l'import réel) — les deux passent. **§13** complété (sous-section « Nettoyage de l'arbre de process ») : nouveau paragraphe sur cette révision, et note sur les jobs imbriqués Windows 8+ sous NSSM (le service `CCW-Watcher` peut déjà être dans un job — l'assignation du process `claude` au job créé par `_preparer_job_windows` doit donc réussir même imbriquée ; si ce n'était pas le cas, le `log.warning` de `_preparer_job_windows` le signalerait — à vérifier lors de la prochaine validation réelle sur la VM CCW). Aucune section renumérotée..

## 27 juillet 2026 — issue #249

Remplace, sous Windows, le `taskkill /PID <pid> /T /F` de `_nettoyer_arbre_claude` par un objet Job noyau (issue #249, suite #247). Contexte : le nettoyage livré par #247 était correct sous POSIX mais très probablement inopérant sous Windows — la seule plateforme où le problème d'origine (`cmd.exe` orphelin verrouillant `Scrabble-Setup.exe` après un build CCW) avait été observé. `_nettoyer_arbre_claude` s'exécute dans le `finally` de `lancer_claude`, donc APRÈS le retour de `proc.communicate()` : à cet instant le process `claude` est déjà terminé et réapé, or `taskkill /PID <pid> /T /F` exige que le PID cible existe ENCORE pour parcourir son arbre généalogique — sur un PID mort il échoue immédiatement (« process not found ») sans toucher un seul descendant, exactement le scénario d'origine. `CREATE_NEW_PROCESS_GROUP` ne comble pas l'écart (sous Windows les groupes de process ne servent qu'au routage Ctrl+C/Ctrl+Break, pas à la terminaison d'une arborescence). Aggravation : seul le succès du `taskkill` produisait un `log.warning`, rendant l'échec totalement silencieux sous Windows ; le test de non-régression #247, exécuté sous Linux, ne couvrait que la branche POSIX. **Solution retenue** : objet Job noyau Windows (`CreateJobObjectW` + `SetInformationJobObject(JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)` + `AssignProcessToJobObject`), implémenté en `ctypes` pur (pas de nouvelle dépendance, pas de `pywin32`) — nouvelles fonctions `_creer_job_windows_kill_on_close`/`_assigner_job_windows`/`_preparer_job_windows`. Le job est créé et le process `claude` y est assigné **immédiatement après son démarrage** (`lancer_claude`, juste après le `Popen`, pendant que le process est encore vivant — seul moment où l'assignation est possible) ; fermer le handle du job dans `_nettoyer_arbre_claude(proc, job_windows)` termine alors toute la descendance encore assignée, PID vivant ou non. La branche POSIX (`start_new_session` + `os.killpg`) n'a **pas été touchée** : déjà correcte et testée. **Journalisation des échecs (point 3)** : `_preparer_job_windows` journalise tout échec de création/assignation du job, et `_nettoyer_arbre_claude` journalise tout échec de fermeture du handle (ou l'absence de job disponible) — la plateforme Windows ne peut plus rester silencieuse, succès ou échec. **Garde-fou (point 4)** : l'intégralité du corps de `_nettoyer_arbre_claude` est désormais enveloppée dans un `try/except Exception` — `_lister_processus_pgid` (OSError sur `iterdir()`), `os.killpg` (PermissionError) et les appels `ctypes` Windows ne peuvent plus s'échapper d'une fonction appelée depuis un `finally`, ce qui aurait masqué la valeur de retour de `lancer_claude`. **Test** : nouveau `tests/test_nettoyage_arbre_windows_249.py` — le scénario Windows réel n'étant pas exécutable sur le ThinkPad (Linux), mock de `ctypes.windll` (+ `os.name` forcé à `"nt"`) vérifiant l'ordre des appels ctypes (`CreateJobObjectW` → `SetInformationJobObject` → `OpenProcess` → `AssignProcessToJobObject` → `CloseHandle`), la journalisation succès/échec à chaque étape, et qu'une exception pendant le nettoyage n'est jamais remontée ; `tests/test_nettoyage_arbre_247.py` (POSIX) repassé sans modification — les deux passent (`python3 tests/test_nettoyage_arbre_247.py` et `python3 tests/test_nettoyage_arbre_windows_249.py` → ✅). ⚠️ **Ce mock ne remplace pas une validation réelle sur la VM CCW** : il vérifie que le code ctypes fait les bons appels, pas que Windows tue effectivement l'arbre de process en pratique — validation par build réel sur CCW encore nécessaire avant de considérer le correctif éprouvé en conditions réelles. **§13** réécrit (sous-section « Nettoyage de l'arbre de process ») : la justification de #247 (« symétrie CCL/CCW préférée à l'objet Job, script unique partagé ») est explicitement invalidée — cette symétrie coûtait la correction sous Windows, un objet Job en `ctypes` pur restant parfaitement compatible avec un script unique CCL/CCW (branche POSIX inchangée, aucune divergence de dépendance). Aucune section renumérotée.

## 27 juillet 2026 — issue #248

Isole le push de la route pièces jointes sur une branche orpheline dédiée, `pieces-jointes` (issue #248). Contexte : la route `POST /joindre-image` (§18, issue #191) terminait par `git push origin HEAD:<branche_courante>` — or git ne peut pas publier un commit sans ses ancêtres, ce push emportait donc AVEC l'image tous les commits locaux non encore poussés de la branche de travail, c'est-à-dire tout travail que CCL avait committé et qu'Alain n'avait pas encore relu : brèche dans le garde-fou central « CCL ne pousse jamais, Alain vérifie puis pousse » puisque rien d'autre n'était censé pousser à sa place ; aggravé par la propagation automatique aux autres clones (watchers en `git pull --ff-only` de début de cycle, dont la VM CCW, en quelques secondes) et par le fait que le fichier était écrit et committé DANS `REP_TRAVAIL` — l'arbre de travail qu'un watcher peut être en train d'utiliser pour une tâche `mode_write` au même instant. **Solution retenue** : commit construit par PLOMBERIE git (`hash-object -w` sur un fichier temporaire hors dépôt, puis `read-tree`/`update-index --cacheinfo`/`write-tree` sur un index TEMPORAIRE isolé via `GIT_INDEX_FILE`, puis `commit-tree`), sans jamais toucher à l'arbre de travail, à l'index réel ni à `HEAD` du dépôt ; racine sans parent à la première publication, sinon enfant du tip précédent (`git fetch origin pieces-jointes` best-effort) ; poussé isolément (`git push origin <sha>:refs/heads/pieces-jointes`) sur une branche **orpheline** ne contenant que `issue-attachments/` — par construction, aucun commit de code ne peut plus jamais être emporté, quel que soit l'état de la branche de travail. URL adaptée en conséquence (`.../pieces-jointes/issue-attachments/<fichier>`) ; le fichier n'est plus jamais écrit dans `REP_TRAVAIL` (transite par un fichier temporaire, nettoyé dans un `finally`). Le repli « garde-fou minimal » (refus si `rev-list --count` > 0) n'a pas été nécessaire, la plomberie s'étant révélée simple à implémenter proprement. **§18 réécrit** (nouvelle sous-section **§18.1bis** détaillant le mécanisme, **§18.2** complété : la justification de l'exception `push` ne repose plus seulement sur l'intention d'Alain mais aussi sur l'impossibilité technique désormais garantie de publier du code par cette voie). **Testé de bout en bout** sur un dépôt jetable (bare + clone) : un commit local « FIX CCL non relu » jamais poussé reste totalement absent d'origin après upload d'image (objet introuvable sur le bare, branche de travail inchangée, `HEAD`/index/arbre de travail du clone intacts — `git status --porcelain` vide) ; branche `pieces-jointes` créée avec un unique fichier sous `issue-attachments/`, sans ancêtre commun avec la branche de travail (`git merge-base` échoue, confirmant l'historique orphelin) ; deuxième upload vérifié en accumulation (2 commits, 2 fichiers, parenté correcte). Aucune section renumérotée hors les ajouts internes au §18.

## 26 juillet 2026 — issue #247

Garantit qu'aucun descendant du process `claude` ne survit au retour de `lancer_claude` (issue #247). Contexte : un `cmd.exe` de build Windows (CCW, `rebuild_scrabble.bat`) était resté vivant après la fermeture de l'issue, verrouillant `Scrabble-Setup.exe` jusqu'à un `taskkill` manuel — sans le moindre signal dans le journal ; défaut de fond, générique : rien ne garantissait qu'un process lancé pendant une tâche soit mort à la fin de celle-ci. **`lancer_claude`** (`watcher.py`) lance désormais `claude` via `subprocess.Popen` (plutôt que `subprocess.run`, pour garder la main sur le PID) avec `start_new_session=True` (POSIX) / `CREATE_NEW_PROCESS_GROUP` (Windows), isolant ce process dans un groupe/une session à lui ; un bloc **`finally`** — donc exécuté quel que soit le mode de sortie (succès, échec, `TimeoutExpired`, exception), et **avant** `commenter_resultat_avec_retry`/`fermer_issue` — appelle la nouvelle `_nettoyer_arbre_claude(proc)` : sous POSIX, `_lister_processus_pgid` énumère (lecture directe de `/proc`, sans dépendance externe) les process vivants du pgid de ce `claude`, journalise chacun en `log.warning` (PID + ligne de commande) puis `os.killpg(pid, SIGKILL)` sur ce seul groupe ; sous Windows, `taskkill /PID <pid> /T /F`. **Solution retenue** (justifiée en détail dans la nouvelle sous-section **§13** « Nettoyage de l'arbre de process après une tâche ») : terminaison de l'arbre après coup plutôt qu'un objet Job Windows (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`) — ce dernier est natif et sans fenêtre de course, mais une API Windows pure (`ctypes`/`pywin32`) sans équivalent POSIX, alors que `watcher.py` est le script UNIQUE partagé par CCL et CCW ; fenêtre de course résiduelle de quelques millisecondes entre la fin de `communicate()`/le timeout et l'appel de nettoyage, jugée négligeable et strictement meilleure que l'absence totale de garantie d'avant #247. **Point 4 (critique), vérifié explicitement** : le nettoyage ne cible **jamais** par nom d'exécutable, seulement le pgid/l'arbre du PID de CE `claude`, garanti distinct de celui du watcher et de tout watcher frère par construction (`start_new_session`/nouvelle session) — une erreur ici aurait pu arrêter tous les watchers d'une même machine. **Journalisation, pas critère d'échec** : chaque orphelin tué produit un `log.warning` explicite ; le nettoyage ne fait jamais échouer la tâche, c'est une garantie de fin de traitement. **Test de non-régression** : nouveau `tests/test_nettoyage_arbre_247.py` — un faux `claude` (script en tête de PATH) lance un vrai enfant bloqué sur lecture (FIFO jamais écrite, équivalent stdin qui n'aboutit jamais) puis termine ; le test vérifie que l'enfant est mort après le retour de `lancer_claude`, que le nettoyage est journalisé (PID présent dans un `log.warning`), et que le process de test (rôle du watcher) n'est jamais affecté — passe (`python3 tests/test_nettoyage_arbre_247.py` → ✅). Aucune section renumérotée.

## 26 juillet 2026 — issue #245

Aligne le texte historique du §14 sur l'amendement #244 (issue #245). Contexte : le paragraphe « ⚠️ Contrainte d'exécution synchrone (rappel) », hérité de #208 et volontairement laissé intact par #244 comme référence documentaire, interdisait encore catégoriquement « un mécanisme d'attente différée, de tâche en arrière-plan ou de "je répondrai plus tard" » — formulation contredite par le texte en vigueur de `consignes/globales.md` depuis #244 (l'arrière-plan encadré, avec interrogation de la sortie en boucle DANS la même exécution, y est permis ; seul conclure son tour de parole avant la fin réelle et vérifiée de l'opération reste proscrit). Un Claude Chat consultant le §14 en premier — cas fréquent, section de référence sur la délégation — pouvait lire l'interdiction absolue sans descendre jusqu'à l'encart d'injection qui la nuançait déjà, et reconduire dans une issue de build une consigne que le système n'applique plus. **§14** : le paragraphe est reformulé pour dire une seule chose, alignée sur `globales.md` — proscrit : conclure son tour de parole avant la fin réelle et vérifiée de l'opération ; permis : l'arrière-plan encadré (interrogation de la sortie en boucle DANS la même exécution) ; restent interdits sans changement : « monitor », notification, rappel programmé, formulations « je répondrai plus tard ». Reste du paragraphe conservé tel quel (aucune reprise possible après réponse, boucle `sleep` + `gh issue view` pour l'attente d'un ouvrier) ; l'encart d'injection qui suit (issues #209/#243) n'a pas été touché, sa nuance restant exacte. Recherche `arrière-plan`/`monitor`/`attente différée` sur tout le fichier : une autre occurrence trouvée hors §14 et hors pied de page — **§12.1** (ligne « Globale » du tableau des trois couches : « contrainte d'exécution synchrone et bloquante, sans attente différée, universelle depuis #243 ») — laissée telle quelle, ce résumé reste exact (l'interdit qu'elle nomme est bien l'attente différée pour conclure, pas l'arrière-plan comme technique) ; le pied de page (historique de #244 et antérieurs) laissé tel quel par consigne explicite. Aucune section renumérotée, aucun fichier `.py` ni `consignes/*.md` modifié.

## 26 juillet 2026 — issue #244

Amende la contrainte d'exécution universelle de #243 pour lever une contradiction qu'elle introduisait avec le plafond de timeout de l'outil Bash (issue #244). Contexte : le texte issu de #243 interdisait catégoriquement l'arrière-plan (« Ne lance jamais une commande en arrière-plan ») et proposait comme repli de relancer avec un timeout explicite plus long — or l'outil Bash a un timeout MAXIMUM par appel (de l'ordre de dix minutes) qu'aucun paramètre ne permet de dépasser ; si un build excède ce plafond (hypothèse plausible pour #241/#242, probablement à l'origine du basculement en arrière-plan qui avait motivé #243), l'agent se retrouvait pris entre deux interdits — attendre en un seul appel ou lancer en arrière-plan — et improviserait. Second défaut, dans la même phrase : le repli « boucle sur sa sortie DANS cette même exécution » SUPPOSE une exécution en arrière-plan (on lance, puis on interroge la sortie en boucle) ; la consigne décrivait donc le bon comportement tout en interdisant le mécanisme qui le rend possible. Le fautif n'est pas l'arrière-plan en soi, c'est de conclure son tour de parole sans avoir attendu la fin réelle de l'opération. **`consignes/globales.md`** : la fin du bullet « Contrainte d'exécution » (à partir de « Si une opération dépasse le timeout d'un appel d'outil… ») est réécrite — ce qui est interdit, c'est de CONCLURE le tour de parole avant que l'opération soit terminée et son résultat vérifié, pas l'arrière-plan comme technique ; en cas de dépassement du timeout d'un appel d'outil, deux voies restent permises : relancer avec un timeout explicite plus long tant que le plafond de l'outil le permet, OU lancer en arrière-plan À CONDITION IMPÉRATIVE d'interroger sa sortie en boucle DANS cette même exécution jusqu'à complétion réelle ; restent interdits sans changement le « monitor », la notification, le rappel programmé et toute formulation « je répondrai/j'attends… » en guise de conclusion ; rappel inchangé qu'aucune reprise n'existe (le watcher ferme l'issue dès la réponse postée). **`consignes/type_chef.md`** vérifié : sa formulation (« aucune attente différée, aucun monitor ») reste cohérente avec le nouveau texte — non touché. **§12.1** (ligne « Globale ») et **§14** (encart d'injection automatique) vérifiés : leurs résumés restent exacts sans qu'il soit besoin d'y ajouter la précision arrière-plan/plafond — non touchés. Aucune section renumérotée, aucun fichier `.py` modifié.

## 26 juillet 2026 — issue #243

Généralise l'interdiction d'attente différée à toute issue et distingue opération longue légitime du blocage sans progrès (issue #243). Contexte : les issues #241/#242 (builds Scrabble, CCW) se sont fermées `done` avec un rapport annonçant attendre une notification de fin de build ou un rappel programmé, alors que le build avait réellement abouti (`Scrabble.exe` et `Scrabble-Setup.exe` présents, datés du jour) — pas un échec de build, un rapport ne reflétant pas la réalité, produit par un agent sorti avant la fin. Deux consignes en cause, inversées par rapport à ce qu'exige une tâche longue : `consignes/globales.md` (injecté dans TOUTE issue) demandait d'abandonner toute commande « boucle/tarde anormalement (> 30s sans progrès net) » — écrit pour #214 (commande refusée par le système de permissions, bouclage réel), mais assez général pour couvrir aujourd'hui un build PyInstaller + Inno Setup (plusieurs minutes, peu de sortie visible), appliqué à la lettre ; l'interdiction qui aurait dû s'appliquer (ne jamais recourir à une attente différée, un « monitor », etc.) vivait dans `consignes/type_chef.md`, injecté SEULEMENT pour le TYPE `chef` — une issue de build n'en est pas une. Le mode de défaillance n'ayant rien de spécifique au rôle de chef (il guette toute tâche dont une étape dépasse le timeout d'un appel d'outil), la contrainte est rendue universelle. **`consignes/globales.md`** : le rappel issu de #214 est reformulé pour distinguer une commande refusée par les permissions ou bloquée SANS AUCUN PROGRÈS (→ abandon immédiat, comportement inchangé) d'une opération longue mais qui PROGRESSE normalement (build, compilation, installation de dépendances, suite de tests, clonage volumineux — → ce n'est PAS une anomalie, il faut attendre sa fin) ; le seuil de 30s ne s'applique plus qu'à l'absence de progrès, plus à la durée en soi. Nouveau rappel généralisé depuis `type_chef.md` : accomplir la tâche en une seule exécution synchrone et bloquante, jamais de commande en arrière-plan / « monitor » / notification / rappel programmé / « je répondrai quand… », relancer avec un timeout explicite plus long ou boucler DANS la même exécution en cas de dépassement du timeout d'un appel d'outil, jamais conclure sur une attente — rappel qu'aucune reprise n'existe, le watcher fermant l'issue dès la réponse postée. **`consignes/type_chef.md`** : allégé pour éviter la redondance — ne garde que la spécificité chef (boucler `sleep` + `gh issue view` en attendant la fermeture des issues ouvrières, puis synthèse finale), la contrainte générale étant désormais dans `globales.md`. **TYPE `build`** : vérification de `watcher.deduire_type_issue`/`TYPES_ISSUE` — `build` n'est PAS une valeur reconnue (`TYPES_ISSUE` = chef/ouvrier/spec_vue/spec_metier/spec_persistance/normal, et `_classer_valeur_type` n'a aucune branche pour « build » : même un en-tête explicite `| TYPE | build |` retomberait sur `normal`) ; `consignes/type_build.md` n'a donc PAS été créé — le mécanisme ne s'y prête pas sans modifier `watcher.py` (hors périmètre de cette issue), et de toute façon le vrai correctif (la contrainte universelle dans `globales.md`) couvre déjà le cas des builds sans dépendre d'un TYPE dédié. **§12.1** : la parenthèse résumant les rappels globaux (ligne « Globale ») mise à jour pour refléter la distinction blocage/progrès et la contrainte d'exécution synchrone désormais universelle. **§14** : le bloc « Contrainte d'exécution impérative » renommé « rappel » et son encart d'injection automatique mis à jour pour pointer vers `globales.md` (universel depuis #243) plutôt que `type_chef.md`, qui n'ajoute plus que la spécificité chef. **§1** : rattrapage d'une omission de #240 — la réécriture du paragraphe sur le pull automatique avait fait disparaître la parenthèse sur les projets à **périmètre dynamique** (dépôt-cible défini par issue, dépôts d'audit non rafraîchis par le pull automatique, distincts du clone de travail du watcher) ; réintroduite, adaptée au nouveau texte. Aucune section renumérotée.

## 26 juillet 2026 — issue #240

Correctif documentaire §1/§14/§16 et rattrapage de trois issues committées sans mise à jour du DOC (issue #240). Incident du 26/07 : le clone `C:\CCW\Bridge_Agent` de la VM (celui d'où s'exécute réellement `watcher.py`) avait **80 commits de retard** sur `origin/master`, sans aucun signal — le service tournait avec du code antérieur à l'issue #195, cause probable de l'incident #236 (issue fermée `done` sans commentaire de résultat). **§1** réécrit : le `git pull --ff-only` automatique de début de cycle porte bien sur `REP_TRAVAIL` avec la même logique CCL/CCW, mais ne met à jour le CODE du watcher que lorsque `REP_TRAVAIL` coïncide avec le clone du dépôt Bridge_Agent — vrai côté CCL, **faux** côté CCW en modèle unifié (#231), où `REP_TRAVAIL = \\VBOXSVR\CCW_Share` n'est même pas un dépôt git et où le clone contenant `watcher.py` (`C:\CCW\Bridge_Agent`) vit ailleurs, mis à jour par personne. L'ancienne affirmation « comportement identique CCL et CCW » est supprimée car trompeuse sur ce point précis. **§16** gagne un bloc d'avertissement opérationnel : ce clone n'est **jamais** mis à jour automatiquement ; procédure obligatoire après tout push touchant `watcher.py` — `git pull --ff-only` dans `C:\CCW\Bridge_Agent` **puis redémarrage du service** `CCW-Watcher` (`nssm restart`, un pull seul ne suffit pas : un process Python déjà démarré garde en mémoire le code chargé à son lancement) — avec la commande de contrôle rapide `git status -sb` (ne doit jamais afficher `behind`), et le cas réel des 80 commits de retard comme justification. **§14** corrigé : dans le bloc « Quand NE PAS passer par un chef » (#225), la référence au service `CCW-Watcher-<Projet>` — nom venant du modèle multi-projets abandonné par #231 — est remplacée par `CCW-Watcher`. Rattrapage de trois issues committées sans entrée de pied de page : **#237** — `commenter_issue`/`editer_dernier_commentaire` passent par `--body-file` (fichier temporaire UTF-8) au lieu de `--body`, supprimant la limite argv Windows de 32767 caractères ; `commenter_resultat_avec_retry` vérifie désormais la publication par relecture de l'issue (un exit code 0 de `gh` ne suffit plus, la présence effective du commentaire est exigée) ; nouveau marqueur `MARQUEUR_RESULTAT` (`<!-- bridge:resultat -->`) en tête du commentaire de résultat, utilisé aussi par `resultat_deja_poste` à la place de l'ancienne sous-chaîne `"## Résultat"` qui matchait à tort `"## Résultat attendu"` ; test `tests/test_verification_commentaire_237.py` ; deux effets de bord assumés — deux appels `gh` par tentative, et possibilité d'un commentaire en double si la publication réussit mais que la relecture échoue transitoirement (perte silencieuse échangée contre doublon visible). **#238** — `fermer_issue` inspecte désormais les codes de retour de `close` et `add-label`, retourne un booléen, et journalise explicitement les états incohérents (fermée sans label / label sans fermeture) sans compensation automatique. **#239** — libellé d'agent de l'ACK déduit automatiquement de `platform.system()` (« agent Linux » / « agent Windows »), avec champ optionnel `LIBELLE_AGENT` pour forcer un libellé explicite si la détection automatique ne convient pas ; le §16 avait déjà été modifié par cette issue mais aucune entrée de pied de page n'avait été ajoutée — rattrapée ici. Aucune section renumérotée.

## 26 juillet 2026 — issue #233

§3 « Créer une issue » : ajout d'une **exception `PROJET`** pour les issues `for-windows` (issue #233, suite #231). Rapport remonté par le Claude du projet `actualise` : lors de la génération d'une issue de build Windows, le champ `PROJET` avait été renseigné avec `actualise` au lieu de `bridge_agent`, en appliquant par erreur la règle générale du §3 (« nom exact du projet cible »). Or le §16.3 (modèle CCW unifié, #231) applique correctement `PROJET=bridge_agent` dans son template — c'est la config du watcher CCW unique qui compte, pas le projet réellement construit — mais le §3, consulté en premier par Claude Chat, ne mentionnait pas cette exception. Ajout d'un second bloc d'avertissement juste après celui existant (« Claude Chat doit toujours inclure `| PROJET | <nom> |` ») précisant que pour les issues `for-windows`, `PROJET` reste toujours `bridge_agent`, le nom du projet cible s'exprimant en texte dans le corps (chemins, `git clone`/`git pull`), avec renvoi au template du §16.3. Aucune section renumérotée.

## 26 juillet 2026 — issue #231

§16 « Agent Windows CCW » : documentation du **modèle CCW unifié** (issue #231), qui remplace le modèle multi-projets (#170, un service NSSM par projet). Un seul service NSSM `CCW-Watcher` surveille désormais les issues `for-windows` de `AlainDelree/Bridge_Agent`, `REP_TRAVAIL = \\VBOXSVR\CCW_Share` (accessible depuis Linux à `/home/alain/Bridge_Agent_CCW_Share/`), chaque projet buildé étant cloné dans un sous-dossier dédié `\\VBOXSVR\CCW_Share\CCW\<projet>\` — séquencement strict des builds par construction (un seul process `watcher.py`), zéro contention CPU/RAM entre builds parallèles. Validé en production avec le build PyInstaller d'`actualise`. Introduction du §16 réécrite (titre « (en préparation) » retiré, devenu opérationnel) ; nouvelle sous-section **§16.3 « Procédure — builder un projet Windows »** détaillant le template d'issue en 4 étapes (exception `git config --global --add safe.directory` sur le chemin UNC — obligatoire une seule fois par sous-dossier —, clone ou `git pull --ff-only`, `pip install -r requirements.txt`, build `python -m PyInstaller --noconfirm --onedir --noconsole`), la récupération manuelle des artefacts côté Linux et le rappel qu'aucun token GitHub Contents n'est requis (dépôts publics, seul le token Issues du service `CCW-Watcher` sert). Les scripts `ajouter_projet_ccw.ps1` et `finaliser_projet_ccw.ps1` (tableau de provisioning) marqués **« obsolète — modèle multi-projets abandonné, conservé à titre historique »** — ne plus les utiliser, mais conservés dans le dépôt sans suppression. Reste du §16 (§16.1 maintenance 90 jours, §16.2 onglet CCW, description historique du modèle multi-projets #170) laissé inchangé, hors du périmètre de cette issue.

## 26 juillet 2026 — issue #225

§14 « Délégation Chef → Ouvrier » : ajout d'un bloc **« Quand NE PAS passer par un chef »** (issue #225), inséré juste après le paragraphe « Principe » et avant « Ce n'est pas déclenché automatiquement… ». Contexte : sur le projet `actualise`, une tâche entièrement Windows avait donné lieu à une issue chef CCL dont le seul travail était de créer immédiatement un ouvrier CCW et d'attendre sa fermeture — sans étape réelle côté Linux, correct mais coûteux (deux issues, deux invocations `claude`, TIMEOUT long, attente synchrone bloquante payée pour rien). Le nouveau bloc pose le **critère de décision** : le chef se justifie quand la tâche comporte du travail réel côté Linux (avant et/ou après) dans la même unité de travail ; si la TOTALITÉ de la tâche s'exécute sous Windows, créer directement l'issue avec `| LABELS | for-windows |` (§3) plutôt qu'un chef. **Contre-exemple explicite** : un chef qui se contente de créer un ouvrier puis d'attendre sa fermeture, sans orchestration réelle, est du surcoût pur. Rappel que l'**exemple validé** plus bas dans la section (dictionnaire déposé côté Linux puis rebuild côté Windows) reste un cas où le chef EST justifié — la nouvelle règle ne le contredit pas. **⚠️ Contrepartie opérationnelle** ajoutée dans le même bloc : le rallumage automatique du watcher à la création d'une issue (§13, mécanisme 2) ne vaut QUE pour les issues `for-linux` — une issue `for-windows` directe ne démarre rien, donc vérifier dans l'onglet CCW (§16.2) que la VM `CCW-Build` tourne et que le service `CCW-Watcher-<Projet>` est démarré avant d'en envoyer une, sinon elle reste ouverte sans aucun signal. En miroir, **§3** (paragraphe décrivant le champ `LABELS`, juste après la phrase sur le cas d'usage `| LABELS | for-windows |`) gagne une phrase de renvoi croisé vers ce bloc du §14. Aucune section renumérotée ; reste du §14 (contrainte d'exécution impérative, format des titres, timeout du chef, exemple validé) et reste du §3 inchangés.

## 25 juillet 2026 — issue #224

Nouvelle section **§19 « Calibration automatique du TIMEOUT »** (issue #224), documentant de bout en bout le système mis en place par les issues #220 (extension d'`historique_durees.json`), #221 (mécanique EWMA `etat_timeout.json`/`etat_ambiance.json`), #222 (exposition du `TIMEOUT_suggéré` dans le commentaire de clôture GitHub) et #223 (exclusion des `expiree=true` du badge d'estimation de l'interface). Jusqu'ici ce système n'était documenté nulle part dans `BRIDGE_AGENT_DOC.md` — seul `CONTEXTE.md` en gardait une trace partielle, ajoutée par #221 et jamais mise à jour depuis, de toute façon plafonnée par sa limite de taille pour l'injection prompt (§12.1). La nouvelle section couvre, à partir d'une lecture du code réel de `watcher.py`/`app/issues.py` (pas une paraphrase des rapports d'issue) : l'objectif et le principe d'inspiration (RTO TCP, Jacobson/Karels), la formule complète et chacun de ses termes, les deux fichiers d'état (`logs/etat_timeout.json`, `logs/etat_ambiance.json` — partagés entre watchers, verrouillés, écriture atomique), le tableau des constantes actuelles en soulignant explicitement qu'elles sont des valeurs de DÉPART non backtestées, le canal d'exposition (bloc `⏱️/📊` dans le commentaire de clôture, sans aucune application automatique — le TIMEOUT réellement utilisé reste celui de l'en-tête, `extraire_timeout`), et une liste explicite des limitations connues (`tag_reseau` jamais peuplé donc `F_reseau`/`F_local` neutres, incohérence inerte de `lire_timeout_suggere` sur échec définitif, démarrage à froid trompeusement optimiste, aucun backtest des constantes, distinction avec le badge `estimer_duree` de #223). Aucune autre section renumérotée ni modifiée.

## 24 juillet 2026 — issue #217

Correctif horloge d'auto-extinction (issue #217) : le watcher pouvait s'éteindre **immédiatement après un traitement réel** lorsque celui-ci s'étirait au-delà du délai d'inactivité (`DELAI_INACTIVITE_MIN`, défaut 20 min). Cause : `derniere_activite` (horloge monotone d'inactivité, #200) n'était réarmée qu'**en tête de cycle**, juste après `lister_issues()` et **avant** de lancer `traiter_issue()` — donc jamais pendant le traitement (potentiellement long : plusieurs timeouts de 300 s + retries en cascade). Si le traitement d'une seule issue dépassait le délai (cas réel `watcher-scrabble.log` du 24/07/2026 : #237/#238 traités sans interruption de 08:59 à 09:22, puis extinction à 09:23:08 — 14 s après le succès de #238), l'horloge restait figée à l'instant du **début** du cycle ; le test d'extinction du cycle suivant se déclenchait alors sur une horloge périmée, ne reflétant pas le travail réellement effectué. **Correctif** (`watcher.py`, boucle principale) : réarmement de `derniere_activite` **aussi APRÈS** la boucle de traitement, dès qu'au moins une issue traitable a été traitée ce cycle (option a du diagnostic — réarmer sur le travail réel, préférée à l'option b « revérifier `lister_issues()` avant `sys.exit` » car elle satisfait plus directement l'objectif « ne jamais éteindre si du travail vient d'avoir lieu », sans appel réseau supplémentaire ni cas où une issue devenue fermée entre-temps laisserait l'extinction filer). Le flag `travail_a_faire` (calculé une fois) conditionne les deux réarmements ; l'extinction reste possible quand plus rien n'est traitable. **Test de non-régression** : `tests/test_auto_extinction_217.py` pilote le vrai `watcher.main()` avec horloge mockée (`time.monotonic`/`time.sleep` patchés) sur 3 scénarios — (1) traitement long ~23 min + issue restante → **pas** d'extinction prématurée (échoue sur le code d'avant #217, passe sur le code corrigé), (2) inactivité réelle → extinction bien déclenchée, (3) issue non-traitable (`done`) → n'empêche pas l'extinction. §13 (mécanisme 3 « Extinction automatique ») mis à jour pour décrire le double réarmement avant/après.

## 24 juillet 2026 — issue #214

Nouveau rappel global « abandon immédiat au refus de permission » (issue #214) : ajout, à la fin de `consignes/globales.md`, d'un rappel systématique — si une commande/un outil est **refusé par le système de permissions** (session non-interactive, aucune approbation possible) ou **boucle/tarde anormalement** (> 30s sans progrès net), CCL doit **abandonner immédiatement** l'approche et le signaler dans son rapport plutôt que de retenter, en basculant si possible sur un repli plus simple (lecture directe, `grep`, analyse manuelle) et sans jamais insister sur une commande déjà refusée. Motivation : comparaison des issues Scrabble #235 (timeout à 300s, bouclage sur une commande refusée) et #238 (succès) — la seule différence significative était la présence, dans #238, d'une consigne explicite d'abandon-au-lieu-de-retenter ; en session non-interactive, un refus de permission Claude Code est systématique et définitif (aucun utilisateur pour approuver), donc retenter est vain. Consigne volontairement **générale** (pas spécifique à Scrabble ni à JS/eslint) car le problème touche toute commande nécessitant une approbation (installation de paquet, exécution d'un binaire, etc.), quel que soit le projet ou le langage. §12.1 : la parenthèse résumant les rappels globaux dans le tableau des trois couches est complétée (ajout d'« abandon immédiat au refus de permission / boucle anormale ») ; la liste complète des rappels n'étant pas reproduite ailleurs dans la doc, aucune autre duplication à mettre à jour.

## 23 juillet 2026 — issue #211

Déplacement de l'injection des consignes trois couches dans `watcher.py` — couverture universelle (issue #211). Les consignes (globales/type/projet, #209) ne sont plus écrites dans le **corps** de l'issue par `app/issues.py` (chemin qui ne couvrait QUE les issues créées via le formulaire web), mais injectées dans le **prompt donné à CCL au moment du traitement** par `watcher.py` (`lancer_claude` → nouvelles `_consignes_injectees`/`_lire_consigne`, reprises de `app/issues.py`), exactement sur le modèle de `CONTEXTE.md`/`FICHIER_CONTEXTE`. Le point de passage devient **unique** : peu importe le chemin de création — formulaire web, `gh issue create` d'un chef (§14), création manuelle GitHub (§3) — `watcher.py` déduit le TYPE (`deduire_type_issue` sur le titre/corps réels) et le projet (`CFG.nom`), puis ajoute le bloc **après** le bloc `CONTEXTE` et **avant** la clause de périmètre / le garde-fou (regroupement des « règles » en fin de prompt, zone la mieux suivie). Cas particulièrement corrigé : les issues **ouvrières créées par un chef** (chemin 2, vraies tâches `mode_write`) recevaient auparavant zéro consigne — c'est justement là que les rappels de sécurité comptent le plus. `app/issues.py::construire_body` revient à un corps **en-tête + corps rédigé** seulement (suppression de `_consignes_injectees`/`_lire_consigne`/`DOSSIER_CONSIGNES` et de l'import `logging` devenu inutile) — source unique de vérité désormais côté watcher, plus de double injection. Garde-fous inchangés (#209) : `globales.md` absent → `log.warning` sans bloquer le traitement ; `type_*`/`projet_*` absents → silencieux. Conséquence assumée (comme pour `CONTEXTE.md`) : les consignes ne sont plus visibles dans le corps d'une issue sur GitHub. **§12.1 réécrite** (modèle prompt + couverture universelle des 3 chemins + emplacement dans le prompt) et **§10** mis à jour (`consignes/` = injecté dans le prompt CCL, plus « en tête de chaque issue »). Testé de bout en bout par une issue `TYPE=chef` `mode_write` créée **directement en CLI** (`gh issue create`, hors formulaire) : le prompt CCL assemblé par le watcher contient bien les consignes globales + `type_chef.md`.

## 23 juillet 2026 — issue #209

Architecture à trois couches d'injection de consignes (issue #209) : nouveau dossier `consignes/` à la racine, injecté **dans le corps de chaque issue** par `app/issues.py` (`construire_body` → `_consignes_injectees`), entre le tableau d'en-tête et le corps rédigé par Claude Chat. Trois couches, de la plus générale à la plus spécifique : **globales** (`consignes/globales.md`, **NON-optionnel** — rappels de sécurité transversaux : ne jamais pousser, backup avant modif, respect du périmètre — injecté dans TOUTE issue), **type** (`consignes/type_<type>.md`, **facultatif** — ex. `type_chef.md` reprenant la contrainte d'exécution synchrone du #208, injecté selon le TYPE déduit par `watcher.deduire_type_issue`), **projet** (`consignes/projet_<projet>.md`, **facultatif** — aucun créé par défaut). Ordre final : en-tête → globales → type (si présent) → projet (si présent) → corps. Vaut en **mono-issue comme en mode lot** (chaque bloc `#Titre:` passe par `construire_body` avec son propre TYPE). **Choix délibéré anti-piège de maintenance** : contrairement à `CONTEXTE.md`, les couches type/projet sont sans obligation de présence (un projet sans `projet_<nom>.md` fonctionne normalement, rien à créer/maintenir) et créées uniquement à la demande. Garde-fous : fichier `type_*`/`projet_*` absent → aucune injection **sans** log (normal, pas une anomalie) ; `globales.md` introuvable → `logging.warning` clair **sans jamais faire échouer** la création d'issue. Nouvelle sous-section **§12.1** décrivant l'architecture, mise à jour du **§10** (dossier `consignes/`) et du **§14** (la contrainte d'exécution synchrone du chef n'est plus à recopier manuellement — elle est injectée automatiquement via `consignes/type_chef.md`). Testé de bout en bout (issue `TYPE=chef` réelle : corps GitHub contenant, dans l'ordre, globales puis chef puis corps original).

## 23 juillet 2026 — issue #208

Finalisation du nettoyage doc MVC (issue #208, suite #207) : le §14 « Délégation Chef → Ouvrier » gagne un bloc **« ⚠️ Contrainte d'exécution impérative »** rappelant que le chef doit accomplir la TOTALITÉ de sa tâche (attente de fermeture des ouvriers + synthèse finale comprises) en **une seule exécution synchrone et bloquante** — aucune reprise n'étant possible après qu'une issue a été répondue/fermée, ne jamais recourir à une attente différée, une tâche en arrière-plan ou un « je répondrai plus tard » ; si une attente est nécessaire, boucler (`sleep` + `gh issue view`) DANS la même exécution. Cette finalisation confirme aussi l'absence des fichiers `CONTEXTE_VUE.md`/`CONTEXTE_METIER.md`/`CONTEXTE_PERSISTANCE.md` à la racine de bridge_agent (jamais créés ici ; seul `CONTEXTE.md` existe et est conservé).

## 23 juillet 2026 — issue #207

Nettoyage doc MVC (issue #207) : **suppression de l'ancien §15 « Pattern Chef + Specs MVC (évolution future) »**, purement prospectif et jamais implémenté (le watcher ne lit pas le champ `SPECS`, aucun routage par couche Vue/Métier/Persistance n'existe) ; les sections suivantes **ne sont pas renumérotées** (16, 17, 18 restent 16, 17, 18) pour préserver les références croisées existantes. Le **§14 est entièrement réécrit** et recadré « Délégation Chef → Ouvrier (changement d'environnement) » : on ne garde que l'usage réel validé — un CCL « chef » crée lui-même une issue « ouvrier » ciblant un autre environnement (typiquement CCL Linux → CCW Windows) via `gh issue create` et surveille sa fermeture avant de livrer, sur instruction explicite (pas de détection auto du rôle chef, pas de décomposition automatique générique) — avec conseil de `TIMEOUT` généreux côté chef et l'exemple validé du build Scrabble/ouvrier CCW. En complément, l'issue chef #207 délègue à 6 issues « ouvrier » (une par projet actif hors bridge_agent et ff_galerie) la suppression des fichiers `CONTEXTE_VUE.md`/`CONTEXTE_METIER.md`/`CONTEXTE_PERSISTANCE.md` — vestiges du §15 abandonné — `CONTEXTE.md` (mécanisme standard hors MVC) étant conservé partout.

## 20 juillet 2026 — issue #191

§18 (nouveau) « Pièces jointes image dans les issues » (issue #191) : l'onglet « Nouvelle issue » accepte désormais un **upload optionnel PNG/JPEG** (champ fichier + bouton « Joindre une image » à côté du corps). Nouvelle route **`POST /joindre-image`** (`app/issues.py`, `joindre_image()`) : valide le type (Content-Type **et** magic bytes) et la taille (**≤ 5 Mo**), sauvegarde dans **`issue-attachments/`** (racine du `REP_TRAVAIL`) sous un nom **horodaté** anti-collision (`AAAAMMJJ-HHMMSS-<nom>.ext`), puis `git add` + `commit` + **`git push origin HEAD:<branche>`** (branche déduite **dynamiquement**, jamais supposée master/main), et retourne l'URL **`raw.githubusercontent.com/<owner>/<repo>/<branche>/issue-attachments/<fichier>`** — format qui s'affiche correctement dans les issues GitHub. Le frontend (`static/js/app.js`, `joindreImage()`/`insererDansCorps()`) insère alors **automatiquement** `![<nom>](<url>)` dans le corps à la position du curseur. **Exception `push` assumée et documentée (§18.2)** : ce commit+push est déclenché par **ALAIN** via l'outil (son action manuelle), **pas par CCL/le watcher** — la règle « CCL ne pousse jamais » n'est donc pas violée (elle vise les modifications de code de l'agent, pas une image qu'Alain publie lui-même). Gestion d'erreurs (§18.4) : **push échoué → aucune URL insérée** (commit conservé en local, poussable plus tard), **projet sans dépôt git → message clair**, type/taille/contenu invalides refusés proprement. `issue-attachments/` volontairement **hors `.gitignore`** (les images doivent être suivies/poussées). Testé de bout en bout (dépôt jetable + remote bare : succès + URL correcte, et chemins d'échec type/taille/magic/push).

## 20 juillet 2026 — issue #187

§17 (nouveau) « Notifications centralisées — détection serveur des transitions » (issue #187) : `new_issue.py`, qui tourne en permanence sur le ThinkPad, détecte désormais LUI-MÊME par polling `gh` les transitions d'issues (fermeture `done` = succès ; label `needs-human` = échec définitif) de **tous** les projets (for-linux ET for-windows), et déclenche bip/`notify-send`/`ntfy` **localement**, y compris pour les issues traitées par la VM **CCW** — **sans aucun appel réseau initié par la VM** (la VM n'écrit que sur GitHub). Nouveau module partagé `notifications.py` (racine) factorisant `bip`/`notifier_bureau`/`notifier_ntfy`/`notifier`, importé par `watcher.py` (enveloppes minces déléguant, sites d'appel inchangés) ET par le nouveau poller `app/notifications_poller.py` (thread démon lancé par `new_issue.py`). Script bip **déplacé/recréé** de `~/NicLink/bip.py` vers `scripts/bip.py` (infrastructure partagée) ; défaut `SCRIPT_BIP` et `configs/*.conf` mis à jour. Anti-doublon (point 4) : réglage `NOTIFIER_LOCAL` (`.conf`, défaut `true`) coupant la notif du watcher + portée `BRIDGE_NOTIF_SCOPE` (env, défaut `for-windows`) du poller. **Défaut livré sans régression ni doublon** (CCL notifie via son watcher, CCW via le poller — variante propre de l'option b) ; **option (a) « centralisation complète » recommandée mais laissée au choix d'Alain** car elle fait de `new_issue.py` une dépendance dure de toute notification (or il n'a pas encore de service systemd) — implémentée et à un réglage près (`BRIDGE_NOTIF_SCOPE=all` + `NOTIFIER_LOCAL=false` partout). **Action requise côté VM CCW** : poser `NOTIFIER_LOCAL=false` dans `configs\*-ccw.conf` pour éviter un double `ntfy`. Bonus (point 5) : le poller lit les labels COURANTS à la fermeture, donc `notif_pc`/`notif_gsm` ajouté EN COURS de traitement est bien pris en compte. Filtre de récence (`BRIDGE_NOTIF_RECENCE_MIN`, défaut 30 min) + amorçage silencieux au 1er cycle évitent le spam de vieilles issues au démarrage ; état en mémoire process.

## 20 juillet 2026 — issue #186

§1 « Vue d'ensemble » : documentation du **`git pull --ff-only` automatique en début de cycle** de `watcher.py` (issue #186, suite du #185 qui l'a implémenté). Le watcher rafraîchit son clone (`REP_TRAVAIL`) au début de chaque cycle de polling, juste avant `lister_issues()` : fast-forward transparent en cas de succès ; en cas de commits locaux non poussés (divergence) le `--ff-only` échoue proprement sans RIEN écraser et le watcher poursuit sur le code local — donc aucun risque à oublier un `git push`. Comportement **identique CCL (Linux) et CCW (Windows)** puisque `watcher.py` est le script unique partagé ; les projets à périmètre dynamique (dépôt-cible par issue) ne sont pas concernés. Un `git pull`/relance manuel reste possible pour une mise à jour immédiate (confort, plus une nécessité). Aucune instruction obsolète de « git pull manuel obligatoire » à corriger dans le §16 (aucune ne subsistait).

## 19 juillet 2026 — issue #174

§16 « Agent Windows CCW » : **onglet « CCW » dans l'interface web** (issue #174, sous-section §16.2) — pilotage complet de la VM et des projets CCW depuis Linux, sans PowerShell manuel dans la VM. Backend `app/ccw.py` (routes `/ccw/*`) exécutant les scripts existants à distance via `VBoxManage guestcontrol` : état/démarrage de la VM (`demarrer_ccw.sh`), liste des projets (nouveau `lister_projets_ccw.ps1`, sortie JSON encadrée), ajout (`ajouter_projet_ccw.ps1`) et finalisation non interactive (nouveau `finaliser_projet_ccw_auto.ps1` + `mettre_a_jour_tokens_ccw.ps1` doté d'un mode `-FichierTokens`). Sécurité : tokens jamais passés en argument ni journalisés (fichier temporaire `0600` poussé puis supprimé des deux côtés dans un `finally`) ; mot de passe `ccw-admin` lu depuis `CCW_ADMIN_PASSWORD` ou `configs/ccw_admin.secret` (gitignoré). Nouvel onglet + panneau dans `templates/index.html`, fonctions `ccw*` dans `static/js/app.js`, classe `.message.avertissement` dans `style.css`.

## 19 juillet 2026 — issue #173

§16 « Agent Windows CCW » : **finalisation d'un projet CCW en une seule commande** (issue #173, suite #170) — ajout de `provisioning/windows/finaliser_projet_ccw.ps1` qui, à partir du seul `-NomProjet`, dérive le service/dossier/config (même logique qu'`ajouter_projet_ccw.ps1`), vérifie leur existence, demande `TOPIC_NTFY` et l'écrit directement dans le config (remplacement ciblé du placeholder `###TOPIC_NTFY_A_DEFINIR###`, reste du fichier préservé en UTF-8 sans BOM), rappelle avec une pause la marche à suivre pour créer le token GitHub dédié, puis **appelle** `mettre_a_jour_tokens_ccw.ps1` (pas de duplication) pour la saisie masquée + pose des tokens + redémarrage + vérif des logs, et conclut par un résumé ; `mettre_a_jour_tokens_ccw.ps1` gagne un paramètre `-NomLog` pour vérifier le bon log de service (`ccw-<nom>-service.log`) ; les rappels d'`ajouter_projet_ccw.ps1` (en-tête + fin de script) et le §16 pointent désormais vers cette commande unique au lieu des 3 étapes dispersées. Non exécuté contre une VM réelle (test manuel par Alain).

## 19 juillet 2026 — issue #172

§11 « Conventions de code » : **règle BOM UTF-8 obligatoire pour tout script `.ps1`** (issue #172) — ajout du BOM (`EF BB BF`) manquant sur `ajouter_projet_ccw.ps1` (#170) et `mettre_a_jour_tokens_ccw.ps1` (#168), qui plantaient sinon sous Windows PowerShell 5.1 avec des `UnexpectedToken` en cascade sur les accents (même signature que #151) ; règle généralisée en §11 + rappel en tête du §16 pour prévenir la récidive (`provisionner.ps1` déjà OK depuis #151).

## 19 juillet 2026 — issue #170

§16 « Agent Windows CCW » : **généralisation multi-projets de CCW** (issue #170) — ajout de `provisioning/windows/ajouter_projet_ccw.ps1` (un clone + un config `configs\<nom>-ccw.conf` + un service NSSM `CCW-Watcher-<NomProjet>` dédiés par projet, sur le modèle des watchers CCL ; paramétrable `-NomProjet`/`-Depot`, idempotent, `watcher.py` inchangé) ; documentation du modèle « un service par projet » et de la **règle d'expiration alignée** des tokens (un token fine-grained dédié par dépôt, mais tous à la même échéance ≈ 17 octobre 2026) ; commande exacte d'instanciation de Scrabble et marche à suivre pour créer son token dédié (Repository access → Scrabble uniquement, Issues read/write + Metadata read-only).

## 19 juillet 2026 — issue #169

§16 « Agent Windows CCW » : ajout de la sous-section **§16.1 Maintenance périodique (renouvellement à 90 jours)** (issue #169) — runbook séquentiel consolidé pour la fenêtre de maintenance d'octobre 2026 : tableau de repères de dates (install **2026-07-19**, expiration Windows **2026-10-17**, token GitHub aligné ~90 j mais non stocké), puis procédure en 3 étapes renvoyant aux scripts existants — vérifier (`verifier_expiration_ccw.py`), recréer la VM (`creer_vm_ccw.py --recreate` + ré-attacher un ISO frais + `lancer_provisioning.py`), renouveler les tokens (`mettre_a_jour_tokens_ccw.ps1`) — sans dupliquer le détail technique déjà présent dans le §16.

## 19 juillet 2026 — issue #168

§16 « Agent Windows CCW » : ajout du script `provisioning/windows/mettre_a_jour_tokens_ccw.ps1` (issue #168) — renouvellement des tokens `GH_TOKEN`/`CLAUDE_CODE_OAUTH_TOKEN` du service `CCW-Watcher` sans reconstruire à la main la chaîne `AppEnvironmentExtra` : saisie masquée (`Read-Host -AsSecureString`), séparateur `` `n`` impératif entre les deux paires (un espace corrompt `GH_TOKEN` → « Bad credentials »), `nssm set`/`nssm restart`, puis affichage automatique des 10 dernières lignes de `logs\ccw-service.log` pour confirmer l'absence d'erreur d'auth.

## 19 juillet 2026 — issue #167

§16 « Agent Windows CCW » : alerte d'expiration de l'éval 90 jours (issue #167) — ajout de `provisioning/windows/eval-expiration.json` (date d'installation **2026-07-19**, expiration **2026-10-17**) et du script `provisioning/windows/verifier_expiration_ccw.py` (côté Linux : calcule les jours restants, alerte + code de sortie 2 à ≤ 10 j, sinon confirmation calme ; `python3 provisioning/windows/verifier_expiration_ccw.py`) ; rappel `cron` + `ntfy` hebdomadaire proposé mais laissé à l'activation d'Alain.

## 19 juillet 2026 — issue #166

§16 « Agent Windows CCW » : ajout du script `provisioning/windows/demarrer_ccw.sh` (issue #166), wrapper de démarrage de la VM `CCW-Build` depuis CCL (headless par défaut, `--gui`/`--fenetre` pour une fenêtre, `--status` pour l'état sans rien démarrer).

## 19 juillet 2026 — issue #153

§3 « Créer une issue » : ajout d'une note sur la **convention de présentation côté Claude Chat** pour l'envoi en lot (issue #153) — quand Claude Chat prépare plusieurs issues, il les présente toutes à la suite dans un seul bloc de code (pas un bloc par issue) pour un copier-coller en un clic.

## 18 juillet 2026 — issue #149

§16 « Agent Windows CCW » : `REP_TRAVAIL` généré par `provisionner.ps1` pointe désormais vers le **chemin UNC** `\\VBOXSVR\CCW_Share` (et non la lettre automontée `$LettrePartage`), seul accessible au service `CCW-Watcher` tournant sous LocalSystem (issue #149, suite #148) ; `$LettrePartage` conservé pour référence mais plus utilisé pour construire `REP_TRAVAIL`.

## 18 juillet 2026 — issue #148

le watcher CCW tourne comme **vrai service Windows** enregistré via NSSM (issue #148, suite #147) — `provisionner.ps1` installe `NSSM.NSSM` (winget) et enregistre le service `CCW-Watcher` (`SERVICE_AUTO_START` + `AppExit Default Restart` + `AppRestartDelay 5000`, stdout/stderr → `logs\ccw-service.log`, idempotent via `nssm stop`/`remove`), en remplacement de l'ancienne tâche planifiée `-AtLogOn` qui ne redémarrait pas au boot sans session ; équivalent direct des services systemd du §13.

## 18 juillet 2026 — issue #147

provisioning **phase 2** (issue #147, suite #146) — ajout de `provisioning/windows/provisionner.ps1` (installe l'outillage dans la VM via winget + Claude Code natif, clone le dépôt, écrit `ccw.conf`, enregistre la tâche planifiée `CCW-Watcher`) et `lancer_provisioning.py` (pousse/exécute ce script depuis CCL via `VBoxManage guestcontrol`) ; `watcher.py` inchangé (portable, `LABEL` paramétrable) ; limite Task Scheduler vs `Restart=always` documentée.

## 18 juillet 2026 — issue #146

ajout du §16 et du label `for-windows` (issue #146) : provisioning phase 1 de la VM Windows CCW (`provisioning/windows/creer_vm_ccw.py` + `autounattend.xml`) destinée aux builds .exe délégués par CCL.

## 17 juillet 2026 — issues #135, #101, #97 (suite #96)

Bridge_Agent v1, 4 projets actifs. §3 « Créer une issue » : ajout de l'**envoi en lot** (issue #135) — coller plusieurs blocs `#Titre:` à la suite dans le même corps déclenche le mode lot (bouton « Envoyer le lot (N issues) »), chaque bloc étant envoyé en séquence comme une issue indépendante (avec ses `PROJET`/`TIMEOUT`/`MODELE` optionnels), sans validation intermédiaire, suivi d'un résumé listant le résultat de chacune. Ajout du projet `ecole` (AlainDelree/Ecole, ~/Ecole) aux tableaux §2 et §7 (issue #101). Section 15 « Chef + Specs MVC » : champ `SPECS` (pluriel, minuscules, combinable en une ligne) — correction du champ `SPEC` introduit par erreur (issue #97, suite #96).
