## Issue #810 — Réinstallation du PC fixe : complément étape 3 (clé d'hôte SSH, adresse réservée, diagnostic d'échec)

`provisioning/windows/REINSTALLATION_CCW.md`, étape 3 complétée par
ajouts (36 lignes, aucune suppression) : encadré rappelant qu'une
réinstallation Windows régénère la clé d'hôte SSH du PC fixe (donc
`ssh-keygen -R <ip>` à faire avant le premier test, pertinent pour
Bridge_Agent — onglet CCW, démarrage automatique des services — comme
pour `relecture_web`, qui partagent `~/.ssh/known_hosts`) ; rappel que
l'adresse du PC fixe est réservée sur la box et identique après
réinstallation tant que la carte réseau ne change pas, avec les deux
emplacements à mettre à jour si elle change (`configs/ccw_ssh.conf` côté
Bridge_Agent, `ccw_host.conf` hors dépôt côté `relecture_web`) ; tableau
distinguant les quatre messages d'échec SSH possibles et leur cause
probable ; encadré sur le symptôme trompeur « PC fixe éteint ou
injoignable » affiché par `relecture_web` quand la cause réelle est la
clé d'hôte. Aucun autre fichier ni aucune autre étape du document
touchés.
