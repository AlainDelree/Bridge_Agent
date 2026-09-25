## 25 septembre 2026 — issue #626

Refonte de l'interface web, **étape 2/n : onglets**. Sortie de la mécanique de
bascule des onglets d'`app.js` vers `static/js/onglets.js`, selon la procédure
type du §6.7 d'`ARCHITECTURE.md`.

### 1. Nouveau module `static/js/onglets.js`

- Association onglet ↔ panneau par **identifiant** (`data-onglet` sur chaque
  `.onglet`, comparé à l'id `panneau-<nom>`), plus par position dans le DOM :
  l'ancien `basculerOnglet()` parcourait un tableau de noms dans l'ordre des
  éléments, ce qui cassait l'association au moindre réordonnancement.
- `activerOnglet(nom)` publie l'onglet actif dans le store (`ongletActif`,
  nouvelle tranche de `socle/store.js`) pour que chaque zone puisse réagir à
  son activation/désactivation, et appelle — via le pont, pendant la
  transition — les initialisations existantes de chaque onglet dans
  `app.js` (`initialisationsPour()`, fonction pure testée séparément).
  **Inchangé** : ce que fait l'activation de Résultats (rechargement de la
  liste, badges, panneau latéral) — périmètre de l'étape 3.
- `initialiserOnglets()`, appelé une seule fois par `socle/index.js`, branche
  la délégation de clic (`dom.surAction`) et active Résultats par défaut.
- Tests : `static/js/tests/onglets.test.js` (`node --test static/js/tests/`),
  7 cas sur `initialisationsPour()` (la partie pure, sans DOM).

### 2. Nouvel ordre des onglets + Résultats par défaut

`templates/fragments/onglets.html` : Résultats en premier (actif au
chargement, décision d'Alain — avant #626 c'était Nouvelle issue), Nouvelle
issue en dernier (n'est plus qu'un backup, seul moyen de joindre un fichier à
une issue, usage très rare), les autres onglets dans leur ordre relatif
inchangé. `onglet_creation.html`/`onglet_resultats.html` : classe `actif`
déplacée en conséquence.

### 3. Suppression de l'onglet « Watchers »

Le tableau des watchers + cases à cocher + actions Lancer/Relancer/Éteindre
par lot n'existent plus : fragment `onglet_watchers.html` supprimé, son
`{% include %}` retiré d'`index.html`, fonctions `statutWatcher`/
`chargerWatchers`/`selectionnerTous`/`mettreAJourCompte`/`actionWatchers` et
`intervalWatchers` supprimés d'`app.js`. La surveillance des watchers reste
dans le **panneau latéral Infrastructure** de l'onglet Résultats (actions par
projet individuel, pas de sélection multiple) — vérifié qu'aucune fonction
supprimée n'y était encore utilisée ; ses appels à `/watchers` (panneau
latéral) et au bandeau de repli REP_TRAVAIL (`rafraichirReplisRepTravail`)
sont inchangés.

### 4. Documentation

`ARCHITECTURE.md` §6.5/§6.7 : module `onglets.js` marqué comme sorti,
nouvelle description de la suppression de l'onglet Watchers et du nouvel
ordre. `BRIDGE_AGENT_DOC.md` : mentions de l'onglet Watchers remplacées par
le panneau latéral Infrastructure et le bouton « Lancer le watcher » du
bandeau global. `VERIFICATIONS_MANUELLES.md` : section « Onglet Watchers »
retirée, ajout d'une vérification de l'onglet par défaut et du nouvel ordre,
mention de `node --test static/js/tests/` en plus des tests du socle.

### 5. Autres ajustements

`app/statique.py` (`importmap_socle()`) étendu pour verser aussi les modules
de fonctionnalité de `static/js/` (hors `app.js`, script classique) dans
l'import map — nécessaire pour que `socle/index.js` importe `../onglets.js`
avec cache-busting. `app/watchers.py` : commentaires mis à jour (routes
utilisées par le panneau latéral/l'onglet Configuration, plus par l'ex-onglet
Watchers).

Tests : `node --test static/js/socle/tests/` (20 passent) et
`node --test static/js/tests/` (7 passent).
