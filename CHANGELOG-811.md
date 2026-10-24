## Issue #811 — Réinstallation du PC fixe : libellés stables pour le diagnostic SSH de l'étape 3

`provisioning/windows/REINSTALLATION_CCW.md`, étape 3 modifiée par ajouts
et remplacements ciblés (20 insertions, 7 suppressions) : le tableau de
diagnostic d'échec SSH gagne une colonne « Cause » avec quatre libellés
stables (« clé d'hôte modifiée », « clé refusée », « connexion refusée »,
« PC éteint ou adresse introuvable »), repris tels quels par
`relecture_web` (projet Relecture_Bridge) — à ne pas renommer sans
prévenir ce projet ; la ligne « délai dépassé » précise désormais les deux
messages possibles (`Connection timed out` / `No route to host`) ; ajout
d'une remarque sur la langue des messages SSH (restent en anglais même en
session système française, constaté sur le ThinkPad pour `Connection
refused` seulement, les autres messages du tableau n'étant pas testés) ;
le rappel sur l'adresse du PC fixe cite désormais `ccw_host.conf.example`
comme modèle versionné du fichier personnel `ccw_host.conf`. Aucun autre
fichier ni aucune autre partie du document touchés.
