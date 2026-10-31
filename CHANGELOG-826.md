## Issue #826 — `consignes/globales.md` : règle « n'arrêter un processus que par son PID, jamais par un motif de nom »

Plusieurs issues avaient échoué parce qu'un agent, pour arrêter un serveur
ou un navigateur de test qu'il avait lancé, utilisait `pkill -f <motif>`,
`killall`, ou `pgrep` suivi d'un arrêt — un motif de nom pouvant correspondre
à d'autres processus de la machine, voire au processus de l'agent lui-même,
tuant alors des tâches légitimes.

Nouvelle puce insérée dans `consignes/globales.md`, immédiatement après la
puce « Interdiction absolue de modifier `configs/*.conf` » (pour la garder
avec les autres puces de sécurité) et avant la puce « Champ COMPLEXITE » :
impose de relever le PID d'un processus lancé pendant l'issue (serveur,
navigateur de test, etc.) au moment de son lancement et de ne tuer que ce
PID précis ; interdit `pkill`, `killall`, `pgrep` suivi d'un arrêt, et toute
commande désignant un processus par un motif de nom — y compris leurs
équivalents Windows `taskkill /IM`, `Stop-Process -Name` et un
`Get-Process` filtré par nom suivi d'un arrêt. Aucune autre puce ni leur
ordre n'a été modifié ; seules des lignes ont été ajoutées (+11, le fichier
passe de 90 à 101 lignes).

Aucun conflit trouvé avec une puce existante ni avec les scripts versionnés
du dépôt : `watcher.py` (`_nettoyer_arbre_claude`, `taskkill /PID <pid>
/T /F`) et `provisioning/windows/interrompre_projet_ccw.ps1`
(`Stop-Process -Id`) ciblent déjà exclusivement un PID, pas un motif de
nom — conformes à la nouvelle règle (et hors de son champ d'application de
toute façon, la règle visant les commandes que l'agent écrit lui-même, pas
le contenu des scripts du projet qu'il exécute).
