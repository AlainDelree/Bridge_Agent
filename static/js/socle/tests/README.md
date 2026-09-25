# Tests du socle JS — issue #625

Tests de **logique pure** en JavaScript, avec le **module de test intégré de
Node** (`node:test` + `node:assert`). **Aucune dépendance, aucun build, aucun
`npm install`.**

## Lancer les tests

Depuis la racine du dépôt :

```bash
node --test static/js/socle/tests/
```

Sortie attendue : `# pass 20  # fail 0` (au moins ; le nombre grandit avec la
refonte).

> Le fichier `static/js/socle/package.json` (`{"type":"module"}`) suffit à ce
> que Node traite les `.js` du socle comme des modules ES. Le navigateur ignore
> ce `package.json`.

## Couverture actuelle

| Fichier                | Ce qui est testé |
|------------------------|------------------|
| `store.test.js`        | `creerStore` (get/set/maj, abonnements global et par clé, immuabilité) et le store applicatif (tranches par défaut, issues indexées par projet+numéro). |
| `persistance.test.js`  | `lire`/`ecrire` (JSON), `lireTexte`/`ecrireTexte`, `supprimer`, `supprimerParPrefixe`, avec un faux `localStorage`. |
| `dom.test.js`          | `echapperHtml` (seule logique de `dom.js` indépendante du DOM). |

Ce qui touche au DOM (utilitaires `dom`, toasts, délégation) et au réseau (`api`,
`sse`) est vérifié **manuellement** dans le navigateur : voir
`VERIFICATIONS_MANUELLES.md` à la racine.
