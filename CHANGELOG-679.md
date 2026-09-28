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
