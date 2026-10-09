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

### 2.6 Garde-fou `configs/*.conf` et actions légitimes d'Alain (issue #724)

`watcher.py` détecte et annule toute modification de `configs/*.conf` survenue
pendant le traitement d'une issue (`_empreinte_configs`/
`_restaurer_configs_modifies`, comparaison du contenu avant/après chaque
tentative — voir `BRIDGE_AGENT_DOC.md` §12 pour la règle elle-même). Comme
`configs/` est **commun à tous les projets**, ce garde-fou traiterait à tort
comme une violation tout geste volontaire d'Alain qui y écrit pendant qu'une
issue tourne sur un **autre** projet. Trois points de `new_issue.py` qui
écrivent légitimement dans `configs/` — création de projet
(`nouveau_projet.ecrire_conf`), suppression (`supprimer_projet._supprimer_conf`)
et enregistrement de l'onglet Configuration (`app/projets.sauvegarder_conf`) —
appellent donc `etat_configs_legitimes.enregistrer(nom_fichier)` juste après
l'écriture disque, horodatée dans `logs/configs_legitimes.json` (purge
automatique au-delà d'une heure, `DUREE_VALIDITE_S`). `_restaurer_configs_modifies`
consulte cette trace avant d'agir sur un fichier changé : une action légitime
postérieure au début du traitement de l'issue n'est ni annulée ni restaurée
(message INFO au lieu du WARNING habituel). Seuls ces trois points appellent
`enregistrer()` — le traitement d'une issue (`watcher.py`, `lancer_claude`,
`traiter_issue`) n'appelle jamais cette fonction, seulement sa contrepartie en
lecture (`instant_legitime`) : une issue ne peut donc pas s'ajouter elle-même
à cette trace.

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
├── sse.js            Canal /stream centralisé (connecté depuis l'étape 3, #627
│                     — voir §6.3) ; `/events` reste géré par l'ancien app.js.
├── toasts.js         Notifications non bloquantes + LA modale de confirmation
│                     destructive. Styles auto-injectés (classes `socle-`).
├── dom.js            Utilitaires DOM + registre de délégation d'événements.
├── persistance.js    localStorage restreint aux préférences d'interface.
├── panne_github.js   Alerte explicite de panne GitHub (issue #732, voir §7).
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
- **sse** — `creerCanalSse(url, gestionnaires, opts)` + `sse.stream`, préconfiguré
  pour écrire dans le store. Connecté par `static/js/resultats.js::initialiser()`
  (issue #627) — pas par `index.js`, pour qu'un import du module reste sûr sous
  Node. `/events` n'est pas repris ici : il reste géré par l'ancien app.js.
- **toasts** — `toasts.info/succes/erreur/avertissement(msg)` (éphémère, jamais
  de « OK » à cliquer) et `toasts.confirmer(msg, opts) → Promise<boolean>` (LA
  seule modale, réservée au destructif). Remplace `alert()` / `confirm()` /
  `afficherToast()`.
- **dom** — `echapperHtml` (pure) et le **registre de délégation** :
  `surAction(selecteur, type, handler)` + `installerDelegation()`.
  Un seul écouteur par type d'événement, routé par `closest(selecteur)` — destiné
  à remplacer les gestionnaires inline du HTML et ceux générés en texte.
- **persistance** — `lire/ecrire` (JSON), `lireTexte/ecrireTexte` (brut, compat
  clés historiques), `supprimer`, `supprimerParPrefixe`, `toutesLesEntrees`
  (scan à préfixe variable), `cleCacheDetail`, `purgerCacheDetailProjets` /
  `purgerCacheDetailHorsProjets` / `purgerProjet` (purge du cache détail, y
  compris à la suppression d'un projet — issue #644), et `CLES` (les clés
  localStorage de l'interface). **Uniquement des préférences d'interface
  locales.** Migration terminée à l'issue #644 : app.js n'accède plus DU TOUT
  au `localStorage` en direct, uniquement via `window.Bridge.persistance`
  (pont, cf. §6.4) — c'est désormais le SEUL point d'accès du code JS.
- **panne_github** — `signalerEchecPossible(reponseJson)`, à appeler avec le
  JSON d'une réponse en échec d'une route gh surveillée. Voir §7 pour le
  mécanisme complet (backend + journal des pannes).

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
| Bandeaux (éval Windows, jetons annuaire, repli REP_TRAVAIL, sélecteur projet) | `bandeaux.html` |
| Barre d'onglets | `onglets.html` |
| Onglet Nouvelle issue | `onglet_creation.html` |
| Onglet Résultats (+ inclut le panneau latéral) | `onglet_resultats.html` |
| Panneau latéral Infrastructure | `panneau_lateral.html` |
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
| 6 | `inbox.css` | reliquat de l'ancien onglet « Résultats inbox » (supprimé, issue #639) : badge d'alerte (onglet Résultats) + historique du watcher spool (panneau latéral) |

**Modules JS par fonctionnalité** : un module par zone, dans `static/js/`,
importé par `index.js` (voir §6.7). Chaque module utilise les briques du socle.
Déjà sortis : `onglets.js` (bascule entre onglets, issue #626, étape 2),
`resultats.js` (moteur de l'onglet Résultats, issue #627, étape 3),
`panneau_lateral.js` (panneau latéral, issue #628, étape 4),
`resultats_coches.js` (case « traité/lu » à état serveur + copie fiable, issue
#636, étape 5b), `actions_ligne.js` (actions cliquables sur la ligne d'une
issue ouverte + son par issue, issue #641, étape 6), `ccw.js` (onglet CCW,
pilotage du PC fixe Windows, issue #649), `journal.js` (onglet Journal
watcher, issue #650), `config.js` (onglet Configuration + zone dangereuse
de suppression de projet, issue #651, étape 12) et `creation.js` (formulaire
« Nouvelle issue » complet, issue #652). Futurs modules (ex.
`nouveau_projet.js`) suivent le même patron,
`nouveau_projet.js`) suivent le même patron.

**Onglet Watchers supprimé (issue #626, étape 2)** : le tableau des watchers
+ cases à cocher + actions Lancer/Relancer/Éteindre par lot n'existent plus.
La surveillance des watchers (un par ligne, statut actif/inactif) reste dans
le **panneau latéral Infrastructure** (`panneau_lateral.html`, actions par
projet individuel — pas de sélection multiple). Résultats est l'onglet actif au
chargement de la page (avant l'issue #626, c'était Nouvelle issue ; l'ordre
actuel des onglets figure dans la note « Onglet Résultats inbox supprimé »
ci-dessous, issue #639).

**Onglet Résultats inbox supprimé (issue #639, étape 9b)** : le fragment
`onglet_inbox.html` et l'entrée `inbox` de la barre d'onglets n'existent plus.
Le suivi des dépôts `issues_inbox/` est fusionné dans la liste Résultats (lignes
« 📥 fichier reçu » / « ✕ fichier refusé », alimentées par les événements SSE
`fichier_recu`/`creation_issue`/`fichier_refuse` de l'étape 9a #631 et
reconstruites au rechargement depuis `/issues-inbox/etat`, `resultats.js`) ; le
badge d'alerte 🚨 est passé sur l'onglet Résultats ; l'historique du watcher
spool a rejoint le panneau latéral. Ordre actuel de la barre d'onglets :
Résultats, Journal watcher, Configuration, CCW, Nouvelle issue.

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

> **Étape 5b réalisée — `static/js/resultats_coches.js` (issue #636)** : sort
> d'`app.js` la **case « traité/lu »** de chaque ligne Résultats. Son état ne vit
> plus dans le `localStorage` mais **côté serveur** (`store.casesCochees`,
> synchronisé via les routes `/cases-cochees` de l'étape 5a, issue #629) : une
> SEULE requête `GET /cases-cochees/<projet>` par projet au chargement, plus une
> **migration idempotente** au premier lancement (les clés
> `resultat-coche:<projet>:<numero>` du `localStorage` sont envoyées en une fois à
> `POST /cases-cochees/importer` puis retirées). `app.js` ne garde que de minces
> relais (`estResultatCoche`/`basculerCocheResultat` → module via le pont). Le
> module porte aussi le **moteur de copie fiable** : cocher une case (ou cliquer
> un badge ✅/Diff/All) engage la copie **pendant le geste** — `ClipboardItem`
> alimenté par une promesse en contexte sécurisé (localhost/HTTPS), texte
> **préchargé** + `execCommand` synchrone en `--lan` (HTTP non-localhost, API
> presse-papier moderne absente) — au lieu de fetcher AVANT d'écrire (ce qui
> sortait de la fenêtre d'activation et faisait échouer la copie par
> intermittence). **Feedback honnête** : jamais de ✓ sur échec (toast d'erreur),
> et le cochage (persistance/grisage/pastilles) ne dépend jamais de la copie.
> Enfin, « Cocher tout » est aligné sur le périmètre des pastilles (les N
> premières issues par projet, `premieresParProjet`), et un bouton **« Tout à
> zéro »** marque comme cochées, côté serveur, toutes les issues chargées de tous
> les projets (confirmation légère, aucune copie). Tests de logique pure :
> `static/js/tests/resultats_coches.test.js`.

> **Étape 6 réalisée — `static/js/actions_ligne.js` (issue #641)** : remplace,
> pour une ligne OUVERTE de l'onglet Résultats, les préfixes statiques ⚠️
> needs-human / ✏️ mode_write par des actions cliquables directement sur la
> ligne (retirer needs-human, interrompre) — `interrompreIssue()`/
> `relancerIssue()` (`app.js`) restent la SEULE implémentation (même route,
> même confirmation, même modale) : la ligne les appelle directement, sans
> duplication. S'y ajoute un contrôle compact « G/P/C/S » (S=Silence, #699)
> pour le son PROPRE à l'issue (#630/#637), dont les fonctions pures ont été **déplacées** (pas
> dupliquées) depuis `panneau_lateral.js` : `sonIssueDepuisReponse`,
> `normaliserChoixSonIssue`, `etatsOptionsSonIssue`. Chargement réseau du son :
> une SEULE requête `GET /son-issue/<projet>` (nouvelle route groupée) par
> projet connu, jamais par ligne — même stratégie que l'étape 5b. En
> contrepartie, le panneau latéral perd les 3 actions désormais sur la ligne
> (Interrompre seul, Retirer needs-human, contrôle de son) — un seul
> emplacement par action ; il garde l'infrastructure (watchers, watcher
> spool), l'interrupteur GLOBAL de son, les toggles 🔔 Notifications,
> « Interrompre et relancer » et **Fermer définitivement** (clôture manuelle
> distincte, jamais demandée sur la ligne). Tests de logique pure :
> `static/js/tests/actions_ligne.test.js`.

> **Correctif étape 6 (issue #642)** : #641 avait rendu ✏️ mode_write cliquable
> pour interrompre — mais cette action existe aussi pour une issue en LECTURE
> (sans le label mode_write), qui n'avait alors plus aucun moyen d'être
> interrompue depuis sa ligne (régression). Correctif : ✏️ redevient PUREMENT
> INFORMATIF (infobulle « Mode écriture en cours », plus de clic) ; une icône
> DÉDIÉE d'interruption (carré vert ✓ au repos, rouge ✕ au survol, pur CSS)
> s'affiche désormais sur toute issue OUVERTE actuellement EN COURS — lecture
> OU écriture — à partir de `afficherIconeInterruption(labels, timing)`
> (`actions_ligne.js`), basée sur le MÊME état (`timing.debut`) que le décompte
> TIMEOUT actif de `resultats.js`, jamais sur le seul label mode_write. Comme ce
> `timing` n'est pas toujours connu au moment de la construction de la ligne,
> l'icône est toujours posée masquée (`display:none`) puis révélée par
> `resultats.js::majBadges()` à chaque recalcul (import direct de la fonction
> pure d'`actions_ligne.js`) — même patron que `.ligne-tempsrestant`/
> `.ligne-estimation`. Le clic appelle directement `interrompreDepuisLigne()` →
> `interrompreIssue()` (app.js, INCHANGÉES) : même route/confirm()/modale,
> aucune logique dupliquée. Le bouton « Interrompre et relancer (watcher CCL) »
> du panneau latéral reste inchangé (action à l'échelle du watcher, pas de
> l'issue seule).

> **Onglet CCW réalisé — `static/js/ccw.js` (issue #649)** : sort d'`app.js`
> l'onglet CCW (pilotage du PC fixe Windows et de ses projets via SSH/SCP,
> routes `/ccw/*`) — `ccwMessage`, `ccwAfficherSortie`, `ccwOccupe`,
> `ccwOuvrirOnglet`, `ccwChargerProjets`, `ccwPreselectionnerProjet`,
> `ccwRedemarrerProjet`, `ccwDemarrerProjet`, `ccwArreterProjet`,
> `ccwNettoyerVerrous`, `ccwAjouterProjet`, `ccwFinaliserProjet`, ainsi que
> l'état `ccwProjetsConnus`/`obtenirCcwProjetsConnus` (issue #375, lu par le
> panneau latéral). Appels réseau migrés vers **api** (`{silencieux:true}`,
> l'erreur restant affichée dans la zone `#ccw-message` dédiée plutôt qu'en
> double par un toast), confirmations natives (`confirm()`) remplacées par
> **toasts.confirmer()**, `alert()` par **toasts**. Gestionnaires `onclick=`
> inline retirés (fragment `onglet_ccw.html` + lignes générées du tableau des
> projets) au profit de la délégation du socle (`dom.surAction`) : la règle de
> pré-sélection d'une ligne ignore désormais explicitement les clics dont la
> cible est un `<button>` (la délégation à écouteur unique du socle ne rejoue
> pas la bulle DOM entre règles — `event.stopPropagation()`, utilisé par
> l'ancien code, n'a ici aucun effet sur les autres règles déjà enregistrées).
> **Couplage avec le panneau latéral (rapport #632)** : `panneau_lateral.js`
> importe désormais DIRECTEMENT `obtenirCcwProjetsConnus`/`ccwChargerProjets`/
> `ccwRedemarrerProjet`/`ccwNettoyerVerrous` depuis `ccw.js` (deux modules ES,
> plus simple et plus sûr que le pont — erreur de compilation immédiate si un
> nom disparaît). Le sens inverse (`ccw.js` doit déclencher
> `rafraichirPanneauLateralResultats()` après un rechargement de la liste)
> reste sur le pont : importer `panneau_lateral.js` depuis `ccw.js`
> créerait un cycle d'imports ES, et cette fonction n'est de toute façon
> publiée que comme globale (`window.rafraichirPanneauLateralResultats`, pour
> l'ancien app.js) — usage du pont dans le sens module → module qu'il ne dessert
> normalement pas, retenu ici pour éviter le cycle sans dupliquer la fonction.
> `ccwOuvrirOnglet` et `ccwRedemarrerProjet` restent en outre publiées en
> globales (`window.*`) : la première pour le mécanisme générique
> `initialisationsPour('ccw')` d'`onglets.js` (inchangé, il atteint aussi bien
> une fonction d'app.js qu'une globale publiée par un module), la seconde pour
> l'appel direct fait par `interrompreEtRelancer()` (app.js, script classique,
> ne peut pas importer ce module). Logique pure extraite et testée
> (`couleurEtatCcw`, `libelleTopicCcw`, `afficherBoutonDemarrer`/
> `afficherBoutonArreter`, `selectionRestauree`) : `static/js/tests/ccw.test.js`.
> La case « Projet CCW » de la modale Nouveau projet (bootstrap initial,
> `npCcw*`) est une fonctionnalité distincte, non touchée par cette étape.

> **Étape 11 réalisée — `static/js/journal.js` (issue #650)** : sort d'`app.js`
> l'onglet **Journal watcher** — `demarrerJournal()` (connexion SSE
> `/journal/<projet>`, une seule à la fois, lignes colorées insérées en tête de
> `#terminal`) et `viderTerminal()`. La variable `sourceSSE`, propriété exclusive
> de ces deux fonctions (vérifié : aucune autre partie d'app.js ne la lisait),
> devient une variable de module (`sourceJournal`), non exposée. **Branchement
> par import direct** (pas par le pont) : `static/js/onglets.js` importe
> `demarrerJournal` et l'appelle directement dans `activerOnglet('journal')` ;
> `index.js` appelle `initJournal()` une fois (délégation du bouton « Vider
> l'affichage », `data-action="journal-vider"`, retire l'`onclick=` inline du
> fragment `onglet_journal.html`). Tests de logique pure (code couleur d'une
> ligne selon son contenu) : `static/js/tests/journal.test.js`.

> **Étape 12 réalisée — `static/js/config.js` (issue #651)** : sort d'`app.js`
> l'onglet **Configuration** — `chargerConfig()`/`sauvegarderConfig()` et
> l'ensemble de la **zone dangereuse** (suppression de projet, issue #587) :
> `ouvrirSupprimerProjet()`, sa modale de confirmation (checklist des 3 cibles
> + nom retapé, aperçu dry-run `GET /supprimer-projet/verifier/<nom>`) et la
> soumission (`POST /supprimer-projet`). **Branchement par import direct**
> (comme `journal.js`, étape 11) : `static/js/onglets.js` importe
> `chargerConfig` et l'appelle directement dans `activerOnglet('config')` ;
> `initialisationsPour('config')` ne pousse plus `'chargerConfig'`.
> Particularité propre à cet onglet (contrairement à `journal.js`) :
> `chargerConfig()` reste aussi appelée directement par l'ancien `app.js`
> (`onProjetChange`, quand l'onglet est déjà actif au moment d'un changement de
> projet) — `config.js` la publie donc AUSSI en `window.chargerConfig`, comme
> une globale ordinaire (même patron que
> `window.rafraichirPanneauLateralResultats`, `panneau_lateral.js`).
> `retirerProjetDuSelecteur` (symétrique d'`ajouterProjetAuSelecteur`) **reste
> dans `app.js`** : il manipule le sélecteur global `#projet` du bandeau
> supérieur, pas un élément de l'onglet Configuration — `config.js` l'appelle
> via le pont (`appelerAncien`). Le bouton global « + Nouveau projet » (même
> bandeau) et tout son flux restent également hors périmètre de cette issue.
> `index.js` appelle `initialiserConfig()` une fois (délégation des boutons
> Enregistrer/Enregistrer et relancer/Supprimer ce projet, du curseur Tâches en
> parallèle et de la modale de suppression — `data-action`, retire tous les
> `onclick=`/`onchange=`/`oninput=` inline de `onglet_config.html` et
> `modale_supprimer_projet.html`). Trois fonctions PURES extraites et testées
> (`static/js/tests/config.test.js`) : `construireResumeIdentite` (résumé HTML
> de l'identité du projet), `suppressionActivable` (les 3 cases cochées ET le
> nom retapé à l'identique, insensible à la casse/aux espaces) et
> `messageStatutCommitDoc` (message de fin selon le statut du commit
> automatique de `BRIDGE_AGENT_DOC.md`, issue #645).
> **Étape 10 réalisée — purge des fuites `localStorage`, migration terminée
> (issue #644)** : `persistance.js` était conçu depuis l'étape 1 comme LE point
> d'accès unique au `localStorage`, mais son propre en-tête documentait que
> l'ancien `app.js` continuait d'y accéder directement pour les clés
> historiques. Cette étape termine la migration : `app.js` (script classique)
> passe désormais systématiquement par `window.Bridge.persistance` (pont, cf.
> §6.4) — plus aucun accès `localStorage` direct en dehors de `persistance.js`.
> Deux amorçages tournaient AVANT `DOMContentLoaded` (donc avant que le module
> socle publie `window.Bridge`, cf. `scripts.html`) : `restaurerProjet()` et
> `initNotifPc()` sont désormais posés sur `window.addEventListener(
> 'DOMContentLoaded', …)`, comme `rafraichirReplisRepTravail` le faisait déjà.
> **Fuite corrigée** : `soumettreSupprimerProjet()` (flux #587) ne purgeait
> AUCUNE clé `localStorage` du projet supprimé — `persistance.purgerProjet(nom)`
> retire désormais son cache détail (`bridge_cache_detail_<nom>_*`) et son
> entrée dans `bridge_filtres_resultats`. **Accumulation réduite** : le cache
> détail (TTL appliqué à la LECTURE seulement, jamais purgé de lui-même) est
> maintenant vidé en totalité à chaque ↻ (`purgerCacheDetailProjets(null)`,
> simplification — les projets actifs étaient de toute façon déjà repurgés à
> chaque ↻ avant #644), et des entrées des projets sortis du filtre à chaque
> bascule de filtre (`purgerCacheDetailHorsProjets`, `basculerFiltreProjet` /
> `basculerTousLesFiltres`) : un projet consulté puis masqué ne s'accumule plus
> indéfiniment. Nouvelles fonctions PURES testées (`clesCacheDetailPourProjets`,
> `clesCacheDetailHorsProjets`) + `toutesLesEntrees()` (remplace le scan brut de
> `resultats_coches.js::migrerLocalStorage`, seul autre accès direct trouvé au
> grep exhaustif).

> **Formulaire « Nouvelle issue » sorti — `static/js/creation.js` (issue #652)** :
> tout l'onglet de création quitte `app.js` (~1200 lignes retirées), comportement
> STRICTEMENT inchangé (objectif structurel). Le module regroupe :
> `collecterFormulaire`, `envoyerIssue`, la bibliothèque de **templates** (#284),
> la **pièce jointe image** (#191/#192), l'**envoi en lot** (#135/#505), les
> **détecteurs d'en-tête à la frappe** (`#Titre`, `PROJET` #109, `TIMEOUT` #111,
> `MODE` #326) + le **résumé d'en-tête** (#117), l'**aperçu**, les modales
> (confirmation/incohérence/erreur) et la **mémorisation de `notif_pc`** (#93).
> Les gestionnaires `onclick=`/`onchange=` inline de `onglet_creation.html`
> (le fragment qui en portait le plus) sont remplacés par la **délégation** du
> socle (`data-action="creation-*"`, `dom.surAction`), y compris les détecteurs
> déclenchés sur `input` de `#corps`, enregistrés dans le même ordre qu'avant.
> **Initialisation par IMPORT DIRECT** depuis `onglets.js` (`initCreation`,
> idempotente, à la première activation de l'onglet) — plus par le pont ; d'où
> `initialisationsPour('creation') === []`. Pont résiduel : `creation.js` publie
> `window.chargerTemplates` / `window.afficherMessage` (appelées par leur nom
> depuis `app.js` — `onProjetChange`, `lancerWatcher`) et appelle
> `onProjetChange()` / `mettreAJourInfoProjet()` via `appelerAncien`. `notif_pc`
> n'étant utilisée QUE par ce formulaire (le panneau latéral dérive l'état de ses
> cases 🔔 des labels GitHub, cf. `etatsCasesNotif`), sa lecture/écriture passe
> par la clé unique `persistance.CLES.notifPc` (déjà point d'accès depuis #644),
> sans duplication. Fonctions PURES nouvellement testées (jusqu'ici non
> couvertes) : `zoneEntete`, `lireChampEntete`, `retirerLigneEntete`,
> `reconnaitreModeTexte`, `detecterIncoherenceProjet`, `decouperCorpsEnBlocs`,
> `projetEffectifBloc`, `modeEffectifBloc` (`tests/creation.test.js`) ;
> `pont_globales.test.js` gagne un garde-fou du **pont inverse** (globales
> `window.*` qu'`app.js` appelle encore par leur nom).

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

## 7. Alerte explicite de panne GitHub (issue #732)

### 7.1 Pourquoi

Pendant un incident GitHub (constaté les 06 et 07/10/2026), les échecs de `gh`
affichés (« Résultats — échec de chargement », erreurs 502) ne disaient pas si
la cause était une panne GitHub, la connexion internet locale ou le jeton —
il fallait aller consulter soi-même https://www.githubstatus.com/.

### 7.2 Backend — `app/github_status.py`

- `classer_echec_gh(message)` : classification **pure**, fondée sur le message
  d'erreur déjà construit par chaque appelant (`res.stderr.strip()`, "Timeout
  (gh n'a pas répondu en 30s).", …) plutôt que sur des booléens d'exception à
  plomber partout. `True` seulement pour un timeout, une erreur réseau ou une
  réponse 5xx — jamais pour une erreur normale (404/401/403/422) ni pour la
  limite de débit (déjà signalée par le bandeau ⚡, §"Indicateur de rate
  limit" / `app/rate_limit.py`).
- `verifier_statut()` : interroge `summary.json` de githubstatus.com (API
  publique, sans authentification), avec un **cache serveur d'environ une
  minute** (`SEUIL_CACHE_S`) — au plus une requête réseau par minute, quel que
  soit le nombre d'appels `gh` en échec entre-temps. Délai court
  (`TIMEOUT_REQUETE_S` = 5s) et ne lève jamais : toute erreur de la
  vérification elle-même retombe sur le message de repli « injoignable »,
  jamais sur une erreur visible supplémentaire.
- Trois messages de repli, par ordre de gravité (`calculer_message_statut`) :
  incident signalé (nom de l'incident + composants concernés parmi `Issues`,
  `API Requests`, `Git Operations`, `Webhooks`) → GitHub opérationnel malgré
  l'erreur (cause probablement locale) → GitHub et sa page de statut tous deux
  injoignables (connexion internet probable).
- **Points d'appel branchés** (`signaler_resultat_gh`, cherché avant d'écrire
  du nouveau code — aucun point central de ce type n'existait) : listes
  d'issues (`_lister_issues_labels`), détail (`issue_detail`), création
  (`creer_issue_gh`), relance (`app/interruption.py::relancer_issue`), labels
  (`modifier_label_notif`) — tous dans `app/issues.py` sauf la relance. Chaque
  réponse JSON d'échec porte un champ `panne_probable` (calculé par
  `classer_echec_gh`, aucun appel réseau à cet endroit) que le JS utilise pour
  décider de vérifier le statut — **jamais dans le chemin de la requête qui a
  échoué** : la vérification réseau elle-même n'a lieu que dans la route
  `GET /github-statut`, appelée séparément par le navigateur.
- Épisodes de panne (pas une erreur individuelle) : `signaler_resultat_gh`
  ouvre un épisode au premier échec classé `panne_probable`, le referme dès
  qu'un appel `gh` surveillé réussit de nouveau. Persisté dans
  `logs/etat_panne_github.json` (survit à un redémarrage de new_issue.py en
  cours d'épisode) ; sa cause est mise à jour à chaque `verifier_statut()`
  (y compris celles déclenchées par le polling JS, voir §7.3) pour refléter,
  à la fermeture, la DERNIÈRE cause connue pendant l'épisode.

### 7.3 Frontend — `static/js/socle/panne_github.js`

`signalerEchecPossible(reponseJson)` ne fait rien si `panne_probable` est
absent/faux. Sinon, `GET /github-statut` (séparé, non bloquant) affiche un
toast selon la gravité reçue (`erreur` pour incident/injoignable,
`avertissement` pour « cause probablement locale ») et, tant que la réponse
porte `panne:true`, se répète toutes les 60s ; dès le retour à `panne:false`,
un message « GitHub est rétabli. » s'affiche une seule fois. Branché aux cinq
points d'appel ci-dessus : `resultats.js` (listes), `app.js` (détail, relance
— via `window.Bridge.panneGithub`, script classique), `creation.js`
(création, mono-issue et lot), `panneau_lateral.js` (labels).

### 7.4 Journal des pannes — `logs/pannes_github.log`

Non versionné (sous `logs/`, déjà gitignoré). **Une ligne par épisode**,
jamais par erreur individuelle, format `cle=valeur` séparé par ` | ` (`debut`,
`fin`, `duree_s`, `cause`, `incident`, `composants`) — voir
`github_status.formater_ligne_journal`/`parser_ligne_journal`. Taille bornée à
`RETENTION_JOURS` (~un an) : purgé à chaque écriture
(`_purger_anciennes_lignes`). Ne contient jamais de jeton ni de contenu
d'issue — uniquement des horodatages et des libellés de cause/composant.

`scripts/resume_pannes_github.py` (lecture seule, aucun effet sur le reste du
fonctionnement) affiche le nombre d'épisodes et la durée cumulée, par mois et
par cause — pour juger, avec ses propres chiffres, si les coupures viennent de
GitHub ou de la connexion locale.

**Limite documentée** (issue #732) : ce journal ne voit que les pannes
survenues PENDANT que `new_issue.py` tournait ET qu'un appel `gh` d'un des
cinq points surveillés a échoué. Une coupure internet qui empêcherait aussi
`new_issue.py` de tourner, ou un échec `gh` hors de ces cinq points (ex.
`annuler_issue`/`fermer_issue`, ou tout appel de `watcher.py`/
`scripts/watcher_issues_inbox.py`, hors périmètre de cette issue), n'y
apparaît pas.

### 7.5 Limite constatée, non corrigée — `issues_inbox/` pendant une panne GitHub

Hors périmètre de l'issue #732 (le Watcher spool n'est pas modifié), mais
vérifié par lecture de code : quand `scripts/watcher_issues_inbox.py` traite
un fichier et que `gh issue create` échoue (panne GitHub comprise — aucune
distinction de cause à cet endroit), `traiter_fichier()` appelle `_rejeter()`
qui déplace le fichier vers `issues_inbox/rejected/` via
`_deplacer_vers_rejected()` — **exactement comme pour un rejet définitif**
(PROJET inconnu, titre dupliqué, etc.). Le fichier n'est donc pas perdu (il
reste visible dans `rejected/`, avec son motif, et déclenche l'alarme de
l'onglet « Résultats inbox », `app/issues_inbox.py::etat_inbox`), mais rien
ne le reprend automatiquement une fois la panne terminée — sans intervention
manuelle (le redéposer dans `issues_inbox/`), un fichier arrivé pendant une
panne GitHub de quelques minutes finit dans le même état qu'une erreur
définitive. Même mécanisme pour un lot multi-issues (`_traiter_lot`, déplacé
vers `rejected/` seulement si TOUS les blocs ont échoué).

---

## 8. Création et suppression de projet (`nouveau_projet.py` / `supprimer_projet.py`)

Même orchestrateur pour le CLI et le bouton web correspondant (mêmes étapes,
mêmes messages, comportement idempotent identique).

**`creer_projet()`** (issues #98/#99, complété par #257) : dépôt GitHub
(`gh repo create` si absent, public par défaut — issue #528) ; génère
`configs/<nom>.conf` depuis un gabarit interne ; crée les labels GitHub
requis (idempotent) ; crée `CONTEXTE.md` vide dans le répertoire de travail ;
si ce répertoire n'est pas encore un dépôt git, `git init` + `git remote add
origin` en **HTTPS** (jamais SSH) + commit initial, avec **push automatique**
**seulement si le répertoire était réellement vide** avant cette étape
(détection par ce que `git add -A` indexe réellement, pas un inventaire brut
du disque — issues #258/#260, pour ne pas confondre un `venv/` gitignoré
préexistant avec du contenu à relire avant push) ; enfin régénère
`BRIDGE_AGENT_DOC.md` (§2/§7, date en bas).

**Casse des valeurs par défaut dépôt/répertoire (issue #738)** : le NOM
interne (clé, nom du `.conf`, labels) reste toujours calculé en minuscules.
Mais `depot_defaut()`/`rep_defaut()` reçoivent désormais le nom **tel que
saisi**, pas sa version mise en minuscules, et `casse_proposee()` décide la
forme à proposer : un nom contenant au moins une majuscule interne
(`AnnuaireToken`, `ChessCoach`) est repris tel quel ; un nom entièrement en
minuscules garde le comportement historique (première lettre capitalisée :
`rummikub` → `Rummikub`). Avant #738, la casse saisie était perdue en trois
endroits avant même d'atteindre ces fonctions : `creer_projet()`,
l'assistant CLI (`etape_nom()`), et la route `verifier_nouveau_projet()`
(`app/nouveau_projet.py`) mettaient tous le nom en minuscules en entrée — et
côté JavaScript, `npVerifier()` (`static/js/app.js`) faisait de même avant
l'appel réseau. Les valeurs proposées restent modifiables à la main, comme
avant. `rep_casse_differente()` ajoute un avertissement non bloquant : si le
répertoire proposé n'existe pas encore mais qu'un dossier de même nom à
casse différente existe déjà dans le même dossier parent (Linux distingue
les majuscules, contrairement à Windows/macOS par défaut), la route
`/nouveau-projet/verifier` le signale (`rep_casse_differente` dans la
réponse JSON) et le modal l'affiche sous le champ répertoire — pour éviter
de créer un second dossier pointant sur un `.conf` différent de celui déjà
en place.

**`supprimer_projet()`** (issue #587, côté CCL/local uniquement — dépôt
GitHub, labels et côté CCW restent hors scope, traités par une issue dédiée)
démonte, dans l'ordre inverse de la création : répertoire de travail du
projet (dépôt git local inclus) ; `configs/<nom>.conf` ; régénération de
`BRIDGE_AGENT_DOC.md`. Mode `--dry-run`/aperçu disponible, sans toucher au
disque. Route web protégée par double confirmation (3 cases à cocher + nom
du projet retapé, revérifié côté serveur).

**Mise à jour de `BRIDGE_AGENT_DOC.md` — commit ET push automatiques (issue
#645)** : `regenerer_tableaux_projets.committer_pousser_doc()` committe et
pousse cette mise à jour dans le dépôt Bridge_Agent après une création ou une
suppression de projet, sans intervention manuelle — un push en échec (réseau,
conflit…) ne fait pas échouer la création/suppression, seule la doc reste à
repousser à la main.

**Garde-fou « aucun `.conf` trouvé » (issue #739)** : `regenerer()` refuse de
réécrire les tableaux §2/§7 si `configs/*.conf` ne fournit aucun projet
(dossier absent, vide, ou sans `.conf` valide) — document inchangé, erreur
renvoyée aux appelants. Protège notamment un worktree CCL isolé (`configs/`
gitignoré, donc vide hors du clone de travail principal) d'un appel qui
vidrait sinon les deux tableaux (vécu deux fois, issues #736/#737).

---

## 9. Bandeau d'expiration des jetons de l'annuaire (`app/jetons_annuaire.py`, issue #741)

Le projet séparé **annuairetoken** tient l'annuaire des jetons d'accès
d'Alain (métadonnées seulement, jamais de valeur de jeton) dans un fichier
`jetons.json`, hors de ce dépôt et hors git. Bridge_Agent le lit **en
lecture seule**, jamais ne l'écrit, pour prévenir avant qu'un jeton
n'expire — même principe que le bandeau « OAuth Token CCW » existant
(`app/eval_windows.py`), dont `etat_jetons_annuaire()` réutilise directement
les seuils/niveaux (`_niveau()`, `SEUIL_ORANGE`=14j, `SEUIL_ROUGE`=5j).

**Chemin du fichier** : par défaut `~/.config/annuairetoken/jetons.json`,
surchargeable par la variable d'environnement `BRIDGE_JETONS_CHEMIN` —
réglage **global à Bridge_Agent, pas par projet**. Aucun mécanisme de
réglage global (hors `configs/*.conf`, par projet et interdit en écriture à
CCL/CCW) n'existe à ce jour dans ce dépôt pour ce genre de valeur ; une
variable d'environnement a donc été choisie faute d'alternative.

**Format lu (version 1)** : objet JSON `{"version": int, "jetons": [...]}`.
Chaque entrée de `jetons` : `id`, `service` (requis, sinon entrée ignorée),
`statut` (`actif`/`abandonné`/`expiré`, sinon ignorée), `expiration`
(`AAAA-MM-JJ` ou `""` = n'expire jamais ; mal formée → ignorée). `projets`,
`depots`, `creation`, `note` sont lus par le format mais **pas utilisés** par
le bandeau (pas de valeur par défaut nécessaire côté Bridge_Agent). Le
format n'évolue que par ajout de clés : toute clé inconnue est ignorée sans
erreur.

**Robustesse** (jamais de plantage de l'interface) :
- fichier absent → aucune alerte, silencieusement (`None`) ;
- fichier illisible (JSON invalide, ou clés `version`/`jetons` absentes) →
  message neutre « jetons.json illisible, bandeau désactivé » (niveau
  `gris`, nouvelle variante CSS de `.bandeau-eval-windows`), détail (chemin
  + exception) journalisé via `logging.getLogger(__name__).warning(...)` ;
- entrée individuelle invalide (statut inconnu, date mal formée, id/service
  manquant) → ignorée, mais comptée et affichée (« N entrée(s) ignorée(s)
  dans jetons.json ») pour qu'un jeton ne disparaisse jamais en silence ;
- statut `abandonné`/`expiré`, ou `expiration` vide → jamais d'alerte,
  jamais compté comme ignoré (entrée valide, juste sans rien à afficher) ;
- jeton `actif` dont la date est dépassée → niveau `rouge` automatiquement
  (jours restants négatifs ≤ `SEUIL_ROUGE`), message « expiré depuis N j » ;
  jours restants = 0 → « expire aujourd'hui ».

**Frontend** : `app/vues.py::index()` passe `jetons_annuaire=
etat_jetons_annuaire()` au gabarit ; `templates/fragments/bandeaux.html`
l'affiche dans un second bandeau, juste sous celui de l'éval Windows,
réutilisant la même classe CSS (`static/css/base.css`).

**Tri et plafond d'affichage** (issue #742) : les jetons en alerte sont
triés par urgence — `jours_restants` croissant (les jetons déjà expirés,
jours négatifs, en premier, le plus en retard d'abord), égalité départagée
par `id` pour un affichage stable. L'affichage est plafonné à
`MAX_LIGNES_JETONS` (= 3, constante en tête du module) lignes de jetons ;
au-delà, les lignes suivantes sont remplacées par une seule ligne de
synthèse (« ⚠️ + N autre(s) jeton(s) à renouveler — voir l'annuaire »,
accord singulier/pluriel selon N). Le niveau du bandeau (`rouge`/`orange`)
reste calculé sur TOUS les jetons en alerte, avant troncature, jamais
seulement sur les lignes visibles — bien que le tri par urgence garantisse
déjà qu'un jeton masqué ne peut jamais être plus grave qu'un jeton visible.
La ligne « N entrée(s) ignorée(s) dans jetons.json » reste distincte :
toujours en dernier, hors de ce plafond, logique de niveau inchangée.

**Tests** : `tests/test_bandeau_jetons_annuaire_741.py`, fichiers factices
(`JETON_FACTICE_*`) dans des dossiers `/tmp` jetables via
`BRIDGE_JETONS_CHEMIN`, jamais sur le vrai fichier d'Alain. Sans réseau.
Couvre aussi le tri (désordre, jetons expirés d'abord, égalité par id) et
le plafond à 3 lignes (exactement 3, 4, 20 jetons ; niveau rouge même si le
jeton critique est masqué ; ligne des entrées ignorées toujours en dernier).

---

*Document technique interne — voir `BRIDGE_AGENT_DOC.md` pour l'usage du bridge.*
