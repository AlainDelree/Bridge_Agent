## 7 novembre 2026 — issue #857

Vidage immédiat du presse-papier au clic de copie (onglet Résultats,
`static/js/resultats_coches.js`) : quand la préparation du texte du rapport
était lente ou que l'écriture échouait, le presse-papier gardait l'ANCIEN
contenu (texte ou capture d'écran) — Alain changeait d'onglet sans remarquer
l'échec et le collait par erreur dans la mauvaise conversation. La cause
exacte des échecs/lenteurs restait établie sans certitude (issues #824/#832) ;
cette issue protège Alain quelle que soit la cause, plutôt que de la
rechercher davantage.

`lancerCopie` (point d'entrée UNIQUE de la case à cocher ET des badges
✅/Diff/All) vide désormais le presse-papier **dans le geste**, AVANT toute
préparation : chaîne vide en mode moderne (`navigator.clipboard.write`, repli
sur un simple espace si le navigateur refuse la chaîne vide) comme en mode
repli (`execCommand`, HTTP non-localhost). Aucun feedback (ni toast de succès
ni d'échec) n'accompagne ce vidage — un collage vide ne déclenche rien côté
Alain, contrairement à un message qui pourrait, lui, être collé par erreur.
Si la copie du rapport réussit ensuite, elle remplace ce contenu vide ; si
elle échoue, le presse-papier reste vide (la fenêtre de secours existante
s'ouvre toujours, issue #782).

Point d'attention #832 respecté : l'écriture vide passe par la MÊME file
`chaineCopieModerne` que l'écriture réelle (nouvelle fonction
`viderPressePapier`, simple appel ajouté en tête de `lancerCopie`) — elle
n'annule donc jamais une écriture réelle déjà en vol, et le rapport s'écrit
toujours APRÈS le vidage de son propre clic, dans l'ordre. Plusieurs cases
cochées très vite ne sont pas optimisées spécifiquement (déjà hors périmètre
depuis #782/#832) mais ne cassent rien : chaque clic enfile son propre vidage
puis sa propre écriture, dans l'ordre d'arrivée.

**Boutons couverts** : case à cocher (`basculer`) et les 3 badges de liste
✅/Diff/All (`copierReponseBadge`/`copierDiffBadge`/`copierAllBadge`) — les
4 passent par `lancerCopie`, donc couverts par UNE seule modification, sans
complexité ajoutée. Hors périmètre (non modifié, volontairement) : le bouton
« copier » du titre de l'onglet En attente (`copierTexteConnu`, issue #823)
et les boutons « Copier résumé »/« Copier tout » du détail d'une issue
(`copierPressePapier` dans `app.js`) — moteurs de copie distincts, non
mentionnés par cette issue.

Tests JS ajoutés (`static/js/tests/resultats_coches_variantes.test.js`,
mode `node --test`) : vidage immédiat avant que le rapport soit prêt (mode
moderne ET mode repli), remplacement du contenu vidé par le rapport après une
écriture réussie, presse-papier resté vide (aucune écriture de contenu) après
un échec d'écriture. Les tests existants qui capturaient la première écriture
clipboard pour vérifier le CONTENU du rapport copié (`attendreProchaineCopie`
et deux mocks dédiés aux files d'attente) ont dû être ajustés pour ignorer
cette nouvelle écriture vide, sans changer ce qu'ils vérifiaient.

Vérifié par les tests : l'ordre d'enfilement (vidage puis rapport, jamais
l'inverse) et le comportement sur échec, en environnement Node simulé.
PAS vérifié par les tests (nécessite un vrai navigateur) : si Firefox accepte
réellement l'écriture d'une chaîne vide via `navigator.clipboard.write`, et
l'ordre d'arrivée effectif des deux écritures une fois sorties du moteur JS.
Étape manuelle ajoutée à `VERIFICATIONS_MANUELLES.md` pour qu'Alain le
vérifie à la main sous Firefox.

Doc : `ARCHITECTURE.md` (section « Étape 5b », issue #636) complétée de
quelques phrases sur `viderPressePapier`/`chaineCopieModerne`.
