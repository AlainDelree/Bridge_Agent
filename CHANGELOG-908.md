# CHANGELOG — bridge_agent (issue #908, à fusionner)

## 22 novembre 2026 — issue #908

Instance unique par projet : verrou de processus unique pris au démarrage
de `watcher.py` (issue #908) — corrige l'incident du 18/11/2026 où deux
process `watcher.py` du même projet (interface web + unité systemd
`watcher@bridge_agent` démarrée à la main pour un test) ont tourné en
parallèle, chacun avec son propre compteur de parallélisme, prenant deux
fois la même issue (#903). `watcher.acquerir_verrou_processus(nom_projet)`
pose désormais, tout au début de `main()`, avant même le fichier PID, un
verrou SYSTÈME (`fcntl.flock` POSIX non bloquant / `msvcrt.locking` sous
Windows) sur un descripteur gardé ouvert toute la durée de vie du process —
`logs/verrous/watcher-processus-<projet>.lock`, nom délibérément distinct
des verrous par issue existants (`<rep>-<empreinte>.lock`, même dossier)
pour ne jamais les confondre. Libéré automatiquement par le noyau à la
fermeture du descripteur, fin propre ou brutale (`kill -9`, crash) — pas un
simple fichier PID, vulnérable à la réutilisation des PID et réécrit sans
concertation par n'importe quel lancement. Un second watcher du même projet
détecte le verrou déjà tenu, journalise un message clair (projet concerné,
verrou tenu par un autre process, arrêt immédiat) et quitte avec un
nouveau code de sortie dédié `EXIT_VERROU_DEJA_PRIS=43`, déclaré dans
`SuccessExitStatus` de `systemd/watcher@.service` (à côté de
`EXIT_INACTIVITE=42`) pour que `Restart=on-failure` ne le relance pas en
boucle — ce n'est pas un crash, c'est le comportement voulu. Jamais hérité
par un enfant (`O_CLOEXEC` + `os.set_inheritable(fd, False)`) : vérifié par
test qu'un process enfant ne voit jamais ce descripteur dans `/proc/self/fd`
— préoccupation réelle pour le mode interactif, dont la session (et le
serveur) tmux survit volontairement au redémarrage du watcher.

Côté interface web (`app/watchers.py`) : AUCUN changement nécessaire — le
fichier PID partagé qu'elle consulte déjà (`watcher_actif()`,
`logs/watcher-<nom>.pid`, publié par `watcher.py` lui-même quel que soit son
mode de lancement depuis l'issue #596) reste une source fiable maintenant
qu'un seul process peut réellement tourner par projet : un second lancement
refusé par le nouveau verrou s'arrête avant même d'écrire ce fichier,
laissant intact celui du watcher légitime.

Comportement Windows (`msvcrt.locking`) : écrit pour fonctionner sans
nouvelle dépendance (module de la bibliothèque standard, même esprit que
`scripts/watcher_issues_inbox.py::acquerir_verrou_instance_unique`, issue
#881, dont ce mécanisme reprend directement le modèle) mais NON exécuté en
test faute d'environnement Windows disponible pendant cette issue —
seulement vérifié par relecture de code.

Tests : `tests/test_verrou_processus_unique_908.py` — deuxième instance
refusée pour le même projet, verrou libéré après un `kill -9` réel du
process qui le tenait, deux projets différents n'interférant jamais, verrou
absent des descripteurs ouverts d'un process enfant (`/proc/self/fd`), code
de sortie dédié bien déclaré dans `SuccessExitStatus` du gabarit systemd.

Documentation : `BRIDGE_AGENT_DOC.md` §1 (nouvel encart « Instance unique
par projet ») + pied de page mis à jour ; `docs/contexte/mode_interactif.md`
(nouvelle sous-section sur la non-héritance du verrou par les sessions
tmux) ; `systemd/watcher@.service` et `installer_services.sh` (commentaires
sur `SuccessExitStatus=42 43`). `CONTEXTE.md` non modifié (déjà proche de
la limite de 4000 caractères, rien d'indispensable à y ajouter).
