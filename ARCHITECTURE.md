# ARCHITECTURE.md — documentation technique de Bridge_Agent

Document **technique interne**, destiné aux sessions de développement sur
Bridge_Agent lui-même (CCL ouvrier ou humain modifiant le code).

> À ne pas confondre avec `BRIDGE_AGENT_DOC.md`, qui est destiné à tous les
> Claude Chat, pour tous les projets, et décrit *l'usage* du bridge. Ici on
> décrit la *mécanique interne* de l'interface web `new_issue.py` / package
> `app/`. Pour la vision produit et le protocole des issues, voir
> `BRIDGE_AGENT_DOC.md`.

---

## 1. Structure du code

Arborescence de l'application web de création d'issues (le watcher `watcher.py`
est un composant séparé, non détaillé ici).

```
Bridge_Agent/
├── new_issue.py            Point d'entrée CLI : parsing des args, création de
│                           l'app via app.create_app(), démarrage du serveur,
│                           gestion des signaux d'arrêt. Aucune logique métier.
├── watcher.py              Composant séparé : surveille les issues GitHub et
│                           exécute les tâches. Fournit Config / charger_config,
│                           réutilisés par app/ (lecture des .conf).
│
├── app/                    Package Flask de l'interface web.
│   ├── __init__.py         Fabrique create_app() : instancie Flask, pose l'état
│   │                       partagé dans app.config, enregistre toutes les routes
│   │                       via _enregistrer_routes() (imports différés).
│   ├── etat.py             Accesseurs get/set à l'état partagé (app.config lu via
│   │                       current_app) + charger_mot_de_passe() depuis le .conf.
│   ├── auth.py             Authentification : décorateur login_requis, routes
│   │                       login/login_post/logout, gabarit de connexion inline.
│   ├── projets.py          Un .conf = un projet : lister_projets, projet_par_nom,
│   │                       lecture/écriture des clés éditables du .conf, routes
│   │                       get_config/post_config. Ajoute la racine au sys.path.
│   ├── issues.py           Création/consultation/annulation d'issues : construction
│   │                       du body markdown + labels, routes apercu/envoyer/
│   │                       issues_liste/issue_detail/issues_en_attente/annuler.
│   ├── watchers.py         Cycle de vie des processus watcher (démarrage, arrêt,
│   │                       détection PID) + routes utilisées par le panneau
│   │                       latéral Infrastructure et l'onglet Configuration.
│   ├── journal.py          Route SSE : streame le fichier de log d'un watcher en
│   │                       temps réel (tail + suivi + détection de rotation).
│   ├── cycle_vie.py        Cycle de vie serveur ↔ onglet : heartbeat, SSE /events
│   │                       (shutdown), route /quitter, thread surveiller_heartbeat.
│   ├── tunnel.py           Tunnel cloudflared (mode --externe) : démarrage/arrêt
│   │                       automatique de « cloudflared tunnel run bridge-agent ».
│   ├── vues.py             Vue générale : route index() qui rend le gabarit
│   │                       principal de l'interface.
│   └── statique.py         Versionnage cache-busting des statiques : url_statique
│                           et importmap_socle, globales Jinja (§6.6, issue #625).
│
├── templates/
│   ├── index.html          Squelette : inclut les fragments (issue #625).
│   └── fragments/          Un fragment par onglet / panneau / modale (§6.5).
├── static/
│   ├── css/                Feuilles découpées par zone, ordre = cascade (§6.5).
│   └── js/
│       ├── app.js          Ancien front (script CLASSIQUE, vidé par étapes).
│       └── socle/          Briques ES : store/api/sse/toasts/dom/persistance,
│                           pont de transition, tests (§6.2). Refonte issue #625.
│
├── configs/                Un fichier <projet>.conf par projet actif.
├── logs/                   Journaux watcher-<projet>.log et fichiers .pid.
└── ssl/                    Certificat auto-signé (cert.pem/key.pem) pour --externe.
```

---

## 2. Décisions d'architecture

