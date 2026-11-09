## 9 novembre 2026 — issue #865

Copie du rapport sous Firefox : le presse-papier gardait l'ancien contenu
pendant toute la préparation — défaut que #857 devait empêcher.

**CAUSE ÉTABLIE** (relecture du code, confirmée par un test adversarial qui
échoue sur l'ancien code et passe sur le correctif — voir
`static/js/tests/resultats_coches_variantes.test.js`) : en mode moderne, le
vidage (chaîne vide) et l'écriture du rapport (contenu différé) étaient
engagés l'un après l'autre SANS ATTENDRE la fin du premier
(`resultats_coches.js`, `lancerCopie`). Firefox annule une écriture encore
pendante dès qu'une nouvelle est lancée avant qu'elle n'aboutisse (constat
déjà établi par #782) : le vidage était donc TOUJOURS annulé par l'écriture
du rapport qui le suivait, AVANT d'avoir pu remplacer l'ancien contenu. Tant
que le contenu du rapport n'est lui-même pas résolu, rien ne remplace donc
l'ancien contenu, qui reste en place pendant toute la préparation — c'est ce
qu'Alain a observé : coller aussitôt après avoir coché une case rendait le
rapport de l'issue précédente, pas un presse-papier vide.

**Correctif** : `viderPressePapier()` renvoie désormais sa promesse (toujours
résolue, jamais rejetée) ; `lancerCopie` ATTEND sa fin réelle avant d'engager
l'écriture du rapport (`copierModerne`). Un vidage prend quelques
millisecondes, bien en deçà de la fenêtre d'activation du clic (issue #858) :
l'engagement du rapport reste donc dans cette fenêtre, juste décalé de
quelques ms — sans répéter le défaut de #782 (écritures qui s'annulent
mutuellement) ni celui de #858 (écriture refusée pour geste expiré). Mode
repli (`--lan`, execCommand) inchangé : déjà synchrone, aucune attente
nécessaire. Un seul point d'entrée (`lancerCopie`) pour la case à cocher et
les 3 badges (✅/Diff/All) : le correctif profite aux quatre sans code
dupliqué.

**Tests ajoutés** (`resultats_coches_variantes.test.js`) : modélisent le
presse-papier RÉEL (contenu à un instant donné, avec la même règle
d'annulation d'écriture pendante que les tests #858 existants) plutôt que le
seul ordre des appels `write()` — insuffisant pour détecter ce défaut.
Couvrent : juste après le clic puis pendant toute une préparation lente
(jamais l'ancien contenu), après succès (le rapport), après échec (reste
vide, jamais l'ancien contenu).

**Ce qui reste une hypothèse, à vérifier à la main dans Firefox** (essai
ajouté à `VERIFICATIONS_MANUELLES.md`) : que Firefox se comporte réellement
comme modélisé par les tests (annulation d'une écriture pendante par une
plus récente, mise à jour du presse-papier différée jusqu'à résolution du
contenu de l'écriture gagnante — jamais avant), et que le délai introduit
par l'attente du vidage ne fait pas sortir l'engagement de l'écriture du
rapport de la fenêtre d'activation du clic.

Fichiers touchés : `static/js/resultats_coches.js` (`viderPressePapier`,
`lancerCopie`, commentaires réécrits), `static/js/tests/resultats_coches_variantes.test.js`
(2 nouveaux tests), `VERIFICATIONS_MANUELLES.md` (essai #857/#865 réécrit).
