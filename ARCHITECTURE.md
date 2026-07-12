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
│   │                       détection PID) + routes de l'onglet « Watchers ».
│   ├── journal.py          Route SSE : streame le fichier de log d'un watcher en
│   │                       temps réel (tail + suivi + détection de rotation).
│   ├── cycle_vie.py        Cycle de vie serveur ↔ onglet : heartbeat, SSE /events
│   │                       (shutdown), route /quitter, thread surveiller_heartbeat.
│   ├── tunnel.py           Tunnel cloudflared (mode --externe) : démarrage/arrêt
│   │                       automatique de « cloudflared tunnel run bridge-agent ».
│   └── vues.py             Vue générale : route index() qui rend le gabarit
│                           principal de l'interface.
│
├── templates/
│   └── index.html          Gabarit principal (interface, onglets).
├── static/
│   ├── css/style.css       Feuille de style de l'interface.
│   └── js/app.js           Logique front (onglets, appels fetch, flux SSE).
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

*Document technique interne — voir `BRIDGE_AGENT_DOC.md` pour l'usage du bridge.*