### 2.1 Flask Blueprints / application factory (`create_app()`)

L'application est construite par une **fabrique** `create_app()` plutôt que par
un objet Flask global créé à l'import. Bénéfices :

- **Pas d'effet de bord à l'import** : instancier l'app (et donc lire l'état,
  poser la SECRET_KEY, enregistrer les routes) ne se produit qu'à l'appel
  explicite de `create_app()`. Un simple `from app import ...` reste inerte.
- **Testabilité / réentrance** : on peut créer plusieurs instances isolées, ou
  n'en créer aucune, sans que le module force un état global.
- **Ordre de démarrage maîtrisé** : `new_issue.py` crée l'app, *puis* charge le
  mot de passe, *puis* installe les signaux — chaque étape sur une app déjà
  construite mais pas encore lancée.

Les routes sont enregistrées à la main via `app.add_url_rule()` dans
`_enregistrer_routes()` (cf. §3), le décorateur `login_requis` étant appliqué
au cas par cas.

### 2.2 État partagé via `app.config` (pas de globales de module)

Tout l'état mutable du serveur (mode externe, mot de passe, arrêt demandé,
heartbeat, processus tunnel) vit dans **`app.config`**, posé par `create_app()`
et lu **à la requête** via `app/etat.py` (`etat.get` / `etat.set`, qui passent
par `current_app`). Aucune de ces valeurs n'est une variable globale de module.

Pourquoi :

- **Imports circulaires** : si l'état était une globale dans un module X, tous
  les modules de routes devraient importer X, et X pourrait avoir besoin d'eux —
  on retombe vite dans des cycles. `app.config` est le point de vérité neutre,
  déjà partagé par tout Flask.
- **Liaisons figées à l'import** : une globale lue au niveau module (ex.
  `MODE_EXTERNE = ...`) capture sa valeur *au moment de l'import*, avant même que
  `new_issue.py` ait décidé du mode. En lisant `app.config` à la requête, on lit
  toujours la valeur courante, mise à jour après coup (ex. `--externe` positionne
  `MODE_EXTERNE = True` seulement après `create_app()`).

Hors contexte de requête (thread daemon, gestionnaire de signal), on n'a pas
`current_app` : on passe alors l'**instance** de l'app explicitement
(cf. `surveiller_heartbeat(app_instance)`, `demarrer_tunnel(app_instance)`) et
on lit `app_instance.config` directement.

### 2.3 Imports différés dans `_enregistrer_routes()`

Les `from app.xxx import ...` sont **à l'intérieur** de `_enregistrer_routes()`,
pas en tête de `app/__init__.py`. Raison : les modules de routes font
`from app import etat` (et parfois `create_app`). Or au moment où Python exécute
le corps de `app/__init__.py`, le package `app` n'est pas encore complètement
initialisé — un import en tête de fichier déclencherait un cycle
(`__init__` → `auth` → `app` pas prêt). En différant ces imports jusqu'à
l'appel de la fonction (donc après que `create_app` a fini de définir le
package), le cycle est rompu.

### 2.4 Générateurs SSE : capturer `current_app.config` avant le générateur

Les routes SSE (`cycle_vie.events`, et par extension `journal.journal`)
retournent un `Response` qui enveloppe une **fonction génératrice**. Ce
générateur est itéré par le serveur *après* la fin de la fonction de vue —
c'est-à-dire **hors du contexte de requête**. À ce moment `current_app` n'est
plus disponible et y accéder lève une erreur.

La parade (voir `cycle_vie.events`) : **capturer `current_app.config` dans une
variable locale pendant qu'on est encore dans le contexte de requête**, puis
n'utiliser que cette variable capturée à l'intérieur du générateur :

```python
def events():
    config = current_app.config          # capturé DANS le contexte de requête
    def generer():
        while True:
            if config.get("ARRET_DEMANDE"):   # lecture directe, PAS etat.get()
                yield "event: shutdown\ndata: stop\n\n"
                return
            ...
    return Response(generer(), mimetype="text/event-stream", ...)
```

