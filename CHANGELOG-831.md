## Issue #831 — Interface web : exiger le mot de passe en mode --lan et limiter les tentatives de connexion par adresse

Le mode `--lan` de `new_issue.py` écoutait sur toutes les interfaces du
réseau local (host 0.0.0.0, HTTP) **sans mot de passe** : le filtre
`AUTEURS_AUTORISES` (#563) ne protège pas ce cas, car les issues créées par
le formulaire sont publiées avec le jeton d'Alain. `--lan` est désormais
aligné sur `--externe` : mot de passe obligatoire, login exigé pour toute
page protégée.

- **`app/__init__.py`** : clé d'état `MODE_EXTERNE` renommée `ACCES_RESEAU`
  (vrai dès que l'écoute dépasse 127.0.0.1, donc en `--lan` comme en
  `--externe` — plus seulement en `--externe`).
- **`app/auth.py`** : `login_requis` exige désormais le login dès que
  `ACCES_RESEAU` est vrai. Ajout d'un blocage par **adresse source**
  (`_ECHECS_PAR_ADRESSE`, en mémoire du processus, perdu au redémarrage),
  en complément du blocage par session (cookie) existant que la suppression
  du cookie contournait entièrement : après 5 échecs depuis une adresse,
  refus des tentatives de cette adresse pendant 15 minutes (même message
  d'erreur), remis à zéro par un succès, expire à l'échéance ou au
  redémarrage. L'adresse cliente (`_adresse_cliente`) reste `remote_addr`
  (non forgeable par un appareil du réseau local qui se connecte
  directement au port exposé) ; en mode `--externe`, l'en-tête
  `Cf-Connecting-Ip` posé par cloudflared n'est pris en compte que lorsque
  `remote_addr` est `127.0.0.1`/`::1` (c'est-à-dire lorsque la requête a
  nécessairement transité par le tunnel local), pour qu'il ne puisse pas
  être imposé par un client direct du réseau local.
- **`new_issue.py`** : extraction de `_mode_reseau()` et
  `_erreur_mot_de_passe_manquant()` (fonctions pures, testables sans
  démarrer de serveur) ; `--lan` refuse désormais de démarrer sans
  `MOT_DE_PASSE` configuré, avec le même message que `--externe`. Aide de
  `--lan`, en-tête d'usage et commentaire du bloc des trois modes mis à
  jour pour dire « mot de passe obligatoire » (et son corollaire : il
  circule en clair sur le réseau local, HTTP non chiffré — non résolu par
  cette issue).
- **Documentation** (`ARCHITECTURE.md`, `VERIFICATIONS_MANUELLES.md`,
  `provisioning/windows/NEW_ISSUE_LOCAL_WINDOWS.md`) : les quelques phrases
  décrivant `--lan` comme « sans mot de passe » sont corrigées.
- **Tests** (`tests/test_lan_motdepasse_rate_limit_831.py`, nouveau) :
  page protégée redirigeant vers `/login` sans session puis accessible
  après connexion en `--lan` ; mode local toujours sans login ; démarrage
  refusé sans mot de passe pour `--lan` et `--externe` (même message) ;
  blocage par adresse indépendant de la session (nouvelle session de la
  même adresse refusée, autre adresse non affectée) ; succès qui remet le
  compteur à zéro ; expiration du blocage par adresse (horloge simulée).
- **Non traité** : aucun fichier `configs/*.conf` modifié. Aucun client
  automatique de l'interface ne s'authentifie — les scripts qui appellent
  `new_issue.py` en HTTP local (`scripts/traitement_fin.py`,
  `scripts/watcher_issues_inbox.py`) ciblent exclusivement des routes déjà
  explicitement exclues de `login_requis` (`/notifier-fin-issue`,
  `/notifier-debut-issue`, `/notifier-fichier-recu`,
  `/notifier-creation-issue`, `/notifier-fichier-refuse`,
  `/notifier-case-decochee`, `/notifier-issue-a-surveiller`, `/heartbeat`) :
  aucun changement de comportement pour eux.
