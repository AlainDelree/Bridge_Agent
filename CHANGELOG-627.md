## 25 septembre 2026 — issue #627

Refonte de l'interface web, **étape 3/n : la liste Résultats pilotée par le store
et le SSE**. Étape la plus sensible (Résultats est l'outil quotidien d'Alain) :
elle sort d'`app.js` le **moteur** de l'onglet — chargement, canal `/stream`,
badges de temps — avec le **store** pour source de vérité unique, sans changement
visible pour l'utilisateur. Trois anomalies confirmées corrigées à la racine.

### 1. Nouveau module — `static/js/resultats.js`

Premier **module par fonctionnalité** de la refonte (cf. `ARCHITECTURE.md §6.5`).
Il détient et orchestre :

- **Chargement** : un chargement initial UNIQUE (à la première activation de
  l'onglet), puis des mises à jour ciblées par événement `/stream`, plus le ↻
  explicite. **Plus aucun rechargement complet à l'activation de l'onglet.** Le
  **cache de liste en `localStorage` est supprimé** : le store est la seule vérité.
- **Canal `/stream`** ouvert via la brique `sse` (`sse.stream.connecter()`), UNE
  SEULE connexion — l'ancien `demarrerStreamFinIssue()` d'`app.js` est retiré dans
  le même mouvement (jamais deux connexions). Traitement **toujours CIBLÉ** sur le
  projet+issue concernés, jamais tous les projets :
  - `debut_issue` : recharge les données de temps **de cette issue** (le décompte
    TIMEOUT démarre) et l'ajoute à la liste si absente ; ne passe **JAMAIS** par la
    vérification post-dépassement ;
  - `fin_issue` : met à jour la ligne (état final, arrêt du décompte) via un fetch
    unique `/issue/<projet>/<numero>` ;
  - `creation_issue` (contrat de l'étape 9a : `projet`, `numero`, `titre`,
    `fichier` si créée via `issues_inbox`) : fait apparaître la ligne avec son
    estimation et « en file », puis l'enrichit par un fetch ciblé. **Codé même si
    l'événement n'est pas encore émis.**
  - le **fetch unique post-dépassement de #334** est conservé, réservé au décompte
    tombé à zéro.
- **Badges** d'estimation et de décompte TIMEOUT : calcul (logique pure) +
  application au DOM + tick 1 s + programmation du fetch #334.
- **Store** : nouvelles tranches `issues` (déjà présente) et **`timing`** ; le
  `derniereNotifIssue` posé par `sse.js` déclenche le traitement ciblé.

### 2. Anomalies corrigées à la racine

1. **Rechargement complet à chaque activation de l'onglet** (~2 appels gh/projet
   pour la liste + 1/issue ouverte pour les temps) → supprimé. Chargement initial
   unique + événements ciblés + ↻. *Vérifiable : aucun appel `/issues-liste` ni
   `/issues-en-attente` en changeant d'onglet (onglet Réseau).*
2. **`debut_issue` cassé** : l'ancien `gererEvenementIssue` rechargeait la liste
   sans les temps, ou — si l'issue était déjà affichée — passait par
   `verifierIssueApresDepassement` (prévu pour #334), laissant le badge « ⏳ en
   file » et marquant l'issue « dépassement déjà vérifié » (faussant plus tard le
   badge de dépassement). Désormais `debut_issue` recharge le timing ciblé et ne
   touche jamais la vérif post-dépassement.
3. **Projet en échec de chargement** : ses issues disparaissaient en silence.
   Désormais, un projet dont le fetch échoue **conserve ses issues précédentes** et
   l'échec est signalé par un **toast**.

### 3. Ce qui reste temporairement dans `app.js` (et pourquoi)

`app.js` conserve, pendant la transition, tout ce qui est **hors périmètre #627**
et/ou entrelacé avec le rendu DOM d'une ligne, piloté par `resultats.js` via un
MIROIR du store (hooks `window.__resultats*`) :

- **Rendu DOM d'une ligne** (`construireLigneIssueDOM`, `rendreListeIssues`,
  `remplacerLigneIssue`, `brancherEvenementsLigneIssue`) : le markup contient la
  **case à cocher**, les **badges ✅/Diff/All** et la copie, l'ouverture du
  **détail** — toutes fonctionnalités hors périmètre. `resultats.js` fournit les
  données et déclenche le rendu ; `app.js` produit le DOM.
- **Filtres** (boutons projet, filtre ouvriers, limite « par projet », ↻) :
  `construireBoutonsFiltre`/`appliquerFiltresListe` construisent aussi le bouton
  **« Cocher tout »** et les **pastilles** (hors périmètre) et lisent l'état de
  filtre persisté — extraction repoussée avec ces fonctionnalités.
- **Sélection, détail d'issue, recherche par titre, lignes issues_inbox, panneau
  latéral** : explicitement hors périmètre — inchangés, alimentés par le miroir
  (`listeIssuesResultats`/`timingIssues`) via le pont.
- `cleTiming`, `trouverLigneIssue`, `remplacerLigneIssue` : petits utilitaires DOM
  encore consommés par ce qui précède.

Le pont (`window.Bridge.resultats`) et le miroir disparaîtront quand ces zones
seront à leur tour migrées (étapes suivantes).

### 4. Tests et vérifications

- **Logique pure** testée sous Node — `static/js/tests/resultats.test.js`
  (`formaterDuree`, calcul des badges de décompte/estimation, `planifierEvenementSse`
  dont le cas `debut_issue`, fusion de chargement conservant un projet en échec).
  Lancer : `node --test static/js/socle/tests/ static/js/tests/` (36 tests OK).
- `app/statique.py` : l'**import map** couvre désormais aussi les modules de
  fonctionnalité de `static/js/` (hors `app.js`, script classique), pour leur
  cache-busting `?v=<mtime>` ; le partage d'instance du store est garanti (mêmes
  URL résolues).
- `VERIFICATIONS_MANUELLES.md` (zone Résultats) et `BRIDGE_AGENT_DOC.md §17.3`
  mis à jour.

### 5. Fichiers touchés

- **Nouveaux** : `static/js/resultats.js`, `static/js/tests/resultats.test.js`,
  `static/js/package.json` (`{"type":"module"}`).
- **Modifiés** : `static/js/app.js` (moteur Résultats retiré, remplacé par des
  relais vers le pont ; ancienne connexion `/stream` supprimée),
  `static/js/socle/store.js` (tranche `timing`), `static/js/socle/sse.js`
  (événement `creation_issue`), `static/js/socle/index.js` (import + amorçage
  `resultats`), `app/statique.py` (import map élargi), `ARCHITECTURE.md`,
  `BRIDGE_AGENT_DOC.md`, `VERIFICATIONS_MANUELLES.md`, `CONTEXTE.md`,
  `static/js/socle/tests/README.md`.
