# Tests du socle JS — issue #625

Tests de **logique pure** en JavaScript, avec le **module de test intégré de
Node** (`node:test` + `node:assert`). **Aucune dépendance, aucun build, aucun
`npm install`.**

## Lancer les tests

Depuis la racine du dépôt (socle + modules par fonctionnalité) :

```bash
node --test static/js/socle/tests/ static/js/tests/
```

Sortie attendue : `# pass 36  # fail 0` (au moins ; le nombre grandit avec la
refonte). Les tests du module Résultats (issue #627) vivent dans
`static/js/tests/resultats.test.js` — le fichier `static/js/package.json`
(`{"type":"module"}`) suffit à ce que Node traite ces `.js` comme des modules ES.

> Le fichier `static/js/socle/package.json` (`{"type":"module"}`) suffit à ce
> que Node traite les `.js` du socle comme des modules ES. Le navigateur ignore
> ce `package.json`.

## Couverture actuelle

| Fichier                | Ce qui est testé |
|------------------------|------------------|
| `store.test.js`        | `creerStore` (get/set/maj, abonnements global et par clé, immuabilité) et le store applicatif (tranches par défaut, issues indexées par projet+numéro). |
| `persistance.test.js`  | `lire`/`ecrire` (JSON), `lireTexte`/`ecrireTexte`, `supprimer`, `supprimerParPrefixe`, avec un faux `localStorage`. |
| `dom.test.js`          | `echapperHtml` (seule logique de `dom.js` indépendante du DOM). |
| `../tests/resultats.test.js` | Module Résultats (issue #627) : `formaterDuree`, calcul des badges de décompte TIMEOUT et d'estimation, `planifierEvenementSse` (dont `debut_issue` qui ne passe jamais par la vérif post-dépassement), fusion de chargement conservant un projet en échec. |
| `../tests/panneau_lateral.test.js` | Panneau latéral (issue #628) : `etatsCasesNotif` (cases 🔔 Notifications de l'issue sélectionnée). |
| `../tests/actions_ligne.test.js` | Actions sur la ligne d'une issue OUVERTE (issue #641) : `actionLigneOuverte` (needs-human/mode_write/aucune action selon les labels), son par issue (#630/#637, réutilisées telles quelles) et son cache par projet (`fusionnerSonsProjet`/`sonConnuDansCache`). |

Ce qui touche au DOM (utilitaires `dom`, toasts, délégation) et au réseau (`api`,
`sse`) est vérifié **manuellement** dans le navigateur : voir
`VERIFICATIONS_MANUELLES.md` à la racine.
