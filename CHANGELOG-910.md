# CHANGELOG — bridge_agent (issue #910, à fusionner)

## 22 novembre 2026 — issue #910

Commentaire d'en-tête obsolète d'`installer_services.sh` (constaté pendant
#908, laissé hors périmètre) : il affirmait encore que `demarrer_watcher()`/
`arreter_watcher()` (bouton « Lancer / Arrêter watcher » de l'interface)
appelaient `systemctl --user start|restart|stop watcher@<projet>`,
comportement de #596 remplacé depuis #682 par un lancement direct de
`watcher.py` (`subprocess.Popen`/SIGTERM, voir `app/watchers.py`). Cette
description périmée laissait croire que l'interface et l'unité systemd
restaient un seul et même mécanisme, alors que ce sont depuis #682 deux
modes de lancement indépendants — la confusion qui a permis le doublon du
18/11/2026 sur le même projet, empêché depuis par le verrou d'instance
unique de #908.

**Corrigé :** bloc de commentaires d'en-tête d'`installer_services.sh`
(lignes 19-38) et les deux lignes `echo` de bilan en fin de script
(dernier bloc) : décrivent maintenant le lancement direct de
`watcher.py` comme mécanisme de l'interface, l'unité systemd comme mode
de lancement séparé non activé par ce script (`systemctl --user start`
sans `enable`), et le verrou d'instance unique de #908 comme garde-fou
anti-doublon commun aux deux modes, quel que soit celui qui démarre en
premier. Commentaires uniquement, aucun comportement ni commande
exécutable modifiés.

**Déjà à jour, vérifiés sans modification :** `systemd/watcher@.service`
(déjà centré sur #908/#682, ne prétend nulle part à une unification avec
l'interface) et `BRIDGE_AGENT_DOC.md` §1 (déjà mis à jour par #908 :
« l'unité systemd … désactivée au démarrage, réservée aux tests manuels »).
Les mentions de #596 restant dans `app/watchers.py`, `watcher.py` et
`systemd/watcher@.service` sont des notices historiques correctes
(« remplace #596 », « Restart=on-failure … issue #596, complété #908 »),
non des affirmations de comportement actuel — laissées inchangées.

Fichiers touchés : `installer_services.sh`.