À l'intérieur d'un générateur SSE, ne jamais appeler `etat.get()`/`etat.set()`
(qui reposent sur `current_app`) : lire/écrire directement l'objet `config`
capturé.

### 2.5 `DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent`

Chaque module de `app/` qui a besoin de la **racine du projet** la recalcule
localement :

```python
DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent
```

`__file__` pointe le module dans `app/` ; `.parent` donne `app/`, `.parent`
encore donne la racine `Bridge_Agent/` — là où vivent `watcher.py`, `configs/`,
`templates/`, `static/`, `ssl/`. (Dans `app/__init__.py` la même constante
s'appelle `RACINE`.) On l'utilise pour :

- compléter `sys.path` afin que `from watcher import ...` fonctionne même quand
  un module `app/` est importé isolément (`app/projets.py`) ;
- pointer Flask vers `templates/` et `static/` (`app/__init__.py`) ;
- localiser les `.conf`, le `watcher.py` à lancer, les fichiers PID/log.

`.resolve()` rend le chemin absolu et insensible au répertoire de travail
courant : le code marche que l'on lance `python3 new_issue.py` depuis la racine
ou depuis ailleurs.

---

## 3. Ajouter une nouvelle route — procédure

1. **Choisir / créer le bon module `app/`** selon le domaine :
   - authentification → `auth.py`
   - projets / `.conf` → `projets.py`
   - issues GitHub → `issues.py`
   - processus watcher → `watchers.py`
   - journal SSE → `journal.py`
   - cycle de vie serveur/onglet → `cycle_vie.py`
   - vue de page → `vues.py`
   - nouveau domaine → créer `app/mon_module.py` (docstring en tête, même style).

2. **Écrire la fonction de vue** dans ce module. Conventions :
   - accéder à l'état partagé via `etat.get` / `etat.set` (jamais de globale) ;
   - dans un générateur SSE, capturer `current_app.config` avant le générateur
     (§2.4) ;
   - si le module a besoin de la racine, définir
     `DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent` (§2.5) ;
   - retourner du JSON via `jsonify(...)` pour les endpoints API.

3. **Enregistrer la route dans `_enregistrer_routes()` de `app/__init__.py`** :
   - ajouter l'import de la vue au bloc d'imports différés en tête de fonction ;
   - ajouter un `app.add_url_rule(chemin, nom_endpoint, vue, methods=[...])`.

4. **Protéger la route si nécessaire** en enveloppant la vue avec
   `login_requis` au moment de l'enregistrement :

   ```python
   app.add_url_rule("/ma-route", "ma_route", login_requis(ma_vue), methods=["POST"])
   ```

   Utiliser `login_requis` pour toute route de l'interface manipulant des
   données ou des actions. Laisser **sans** `login_requis` uniquement les
   endpoints qui doivent rester accessibles sans session : `/login`,
   `/login_post`, `/logout`, `/heartbeat`. (Rappel : `login_requis` n'est actif
   qu'en mode `--externe` avec un mot de passe configuré ; en mode local il
   laisse tout passer.)

5. **Vérifier** : `python3 -m py_compile app/mon_module.py app/__init__.py`,
   puis lancer `python3 new_issue.py` et tester la route.

---

## 4. Vision multi-agent (résumé)

La direction visée — un CCL « chef d'orchestre » qui découpe une tâche complexe
en sous-tâches, crée une issue GitHub par sous-tâche, et fait traiter celles-ci
en parallèle par des CCL « ouvriers » avant d'assembler les résultats — est
décrite en détail à la **section 14 de `BRIDGE_AGENT_DOC.md`** (flux,
points à concevoir : découpage, synchronisation, anti-boucle, concurrence git,
timeout global, échec partiel).

**Lien avec le découpage modulaire de ce code** : le refactoring de `app/` en
modules à responsabilité unique n'est pas qu'esthétique — il prépare ce modèle
multi-agent. Chaque module (`auth`, `issues`, `watchers`, `journal`,
`cycle_vie`, `tunnel`, `projets`, `vues`) est une **frontière nette** qui peut
devenir la **sous-tâche d'un ouvrier** : « modifie l'auth », « ajoute une route
issues » sont des périmètres indépendants, limitant les conflits git quand
plusieurs CCL écrivent en parallèle (le point « périmètre & concurrence » de la
section 14). Plus le code est modulaire, plus le découpage en sous-tâches
indépendantes est naturel.

---

## 5. Historique des refactorings majeurs

### 2026-07 — refactoring modulaire (issues #65 → #73, assemblage #74–#75)

Passage d'un `new_issue.py` monolithique à un package `app/` structuré :

- **`new_issue.py` : 2762 → 150 lignes.** Ne reste que le point d'entrée CLI
  (parsing des args, `create_app()`, démarrage du serveur, gestion des signaux).
- **Frontend extrait** hors du Python vers `templates/index.html`,
  `static/css/style.css` et `static/js/app.js` (les gabarits/JS étaient
  auparavant des chaînes inline). Exception assumée : le petit gabarit de login
  reste inline dans `auth.py` car utilisé uniquement par ce module.
- **9 modules dans `app/`**, chacun à responsabilité unique, extraits par étapes
  successives : `projets`, `auth`, `tunnel`, `watchers`, `issues`, puis
  `journal` / `cycle_vie` / `vues` (étape 8), et enfin l'assemblage via
  `create_app()` dans `app/__init__.py` (#74–#75), qui a introduit l'état
  partagé dans `app.config` (`etat.py`) et les imports différés.

Résultat : responsabilités isolées, état partagé propre, aucune globale de
module — la base sur laquelle s'appuient les décisions du §2 et le §4.

---

## 6. Refonte de l'interface web — carte de migration (issue #625)

> **Document de référence des étapes suivantes.** Il se veut auto-suffisant :
> une issue « sortir la fonctionnalité X de app.js » doit pouvoir s'appuyer sur
> ce seul §6. Les étapes suivantes peuvent tourner **en parallèle**, dans des
> worktrees distincts, en touchant autant que possible des fichiers différents.

### 6.1 Pourquoi et principe

`static/js/app.js` (~6400 lignes), `templates/index.html` (~900) et l'ancien
`static/css/style.css` (~500) sont refondus **par étapes**. Architecture retenue
par Alain : **modules JavaScript natifs** (`<script type="module">`), **sans
étape de build**, organisés autour de **briques partagées** (le « socle ») et de
**modules par fonctionnalité** (à venir). **Contrainte absolue : aucun changement
visible pour l'utilisateur à aucune étape.**

L'étape 1 (issue #625) pose le socle et découpe les fichiers **sans rien
remplacer** : l'ancien `app.js` reste seul aux commandes. Le socle est **inerte**
(chargé, testé, mais ne pilote aucun rendu et n'ouvre aucune connexion SSE).

### 6.2 Arborescence des modules du socle (`static/js/socle/`)

```
static/js/socle/
├── package.json      {"type":"module"} — fait traiter les .js comme ESM par Node
│                     (tests). Ignoré par le navigateur.
├── index.js          Point d'entrée chargé comme MODULE. Assemble les briques,
│                     installe le pont. N'ouvre PAS le SSE, n'enregistre AUCUNE
│                     délégation (socle inerte à l'étape 1).
├── store.js          Source de vérité unique (voir §6.3).
├── api.js            Accès unique aux routes Flask, vérifie response.ok,
│                     remonte toute erreur via toasts (plus d'erreur avalée).
├── sse.js            Canaux /stream et /events centralisés — NON connectés.
├── toasts.js         Notifications non bloquantes + LA modale de confirmation
│                     destructive. Styles auto-injectés (classes `socle-`).
├── dom.js            Utilitaires DOM + registre de délégation d'événements.
├── persistance.js    localStorage restreint aux préférences d'interface.
├── pont.js           Mécanisme de transition ancien⇄nouveau (voir §6.4).
└── tests/            Tests `node:test` (store, persistance, dom) + README.
```

### 6.3 Responsabilité de chaque brique (ce qu'elle expose)

- **store** — état applicatif centralisé, indexé de façon stable. Tranches :
  `issues` (dictionnaire indexé par `cleIssue(projet, numero)` = `"projet#numero"`),
  `selection`, `filtres`, `projets`, `watchers`, `issuesInbox`, `son`,
  `rateLimit`. API : `get` / `set` / `maj` / `abonner` / `abonnerCle`, plus les
  aides issues `lireIssue` / `ecrireIssue` / `remplacerIssues` / `listerIssues`.
  `creerStore(etatInitial)` est la fabrique générique testable.
- **api** — `api.get/post/supprimer(url, …)` : vérifie **systématiquement**
  `response.ok`, lève `ErreurApi{statut,url,corps}` et affiche un toast (sauf
  `{silencieux:true}`). Remplace les ~68 `fetch()` en dur qui testaient un champ
  métier du JSON et laissaient passer les 500.
- **sse** — `creerCanalSse(url, gestionnaires, opts)` + `sse.stream`/`sse.events`
  préconfigurés pour écrire dans le store. **`connecter()` n'est appelé nulle
  part à l'étape 1** : interdiction de double connexion `/stream` ou `/events`
  tant que l'ancien code gère les siennes.
- **toasts** — `toasts.info/succes/erreur/avertissement(msg)` (éphémère, jamais
  de « OK » à cliquer) et `toasts.confirmer(msg, opts) → Promise<boolean>` (LA
  seule modale, réservée au destructif). Remplace `alert()` / `confirm()` /
  `afficherToast()`.
- **dom** — `$`, `$$`, `creerElement`, `echapperHtml` (pure) et le **registre de
  délégation** : `surAction(selecteur, type, handler)` + `installerDelegation()`.
  Un seul écouteur par type d'événement, routé par `closest(selecteur)` — destiné
  à remplacer les gestionnaires inline du HTML et ceux générés en texte.
- **persistance** — `lire/ecrire` (JSON), `lireTexte/ecrireTexte` (brut, compat
  clés historiques), `supprimer`, `supprimerParPrefixe`, et `CLES` (rappel des
  clés localStorage d'app.js). **Uniquement des préférences d'interface locales.**

### 6.4 Mécanisme de transition (`pont.js`) — à retirer à la dernière étape

L'ancien `app.js` **doit rester un script CLASSIQUE**, chargé À CÔTÉ du module
(pas importé par lui) : dans un module tout est isolé et en mode strict, or les
>70 gestionnaires inline du HTML et les handlers générés en texte appellent les
~233 fonctions d'app.js **par leur nom global**. L'importer comme module casserait
l'interface.

`pont.js` est **le seul point de contact** entre les deux mondes, dans les deux
sens :

1. **ancien → socle** : `installerPont({store, api, …})` publie les briques sous
   `window.Bridge`. L'ancien code peut donc, temporairement, faire
   `window.Bridge.toasts.info(...)` ou lire `window.Bridge.store`.
2. **socle → ancien** : `appelerAncien('nomFonction', …args)` appelle une
   fonction globale de l'ancien app.js sans y référer en dur (elle n'est pas
   importable), avec un `warn` si absente.

**Cohabitation avec le store** : à l'étape 1 le store ne pilote rien. Quand une
donnée migrera dans le store et que l'ancien code en aura encore besoin, on
posera **dans pont.js** un miroir explicite (`store.abonnerCle(cle, …)` →
variable/DOM ancien), retiré avec le reste.

**Suppression** : à la dernière étape (app.js vidé), supprimer `pont.js`, l'appel
`installerPont()` dans `index.js`, et toute référence à `window.Bridge` /
`appelerAncien`. Aucune autre brique ne dépend de `pont.js`.

**Ordre de chargement** (`templates/fragments/scripts.html`) — à préserver :
1. `<script type="importmap">` (versionnage des modules, cf. §6.6) ;
2. `<script>` inline Jinja : `window.COULEURS_PERSISTEES`,
   `window.MIMES_IMAGE_ACCEPTES` (doit précéder les deux mondes) ;
3. `<script src=app.js>` (classique, s'exécute au parsing) ;
4. `<script type="module" src=index.js>` (différé ⇒ s'exécute **après** app.js et
   après le script inline : l'ancien code et les variables Jinja sont prêts).

### 6.5 Correspondance zones de l'interface ↔ fichiers

**Fragments HTML** (`templates/index.html` = squelette qui `{% include %}`) :

| Zone | Fragment (`templates/fragments/`) |
|------|-----------------------------------|
| Entête (titre, rate-limit, Quitter, Déconnexion) | `entete.html` |
| Bandeaux (éval Windows, repli REP_TRAVAIL, sélecteur projet) | `bandeaux.html` |
| Barre d'onglets | `onglets.html` |
| Onglet Nouvelle issue | `onglet_creation.html` |
| Onglet Résultats (+ inclut le panneau latéral) | `onglet_resultats.html` |
| Panneau latéral Infrastructure | `panneau_lateral.html` |
| Onglet Résultats inbox | `onglet_inbox.html` |
| Onglet Configuration | `onglet_config.html` |
| Onglet Journal | `onglet_journal.html` |
| Onglet CCW | `onglet_ccw.html` |
| Modales | `modale_confirmation.html`, `modale_nouveau_projet.html`, `modale_supprimer_projet.html`, `modale_recherche_titre.html`, `modale_interrompre.html`, `modale_duree_watcher_inbox.html`, `overlay_arret.html` |
| Scripts (importmap + Jinja + app.js + module) | `scripts.html` |

**Feuilles CSS** — chargées dans cet ORDRE dans `<head>` (ordre = cascade ;
concaténation byte-identique à l'ancien `style.css`, vérifiée) :

| Ordre | Feuille (`static/css/`) | Zone |
|-------|-------------------------|------|
| 1 | `base.css` | reset, mise en page, primitives de formulaire |
| 2 | `composants.css` | boutons, messages, aperçu, rappels Nouveau projet, terminal |
| 3 | `resultats.css` | onglet Résultats (liste, détail, panneau latéral, diff) |
| 4 | `modales.css` | overlay/carte de modale, boutons destructifs, overlay d'arrêt |
| 5 | `recherche-interruption.css` | recherche par titre + interruption (zone Résultats) — **DOIT rester après `modales.css`** (`.modal-recherche-titre` surcharge `.modal-carte` à specificité égale) |
| 6 | `inbox.css` | onglet Résultats inbox |

**Modules JS par fonctionnalité** : un module par zone, dans `static/js/`,
importé par `index.js` (voir §6.7). Chaque module utilise les briques du socle.
Déjà sortis : `onglets.js` (bascule entre onglets, issue #626, étape 2) et
`resultats.js` (moteur de l'onglet Résultats, issue #627, étape 3). Futurs
modules (ex. `creation.js`, `config.js`, `ccw.js`, `journal.js`,
`inbox.js`, `nouveau_projet.js`) suivent le même patron.

**Onglet Watchers supprimé (issue #626, étape 2)** : le tableau des watchers
+ cases à cocher + actions Lancer/Relancer/Éteindre par lot n'existent plus.
La surveillance des watchers (un par ligne, statut actif/inactif) reste dans
le **panneau latéral Infrastructure** (`panneau_lateral.html`, actions par
projet individuel — pas de sélection multiple). Ordre actuel de la barre
d'onglets (`onglets.html`) : Résultats, Résultats inbox, Journal watcher,
Configuration, CCW, Nouvelle issue — Résultats est l'onglet actif au
chargement de la page (avant l'issue #626, c'était Nouvelle issue).

> **Étape 3 réalisée — `static/js/resultats.js` (issue #627)** : premier module
> par fonctionnalité. Il sort d'`app.js` le **moteur** de l'onglet Résultats —
> chargement de la liste (initial unique + ↻, sans cache localStorage), canal
> `/stream` (via la brique `sse`, UNIQUE connexion), traitement CIBLÉ des
> événements `debut_issue`/`fin_issue`/`creation_issue`, fetch unique
> post-dépassement #334, et calcul + application des badges de décompte/estimation
> — avec le **store** (tranches `issues` + `timing`) pour source de vérité unique.
> `app.js` conserve, pendant la transition, le rendu DOM d'une ligne et les
> fonctionnalités hors périmètre (filtres, case à cocher, badges ✅/Diff/All,
> détail, recherche, panneau latéral), qui lisent un MIROIR du store via quelques
> hooks `window.__resultats*` posés dans `app.js` et appelés par `resultats.js`.
> Tests de logique pure : `static/js/tests/resultats.test.js`. L'import map
> (§6.6) couvre désormais aussi ces modules de `static/js/` (hors `app.js`).

> **Note parallélisme** : HTML et JS se découpent proprement par zone. Le CSS
> est plus contraint : la cascade impose de garder l'ordre source, donc quelques
> règles partagées (`button`, `.message`, primitives) vivent dans `base.css` /
> `composants.css`. Règle : une étape ajoute ses règles dans la feuille de SA
> zone ; ne toucher `base.css`/`composants.css` que pour un changement réellement
> transverse.

### 6.6 Versionnage des fichiers servis (cache-busting)

`app/statique.py` expose deux globales Jinja (`enregistrer_aides_statiques`
dans `create_app`) :

- `url_statique(chemin)` = `url_for('static', …)` + `?v=<mtime>`. Utilisée pour
  chaque CSS, pour `app.js` et pour le `src` du module d'entrée : dès qu'un
  fichier change, son URL change, le navigateur refetch — sans vider le cache.
- `importmap_socle()` = un **import map** JSON remappant chaque module du socle
  vers son URL `?v=<mtime>`. Nécessaire car les imports RELATIFS entre modules ES
  (`import './store.js'`) ne propagent pas le `?v=` de l'importateur. Les modules
  gardent des imports relatifs (indispensables à `node --test`) ; le navigateur
  applique l'import map pour le cache-busting par fichier.

Les fichiers statiques ne sont **pas** derrière `login_requis` : les modules et
CSS sont donc servis (statut 200, `text/javascript` / `text/css`) en local,
`--lan` et `--externe`, **même session expirée** (la page protégée redirige vers
`/login`, mais pas ses ressources statiques). Vérifié par un test serveur.

### 6.7 Procédure type — sortir une fonctionnalité de l'ancien code

Pour chaque fonctionnalité migrée (étapes suivantes), dans l'ordre :

1. **Créer/compléter son module** dans `static/js/` (ex. `resultats.js`),
   importé par `index.js`. Y déplacer les fonctions concernées d'app.js ; leur
   état passe dans le **store**, leurs appels réseau passent par **api**, leurs
   messages par **toasts**.
2. **Brancher ses événements via le registre de délégation** (`dom.surAction`)
   au lieu des `onclick=` inline.
3. **Retirer les gestionnaires inline** de sa zone (fragment HTML) et les
   handlers générés en texte correspondants.
4. **Supprimer le code correspondant d'app.js.** Vérifier qu'aucune autre partie
   d'app.js n'appelle encore ces fonctions (sinon, passer par le pont le temps
   de la transition).
5. **Vérifier** : `node --test static/js/socle/tests/` (+ tests du nouveau
   module si ajoutés) et **rejouer `VERIFICATIONS_MANUELLES.md`** (au moins la
   zone touchée + le préambule « une seule connexion SSE »).

Quand app.js est vide : retirer le pont (§6.4) et le `<script src=app.js>`.

---

*Document technique interne — voir `BRIDGE_AGENT_DOC.md` pour l'usage du bridge.*
