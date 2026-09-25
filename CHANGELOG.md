# CHANGELOG — bridge_agent

Historique complet des évolutions du projet, une section par issue, la
plus récente en premier. Auparavant maintenu comme un unique paragraphe
en pied de page de `BRIDGE_AGENT_DOC.md` ; extrait ici tel quel (issue
#252) car ce paragraphe avait fini par peser plusieurs dizaines de
milliers de caractères sur une seule ligne logique, coûteux à relire et
à réécrire, et sans garde-fou contre une perte silencieuse de contenu.

Convention d'ajout : voir §10 de `BRIDGE_AGENT_DOC.md`.

## 25 septembre 2026 — issue #625

Refonte de l'interface web, **étape 1/n : socle**. Architecture retenue par
Alain : modules JavaScript natifs (`<script type="module">`), **sans étape de
build**, briques partagées + modules par fonctionnalité (à venir). Cette étape
pose les fondations pour que les étapes suivantes tournent **en parallèle** dans
des worktrees distincts. **Contrainte absolue tenue : aucun changement visible
pour l'utilisateur** — corps de `index.html` vérifié byte-identique après rendu
Flask (hors entête/scripts), CSS reconcaténé byte-identique à l'ancien
`style.css`.

### 1. Briques partagées — `static/js/socle/`

Nouveau sous-dossier de modules ES, **inertes à cette étape** (chargés, testés,
mais ne remplacent rien) :

- `store.js` — source de vérité unique : tranches issues (indexées par
  `projet#numero`), sélection, filtres, projets, watchers, issues_inbox, son,
  rate-limit ; `get`/`set`/`maj`/`abonner`/`abonnerCle` + aides issues.
  `creerStore()` fabrique générique testable.
- `api.js` — accès unique aux routes Flask, vérifie **systématiquement**
  `response.ok`, lève `ErreurApi` et remonte via toasts (plus d'erreur avalée).
- `sse.js` — canaux `/stream` et `/events` centralisés, **NON connectés** (pas de
  double connexion tant que l'ancien code gère les siennes).
- `toasts.js` — notifications non bloquantes (jamais de « OK » à cliquer) + LA
  seule modale, réservée aux confirmations destructives. Styles auto-injectés.
- `dom.js` — utilitaires (`$`, `$$`, `creerElement`, `echapperHtml`) + registre
  de délégation d'événements (`surAction`) destiné à remplacer les handlers
  inline.
- `persistance.js` — localStorage restreint aux préférences d'interface.
- `index.js` — point d'entrée module ; `pont.js` — mécanisme de transition.

### 2. Coexistence avec l'ancien code

`app.js` reste chargé comme **script CLASSIQUE** (ses ~233 fonctions restent
globales pour les >70 gestionnaires inline). Le module d'entrée est chargé **à
côté** (différé ⇒ après app.js). `pont.js` est l'unique point de contact
(`window.Bridge` pour ancien→socle, `appelerAncien()` pour socle→ancien), conçu
pour être **retiré entièrement à la dernière étape**. Ordre de chargement
préservé (variables Jinja disponibles pour les deux mondes).

### 3. Découpage des fichiers

- `templates/index.html` → squelette + `templates/fragments/` (un fragment par
  onglet, panneau latéral, bandeaux, entête, chaque modale, scripts).
- `static/css/style.css` → 6 feuilles par zone (`base`, `composants`,
  `resultats`, `modales`, `recherche-interruption`, `inbox`), chargées dans
  l'ordre qui **préserve exactement la cascade** (reconcaténation byte-identique
  vérifiée). `app.js` reste d'un seul tenant (vidé par les étapes suivantes).

### 4. Fichiers servis (cache-busting)

Nouveau `app/statique.py` : `url_statique()` (ajoute `?v=<mtime>` aux CSS/JS) et
`importmap_socle()` (import map versionnant les imports relatifs entre modules ES,
sans build). Vérifié : modules servis en `text/javascript` et CSS en `text/css`,
statut 200, en local / `--lan` / `--externe`, **y compris session expirée** (les
statiques ne sont pas derrière `login_requis`).

### 5. Filet de sécurité

- Tests de logique pure avec le module intégré de Node (`node:test`, aucune
  dépendance) : `store`, `persistance`, `dom` — **20 tests, tous verts**.
  Lancement : `node --test static/js/socle/tests/` (cf. README des tests).
- `VERIFICATIONS_MANUELLES.md` (racine) : liste de non-régression à rejouer par
  Alain après chaque étape (tous onglets, panneau latéral, modes `--lan`/externe).

### 6. Documentation

- `ARCHITECTURE.md` §6 : carte de migration complète (arborescence, rôle de
  chaque brique, mécanisme de transition, correspondance zones↔fichiers,
  versionnage, procédure type pour sortir une fonctionnalité de l'ancien code).
- `CONTEXTE.md` mis à jour et ramené sous le plafond de 4000 caractères.

Fichiers : +`static/js/socle/*` (8 modules + package.json), +`static/js/socle/tests/*`,
+`templates/fragments/*` (18 fragments), +`static/css/{base,composants,resultats,
modales,recherche-interruption,inbox}.css`, +`app/statique.py`,
+`VERIFICATIONS_MANUELLES.md` ; ~`templates/index.html`, ~`app/__init__.py`,
~`ARCHITECTURE.md`, ~`CONTEXTE.md` ; −`static/css/style.css` (découpé).

## 25 septembre 2026 — issue #624

Remplace #623 (fermée après 3 dépassements de TIMEOUT, conception laissée
ouverte). Corrige la régression diagnostiquée en #621 : depuis #614,
`_projets_dans_la_portee()` (`app/notifications_poller.py`) filtrait les
projets interrogés par `gh` sur le champ `LABEL` de leur `.conf` — un
**défaut** de projet, pas la vérité, puisque c'est le label `for-windows`/
`for-linux` posé sur **chaque issue** (exclusifs, §16) qui dit si elle
concerne CCW. Aucun `.conf` CCL ne portant `LABEL=for-windows`, le poller
n'interrogeait plus aucun projet et ne détectait plus aucune transition
d'issue CCW sur le ThinkPad — seul chemin de notification pour CCW, le
watcher Windows postant ses signaux SSE vers `localhost:5100`, sa propre
machine, jamais atteinte depuis le ThinkPad.

Le poller surveille désormais une **liste d'issues** (`depot`, `numéro`),
pas des projets : `app.notifications_poller._ISSUES_SURVEILLEES`, remplie
par un balayage unique de toutes les issues ouvertes `for-windows` sur tous
les projets configurés au démarrage de `new_issue.py`
(`_balayage_initial()`), et tenue à jour en direct à chaque création ou
relance d'une telle issue depuis le ThinkPad — formulaire web
(`app.issues.envoyer`), bouton « Relancer » de l'onglet Résultats
(`app.interruption.route_relancer`), et `scripts/watcher_issues_inbox.py`
via la nouvelle route `POST /notifier-issue-a-surveiller` (ce dernier tourne
dans un process séparé, incapable de muter directement la liste du process
`new_issue.py`). Liste vide → aucun appel `gh` à ce cycle (cas courant, CCW
n'étant utilisé qu'une ou deux fois par semaine).

À chaque cycle, pour chaque issue de la liste : détection de la prise en
charge (commentaire ACK), en réutilisant `app.issues._debut_traitement`/
`_commentaires_issue` (logique de `/issues-en-attente`) plutôt que de la
dupliquer, avec poussée d'un événement SSE `debut_issue` sur `/stream` ;
détection des transitions terminales (`done`/`needs-human`), notifiées comme
avant (bip/bulle/ntfy selon les labels `notif_*`) plus, désormais, un
événement SSE `fin_issue` sur `/stream` — décorrélé des labels `notif_*`,
comme `watcher.py::notifier_fin_sse` pour CCL. Une issue est retirée de la
liste dès sa transition terminale ; une relance réussie l'y réinjecte.
Garde-fous conservés : anti-spam au démarrage (aucune notification pour une
ACK/transition déjà présente à l'amorçage), filtre de récence, lecture des
labels `notif_*` courants au moment de la détection.

Limite documentée, non traitée : une issue `for-windows` créée directement
sur GitHub ou par un chef n'est ajoutée à la liste surveillée qu'au prochain
démarrage de `new_issue.py` (rattrapée par `_balayage_initial()`).

Tests (`tests/test_poller_issues_ccw_624.py`) : remplissage de la liste
(balayage initial multi-projets, ajout direct filtré par
`BRIDGE_NOTIF_SCOPE`), retrait après transition terminale (avec/sans
amorçage, filtre de récence), détection de l'ACK réutilisant réellement
`_debut_traitement`, et liste vide → aucun appel `gh`. Aucun appel `gh` réel
dans ces tests : `_gh_list`/`_gh_view_issue`/`_commentaires_issue` sont
monkeypatchés.

Doc : BRIDGE_AGENT_DOC.md §17 (poller), §17.1 (mécanisme SSE désormais
décorrélé des labels `notif_*` côté CCW aussi), §17.2 (correction de la
période de polling indiquée — 20 s dans la doc, 60 s dans le code depuis
#188), §17.3 (nouvelle route `/notifier-issue-a-surveiller`).

Fichiers modifiés : `app/notifications_poller.py` (remplacement du
balayage par projet par la liste surveillée, nouvelle route Flask),
`app/__init__.py` (enregistrement de la route), `app/issues.py`
(`numero_depuis_url`, hook dans `envoyer()`), `app/interruption.py` (hook
dans `route_relancer()`), `scripts/watcher_issues_inbox.py` (hooks dans
`_traiter_bloc`/`_traiter_relance`, POST best-effort vers la nouvelle
route), `tests/test_poller_issues_ccw_624.py` (nouveau),
`BRIDGE_AGENT_DOC.md`.

## 25 septembre 2026 — issue #620

Diagnostic #579 (bas niveau, point 2) : `nouveau_projet.py` (~1450 lignes)
mélangeait plusieurs responsabilités ; la plus clairement séparable — la
science des couleurs (~410 lignes, algorithmes WCAG/Lab, génération de
palette, `couleur_affichee`, `couleur_hash_projet`) — était en outre
autonome, sans dépendance vers le reste du fichier.

Extraite telle quelle vers un nouveau module `palette.py` à la racine du
dépôt : constantes (`SATURATION_PALETTE`, `COULEURS_PROJETS_EXISTANTS`,
`PALETTE_COULEURS`, `PROJETS_COULEUR_RECYCLEE`, etc.), fonctions privées
(`_hsl_vers_hex`, `_linearise_srgb`, `_luminance_relative`,
`_contraste_avec_noir`, `_plancher_contraste_teinte`, `_plancher_effectif`,
`_lab_depuis_hsl`, `_distance_lab`, `_teinte_lab`, `_ecart_teinte`,
`_lab_depuis_hex`) et fonctions publiques (`generer_palette`,
`couleur_hash_projet`, `couleur_affichee`). `nouveau_projet.py` importe
désormais `COULEURS_PROJETS_EXISTANTS`/`PALETTE_COULEURS` depuis `palette` ;
`couleurs_utilisees()`/`couleurs_disponibles()`, qui combinent ces couleurs
avec la lecture de `configs/*.conf`, restent inchangées sur place.

Bénéfice concret : `regenerer_tableaux_projets.py` faisait un import local
différé de `nouveau_projet` pour accéder à `couleur_affichee` — un
`from nouveau_projet import couleur_affichee` en tête de fichier créait un
cycle (ce module importe déjà `regenerer_tableaux_projets` à son chargement,
issue #571/#608). Avec `palette.py`, sans dépendance vers `nouveau_projet`,
l'import se fait désormais proprement en tête de fichier
(`from palette import couleur_affichee`).

`app/nouveau_projet.py` (accès à `couleurs_disponibles`) continue de
fonctionner sans modification, ces fonctions restant dans `nouveau_projet.py`.
Vérifié : `py_compile` sur les trois fichiers, suite de tests existante
(pytest + scripts autonomes) toujours verte, `create_app()` toujours
fonctionnel, et test manuel de `lire_projets()` sur un dossier `.conf`
temporaire (couleur gelée, couleur recyclée grisée, couleur `.conf`
persistée — les trois niveaux de priorité de `couleur_affichee`).

## 25 septembre 2026 — issue #620

Extraction de la science des couleurs des projets (issue #620, suite diagnostic #579 point 2) : les ~410 lignes autonomes de `nouveau_projet.py` (constantes `SATURATION_PALETTE`/`SEUIL_CONTRASTE_NOIR`/`COULEURS_PROJETS_EXISTANTS`/etc., fonctions privées `_hsl_vers_hex`/`_lab_depuis_hsl`/`_distance_lab`/`_teinte_lab`/etc. et publiques `generer_palette`/`couleur_hash_projet`/`couleur_affichee`) déménagent dans un nouveau module `palette.py` à la racine du dépôt, sans dépendance vers le reste de `nouveau_projet.py`. `nouveau_projet.py` importe désormais `COULEURS_PROJETS_EXISTANTS`/`PALETTE_COULEURS` depuis `palette.py` (comportement de `couleurs_utilisees()`/`couleurs_disponibles()` inchangé, vérifié bit-à-bit identique à l'ancien code). `regenerer_tableaux_projets.py` importe `couleur_affichee` directement en tête de fichier depuis `palette.py` — l'ancien import local différé (`import nouveau_projet` à l'intérieur de `lire_projets()`) n'existait que pour éviter un cycle avec `nouveau_projet.py` (qui importe `regenerer_tableaux_projets`, issue #571) ; `palette.py` n'a aucune dépendance vers `nouveau_projet.py`, le cycle disparaît donc avec l'extraction. `app/nouveau_projet.py` (accès à `couleurs_disponibles()`) continue de fonctionner sans modification.

## 25 septembre 2026 — issue #619

Diagnostic #579 (bas niveau, point 2) : `_traiter_issue_synchrone` (watcher.py)
faisait ~610 lignes et empilait séquentiellement plusieurs responsabilités
distinctes (guards, bootstrap CCW, résolution de périmètre, verrou, lecture
active, boucle de tentatives, succès/échec, nettoyage) — correcte mais
difficile à naviguer. Découpée en 12 sous-fonctions privées nommées d'après
les blocs commentés déjà présents, comportement strictement identique :

- `_guards_precoces_et_bootstrap` — déjà en cours / déjà en échec définitif /
  déjà traitée / bootstrap CCW (issue #556).
- `_deduire_mode_et_logguer` — priorité/critique/timeout/modèle/mode +
  avertissements de log associés.
- `_resoudre_contexte_execution` (+ dataclass `ContexteExecution`) —
  périmètre effectif (worktree isolé #337, REPO_CIBLE #125, SOUS_DOSSIER
  #550), avec repli sur `CFG.perimetre`/`CFG.rep_travail`.
- `_acquerir_verrou_pour_issue` — verrou anti-collision inter-process (#189).
- `_preparer_lecture_active` — dossier scratch + empreinte REP_TRAVAIL (#327).
- `_demarrer_traitement` — détection RELANCE, ACK, chrono, pre-flight token,
  empreinte configs/*.conf.
- `_executer_une_tentative` — appel `lancer_claude` + garde-fou de format
  (#581) + restauration configs modifiés.
- `_verifier_violation_scratch` — garde-fou niveau 2 lecture active (#327).
- `_finaliser_succes` — commentaire de résultat, fermeture, historique des
  durées, calibration TIMEOUT (#221/#222), notification.
- `_tracer_tentative_expiree` — trace timeout dans l'historique des durées
  (#220) + calibration backoff.
- `_gerer_abandon_max_essais` — retry infini si critique, sinon diagnostic +
  needs-human + notification.
- `_nettoyer_apres_traitement` — libération verrou, nettoyage scratch, log
  fin de worktree (bloc `finally`).

`_traiter_issue_synchrone` devient un orchestrateur de 93 lignes qui
enchaîne ces appels avec les mêmes retours anticipés qu'avant. Point
d'attention préservé : `_preparer_lecture_active` retourne `chemin_scratch`
même en cas d'abandon (échec du `mkdir` après résolution du chemin), pour
que le nettoyage dans `finally` reste identique au comportement historique.

Vérification : suite de tests existante (21 fichiers) verte sans
modification, `py_compile` OK, plus 3 scénarios manuels bout-en-bout
(succès dry-run, abandon après max_essais, guard needs-human) exerçant
l'orchestration réelle en mockant les I/O réseau — aucune régression
observée. Pas de lancement d'issue réelle CCL de bout en bout dans cette
tâche (limitation d'environnement, aucun accès à une vraie issue GitHub
depuis ce worktree) ; les scénarios manuels ci-dessus couvrent le même
enchaînement de fonctions.

## 25 septembre 2026 — issue #618

Diagnostic #579 (bas niveau, point 2) : extraction de `TEMPLATE_LOGIN`
(`app/auth.py`) vers `templates/login.html`, sans changement fonctionnel.

- La chaîne Python `TEMPLATE_LOGIN` (~42 lignes HTML+CSS+Jinja inline)
  est déplacée telle quelle vers `templates/login.html`, cohérent avec
  `templates/index.html` (déjà un fichier Jinja séparé).
- `app/auth.py` : les trois appels `render_template_string(TEMPLATE_LOGIN,
  ...)` (`login()`, `login_post()` ×2) remplacés par
  `render_template("login.html", ...)`. Import Flask allégé
  (`render_template_string` → `render_template`). Constante
  `TEMPLATE_LOGIN` et docstring module mis à jour en conséquence.
- Vérification : `py_compile` OK, suite de tests existante verte
  (14 passed), rendu réel testé via `app.test_client()` — page login
  affichée (200, contenu attendu), variables Jinja `erreur` et `bloque`
  bien transmises (message d'erreur, `disabled` sur input/bouton).

## 25 septembre 2026 — issue #617

Diagnostic #579 (bas niveau, points 1/2/3.4) : trois petites duplications
niveau 3 éliminées, sans changement fonctionnel visé.

- **`_ecrire_json_atomique` dupliquée** (`watcher.py` et
  `scripts/archiver_historique.py`, même logique fichier temp +
  `os.replace`) : extraite vers `scripts/utils.py::ecrire_json_atomique`,
  nouveau module bas niveau partagé. `watcher.py` (déjà `sys.path.insert`
  sur `scripts/` pour `traitement_fin`) l'importe sous l'alias
  `_ecrire_json_atomique` pour ne rien changer aux appelants internes ;
  `scripts/archiver_historique.py` fait de même. Un seul exemplaire du
  code, deux points d'entrée inchangés.
- **`os.system(aplay)` → `subprocess.run`** (`scripts/traitement_fin.py`,
  fonctions `bip_plat()` et `bip()`, ~l.91 et ~l.113) : les deux appels
  `os.system(f'aplay {tmp} 2>/dev/null')` remplacés par
  `subprocess.run(["aplay", tmp], capture_output=True)` — même résultat
  (échec silencieux, pas d'exception si `aplay` absent ou en erreur), sans
  passer par un shell, cohérent avec `scripts/bip_Cloche.py`.
- **Sonde PID inline** (`app/watchers.py::watcher_actif()`) : le
  `os.kill(pid, 0)` inline remplacé par un appel à `watcher._pid_vivant`
  (déjà importé sans cycle — `app/watchers.py` importait déjà `Config` et
  `taches_en_cours` depuis `watcher`), fonction cross-plateforme
  POSIX/Windows (issue #584) plutôt qu'un troisième exemplaire de sonde de
  process. Note : `_pid_vivant` traite `PermissionError` comme « vivant »
  par prudence (asymétrie volontaire documentée dans `watcher.py`, contre
  un faux négatif en cas de PID recyclé), alors que l'ancien code local le
  traitait comme « inactif » — différence mineure, cohérente avec l'usage
  qu'en fait déjà `watcher.py` pour ses propres verrous.

Vérification : `py_compile` OK sur les 5 fichiers touchés/ajoutés, import
réel de `watcher`, `app.watchers` et `scripts/archiver_historique.py`
testé (pas seulement compilation syntaxique), les 21 scripts de `tests/`
passent (code de sortie 0), et un test manuel de `bip_plat()`/`bip()` via
`subprocess.run` confirme que le son de fin d'issue continue de fonctionner.

## 25 septembre 2026 — issue #616

Depuis le passage au PC fixe physique (issue #446, août 2026), le §16 de
`BRIDGE_AGENT_DOC.md` (Agent Windows CCW) accumulait de nombreux blocs
marqués explicitement « obsolète — conservé à titre historique » décrivant
l'ancienne architecture VM VirtualBox (éval 90 jours, `VBoxManage`,
`creer_vm_ccw.py`, `autounattend.xml`, `lancer_provisioning.py`,
`demarrer_ccw.sh`, `eval-expiration.json`, `verifier_expiration_ccw.py`,
partage réseau `\\VBoxSvr\CCW_Share`) : dette documentaire payée en tokens
à chaque conversation Claude Chat chargeant la doc, et source de confusion
entre l'état révolu et l'état courant. Décision actée (issue) : supprimer
ces blocs, pas les extraire vers un fichier historique séparé.

- Tableau des scripts de provisioning (§16) : suppression des 6 lignes
  purement obsolètes (`creer_vm_ccw.py`, `autounattend.xml`,
  `lancer_provisioning.py`, `demarrer_ccw.sh`, `eval-expiration.json`,
  `verifier_expiration_ccw.py`) ; retrait des mentions « (dans la VM… )»
  sur les 6 scripts encore actifs (`mettre_a_jour_tokens_ccw.ps1`,
  `ajouter_projet_ccw.ps1`, `lister_projets_ccw.ps1`,
  `finaliser_projet_ccw_auto.ps1`, `finaliser_projet_ccw.ps1`,
  `surveiller_builds.ps1`) ; `provisionner.ps1` conservé comme référence
  des étapes d'installation logicielle, description nettoyée des mentions
  VM.
- Bloc « Lancer le provisioning (obsolète — via VM) » et son extrait bash
  (`lancer_provisioning.py`) supprimés.
- Sous-section entière **§16.1 Maintenance périodique (renouvellement à
  90 jours)** supprimée (recréation de VM, `eval-expiration.json`,
  `VBoxManage storageattach`, ré-attachement d'ISO) — le renouvellement des
  tokens GitHub/Claude, seule partie encore valide, était déjà documenté
  plus haut dans le §16 (script `mettre_a_jour_tokens_ccw.ps1`). Le renvoi
  `cf. §16.1` restant dans la description du token par projet a été retiré.
  La numérotation des sous-sections n'a pas été renumérotée (le §16 passe
  directement de son intro à 16.2, comme le document passe déjà du §14 au
  §16 sans §15).
- §16.3 : callout « Étape 0 et note safe.directory obsolètes » + bloc bash
  associé supprimés, ainsi que les deux notes historiques (safe.directory,
  staging local) mentionnant l'ancien partage VirtualBox ; reformulation
  mineure de la note « Récupération des artefacts » et de la note
  « staging local » pour retirer les mentions VirtualBox devenues sans
  objet.
- §16.4 (bouton « Interrompre ») : reformulation du callout et du
  paragraphe technique pour retirer les deux mentions `VBoxManage
  guestcontrol` (remplacées par « ancien mécanisme de pilotage à distance
  de la VM » / « à distance »), sans supprimer la documentation du
  fonctionnement actuel du bouton (`app/interruption.py::
  interrompre_windows`, toujours inopérant sur PC physique — pas de
  changement de code dans le cadre de cette tâche, doc uniquement).
- Renvoi orphelin « Specs MVC §15 » (§12) corrigé en « Specs MVC » (le §15
  n'existe plus dans le document).
- Conservé tel quel : l'encart « ⚠️ Changement de plateforme (depuis août
  2026, issue #446) » en tête du §16, qui explique en quelques lignes le
  passage VM → PC fixe — seul contexte minimal encore utile pour comprendre
  d'anciens commits mentionnant une VM.

Vérification : plus aucune mention de VirtualBox/VBoxManage/
`creer_vm_ccw.py`/`autounattend.xml`/`lancer_provisioning.py`/
`demarrer_ccw.sh`/`eval-expiration.json`/`verifier_expiration_ccw.py` dans
le §16 en dehors de l'encart « Changement de plateforme » conservé
volontairement (et d'une brève justification historique déjà concise sur
le compte NSSM `AlainW`, hors périmètre de nettoyage de l'issue). Fences
markdown et séquence des titres `###` du §16 vérifiées cohérentes après
coup. `py_compile` sans objet (fichier `.md`).

## 25 septembre 2026 — issue #615

Le widget `/rate-limit` (#607) n'était rafraîchi que par le polling JS à
intervalle fixe (30s) — une rafale de consommation gh entre deux polls
pouvait épuiser le quota sans que le widget le reflète, et aucun log ne
permettait de corréler une consommation anormale avec sa source.

Piste initiale (capturer les headers HTTP `x-ratelimit-*` de chaque appel
`gh` existant via `--include`) écartée après vérification : les
sous-commandes utilisées dans ce projet (`gh issue list/view/create/
close/edit/comment`) n'exposent pas `--include`/`-i` — seule `gh api`
l'a (gh 2.45.0). Réécrire tous ces appels en `gh api` équivalents aurait
été disproportionné pour ce ticket. Repli explicitement permis par
l'issue retenu à la place :

- **`etat_rate_limit.py`** (nouveau) : état partagé du quota GraphQL,
  persisté dans `logs/etat_rate_limit.json` (écriture atomique + verrou
  anti-collision, même pattern que `etat_timeout.json`/`etat_ambiance.json`,
  issue #221) puisque `watcher.py` tourne dans un process séparé de
  l'app Flask qui sert `/rate-limit`. `maj_rate_limit(origine)` appelle
  `gh api rate_limit` (n'entame NI le quota `core` NI le quota `graphql`,
  issue #263) et journalise la mise à jour en DEBUG avec l'`origine`
  (module.fonction appelant) — permet de corréler une consommation
  anormale avec sa source lors d'un futur épisode. `lire_rate_limit()`
  lit l'état sans jamais lever d'exception (fichier absent/corrompu →
  `None`).
- **`watcher.py`** : `fermer_issue()` appelle `maj_rate_limit("watcher.
  fermer_issue")` juste après la fermeture effective de l'issue —
  rafraîchit le quota dans les secondes qui suivent l'appel gh
  significatif, sans attendre le prochain polling du widget.
- **`app/issues.py`** : `maj_rate_limit()` appelé après création
  (`envoyer`), annulation (`annuler_issue`) et fermeture définitive
  (`fermer_issue`) d'une issue.
- **`app/notifications_poller.py`** : `maj_rate_limit()` appelé une
  seule fois par cycle complet de `surveiller_transitions()` (pas par
  projet) — ce poller vise justement à alléger la charge gh cumulée
  (#188, #614) ; un appel rate_limit par projet irait à rebours de cet
  objectif pour un gain de fraîcheur négligeable.
- **`app/rate_limit.py`** : la route `GET /rate-limit` sert d'abord
  l'état partagé s'il a moins de `SEUIL_FRAICHEUR_S` (20s, sous la
  cadence de polling JS de 30s) — potentiellement rafraîchi entretemps
  par un autre process (watcher.py). Sinon, retombe sur l'appel gh
  direct d'origine (issue #607), qui met lui-même à jour l'état partagé
  au passage. Contrat de la route inchangé (`{ok, used, limit,
  remaining, reset}`) : le widget JS (`static/js/app.js`) n'a pas eu à
  changer.

Vérification : `py_compile` sur tous les modules touchés + import de
`app.create_app()` et `etat_rate_limit` (résolution du `sys.path`
inséré par `app.projets`) ; suite de tests existante (`pytest tests/`,
14 passed) toujours verte.

## 25 septembre 2026 — issue #614

Réduit la consommation GraphQL du poller de notifications (`app/notifications_poller.py`) :
le filtre `_dans_la_portee()` (diagnostic #613) n'intervenait qu'**après** les
appels `gh issue list`, sur les transitions déjà récupérées — avec 14 projets
configurés, `surveiller_transitions()` interrogeait donc systématiquement les
14 projets à chaque cycle (2 appels gh chacun, 28/cycle) quel que soit
`BRIDGE_NOTIF_SCOPE`, alors que le défaut `for-windows` n'a besoin que des
projets CCW.

- **Nouvelle fonction `_projets_dans_la_portee()`** : filtre la liste retournée
  par `lister_projets()` **avant** la boucle principale de
  `surveiller_transitions()`, sur le champ `LABEL` du `.conf` de chaque projet
  (`cfg.label`) — `SCOPE=for-windows`/`for-linux` ne gardent que les projets au
  label correspondant, `SCOPE=all` garde tout (comportement inchangé),
  `SCOPE=off` reste court-circuité plus haut (aucun changement). Distincte de
  `_dans_la_portee()` (conservée telle quelle), qui filtre les *transitions*
  sur les labels de l'*issue* elle-même — sécurité complémentaire en aval, non
  redondante.
- **Log de chaque appel gh** : `_gh_list()` journalise désormais
  `gh issue list <dépôt> label=<label> state=<état>` avant chaque appel réseau
  (log de `new_issue.py`), pour permettre un diagnostic précis lors d'un futur
  épisode d'épuisement de quota GraphQL.
- **BRIDGE_AGENT_DOC.md §17** mis à jour : décrit le filtrage par SCOPE en
  amont des appels gh et la disponibilité du log par appel.
- Suite de tests existante toujours verte (14 passed).

## 25 septembre 2026 — issue #612

Corrige trois incohérences laissées par #609/#611 : docstring obsolète,
commentaire erroné sur l'incident `relecture_bridge` #73, extension du
mécanisme de report aux autres déclencheurs de redémarrage.

- **Docstring `repli_rep_travail` déjà simplifiée par #611** (vérifié) :
  ne décrit plus qu'un seul cas — le repli en tout dernier recours après
  échec des 3 tentatives de création de worktree (#589). Aucune trace
  résiduelle du « Cas 1 » (premier slot dans `REP_TRAVAIL`) supprimé par
  #611.
- **Commentaire erroné sur #73 corrigé** (`app/watchers.py` ×3,
  `static/js/app.js` ×2, `BRIDGE_AGENT_DOC.md` ×2) : attribuaient
  l'incident au repli #589 (« reprise sur un worktree déjà pris, repli
  silencieux sur REP_TRAVAIL »). Diagnostic confirmé le 24/09/2026 :
  `#73` tournait dans son worktree dédié avec `MAX_WRITE_PARALLELE=1` ;
  Alain a changé la valeur à 2 et relancé le watcher ; `systemctl --user
  restart` a tué tout le cgroup (dont le process CCL en cours) ; le
  watcher a repris `#73` comme premier slot et l'a lancée directement
  dans `REP_TRAVAIL` — l'ancien comportement du premier slot, supprimé
  depuis par #611. Aucune ligne « déjà pris » dans les logs. Les
  commentaires décrivent maintenant la vraie cause (kill systemd du
  cgroup au redémarrage), distincte du repli #589.
- **`BRIDGE_AGENT_DOC.md`** : paragraphe « Signal d'interface (issue
  #609) » mis à jour — il ne subsiste plus qu'un seul cas de repli
  (#589), plus deux cas à distinguer comme avant #611 ; le bandeau ne
  s'allume donc plus à chaque tâche `mode_write` normale.
- **Extension aux autres déclencheurs (vérification, point 3)** :
  - Bouton « Relancer » du panneau Infrastructure/onglet Watchers :
    déjà couvert — passe par la même route `/lancer-watcher` →
    `demarrer_watcher_ou_differer` que « Enregistrer et relancer »
    (`sidebarRelancerWatcherCCL`/`actionWatchers`, `static/js/app.js`).
    Aucun code à ajouter, documenté explicitement dans
    `BRIDGE_AGENT_DOC.md`.
  - Redémarrage systemd sur crash (`Restart=on-failure`) : NE PEUT PAS
    être intercepté côté Python (le process CCL est tué avant d'avoir la
    main). Limite documentée explicitement dans `BRIDGE_AGENT_DOC.md`
    (§16 et §"Redémarrage forcé différé"), pour ne pas laisser croire que
    #609/#611 couvrent ce cas.
- Suite de tests existante toujours verte (14 tests pytest + 19 scripts
  autonomes, tous OK).

## 25 septembre 2026 — issue #611

Corrige l'incohérence entre l'encart #577 de `BRIDGE_AGENT_DOC.md`
(« REP_TRAVAIL n'est plus jamais touché directement ») et le code réel
depuis #337 : à `MAX_WRITE_PARALLELE > 1`, le premier slot d'un lot
`mode_write` était délibérément dispatché dans `REP_TRAVAIL`
(`worktree=None`), sans isolation — un redémarrage du watcher pendant
ce premier slot tuait le processus CCL et laissait du travail inachevé
mélangé dans `REP_TRAVAIL` (`relecture_bridge` #73).

- **`watcher.py`** : le bloc `if not actifs:` de `traiter_issue` (premier
  slot direct sur `REP_TRAVAIL`) est supprimé — toute tâche `mode_write`,
  quel que soit son rang dans le lot, passe désormais par la création d'un
  worktree dédié. Nouvelle fonction `_creer_worktree_avec_retries(numero)` :
  enveloppe `_creer_worktree` avec jusqu'à 2 tentatives supplémentaires sous
  noms alternatifs (`-bis`, `-ter`, via le nouveau paramètre `suffixe` de
  `_chemin_worktree`/`_branche_worktree`/`_creer_worktree`) quand l'échec est
  attribuable à un chemin/branche déjà pris (reliquat non nettoyé, #589) —
  aucune retentative sur une erreur git générique, qu'un changement de nom
  ne résoudrait pas. Si les 3 tentatives échouent, nouvelle fonction
  `_signaler_repli_worktree_echoue(numero, raison)` : `notify-send` immédiat
  (`notifier_bureau`, urgence `critical`) + `log.warning` explicite avec le
  chemin, avant le repli en tout dernier recours sur `REP_TRAVAIL` (toujours
  en tâche de fond à `MAX_WRITE_PARALLELE > 1`, pour que la boucle
  principale reste libre). `_lancer_thread_ecriture` et
  `_traiter_issue_synchrone` transmettent `echec_worktree_deja_pris` dans ce
  cas aussi, pour que le compte-rendu de clôture (#589) mentionne le repli
  quel que soit le chemin qui y a mené.
- **`tests/test_worktree_parallelisation_337.py`** : nouveaux scénarios pour
  `_creer_worktree_avec_retries` (réussite via `-bis`, épuisement des 3
  tentatives, pas de retry sur erreur générique) et pour le repli signalé
  (`notify-send` capturé par un faux exécutable) à `MAX_WRITE_PARALLELE <= 1`
  et `> 1`. Scénario de parallélisation à 2 tâches mis à jour : les deux
  obtiennent désormais chacune un worktree dédié (plus aucune dans
  `REP_TRAVAIL`).
- **`BRIDGE_AGENT_DOC.md`** : encart et section détaillée réécrits pour
  décrire le comportement sans exception (worktree pour toute tâche
  `mode_write`) et la séquence de repli (tentatives `-bis`/`-ter` puis
  signalement actif en dernier recours).

Suite de tests existante (21 fichiers) toujours verte.

## 24 septembre 2026 — issue #609

Enregistrer la configuration d'un projet ne redémarre plus son watcher
pendant une tâche en cours — vécu sur `relecture_bridge` (issue #73) :
juste après le lancement d'une issue `mode_write`, une config enregistrée
via l'onglet Configuration (« Enregistrer et relancer ») a redémarré le
watcher en plein traitement ; au redémarrage, l'issue a été reprise, son
worktree dédié était « déjà pris » par la première tentative, repli sur
REP_TRAVAIL (#589), et le travail — non isolé — a été embarqué dans un
commit automatique d'un autre outil puis poussé par erreur.

**Point 1 (vérification du log) non traité** : `logs/watcher-relecture_bridge.log`
vit dans `/home/alain/Bridge_Agent/logs/` (dépôt principal), hors du
périmètre strict de ce worktree (`/home/alain/bridge_agent-issue609`).
Signalé plutôt que contourné.

- **`watcher.py`** : `acquerir_verrou()` prend désormais un paramètre `mode`,
  consigné dans le fichier de verrou (`logs/verrous/*.lock`, champ `mode=`,
  positionné avant `rep=` qui reste en dernier). Nouvelle fonction publique
  `taches_en_cours(nom_projet)` : scanne les verrous actifs (pid propriétaire
  vivant) et retourne les tâches en cours d'un projet — seul canal permettant
  à `new_issue.py` (process séparé du watcher) de savoir si un projet a une
  tâche en cours, `issues_en_cours` restant en mémoire du process watcher.
- **`app/watchers.py`** : `tache_en_cours(cfg)` (liste des tâches actives),
  `repli_rep_travail(cfg)` (une tâche `mode_write` tourne directement dans
  REP_TRAVAIL, hors worktree isolé — premier slot d'une parallélisation
  normale ET repli #589, même risque dans les deux cas, non distingués).
  `demarrer_watcher_ou_differer(cfg, forcer)` remplace `demarrer_watcher`
  comme point d'entrée de la route `/lancer-watcher` : un redémarrage forcé
  d'un watcher occupé n'est plus exécuté immédiatement (il couperait la
  tâche) — mémorisé dans `_redemarrages_differes`, exécuté automatiquement
  par le nouveau thread démon `surveiller_redemarrages_differes` dès la fin
  de la tâche (sondé toutes les `INTERVALLE_SURVEILLANCE_DIFFERE` = 15 s).
  `demarrer_watcher()`/`redemarrer_si_eteint()` (toujours `forcer=False`)
  restent inchangés — jamais concernés, un watcher avec une tâche en cours
  étant par construction déjà actif.
- **`new_issue.py`** : démarre `surveiller_redemarrages_differes` en thread
  démon, aux côtés de `surveiller_heartbeat`/`surveiller_transitions`.
- **Interface** : route `/watchers` expose `tache_en_cours`,
  `repli_rep_travail`, `redemarrage_differe` par projet. Onglet Watchers
  (`templates/index.html`, `static/js/app.js`) : nouvelle colonne « Statut »
  (⏳ tâche en cours / ⏳ redémarrage différé / ⚠️ REP_TRAVAIL en écriture).
  Bandeau global (même principe que le bandeau éval Windows #454), visible
  sur tous les onglets, listant les projets dont une tâche `mode_write`
  tourne actuellement dans REP_TRAVAIL. `sauvegarderConfig(relancer)` affiche
  « redémarrage différé, appliqué automatiquement à la fin de la tâche en
  cours » au lieu de « Watcher relancé » quand `/lancer-watcher` répond
  `differe: true`.
- **`BRIDGE_AGENT_DOC.md`** : nouveau point 4 dans « Cycle de vie des
  watchers » ; note ajoutée dans la section worktrees/repli #589.

Aucune régression sur les 5 appelants existants de `redemarrer_si_eteint`
(toujours `forcer=False`, jamais différés) ni sur `interrompre_linux`
(tue déjà tout l'arbre du watcher puis le laisse éteint — aucun redémarrage
forcé automatique à sa suite).

## 24 septembre 2026 — issue #608

Colonne « Couleur » ajoutée au tableau des projets actifs (§2 de
`BRIDGE_AGENT_DOC.md`) : `relecture_web` (projet `relecture_bridge`) n'a
accès qu'à ce tableau public — `configs/` est hors de son périmètre — et
voulait pouvoir afficher la couleur d'accent de chaque projet sans confondre
des noms proches (`bridge_agent`/`relecture_bridge`, `alchess`/`chesscoach`).

- **`nouveau_projet.py`** : nouvelle fonction `couleur_affichee(nom,
  couleur_conf)`, miroir Python de `couleurProjet()` (`static/js/app.js`) —
  réutilise `COULEURS_PROJETS_EXISTANTS`/`COULEUR_PROJET_INACTIF` existants
  plutôt que de dupliquer la règle de priorité. Ajout de
  `PROJETS_COULEUR_RECYCLEE` (ensemble miroir de `COULEURS_PROJET` côté JS
  pour `ecole`/`ff_galerie`, issue #540) et de `couleur_hash_projet()`
  (miroir de `couleurHashProjet()`, converti en hex via `_hsl_vers_hex`
  plutôt qu'en `hsl(...)`).
- **`regenerer_tableaux_projets.py`** : la colonne `Couleur` est ajoutée en
  **dernière position** du tableau `TABLEAU_PROJETS_ACTIFS` (pour ne décaler
  aucune colonne existante — vérifié qu'aucun autre lecteur du dépôt ne parse
  ce tableau par position). `lire_projets()` importe `nouveau_projet`
  localement (pas en tête de fichier) pour éviter un cycle d'import avec
  `nouveau_projet.py`, qui importe déjà `regenerer_tableaux_projets` à son
  chargement (issue #571) — testé dans les deux ordres d'import.
- **`BRIDGE_AGENT_DOC.md`** : §2 et « Couleur d'accent des projets » mis à
  jour pour documenter la nouvelle colonne et le cas des projets à couleur
  recyclée. Le tableau généré lui-même n'a **pas** été régénéré dans ce
  worktree isolé : `configs/*.conf` (gitignoré) n'y est pas présent — à
  lancer par Alain (`python3 regenerer_tableaux_projets.py`) après fusion,
  sur un checkout ayant accès aux vrais `.conf`.

## 24 septembre 2026 — issue #607

Indicateur compact du rate limit GitHub GraphQL dans le bandeau
supérieur de `new_issue.py`, toujours visible quel que soit l'onglet
actif (entre le titre « Bridge Agent » et le compteur « N projet(s)
disponible(s) ») — répond au cas concret du 24/09 (13 watchers
démarrés simultanément) où l'onglet Résultats affichait « Aucune
issue à afficher » sans explication pendant que le quota était épuisé.

- **`app/rate_limit.py`** (nouveau) : route `GET /rate-limit`, exécute
  `gh api rate_limit --jq '.resources.graphql'` côté serveur et
  renvoie `{ok, used, limit, remaining, reset}` — ou `{ok: false,
  erreur}` en cas d'échec (gh absent, timeout, rate limit REST atteint)
  sans jamais lever d'erreur HTTP. Cet appel ne consomme NI le quota
  `core` NI le quota `graphql` (vérifié empiriquement, issue #263,
  `scripts/mesurer_api.py`) : son polling ne peut donc pas lui-même
  épuiser le quota qu'il surveille.
- **`app/__init__.py`** : enregistrement de la route (`login_requis`,
  comme `/watchers`/`/statut`).
- **`templates/index.html`** : `<span id="rate-limit-widget">` inséré
  entre `<h1>` et `.statut`.
- **`static/js/app.js`** : `rafraichirRateLimit()`, polling global
  indépendant de l'onglet actif (`setInterval`, 30s — même cadence que
  le monitoring infrastructure de la sidebar Résultats), format
  `⚡ 132 / 5000 · reset 20:15` (heure de reset convertie en local côté
  navigateur via `toLocaleTimeString`). État dégradé `⚡ ? / 5000` en
  gris si l'appel échoue, sans faire disparaître le widget.
- **`static/css/style.css`** : classes `.rate-limit` + `.rl-vert` /
  `.rl-orange` / `.rl-rouge` / `.rl-gris` (mêmes teintes que les
  badges de temps restant existants). Seuils de couleur : vert < 70%
  utilisé, orange 70-90%, rouge > 90% (risque immédiat). Le
  `margin-left:auto` qui poussait `.statut` à droite est déplacé sur
  `.rate-limit` : le widget, le compteur de projets et les boutons
  d'en-tête restent groupés à droite, comme avant.

Vérification : valeurs de `/rate-limit` comparées à `gh api rate_limit
--jq '.resources.graphql'` en terminal (identiques) ; seuils de
couleur testés à 69/70/90/91% ; état d'erreur simulé (PATH sans `gh`)
→ `{ok: false, erreur: "gh introuvable dans le PATH."}`, HTTP 200 (pas
de plantage) ; `py_compile` sur tous les modules Python touchés +
suite de tests existante (`pytest tests/`, 14 passed) toujours verts.

## 24 septembre 2026 — issue #606

§16 « Agent Windows CCW » : extraction de `provisioning/windows/ccw-commun.psm1` (issue #606, sous-issue A de l'étude de faisabilité #604, suite du diagnostic #579) — regroupe ce qui était dupliqué entre les 3 scripts CCW **locaux** (`creer_projet_ccw_complet.ps1` à la racine, `provisioning/windows/ajouter_projet_ccw.ps1`, `provisioning/windows/finaliser_projet_ccw.ps1`) : helpers d'affichage `Info`/`Ok`/`Avert` (préfixe fixé une fois via `Set-PrefixeCcw`), `Get-CheminsProjetCcw` (dérivation `NomService`/`RepDepot`/`NomConf`/`NomLog`/`CheminConf` à partir du seul `NomProjet`, avec le cas spécial `Bridge_Agent` → service `CCW-Watcher` sans suffixe, même convention que `lister_projets_ccw.ps1`/`finaliser_projet_ccw_auto.ps1`), et `Lire-ValeurFichier` (lecture d'une clé dans un `.conf`, reprise de `mettre_a_jour_tokens_ccw.ps1`). Les 3 scripts locaux importent désormais le module (`Import-Module (Join-Path $PSScriptRoot '...ccw-commun.psm1') -Force`) au lieu de dupliquer cette logique. `app/ccw.py::ccw_ajouter_projet()` copie maintenant `ccw-commun.psm1` en plus de `ajouter_projet_ccw.ps1` vers `C:\Windows\Temp\` (seul script local également poussé seul par SCP). Scripts distants (`finaliser_projet_ccw_auto.ps1`, `mettre_a_jour_tokens_ccw.ps1`, `lister_projets_ccw.ps1`) non touchés — leur autonomie sans dépendance externe reste délibérée (#604) ; `lister_projets_ccw.ps1` traité séparément dans la sous-issue B si retenue.

## 24 septembre 2026 — issue #603

Alignement de `creer_projet_ccw_complet.ps1` (racine du dépôt) sur les
conventions des 11 autres scripts `.ps1` de `provisioning/windows/`
(diagnostic #579, point 4) — 4 problèmes à risque réel corrigés :

- **BOM UTF-8** ajouté en tête du fichier (`EF BB BF`) — sans lui,
  PowerShell 5.1 plante silencieusement au premier accent ajouté.
- **`.conf` sans BOM** : remplacement de `Set-Content -Encoding UTF8`
  (qui écrit un BOM parasite) par `[IO.File]::WriteAllText(...,
  UTF8Encoding($false))`, comme `ajouter_projet_ccw.ps1` — évite de
  corrompre silencieusement la lecture par `watcher.py`.
- **Fuite de secret BSTR** : ajout de la fonction
  `ConvertFrom-SecureStringPlain` (try/finally +
  `Marshal::ZeroFreeBSTR`), même pattern que
  `mettre_a_jour_tokens_ccw.ps1`, appliquée aux deux tokens saisis.
- **Chemin codé en dur** : `$CheminClaude` dérivé dynamiquement de
  `$env:USERPROFILE` au lieu du compte `AlainW` en dur — ne casse plus
  silencieusement si le compte de service change.

Le point 5 du diagnostic (extraction d'un module commun
`provisioning/windows/ccw-commun.psm1` pour la dérivation de chemins
projet dupliquée entre ce script et `ajouter_projet_ccw.ps1`/
`finaliser_projet_ccw.ps1`) dépasse la COMPLEXITE `normal` de cette
issue — reporté à l'issue séparée #604, comme prévu par le corps de
#603.

Aucun test PowerShell direct (script non exécutable côté Linux) ; le
test statique existant `tests/test_ajouter_projet_ccw_env_558.py`
(cohérence `AppEnvironmentExtra` entre les 3 scripts qui le posent) et
l'ensemble des tests Python (`py_compile` + suite `tests/`) restent
verts.

## 24 septembre 2026 — issue #602

Retrait des 2 étapes manuelles caduques depuis #597 du corps de l'issue CCL
généré par `app/projet_ccw.py::_corps_issue_ccl()` (case « Projet CCW » du
formulaire de création, issue #559).

- `app/projet_ccw.py::_corps_issue_ccl()` : supprime les 2 anciennes étapes
  numérotées (ajout d'une entrée au tableau `$Projets` de
  `reinstaller_projets_ccw.ps1` + ligne dans le tableau de rappel de
  `REINSTALLATION_CCW.md` §7) — toutes deux automatisées depuis #597
  (dérivation dynamique de `$Projets` depuis `configs\*-ccw.conf`) et #556
  (le fichier `.conf` est déjà créé par le flux CREATION). Le corps devient
  purement informatif (section « Contexte » expliquant qu'aucune action
  manuelle n'est requise), conservant la référence croisée vers l'issue CCW.
- `tests/test_projet_ccw_559.py::scenario_corps_issue_ccl_contenu` : les
  assertions vérifient désormais l'ABSENCE des 2 anciennes instructions
  plutôt que leur présence.
- `BRIDGE_AGENT_DOC.md` §16 (séquence `bootstrap_projet_ccw`, point 3) :
  description mise à jour pour refléter le corps simplifié.
- Évaluation demandée par l'issue : le corps de l'issue CCL, une fois les 2
  étapes retirées, ne contient plus aucune action exécutable (seulement du
  contexte + la cross-référence) — l'issue CCL elle-même pourrait donc être
  supprimée du flux (route `bootstrap_projet_ccw`, frontend, doc, tests).
  Non fait ici : ce retrait toucherait le contrat de l'issue CCW (paramètre
  `numero_ccl`), le template/JS affichant les 2 liens d'issue, et une bonne
  partie de `tests/test_projet_ccw_559.py` — portée plus large que la
  COMPLEXITE `normal` déclarée pour #602, et l'issue demande explicitement
  de ne pas supprimer le flux sans confirmation. Recommandation : ouvrir une
  issue dédiée si ce retrait complet est souhaité (même logique de scission
  que #601/#602).

Tests : suite complète (21 fichiers `tests/test_*.py`) toujours verte.

## 24 septembre 2026 — issue #601

Factorisation du tableau markdown `## En-tête` dans une fonction commune
`formater_entete()` (diagnostic #579 §3.2) : ce tableau était construit à
la main dans trois sites (`app/issues.py`, `app/projet_ccw.py` ×2,
`scripts/watcher_issues_inbox.py`), avec des divergences déjà présentes
(TIMEOUT/PRIORITE en dur à certains endroits, ligne COMPLEXITE hors
tableau) — or ce tableau est re-parsé tel quel par `watcher.py`, une
dérive future aurait pu casser le parsing silencieusement.

- `app/issues.py` : nouvelle fonction `formater_entete(mode, priorite,
  timeout, projet, *, source="CC", dest="CCL", retour="CC", modele=None,
  complexite=None)` — reproduit EXACTEMENT le format existant (`timeout`
  sans le suffixe `s`, ajouté par la fonction ; `MODELE` et `COMPLEXITE`
  optionnels, absents par défaut). `construire_body()` l'utilise
  désormais au lieu de construire ses lignes à la main.
- `app/projet_ccw.py` : `_corps_issue_ccl()` et `_corps_issue_ccw()`
  appellent `formater_entete()` (import local, comme le reste des imports
  `app.issues` de ce module, pour éviter tout souci d'import circulaire).
  Le bloc `CREATION_*` de `_corps_issue_ccw()` reste construit à part et
  concaténé après l'en-tête (format spécifique à ce seul site, non inclus
  dans la fonction commune).
- `scripts/watcher_issues_inbox.py` : `construire_body()` appelle
  `formater_entete()` au lieu de dupliquer les lignes du tableau.

Format de sortie vérifié identique bit-à-bit à l'ancien code (comparaison
manuelle des chaînes produites, avant/après, pour les trois sites) — pas
de modification du format attendu par `watcher.py`. Suite de tests
existante (21 fichiers, dont `tests/test_projet_ccw_559.py`) toujours
verte sans aucune modification des tests.

## 24 septembre 2026 — issue #600

Factorisation de l'enrobage « redémarrer le watcher s'il est éteint »,
dupliqué à 5 endroits avec des comportements divergents en cas d'échec
(diagnostic #579) — nouveau helper `redemarrer_si_eteint()` dans
`app/watchers.py`.

- `app/watchers.py` : nouvelle fonction `redemarrer_si_eteint(cfg, *,
  tracer=False)`, enrobage de `demarrer_watcher(cfg, forcer=False)`.
  Retourne `(demarre, pid, trace)` — `demarre` distingue désormais
  `True` (relancé), `False` (tournait déjà) et `None` (échec, repris
  d'`app/interruption.py`) ; `trace` est une chaîne prête à insérer dans
  un commentaire GitHub (non vide seulement si `tracer=True`). Un échec
  produit systématiquement un `log.warning` — jamais silencieux, à la
  différence de l'ancien `except: pass` d'`app/projet_ccw.py`.
- 5 sites remplacés par des appels à ce helper : `app/issues.py`
  (~l.356), `app/interruption.py` (~l.531), `app/projet_ccw.py` (~l.416),
  `scripts/watcher_issues_inbox.py` (~l.621 et ~l.864).
- Garde `for-linux` **non** internalisée dans le helper : dans
  `app/issues.py` et `app/interruption.py`, elle porte sur le routage de
  l'issue (labels for-linux/for-windows, #164), une décision propre à
  l'appelant — le helper ne reçoit qu'un `cfg` de projet, sans notion de
  labels. Les 3 autres sites ne l'avaient jamais eue (contexte déjà
  filtré sur bridge_agent) : rien à y ajouter.
- `tests/test_champ_redacteur_599.py` et `tests/test_champ_relance_516.py` :
  les scénarios qui substituaient `w.demarrer_watcher` (attribut copié
  au moment de l'import dans `watcher_issues_inbox.py`) substituent
  désormais `app.watchers.demarrer_watcher` directement, puisque
  `redemarrer_si_eteint()` résout `demarrer_watcher` par lookup dans son
  propre module (`app.watchers`) et non plus dans celui de l'appelant.
  Suite de tests (21 fichiers scénarios) toujours verte.

## 24 septembre 2026 — issue #599

Ajout du champ d'en-tête optionnel `REDACTEUR` dans `issues_inbox/`, validé
pour cohérence avec `PROJET` **avant** toute création d'issue GitHub — filet
de sécurité contre une issue rédigée par Claude Chat dans le contexte d'un
projet puis déposée par erreur sous un `PROJET` différent (distraction,
relecture insuffisante d'Alain avant dépôt du fichier).

- `scripts/watcher_issues_inbox.py` : `REDACTEUR` ajouté à `CHAMPS_ENTETE`
  et à `extraire_champs()` ; nouvelle fonction `valider_redacteur()` appelée
  par `valider()` avant toute autre vérification. Trois règles : (1)
  `REDACTEUR == PROJET` → OK ; (2) label `for-windows` **et**
  `REDACTEUR == bridge_agent` → OK (canal central CCW, quel que soit le
  `PROJET` réellement ciblé) ; (3) tout autre cas → rejet vers
  `issues_inbox/rejected/` avec message explicite de discordance, journalisé
  dans `issues_inbox.log`. `REDACTEUR` absent → aucune validation
  (rétrocompatibilité avec les issues existantes).
- `BRIDGE_AGENT_DOC.md` : `REDACTEUR` ajouté au tableau des champs
  d'en-tête de `issues_inbox/` (§3.3), règle de validation détaillée dans
  §3.4, et entrée miroir dans le tableau général des champs spéciaux (§6).
- `tests/test_champ_redacteur_599.py` (12 scénarios) : extraction du champ,
  les 3 règles de `valider_redacteur()`, et le chemin complet
  `traiter_fichier()` pour les 4 cas de vérification demandés par l'issue
  (REDACTEUR == PROJET, REDACTEUR d'un autre projet sans for-windows,
  canal CCW for-windows + REDACTEUR=bridge_agent, REDACTEUR absent).

## 23 septembre 2026 — issue #598

Ajout d'un `PATH` explicite dans `systemd/watcher@.service` : les services
systemd --user démarrent avec un `PATH` minimal, sans les chemins ajoutés
par le shell interactif — notamment `~/.npm-global/bin` (où réside `claude`)
et `~/Bridge_Agent/venv/bin`. Après la migration systemd de #596, l'issue #67
(relecture_bridge) a échoué immédiatement avec « Claude Code introuvable
(claude non trouvé dans PATH) ». Même piège que celui déjà documenté côté
CCW/NSSM (§16 du DOC).

Un correctif manuel (`systemctl --user edit --full` + `daemon-reload` +
`restart`) avait déjà été appliqué en prod sur toutes les instances, mais
ne vivait que dans `~/.config/systemd/user/` — perdu à la prochaine
exécution d'`installer_services.sh`, qui écrase ce fichier depuis le
gabarit du dépôt.

- `systemd/watcher@.service` : directive `Environment="PATH=..."` ajoutée
  dans `[Service]`, en chemins absolus (systemd n'interprète pas `~`) —
  `/home/alain/Bridge_Agent/venv/bin`, `/home/alain/.npm-global/bin`,
  `/home/alain/.local/bin`, `/home/alain/bin`, puis le PATH système standard.
  Validé avec `systemd-analyze verify`.
- `BRIDGE_AGENT_DOC.md` (section « Watchers supervisés par systemd --user ») :
  nouveau point documentant l'exigence du `PATH` explicite, la cause, et la
  commande de vérification post-installation (`/proc/<pid>/environ`).

## 23 septembre 2026 — issue #596

Réactivation des watchers de projet en services `systemd --user`
(`watcher@<projet>.service`), abandonnée une première fois par l'issue #119 :
`Restart=always` + `RestartSec=10` relançait systématiquement tout watcher
qui venait de s'éteindre proprement pour inactivité (`DELAI_INACTIVITE_MIN`,
#199/#200), en boucle sans fin. Constaté concrètement le 22/09/2026 lors d'un
redémarrage du ThinkPad ayant interrompu plusieurs watchers en cours, sans
aucune supervision pour les relancer.

Correction de l'incompatibilité : `Restart=on-failure` + `SuccessExitStatus`
sur un code de sortie dédié à l'auto-extinction (distinct de 0), pour que
systemd relance un crash réel mais jamais un arrêt volontaire — qu'il
s'agisse de l'auto-extinction pour inactivité ou d'une interruption manuelle
(#323).

- `watcher.py` :
  - Nouvelle constante `EXIT_INACTIVITE = 42` — code de sortie de
    l'auto-extinction pour inactivité, désormais `sys.exit(EXIT_INACTIVITE)`
    au lieu de `sys.exit(0)`.
  - `main()` publie désormais son propre fichier PID
    (`logs/watcher-<nom>.pid`) dès son démarrage, quel que soit son mode de
    lancement (terminal, `systemctl`, ou bouton de l'interface) — jusqu'ici
    c'était uniquement `app/watchers.py::demarrer_watcher` (via
    `subprocess.Popen`) qui l'écrivait après coup, ce qui n'aurait plus
    fonctionné pour un watcher lancé directement par systemd. Toute la
    détection existante basée sur ce fichier (`watcher_actif`,
    `_watcher_actif`/`detecter_conflit_watcher`, `interrompre_linux`) reste
    inchangée. Nettoyage du fichier PID ajouté aussi sur `KeyboardInterrupt`
    (Ctrl+C manuel), par symétrie avec l'auto-extinction.
- `systemd/watcher@.service` : `Restart=always` → `Restart=on-failure`,
  ajout de `SuccessExitStatus=42`.
- `installer_services.sh` : la liste de projets codée en dur est remplacée
  par une lecture dynamique de `configs/*.conf` valides via
  `app.projets.lister_projets()` (même définition de « projet actif » que le
  reste de l'interface) ; mise à jour des commentaires d'en-tête (l'ancien
  avertissement de conflit avec le bouton « Lancer/Arrêter watcher » de
  l'interface ne s'applique plus, les deux mécanismes étant désormais
  unifiés).
- `app/watchers.py` :
  - `demarrer_watcher()` appelle `systemctl --user start|restart
    watcher@<projet>` au lieu de `subprocess.Popen` (avec un court sondage
    du fichier PID pour renvoyer le nouveau pid).
  - `arreter_watcher()` appelle `systemctl --user stop watcher@<projet>` au
    lieu d'un `os.kill(pid, SIGTERM)` direct.
  - `watcher_actif()`/`chemin_pid()` inchangés (toujours basés sur le
    fichier PID).
  - Imports `signal`/`sys` retirés (devenus inutiles) ainsi que la constante
    `DOSSIER_SCRIPT` (plus utilisée).
- `app/interruption.py` : nouvelle fonction
  `_neutraliser_relance_systemd()`, appelée par `interrompre_linux()` juste
  après confirmation de la mort de l'arbre de process. Sans elle, le SIGKILL
  existant du bouton « Interrompre cette issue » (#323) serait vu par
  systemd comme un crash et le watcher serait relancé après 10 s par
  `Restart=on-failure` — contredisant le contrat de #323 (« jamais de
  relance automatique après une interruption manuelle »). Appelle
  `systemctl --user stop watcher@<projet>`, un arrêt délibéré du point de
  vue de systemd qui n'active jamais la politique `Restart=`. Best-effort :
  ne fait jamais échouer l'interruption elle-même (watcher lancé hors
  systemd, ou service non installé pour ce projet).
- `BRIDGE_AGENT_DOC.md` : remplacement du bloc « Historique : services
  systemd (abandonnés) » par la documentation du mécanisme actif
  (démarrage/relance, installation dynamique, unification avec les boutons
  de l'interface, interaction avec le bouton Interrompre, absence de sudo
  nécessaire) ; mise à jour de la section « Cycle de vie des watchers » pour
  mentionner systemd et le nouveau code de sortie `EXIT_INACTIVITE`.

Hors périmètre (conforme à l'intention de l'issue) : `new_issue.py` reste
lancé manuellement (pas de service systemd dédié) ; le watcher spool
(`scripts/watcher_issues_inbox.py`) garde son propre mécanisme de
durée/échéance.

Vérification : suite de tests existante (20 fichiers `tests/test_*.py`,
dont `test_auto_extinction_217.py` qui pilote le vrai `watcher.main()`)
toujours verte après ces changements ; `py_compile` OK sur tous les fichiers
Python modifiés. L'installation réelle des services (`installer_services.sh`,
`systemctl --user enable --now`) et la vérification post-redémarrage du
ThinkPad restent à faire par Alain — hors de portée d'une session CCL en
worktree isolé (nécessite d'agir sur `~/.config/systemd/user/` et
`loginctl enable-linger` de la session réelle, hors du périmètre de ce
worktree).

## 23 septembre 2026 — issue #595

Modal « Supprimer le projet » (zone dangereuse) : le bouton « Supprimer
définitivement » restait visuellement identique (rouge plein) même une
fois désactivé (`disabled`), car aucune règle CSS ne stylait cet état —
un utilisateur pouvait croire le bouton actif alors qu'un clic ne
déclenchait rien (comportement natif HTML silencieux, sans retour
visuel). La logique de grisage elle-même (`spMajBoutonEtat()` dans
`static/js/app.js`, issue #587) était déjà correcte : bouton désactivé
à l'ouverture, tant que les 3 cases ne sont pas cochées et que le nom
retapé ne correspond pas exactement au projet ciblé. Ajout de
`button.danger-plein:disabled{...}` dans `static/css/style.css` (fond
gris `#ccc`, texte `#888`, curseur `not-allowed`) pour que l'état
désactivé soit visible, symétriquement à `button.primaire:disabled`
déjà existant. Vérifié en conditions réelles (Playwright + Chromium
headless, projet de test temporaire hors dépôt) : gris tant que le nom
est incorrect, rouge dès la correspondance exacte.

## 23 septembre 2026 — issue #594

Onglet Configuration → Zone dangereuse : ajout d'un rappel « **Projet ciblé : <nom>** » (gras, rouge) juste au-dessus du bouton « 🗑 Supprimer ce projet… » (issue #594) — mis à jour dynamiquement, sans rechargement de page, à chaque changement de la combobox `#projet` en haut de page (`appliquerAccentProjet()` dans `static/js/app.js`, appelée par `onProjetChange()`), pour qu'un utilisateur ne regardant que le bas de la page sache sans ambiguïté quel projet sera supprimé avant de cliquer.

## 23 septembre 2026 — issue #593

Retrait de `testrelectureprojet` de `BRIDGE_AGENT_DOC.md` : projet test
supprimé, qui avait été ajouté manuellement (hors création standard
Bridge_Agent) pour apparaître dans Relecture_Bridge.

- `BRIDGE_AGENT_DOC.md` :
  - Ligne 85 (tableau §2, projets actifs) : suppression de la ligne
    `| testrelectureprojet | AlainDelree/Testrelectureprojet | ~/Testrelectureprojet | (conf local) |`.
  - Ligne 723 (tableau §7, REP_TRAVAIL par projet) : suppression de la ligne
    `| testrelectureprojet | /home/alain/Testrelectureprojet |`.
  - Vérifié : `grep -i "testrelectureprojet" BRIDGE_AGENT_DOC.md` ne retourne
    plus aucun résultat.

## 23 septembre 2026 — issue #592

Exclusion des RELANCES de la mise à jour de `duree_typique` (biais de mesure
EWMA, §19/§21). Quand une issue est relancée via le champ RELANCE (#516)
après un échec `needs-human` ou un timeout, `watcher.py` peut retrouver dans
le worktree du travail déjà effectué par la tentative précédente : la durée
mesurée (nouvelle ACK → clôture) est alors artificiellement courte et tirait
`duree_typique` vers le bas. Quantifié sur GitHub : 7 RELANCES sur 192 issues
`done` depuis le 2026-09-02 (3.6%).

- `watcher.py` :
  - Nouveau marqueur `MARQUEUR_ECHEC_TENTATIVES = "❌ Échec après"` (préfixe
    du message d'échec définitif déjà posté par le watcher avant
    `needs-human`, ~L4453).
  - Nouvelles fonctions `_lister_commentaires(numero)` (lecture best-effort
    des commentaires actuels de l'issue via `gh issue view --json comments`)
    et `_issue_est_relance(commentaires)` (True si `MARQUEUR_ECHEC_TENTATIVES`
    est déjà présent dans cet historique).
  - `_traiter_issue_synchrone` : détection `est_relance` juste AVANT le
    commentaire d'ACK (donc sur l'historique strictement antérieur à cette
    exécution) — un seul appel réseau, réutilisé côté succès plus bas.
  - `_maj_combinaison_timeout` / `maj_calibration_timeout` : nouveau
    paramètre `relance` (défaut `False`). Sur succès avec `relance=True`,
    la durée est traitée comme CENSURÉE, même principe que le timeout :
    aucune mise à jour de `duree_typique`/`variabilite`/succès rapides/
    backoff, ni de F_reseau/F_local (même biais de durée artificiellement
    courte) — seul un compteur `n_relances_exclues` (par combinaison) est
    incrémenté à titre de traçabilité.

- `tests/test_relance_exclusion_calibration_592.py` (nouveau) : 4 scénarios
  — détection RELANCE sur l'historique des commentaires (positif/négatif/
  historique vide), exclusion de `duree_typique`/`variabilite` avec
  incrément de `n_relances_exclues`, non-régression d'un succès normal
  (mise à jour comme avant #592), et `maj_calibration_timeout` bout en bout
  (amorce → RELANCE inchangée → issue normale de nouveau mise à jour).
  Suite de tests existante (20 fichiers) toujours verte.

## 23 septembre 2026 — issue #590

Backoff EWMA irrécupérable (§19) — ancrage de la condition « succès rapide »
sur `duree_typique` au lieu du `TIMEOUT` courant, et plafond de sécurité sur
`TIMEOUT_suggéré`. Constaté sur `relecture_bridge|normal|write|normal` :
`multiplicateur_backoff` monté à 7481.83 (→ `TIMEOUT_suggéré` ~2 062 012s,
~23 jours) et `relecture_bridge|normal|write|lourd` à 7.59 — dans les deux
cas le backoff ne pouvait plus jamais redescendre seul.

- `watcher.py` :
  - Cause : `_maj_combinaison_timeout` comparait `duree_s` à
    `SEUIL_SUCCES_RAPIDE × timeout_courant`, où `timeout_courant` est le
    `TIMEOUT` de l'en-tête de CETTE exécution — une valeur décorrélée du
    comportement réel de la combinaison (peut rester basse d'une issue à
    l'autre, ex. constaté « 300s, TIMEOUT plancher, trop court »). Un succès
    pourtant nettement plus rapide que la normale pouvait ainsi ne jamais
    franchir la barre, bloquant `succes_rapides_consecutifs` à 0 et le
    backoff dans son état emballé — sans recours (verrou permanent).
  - Correctif de fond : la comparaison est désormais ancrée sur
    `duree_typique + K_VARIABILITE × variabilite` — le repère historique
    EWMA propre à la combinaison — totalement indépendant du `TIMEOUT` de
    l'exécution en cours et donc du `multiplicateur_backoff` lui-même.
    Suppression du paramètre `timeout_courant`, devenu inutile, de
    `_maj_combinaison_timeout` et `maj_calibration_timeout` (et des deux
    points d'appel dans `_traiter_issue_synchrone`).
  - Filet de sécurité : nouvelle constante `TIMEOUT_SUGGERE_PLAFOND = 3600`
    (1h — largement au-dessus des complexités `lourd` observées à ce jour)
    et nouvelle fonction `_timeout_suggere_borne()` (formule §19.2 + bornage
    plancher/plafond), utilisée par `maj_calibration_timeout` et
    `lire_timeout_suggere` — protège contre tout emballement futur non
    anticipé du backoff, même après le correctif d'ancrage ci-dessus.
  - Correction manuelle des deux valeurs anormales dans
    `logs/etat_timeout.json` demandée par l'issue : **non appliquée** —
    ce fichier (gitignoré, état d'exécution) vit dans le clone de travail
    réel (`/home/alain/Bridge_Agent`), hors du périmètre de ce worktree
    isolé (`/home/alain/bridge_agent-issue590`). Alain doit remettre
    manuellement `multiplicateur_backoff` à `1.0` pour les combinaisons
    `relecture_bridge|normal|write|normal` (7481.83) et
    `relecture_bridge|normal|write|lourd` (7.59) dans
    `/home/alain/Bridge_Agent/logs/etat_timeout.json` après déploiement
    de ce fix.

- `tests/test_backoff_ancrage_duree_typique_590.py` (nouveau) : 4 scénarios
  — succès rapide détecté malgré un backoff emballé (cas réel), 3 succès
  rapides consécutifs réinitialisant le backoff, succès non notablement
  rapide remettant le compteur à zéro sans y toucher, et plafonnement de
  `TIMEOUT_suggéré` (`_timeout_suggere_borne`). Suite de tests existante
  (18 fichiers) toujours verte.

## 22 septembre 2026 — issue #589

Repli silencieux sur REP_TRAVAIL quand la création du worktree échoue
(chemin ou branche déjà pris) — rendu visible sans changer le comportement
du repli lui-même, qui reste volontaire et propre (cf. BRIDGE_AGENT_DOC.md).
Scénario déclencheur : une tentative interrompue (TIMEOUT trop court)
laisse un worktree orphelin ; la relance échoue à recréer un worktree au
même chemin/branche et retombe sur REP_TRAVAIL sans aucun signal — découvert
seulement en tentant un nettoyage manuel plus tard.

- `watcher.py` :
  - `_creer_worktree` retourne désormais `(chemin, raison_deja_pris)` au lieu
    de `chemin` seul. `raison_deja_pris` n'est renseignée QUE quand l'échec
    est attribuable à un chemin ou une branche déjà pris (les deux
    vérifications sont faites AVANT l'appel à `git worktree add`, pas par
    reconnaissance de mots-clés dans le message d'erreur git — localisé,
    donc peu fiable) ; reste `None` pour une erreur git générique, afin de ne
    pas présumer une cause qu'on n'a pas vérifiée. Nouvelle vérification de
    la branche (`git rev-parse --verify`) en plus de celle déjà existante sur
    le chemin. Dans les deux cas « déjà pris », un `log.warning` explicite
    mentionne désormais le chemin concerné et la cause précise, distinct du
    `log.warning` générique pour les autres échecs.
  - `_traiter_issue_synchrone` : nouveau paramètre `echec_worktree_deja_pris`
    — quand renseigné, un avertissement (`avertissement_worktree_deja_pris`)
    est injecté en tête du compte-rendu de clôture posté sur l'issue (succès
    comme échec final), avant le corps du résultat, sur le même principe que
    `avertissement_conflit` déjà en place.
  - `traiter_issue` : les deux points d'appel de `_creer_worktree` (chemin
    parallélisé et chemin séquentiel MAX_WRITE_PARALLELE<=1, issue #577)
    transmettent désormais `raison_deja_pris` à `_traiter_issue_synchrone`.
- `tests/test_worktree_parallelisation_337.py` :
  - `scenario_creer_worktree_succes_et_repli` : adapté à la nouvelle
    signature tuple, vérifie que `raison` est `None` au succès et renseignée
    (avec le chemin) pour le repli « chemin déjà pris ».
  - `scenario_max_1_repli_si_worktree_echoue` : étendu pour vérifier les deux
    volets de #589 — un `log.warning` explicite (chemin + « déjà pris »),
    capturé via le nouvel utilitaire `_capturer_logs_watcher`, et la présence
    de la mention dans le compte-rendu réellement posté sur l'issue (corps
    capturé par le faux `gh` de test, `corps-<numero>.md`).

Hors scope, comme demandé : aucune suppression automatique du worktree
orphelin — le nettoyage reste toujours manuel (`git worktree remove` jamais
appelé automatiquement), y compris dans ce chemin.

Vérifié : `py_compile` sur les deux fichiers touchés, les 9 scénarios de
`tests/test_worktree_parallelisation_337.py` passent (dont les deux
nouvelles assertions #589), ainsi que l'intégralité des 16 autres suites de
tests existantes (aucune régression).

## 22 septembre 2026 — issue #588

Correction de `_debut_traitement()` (`app/issues.py`) : affichait à tort
« ⏳ en file » avec une estimation fraîche pour une issue qui venait
d'épuiser ses 3 tentatives, pendant la courte fenêtre où `watcher.py` a déjà
posté le commentaire « Échec après N tentatives » mais pas encore le label
`needs-human` (deux appels `gh` distincts, non atomiques). Le marqueur
« Échec après N tentatives » ne réinitialise plus systématiquement `debut` à
`None` : il ne le fait que s'il n'est **pas** récent (nouvelle constante
`FENETRE_TRANSITOIRE_ECHEC_S = 120`, marge couvrant le pire cas des deux
appels `gh` à 30s de timeout chacun). En-dessous du seuil, `debut` reste
l'ACK du cycle qui vient réellement de tourner plusieurs minutes. Au-dessus,
comportement #525 inchangé (issue relancée après retrait manuel de
`needs-human`, ACK du cycle précédent dans l'historique → « en file »
préservé jusqu'à une nouvelle ACK).

- `app/issues.py` : ajout `FENETRE_TRANSITOIRE_ECHEC_S`, `_echec_recent()`,
  condition ajoutée dans `_debut_traitement()`, docstring mise à jour.
- `tests/test_fenetre_transitoire_echec_588.py` (nouveau) : 6 scénarios
  purs (aucun accès réseau) — échec récent → `debut` conservé, échec juste
  sous le seuil, non-régression #525 (échec ancien → « en file », nouvelle
  ACK après relance fait foi), aucun commentaire, ACK simple sans échec.

## 22 septembre 2026 — issue #587

Flux de suppression de projet — côté CCL/local, symétrique à la création
(diagnostic #580). Décommissionner un projet exigeait jusqu'ici une
chirurgie manuelle sur au moins 8 cibles, avec un risque réel d'oubli ; cette
issue couvre volontairement les 4 cibles côté CCL/local, le dépôt GitHub et
le côté CCW faisant l'objet d'issues séparées.

- `supprimer_projet.py` (nouveau) : orchestrateur `supprimer_projet(nom,
  dry_run)` symétrique à `nouveau_projet.creer_projet()`, qui démonte dans un
  ordre sûr — répertoire de travail (contenu + dépôt git local, une seule
  opération de disque puisque `.git` y vit) puis `configs/<nom>.conf` puis
  régénération immédiate de §2/§7 de `BRIDGE_AGENT_DOC.md`
  (`regenerer_tableaux_projets.regenerer()`) — en s'arrêtant dès qu'une étape
  échoue plutôt que de continuer aveuglément. Ordre volontairement inverse de
  la création : le `.conf` n'est retiré qu'une fois le répertoire de travail
  effectivement supprimé, pour ne jamais laisser un répertoire orphelin sans
  trace de son existence en cas d'échec. Mode à blanc
  (`previsualiser_suppression`/`--dry-run`) : aucune écriture disque ni sur
  la doc. CLI interactif avec confirmation par saisie du nom (`--oui` pour
  l'usage scripté).
- `app/supprimer_projet.py` (nouveau) : réutilise ce script sans le
  dupliquer. `GET /supprimer-projet/verifier/<nom_projet>` (dry-run, 404 si
  absent) et `POST /supprimer-projet` (suppression réelle), toutes deux
  protégées par `login_requis`. La route POST revérifie indépendamment côté
  serveur que le champ `confirmation` reproduit exactement le nom du
  projet — la checklist côté interface, elle, peut être contournée par un
  appel direct.
- `app/__init__.py` : enregistrement des deux routes.
- `templates/index.html` : zone dangereuse dans l'onglet Configuration
  (bouton « 🗑 Supprimer ce projet… ») et modal de confirmation — aperçu
  chargé automatiquement, 3 cases à cocher (une par cible) + nom du projet
  retapé à l'identique, double garde-fou avant que le bouton de suppression
  définitive ne s'active.
- `static/js/app.js` : `ouvrirSupprimerProjet`/`fermerSupprimerProjet`,
  `spChargerApercu` (peuple l'aperçu depuis la route GET), `spMajBoutonEtat`
  (active le bouton seulement si les 3 cases + le nom retapé sont corrects),
  `soumettreSupprimerProjet` (appelle la route POST, affiche le compte-rendu
  par étape), `retirerProjetDuSelecteur` (symétrique de
  `ajouterProjetAuSelecteur`, retire l'option du sélecteur global au succès).
- `regenerer_tableaux_projets.py` : docstring mise à jour — elle admettait
  explicitement l'absence de flux de suppression automatisé (citée dans le
  diagnostic #580) ; documente désormais que `supprimer_projet.py` déclenche
  lui aussi la régénération, au même titre que `nouveau_projet.py`.
- `BRIDGE_AGENT_DOC.md` : nouvelle sous-section « Suppression de projet,
  côté CCL/local (issue #587) », symétrique de celle décrivant déjà la
  création (juste avant), plus la commande CLI dans §13.
- `tests/test_supprimer_projet_587.py` (nouveau) : aperçu (projet absent,
  projet présent — aucune écriture), dry-run (ne touche à rien), succès réel
  (ordre des étapes, `.conf` + répertoire supprimés, doc régénérée une seule
  fois), arrêt propre si la suppression du répertoire échoue (`.conf`
  conservé, doc jamais régénérée), nom vide, et les deux routes Flask
  (dry-run 404, confirmation incorrecte → 400, succès → 200).

Explicitement hors scope (décision actée dans le diagnostic #580) :
suppression du dépôt GitHub et de ses labels (geste manuel volontaire), et
tout le côté CCW (clone Windows, `configs\<nom>-ccw.conf`, service NSSM,
tokens, entrée `$Projets`, ligne `REINSTALLATION_CCW.md` §7).

Vérifié : `py_compile` sur tous les fichiers touchés, `create_app()` démarre
sans erreur et expose bien les deux nouvelles routes, les 9 scénarios de
`tests/test_supprimer_projet_587.py` passent, ainsi que l'intégralité des 16
autres suites de tests existantes (aucune régression). Non vérifié dans ce
worktree (pas d'accès réseau/GitHub authentifié) : test bout en bout réel
sur un projet jetable — demandé en vérification de l'issue, à faire par
Alain avant de considérer le flux entièrement validé.

## 22 septembre 2026 — issue #585

Retrait du diagnostic temporaire #157 (`app/diag_heartbeat.py`), balisé
« à retirer » depuis son ajout le 19 juillet mais resté câblé plus de
deux mois après validation du correctif heartbeat/SSE. Procédure de
retrait suivie telle qu'écrite dans le module lui-même : suppression du
fichier (88 lignes), de l'import et des quatre appels `diag_heartbeat.log_*()`
dans `app/cycle_vie.py` (heartbeat, connexion/déconnexion SSE, arrêt par
`surveiller_heartbeat`), de l'import et de l'enregistrement de route dans
`app/__init__.py`, et du bloc `console.log`/`fetch('/diag-visibilite')`
dans `demarrerCycleVie()` (`static/js/app.js`) — en conservant
`envoyerHeartbeat()` sur `visibilitychange`, qui fait partie du correctif
et non du diagnostic. Point de sécurité traité au passage : la route
`/diag-visibilite` disparaît avec le reste, ce qui élimine une route POST
qui n'était pas protégée par `login_requis`, contrairement au reste de
l'application. `logs/heartbeat_diag.log` n'existait pas dans ce
worktree, rien à supprimer sur ce point. Vérifié : `py_compile` OK,
`create_app()` démarre sans erreur, `/diag-visibilite` répond 404, aucune
référence résiduelle (`grep` sur `diag_heartbeat`/`diag-visibilite`/`DIAG
#157`), suite de tests existante verte (un seul échec,
`test_init_git_local_258.py`, pré-existant et sans rapport — dépendant du
réseau, échoue identiquement avant ce commit).

## 22 septembre 2026 — issue #586

Fix `tests/test_init_git_local_258.py`, périmé et non collecté par pytest
(diagnostic #579). Deux causes cumulées, une seule anticipée par le
diagnostic :

1. `scenario_deja_git` comparait le résultat de `initialiser_git()` par
   égalité stricte de dictionnaire à une valeur écrite avant le fix #530
   (filet de sécurité email noreply GitHub), donc sans la clé
   `email_corrige` que la fonction renvoie désormais toujours. Dictionnaire
   attendu mis à jour avec `"email_corrige": None`.
2. Non anticipé par #579 : `scenario_contenu_preexistant_pas_de_push`
   vérifiait `"public" in res["detail"]`, texte retiré du message `detail`
   de `nouveau_projet.py` par le fix #528 (choix public/privé du dépôt à la
   création) — un dépôt n'est plus systématiquement public. Assertion
   corrigée pour ne plus exiger ce mot, seule la mention « non relu »
   restant garantie et pertinente.

Par ailleurs, aucune fonction du fichier n'était préfixée `test_` : un
`pytest tests/` classique ne testait donc rien de ce fichier, l'échec ne se
manifestant qu'en exécution directe
(`python3 tests/test_init_git_local_258.py`). Les 5 fonctions
`scenario_*` renommées en `test_*` (et leurs références dans `main()`)
pour que pytest les collecte réellement.

Vérifié : les 5 scénarios passent en exécution directe (code retour 0) et
via `pytest tests/test_init_git_local_258.py` (5 passed). Seul le fichier
de test a été modifié, aucune logique de production touchée.

## 19 septembre 2026 — issue #575

Incident réel en mode `--externe` sur mobile : le bouton « Déconnexion »
se trouve pile sous le doigt quand on veut fermer le panneau
Infrastructure sur petit écran — clic accidentel, déconnexion
immédiate, obligeant à retaper le mot de passe.

`templates/index.html` : le bouton « Déconnexion » demande désormais
confirmation (`confirm('Se déconnecter ?')`) avant de naviguer vers
`/logout` — annulable, sans action si refusée. Même pattern déjà en
place pour le bouton « Quitter » (fonction `quitter()`,
`static/js/*.js`). Aucun changement d'apparence, de disposition ni de
media query : uniquement l'`onclick` du bouton, identique sur desktop
et mobile.

# CHANGELOG-556 — entrées à fusionner dans CHANGELOG.md

## 15 septembre 2026 — issue #556 (2/3)

Traitement du champ d'en-tête `CREATION` dans `watcher.py` — bootstrap
automatique d'un service CCW dédié, suite de la conception validée en #554
et de la génération de la paire de clés RSA 3072 (#554 1/3) : ENTIÈREMENT
déterministe, n'invoque JAMAIS `claude` (décision #554 §2.5) — réutilise
directement les scripts PowerShell déjà testés (`ajouter_projet_ccw.ps1`
puis `finaliser_projet_ccw_auto.ps1 -FichierValeurs`, format vérifié par
lecture du script avant écriture du code, identique à celui déjà produit
par `app/ccw.py`).

`_traiter_issue_synchrone` détecte `| CREATION | oui |` tôt dans le
dispatch, AVANT tout ce qui touche au pipeline `lancer_claude`. Convention
de 6 champs d'en-tête proposée et documentée (`CREATION`,
`CREATION_NOM_PROJET`, `CREATION_DEPOT`, `CREATION_TOPIC_NTFY`,
`CREATION_GH_TOKEN`, `CREATION_OAUTH_TOKEN`) : les deux tokens transitent
chiffrés individuellement (RSA/OAEP-SHA256 via `openssl pkeyutl -encrypt`,
clé publique de bootstrap) puis encodés en base64 sur une seule ligne.
`_extraire_champ_entete` compare le nom de champ EXACTEMENT (pas une
sous-chaîne comme les extracteurs existants SOUS_DOSSIER/REPO_CIBLE) : évite
la collision entre `CREATION` et son propre préfixe partagé avec
`CREATION_NOM_PROJET`/etc.

Résolution robuste du chemin `openssl` (`_resoudre_openssl`, point
d'attention hérité de #557 puisque #558 n'était pas encore mergé au moment
de cette tâche) : PATH → installation manuelle Windows
(`C:\Program Files\OpenSSL-Win64\bin\openssl.exe`, pas sur le PATH par
défaut sur CCW) → repli `usr\bin` de Git pour Windows — dupliqué en Python
plutôt que réutilisé depuis `Resoudre-OpenSSL` côté PowerShell
(`provisionner.ps1`, #554) : pas de dot-sourcing PowerShell depuis Python,
et un simple calcul de chemin ne justifie pas d'exécuter un script externe.

Retrait immédiat des deux tokens chiffrés du corps GitHub (`gh issue edit
--body-file`, remplacés par `<retiré après application>`) DÈS que les
valeurs sont en mémoire — avant même la tentative de déchiffrement — pour
limiter le temps d'exposition résiduel (§2.4 de #554). Fichier de valeurs
temporaire supprimé en deux lignes de défense (le `finally` PowerShell déjà
en place côté `finaliser_projet_ccw_auto.ps1`, PUIS un nettoyage Python en
repli). Compte-rendu + fermeture si succès (codes 0/2), `needs-human` + log
complet en commentaire si échec — un champ manquant est traité comme une
erreur de configuration définitive (aucun script PowerShell ni
déchiffrement tenté).

Testé sans vraie issue GitHub ni machine CCW réelle (sur le modèle du test
`SOUS_DOSSIER` de #550) : `tests/test_creation_bootstrap_ccw_556.py`, 15
scénarios — extraction/détection, non-collision `CREATION`/
`CREATION_NOM_PROJET`, retrait des tokens, résolution `openssl` (3 replis),
chiffrement/déchiffrement RÉEL via un openssl local (RSA 3072 généré à la
volée), chemin complet succès/champ manquant/dry-run (faux `gh` et faux
`powershell` sur le `PATH`), et un scénario bout en bout via `traiter_issue`
vérifiant qu'un faux `claude` marqueur n'est jamais touché.

Documenté en détail dans `BRIDGE_AGENT_DOC.md` §16.6 (nouvelle
sous-section), à l'intention du formulaire web à venir (3/3, #559 ou
suivant — non traité ici, `new_issue.py` non touché).

## 22 septembre 2026 — issue #584

Verrou anti-collision `REP_TRAVAIL` (`watcher.py`, #189/#322) : filet de
sécurité complémentaire contre un verrou orphelin. Incident réel : issue
#583 (canal unifié for-windows, mode_write) bloquée 48 minutes
(12:48–13:36), chaque cycle du watcher affichant « un autre traitement
détient déjà le verrou sur C:\CCW_Share ». Hypothèse posée dans #584 (un
chemin de sortie anticipée de `_traiter_issue_synchrone` — refus précoce,
avant tout travail réel — ne relâcherait pas le verrou faute de
`try`/`finally` symétrique) vérifiée par lecture de code et **INFIRMÉE** :
le `try` qui enveloppe tout le corps de `_traiter_issue_synchrone`, verrou
compris, existe depuis l'introduction même du mécanisme (issue #189,
2026-07-20, commit `6a91a0a`) et son `finally` (`liberer_verrou`) couvre
déjà tous les chemins de sortie ajoutés depuis — succès, échec après
tentative(s), abandon définitif (`needs-human`), et refus précoce (claude
répond ❌ en quelques secondes, exit code 0, avant tout travail réel).
Confirmé par deux nouveaux scénarios de `tests/test_verrou_refus_precoce_584.py`
(`scenario_refus_precoce_libere_verrou`,
`scenario_echec_rapide_sans_travail_libere_verrou`) : appel direct de
`_traiter_issue_synchrone` avec un faux `claude` répondant respectivement
❌ en exit 0 et en échec non-zéro immédiat — verrou absent après coup dans
les deux cas.

Cause réelle la plus probable de l'incident, en revanche : un watcher tué
BRUTALEMENT (crash, `kill -9`, redémarrage de service — cohérent avec
« erreur de conception de l'issue elle-même, corrigée après coup côté
Alain » évoqué dans #584) pendant qu'il détenait le verrou. Aucun
`try`/`finally` Python ne survit à un `kill -9`, sur aucune plateforme :
c'est le rôle du filet de sécurité existant par péremption par ancienneté
(issue #322, `acquerir_verrou`) — mais celui-ci se calcule à partir de
`max_essais × (TIMEOUT_projet + pause) + marge`, potentiellement des
dizaines de minutes pour un projet à `TIMEOUT` élevé (1800 s dans #583),
ce qui correspond à l'ordre de grandeur du blocage observé.

Nouveau filet complémentaire, plus rapide, dans `acquerir_verrou`
(`watcher.py`) : ajout de `_pid_vivant(pid)` (sonde cross-plateforme,
lecture seule — POSIX `os.kill(pid, 0)`, Windows `OpenProcess` avec le
droit minimal `PROCESS_QUERY_LIMITED_INFORMATION`, même pattern déjà en
place pour l'objet Job Windows de #249) et `_lire_pid_verrou(verrou)`
(lit le champ `pid=<n>` du fichier verrou — le PID du **watcher**, écrit
inconditionnellement dès la création du verrou, à ne pas confondre avec
`claude_pgid=<n>` qui n'arrive qu'après le lancement de claude, #322). Si
la péremption par ancienneté n'a pas encore tranché ET que le PID
propriétaire est confirmé mort, le verrou est repris **immédiatement**
(nouveau log dédié « Verrou orphelin sur ... — repris immédiatement »),
sans attendre l'écoulement de la péremption par ancienneté — corrige
directement le délai de #583. Asymétrie volontaire documentée sur
`_pid_vivant` : un PID introuvable est un fait certain (aucun faux négatif
possible), mais un PID trouvé vivant ne prouve pas qu'il s'agit encore du
même process (réutilisation de PID par l'OS, notamment après un temps long
ou un reboot) — dans le doute (PID vivant, sonde en échec, plateforme non
gérée), la fonction répond `True` et l'appelant retombe sur le critère
d'ancienneté existant : ce filet ne peut donc jamais rendre un verrou
encore valide plus fragile qu'avant #584. Le nettoyage de l'éventuel
`claude` orphelin (pgid stocké, POSIX uniquement, #322) reste appliqué à
l'identique dans les deux cas de reprise. Deux scénarios supplémentaires
dans `tests/test_verrou_refus_precoce_584.py`
(`scenario_pid_mort_repris_immediatement`,
`scenario_pid_vivant_reste_bloque`) : verrou frais (donc très loin de la
péremption par ancienneté) avec PID propriétaire confirmé mort → repris
immédiatement ; même verrou frais avec PID propriétaire vivant (le
process du test lui-même) → reste bloquant, sans régression.

Documentation : section « Parallélisation mode_write via git worktrees »
de `BRIDGE_AGENT_DOC.md` complétée par deux nouvelles puces (libération
garantie du verrou quel que soit le chemin de sortie ; filet de sécurité à
deux niveaux) ; §16.4 « Interrompre une issue CCW coincée » (procédure
manuelle historique pour ce même symptôme, issue #287) mis à jour pour
signaler l'atténuation automatique apportée par #584, la procédure
manuelle restant le repli si la sonde PID ne peut pas conclure (PID
recyclé par l'OS). Pied de page de `BRIDGE_AGENT_DOC.md` glissé d'un cran
en conséquence (§10) — l'entrée #540 (couleur d'accent des projets) en
sort, elle reste disponible ci-dessous.

## 20 septembre 2026 — issue #577

Section « Parallélisation mode_write via git worktrees » (#337) de
`BRIDGE_AGENT_DOC.md` : isolation de `REP_TRAVAIL` vis-à-vis d'Alain
désormais **systématique**, y compris à `MAX_WRITE_PARALLELE = 1` (issue
#577). Incident réel ayant motivé ce changement, sur `relecture_bridge`
(`MAX_WRITE_PARALLELE=1`) : Alain a fait un `git commit`/`git stash` manuel
dans `REP_TRAVAIL` pendant qu'une issue `mode_write` y travaillait
directement (comportement d'avant #577, gaté par `CFG.max_write_parallele
> 1`) — collision directe, une modification manuelle temporairement
effacée, récupérée de justesse depuis un commit orphelin. `watcher.py`
(`traiter_issue`) découple désormais explicitement les deux besoins que le
couplage précédent confondait : `MAX_WRITE_PARALLELE` continue de piloter
uniquement la parallélisation **entre** tâches CCL (thread principal vs
threads dédiés, utilité réelle seulement `> 1`) ; l'isolation via worktree,
elle, s'applique dans tous les cas. À `MAX_WRITE_PARALLELE ≤ 1`,
`_creer_worktree(numero)` est maintenant appelée avant
`_traiter_issue_synchrone`, celle-ci restant appelée directement (aucun
`threading.Thread`, comportement séquentiel historique préservé) — mais
désormais avec `chemin_worktree` renseigné au lieu de `None`. Repli propre
sur `REP_TRAVAIL` si la création du worktree échoue (chemin/branche déjà
pris), comme pour le cas parallélisé. Nettoyage/traçabilité déjà en place
(alerte d'accumulation de worktrees #432, comptage `MAX_WRITE_PARALLELE`
via `needs-human` #576) inchangés — ces worktrees « solo » sont
indiscernables des worktrees créés en parallélisation, aucun traitement
spécial requis. `tests/test_worktree_parallelisation_337.py` étendu : la
scénario de non-régression à `MAX_WRITE_PARALLELE=1` devient un scénario
d'isolation (worktree utilisé, `REP_TRAVAIL` inchangé — même HEAD, aucun
fichier ajouté, aucun thread créé) ; nouveau scénario couvrant le repli sur
`REP_TRAVAIL` si la création du worktree échoue à `MAX_WRITE_PARALLELE=1`.

## 18 septembre 2026 — issue #571

§2 « Projets actifs » et §7 « Périmètre par projet » de
`BRIDGE_AGENT_DOC.md` n'étaient maintenus qu'à la main, indépendamment des
`configs/*.conf` réellement lus par `watcher.py` — source de vérité
fonctionnelle (`NOM`/`DEPOT`/`REP_TRAVAIL`/`PERIMETRE`). Toute divergence
(création, suppression, renommage d'un projet oublié dans un des
tableaux) pouvait se reproduire, et s'était reproduite : `testccwprojet`
(projet de test entièrement nettoyé — dépôt GitHub, service CCW, `.conf`
local, entrées de `reinstaller_projets_ccw.ps1`) restait visible dans ces
deux tableaux.

Nouveau script `regenerer_tableaux_projets.py` (racine) : scanne
`configs/*.conf`, ignore les fichiers sans champ `NOM` (ex.
`configs/ccw_ssh.conf`, config technique de connexion SSH, pas un projet
watcher), et remplace intégralement le contenu des deux tableaux entre
des marqueurs HTML dédiés (`<!-- DEBUT:TABLEAU_PROJETS_ACTIFS -->`/
`<!-- DEBUT:TABLEAU_PERIMETRE_PROJETS -->` + `FIN:` correspondants,
ajoutés dans `BRIDGE_AGENT_DOC.md`) — jamais d'édition manuelle. Projets
triés par ordre alphabétique du `NOM` (l'ordre chronologique d'ajout
historique n'est pas reconstituable depuis le disque) ; effet de bord
assumé, la casse affichée suit désormais celle du `NOM` du `.conf`
(`apiselect`, en minuscules, remplace l'ancien `ApiSelect` du tableau —
qui ne correspondait à aucun champ réel).

`nouveau_projet.py::mettre_a_jour_doc()` (route Flask) et `etape_doc()`
(CLI interactif) dupliquaient chacun leur propre logique d'insertion de
ligne (`_inserer_ligne_tableau`, `_afficher_rep`) — les deux délèguent
maintenant à `regenerer_tableaux_projets.regenerer()`, un seul mécanisme
écrit désormais dans ces tableaux ; helpers dupliqués supprimés, ainsi
que `MOIS_FR`/`from datetime import date`, devenus inutiles dans
`nouveau_projet.py`. Le script reste aussi utilisable seul et à la
demande (`python3 regenerer_tableaux_projets.py`, sans argument) — la
commande à relancer après un nettoyage manuel de projet (pas de flux de
suppression automatisé aujourd'hui) pour resynchroniser la doc avec la
réalité du disque ; conséquence directe, testé en simulant un cycle
création/suppression d'un `.conf` de test, `testccwprojet` disparaît des
deux tableaux — de même que `relecture_bridge`, ajouté au commit
précédent (§2/§7) mais sans `configs/relecture_bridge.conf` présent sur
ce disque : ⚠️ à vérifier par Alain (projet réellement sans watcher
dédié, ou `.conf` restant à créer — CCL n'a pas le droit de créer/modifier
`configs/*.conf`).

Piège évité en cours de route (documenté en §10 de `BRIDGE_AGENT_DOC.md`,
déjà rencontré à l'issue #268) : le premier essai de mise à jour
automatique de la date de pied de page utilisait un `re.sub` sur le texte
entier du fichier, qui a corrompu l'exemple donné en §10
(`` *Dernière mise à jour : <date> — ...* ``) au lieu du vrai pied de
page en fin de fichier — corrigé en ne substituant que sur la ligne qui
**commence** par le marqueur (même garde-fou que l'ancien code de
`nouveau_projet.py`), avec test de non-régression manuel (relecture du
diff avant/après).

Tableau §7 de `provisioning/windows/REINSTALLATION_CCW.md` (étape 7,
recréation des services CCW dédiés) : choix documenté de le laisser **en
dehors** de ce mécanisme, pas appliqué silencieusement. Ce n'est pas la
même liste : un sous-ensemble des projets (ceux avec un service Windows
dédié), décision manuelle indépendante des `.conf` Linux, dont la source
de vérité déclarée reste déjà le tableau `$Projets` de
`reinstaller_projets_ccw.ps1` (issue #552) — note ajoutée dans
`REINSTALLATION_CCW.md` pour expliciter cette distinction plutôt que de
laisser deviner pourquoi ce tableau-ci échappe à la régénération.

## 14 septembre 2026 — issue #542

Mode lecture bloqué sur des commandes nécessitant une approbation
interactive impossible en session non-interactive (issue #542, constaté
sur CCW via l'issue de diagnostic #541 : `git fetch`/`git pull` et
`Add-Type -AssemblyName ...` refusés par Claude Code avec « This command
requires approval »). Confirmé dans le code (`lancer_claude`) :
`MODE_LECTURE` n'a jamais `--dangerously-skip-permissions` (réservé à
`mode_write`/`mode_scratch`) — reproduit à l'identique sur CCL avec le CLI
`claude` nu (`git -C ... fetch` bloqué avec le même message), donc bien un
bug partagé par les deux plateformes (`watcher.py` commun), pas spécifique
à CCW/Windows.

Plutôt que d'ajouter `--dangerously-skip-permissions` en lecture seule (ce
qui désarmerait toutes les protections de Claude Code sans le filet de
sécurité technique dont bénéficie la lecture active, empreinte
avant/après), ajout d'une allowlist fine via `--allowedTools` — mécanisme
natif de Claude Code qui débloque des commandes précises sans toucher au
reste : `git fetch` (jamais d'écriture dans l'arbre de travail),
`git pull --ff-only` (échoue plutôt que de merger — même opération que le
`git pull --ff-only` déjà fait automatiquement par le watcher en début de
cycle sur `REP_TRAVAIL`) et `Add-Type -AssemblyName` côté CCW (charge un
assembly .NET nommé, sans exécuter de code arbitraire —
`Add-Type -TypeDefinition`, qui compile du C#, reste volontairement hors
liste). Nouvelle constante `OUTILS_LECTURE_AUTORISES` dans `watcher.py`,
ajoutée à `cmd` uniquement en `MODE_LECTURE`. `git status`/`log`/`diff`/
`show` n'ont pas eu besoin d'y être ajoutés : déjà autorisés sans
approbation par l'heuristique interne de Claude Code (vérifié).

Vérification de bout en bout via `lancer_claude` en conditions réelles
(pas seulement `claude --help`) : `git fetch --dry-run` + `git pull
--ff-only` s'exécutent sans blocage en mode lecture (résultat renvoyé
normalement) ; une tentative d'écriture hors allowlist (redirection shell
vers un fichier du projet) reste bloquée par le sandbox, confirmant que le
périmètre d'écriture de la lecture seule n'a pas été élargi. Le cas
`Add-Type -AssemblyName` (spécifique PowerShell/CCW) n'a pas pu être
vérifié en conditions réelles faute d'environnement Windows disponible ici
— à confirmer côté CCW à l'occasion d'une prochaine tâche PowerShell en
lecture seule.

## 13 septembre 2026 — issue #540

Recyclage de la couleur des projets à l'arrêt (`ecole`, `ff_galerie`) vers
un gris neutre partagé, pour libérer leur ancienne couleur dédiée dans une
palette déjà contrainte (#539 : combinaison distance CIE76 + écart de
teinte Lab, seulement 5 couleurs libres avant cette issue).

Nouvelle constante `COULEUR_PROJET_INACTIF = "#767676"` définie à deux
endroits (`nouveau_projet.py` et `static/js/app.js`, pas de mécanisme de
partage de constantes entre les deux) : contraste texte noir 4,62:1
(`_contraste_avec_noir(0, 0, 46)`), au-dessus du seuil `SEUIL_CONTRASTE_NOIR`
(4,5:1) commun aux couleurs actives — sans contrainte de saturation 100% ni
de distance/teinte Lab, le but étant justement de signaler visuellement
l'absence d'identité propre.

Traitement volontairement ASYMÉTRIQUE entre les deux fichiers, vérifié
concrètement plutôt que supposé :
- `nouveau_projet.py` : `ecole` et `ff_galerie` **retirées** de
  `COULEURS_PROJETS_EXISTANTS` (pas remplacées par le gris). Ce dictionnaire
  est passé en `couleurs_a_eviter` à `generer_palette()`, qui compare les
  couleurs par angle de teinte Lab (`_teinte_lab`) ; un gris (saturation 0)
  a un a\*/b\* quasi nul, donc un angle `atan2(0,0)` dégénéré à 0°, qui
  entre en collision avec l'exclusion de teinte prévue pour les rouges et
  fait échouer l'assertion de fin de `generer_palette()` — reproduit
  concrètement en testant les deux variantes (retrait vs. remplacement par
  le gris) avant de choisir. Les retirer suffit et n'a pas cet effet de
  bord : `couleurs_disponibles()` passe de 5 à 6 couleurs proposées à un
  futur projet, confirmant que l'ancienne couleur dédiée est bien recyclée.
- `static/js/app.js` : `ecole` et `ff_galerie` restent des clés de
  `COULEURS_PROJET` (seule source de vérité pour l'affichage, y compris des
  projets à l'arrêt), simplement avec la valeur `COULEUR_PROJET_INACTIF` à
  la place de leur ancienne teinte dédiée.

Documentation : sous-section « Couleur d'accent des projets » de
`BRIDGE_AGENT_DOC.md` complétée d'une procédure de recyclage réutilisable
pour un futur projet mis à l'arrêt (retrait côté Python, remplacement de la
valeur côté JS, pourquoi ce n'est pas symétrique).
## 13 septembre 2026 — issue #539

Suite retour d'usage sur #535 : 3 paires de couleurs de projet restaient
visuellement trop proches malgré une distance CIE76 au-dessus du seuil de
garde de 15 posé en #535 — `alchess`/`rummikub`, `ecole`/`chesscoach`,
`actualise`/`gestionmail`.

**Diagnostic (point 1 de l'issue)** : les couleurs réellement en usage pour
`alchess`/`rummikub` et `ecole`/`chesscoach` ont une distance CIE76 de 56 et
52 — largement AU-DESSUS du seuil de 15, pas « de justesse » comme supposé.
La vraie cause : leur écart d'angle de teinte dans le plan Lab a\*/b\* n'est
que de 1,6° et 0,4° — ces couleurs ne diffèrent quasiment qu'en clarté/chroma,
pas en teinte. CIE76 (distance euclidienne L/a\*/b\*) traite cet écart comme
n'importe quel autre, alors que l'œil, sur une petite pastille, identifie
d'abord la teinte : deux nuances d'une même teinte se lisent comme UNE seule
couleur, pas deux. `actualise`/`gestionmail` n'a pas pu être mesurée sur la
couleur réelle (gestionmail est un projet créé après #535, sa couleur ne vit
que dans `configs/gestionmail.conf`, hors périmètre de ce worktree et de
toute façon jamais modifiable par CCL/CCW) — mais le même mécanisme est en
cause : `actualise` (ancienne valeur, teinte Lab ≈292°) se trouvait dans la
même zone bleu-violet que `ff_galerie` (285,5°), `gestionmail` (candidat le
plus proche de la palette de l'époque : `#9191FF`, ≈296°) et `chesscoach`
(318,3°).

**Correction (points 2 et 3)** : `nouveau_projet.py` — ajout d'un second seuil
de garde `SEUIL_ECART_TEINTE_MIN` (15°, écart minimal d'angle de teinte Lab
entre deux couleurs de la palette), complémentaire de `SEUIL_DISTANCE_MIN`
(remonté 15→20, défense en profondeur mais insuffisant seul ici : 56 et 52
sont déjà loin au-dessus). `generer_palette()` vérifie désormais les deux
seuils, par construction (filtrage des candidats) ET par assertion finale.
Correction ciblée de 4 couleurs seulement dans `COULEURS_PROJETS_EXISTANTS`
(les 7 autres restent inchangées, même esprit que la correction #534
ecole/ff_galerie) :
- `alchess` `#00FF00`→`#00D68F` (pas de champ COULEUR persisté en `.conf`,
  contrairement à `rummikub` → conservée)
- `ecole` `#DE85FF`→`#CC7400` (pas de champ COULEUR persisté, contrairement à
  `chesscoach` → conservée ; nouvelle teinte ambre/moutarde, clin d'œil à la
  couleur qu'ecole portait déjà entre #534 et #535)
- `actualise` `#086BFF`→`#009DD6` (seul levier disponible côté code puisque
  gestionmail — l'autre membre de la paire — n'est pas modifiable ; nouvelle
  teinte délibérément écartée de toute la zone bleu-violet 197°-320°)
- `bloc_score` `#FFB0AB`→`#FF8595` : 4e paire découverte en appliquant le
  nouveau seuil (non signalée dans l'issue) avec `bridge_agent` (écart de
  teinte 13,2°, sous le nouveau plancher de 15°) — `bridge_agent` non
  retouché, nouvelle teinte toujours rose/saumon pâle.

Toutes les paires (11 couleurs figées + palette régénérée) validées sans
violation par script (120 paires testées, contraste texte noir >= 4,5:1
conservé partout). `static/js/app.js` (`COULEURS_PROJET`) mis à jour en
synchro.

**Mécanisme de sélection pour les futurs projets (point 4)** :
`generer_palette()` accepte désormais un paramètre `couleurs_a_eviter`
(passé avec `COULEURS_PROJETS_EXISTANTS`) et l'utilise comme réservation
initiale de l'algorithme glouton — pas seulement en post-filtrage comme le
faisait déjà `couleurs_utilisees()`. Sans ce paramètre, la garantie de
distance/teinte ne portait que sur les couleurs générées ENTRE ELLES, jamais
sur les 11 couleurs gelées en dur : c'est exactement ce trou qui avait laissé
passer la collision `actualise`/`gestionmail` (gestionmail avait pris une
couleur de la palette, valide par rapport aux autres couleurs générées, mais
jamais vérifiée par rapport à `actualise`). Avec ce paramètre, toute couleur
encore proposée à un futur projet est garantie distincte de TOUS les projets
existants. Conséquence attendue : `NB_COULEURS_PALETTE` (30 demandées) ne
produit plus que 5 couleurs effectivement disponibles au-delà des 11
historiques (contre 40 avant #539) — la combinaison seuil de distance +
seuil de teinte limite mécaniquement le nombre de couleurs vraiment
distinctes sur le cercle chromatique ; à surveiller si de nombreux nouveaux
projets sont créés.

**Point d'attention laissé à Alain** : la couleur réelle de
`configs/gestionmail.conf` n'a pas pu être lue (hors périmètre du worktree
`/home/alain/bridge_agent-issue539`, et modification de `configs/*.conf`
interdite à CCL/CCW dans tous les cas) ni donc revérifiée contre la nouvelle
valeur d'`actualise`. À vérifier manuellement ; si elle s'avère encore trop
proche d'une des 11 couleurs figées (ou d'une future couleur de
`PALETTE_COULEURS`), seule une modification manuelle du `.conf` par Alain
peut la corriger.

## 11 septembre 2026 — issue #528

`creer_depot()` (`nouveau_projet.py`) n'était plus systématiquement `--public`
codé en dur : nouveau paramètre `public: bool = True` déterminant le flag
`gh repo create` (`--public`/`--private`), défaut cohérent avec le
comportement historique. Exposé dans les deux points d'entrée existants :
CLI (`etape_depot()`, question « Dépôt public (non = privé) » juste après la
confirmation de création) et formulaire web (case à cocher « Dépôt public »
dans `templates/index.html`, visible seulement quand le dépôt cible n'existe
pas encore, comme la case « Créer le dépôt » dont elle dépend) → transmis à
`app/nouveau_projet.py`/`creer_projet()` puis à `creer_depot()`. Aucune étape
ultérieure (`initialiser_git()`, clonage, remote, push) ne suppose un accès
public : tout passe par `gh`/`git` en HTTPS authentifié via `GH_TOKEN`
(`_url_https()`, §9), donc un dépôt privé fonctionne à l'identique côté
interface — seule condition, que ce token ait les permissions nécessaires
sur ce dépôt. Commentaires/messages qui présupposaient un dépôt public
(docstrings, messages CLI, encarts web) mis à jour en conséquence. §13 de la
doc complété.

## 7 septembre 2026 — issue #521

Traçabilité minimale sur `logs/historique_durees.json` et
`logs/etat_timeout.json`, pour diagnostiquer une future perte de données
comme celle du 7 septembre 2026 restée inexpliquée faute de preuve (fichiers
gitignorés, aucun historique git natif).
- Approche retenue (parmi les deux esquissées dans l'issue) : un journal
  séparé append-only, plutôt qu'une exception ciblée au `.gitignore` de
  `logs/` — `historique_durees.json` grossit à chaque issue close
  (cf. `scripts/archiver_historique.py`), le suivre en git alourdirait
  chaque commit de sauvegarde CCL sans rapport avec la tâche en cours.
- `watcher.py` : nouveau `logs/journal_ecritures_historique.jsonl` (JSON
  Lines, déjà couvert par le `.gitignore` existant de `logs/`) via
  `_journaliser_ecriture` (nouvelle fonction). Une ligne par écriture
  significative : `nb_avant`/`nb_apres` (nombre d'entrées), taille en octets
  avant/après, `operation`, et `reinitialise_corruption=true` si l'écriture
  repart d'un JSON illisible (la signature exacte d'une perte de données
  silencieuse — jusqu'ici, `enregistrer_duree` réinitialisait déjà
  discrètement l'historique à `[]` dans ce cas, sans laisser aucune trace).
  Appelé depuis `enregistrer_duree` (`operation="cloture_issue"`,
  `historique_durees.json`) et depuis `_maj_etat_json` pour
  `etat_timeout.json` uniquement (`operation="calibration_timeout"`,
  nombre de combinaisons avant/après) — `etat_ambiance.json` non instrumenté
  (deux clés fixes `F_reseau`/`F_local`, jamais perdues de la même façon,
  hors du périmètre demandé par l'issue).
- `scripts/archiver_historique.py` : écrit aussi dans ce même journal
  (`operation="archivage_manuel"`, nouvelle fonction locale
  `_journaliser_archivage`, sans importer `watcher.py` — cohérent avec le
  découplage volontaire du script) lors d'une exécution réelle (jamais en
  `--dry-run`). But : qu'une réduction volontaire et attendue du fichier
  (archivage manuel par Alain) ne soit jamais confondue, à la lecture du
  journal, avec une chute inexpliquée.
- `BRIDGE_AGENT_DOC.md` (§19.3, §19.7) : documentation du nouveau journal et
  de son rôle diagnostique.
- Aucun test dédié ajouté : vérification manuelle (écritures normales,
  simulation d'une corruption suivie d'une réinitialisation, exécution de
  `archiver_historique.py`) dans un dossier temporaire isolé, hors du
  périmètre du projet — cf. rapport de clôture de l'issue.

## 2 septembre 2026 — issue #516

Champ `RELANCE` dans `issues_inbox/` : corriger/relancer une issue
`needs-human` sans repasser par une édition manuelle sur GitHub. Jusqu'ici,
ajuster un `TIMEOUT` trop court après un échec par dépassement obligeait à
sortir du flux `issues_inbox` — redéposer un `.txt` avec le même titre
échouait systématiquement (anti-doublon §3.4, qui rejette tout titre déjà
porté par une issue OUVERTE, `needs-human` incluse).
- `scripts/watcher_issues_inbox.py` : nouveau champ d'en-tête optionnel
  `| RELANCE | #N |` (en cohérence avec `SUITE_DE`, §6). Présent, il
  détourne tout le bloc vers la correction de l'issue #N déjà ouverte —
  aucune création, anti-doublon court-circuité (n'a de sens que pour une
  création). Validation avant modification (`valider_relance`,
  `_recuperer_issue`) : `PROJET` résout le dépôt cible, `RELANCE` doit être
  un numéro exploitable, `gh issue view --repo` confirme l'existence et
  l'appartenance au bon dépôt, l'issue doit être OUVERTE — sinon rejet vers
  `rejected/`, même mécanique que les rejets existants. Champs corrigibles
  dans le corps : `TIMEOUT` et `MODELE` uniquement (`_fusionner_entete`/
  `_maj_ligne_entete` — corrige une ligne déjà présente, n'en insère jamais
  une nouvelle). `MODE` est exclu (le mode réel est armé par le label GitHub
  `mode_write`/`mode_scratch`, pas par le texte du corps — le
  resynchroniser depuis ce chemin est jugé hors-scope pour cette première
  itération) ; `LABELS` aussi (n'apparaît jamais dans le corps).
- `app/interruption.py` : logique de `route_relancer()` (bouton
  « 🔄 Relancer », issue #460) extraite dans `relancer_issue(depot, numero,
  commentaire=...)`, réutilisée telle quelle par le champ `RELANCE` — aucun
  retrait de label / pose de commentaire dupliqué entre les deux flux. Le
  commentaire posté depuis `issues_inbox/` mentionne explicitement RELANCE,
  résume les champs corrigés et reprend le texte libre éventuel du fichier
  déposé.
- `BRIDGE_AGENT_DOC.md` : nouveau §3.14, ligne `RELANCE` ajoutée au tableau
  §6.
- `tests/test_champ_relance_516.py` (nouveau) : extraction du champ,
  parsing du numéro, fusion des champs corrigibles (jamais d'insertion d'un
  champ absent), chemin complet `_traiter_relance` (succès, issue fermée,
  numéro invalide) — tous les appels `gh` substitués, aucun accès réseau.
- Formulaire web (`new_issue.py`) volontairement non modifié : il sert à
  **créer** des issues et dispose déjà d'un chemin dédié pour cibler une
  issue existante (bouton « 🔄 Relancer ») — dupliquer `RELANCE` là
  n'apporterait rien.

## 30 août 2026 — issue #509

Panneau Infrastructure — bouton « Retirer needs-human » sur l'issue
sélectionnée : demande déjà entièrement couverte par l'issue #460
(commit `8dec213`, fusionné dans `master` avant #509). Vérification faite
que le bouton « 🔄 Relancer » de `#pl-zone-actions`
(`rendrePanneauLateralActions()`, `static/js/app.js`) remplit exactement
le besoin décrit : visible uniquement quand l'issue sélectionnée porte le
label `needs-human` et est ouverte, retire ce label via `gh issue edit
--remove-label` (route `POST /relancer-issue`,
`app/interruption.py::route_relancer`, même mécanisme `--add-label`/
`--remove-label` que `app/issues.py::modifier_label_notif`), ne ferme pas
l'issue, poste un commentaire de trace, puis rafraîchit la liste et le
détail sans rechargement manuel complet. Aucune modification de code
nécessaire.
- `BRIDGE_AGENT_DOC.md` : ajout de la sous-section « Relancer une issue
  bloquée en `needs-human` (issue #460, cf. #509) » (juste après
  « Interrompre une issue bloquée »), qui manquait — seul point réellement
  manquant identifié pour cette issue.

## #507 — CONTEXTE.md : correction de deux mentions obsolètes de "VM Windows"

`CONTEXTE.md` mentionnait encore « VM Windows » à deux endroits (description
du module `app/ccw` et entrée changelog §16), alors que la migration vers un
PC fixe physique est actée depuis longtemps (`BRIDGE_AGENT_DOC.md` §16,
issue #446). Remplacé par « PC Windows physique », cohérent avec le
vocabulaire de `BRIDGE_AGENT_DOC.md`. Vérifié qu'aucune autre mention de VM
ne subsiste dans le fichier.

## #506 — eval-expiration.json : correction date d'installation Windows PC fixe (2026-08-30)

`provisioning/windows/eval-expiration.json` contenait déjà `date_installation:
2026-08-17` / `date_expiration: 2026-11-15` (mis à jour par le fix #452, le
2026-08-18) — pas les valeurs `2026-07-19`/`2026-10-17` que l'issue supposait.
La mesure fraîche du 30 août 2026 fournie dans l'issue (`GracePeriodRemaining`
= 111244 min ≈ 77,25 j restants) recalcule une expiration au **2026-11-15**
et une installation au **2026-08-17** — exactement les valeurs déjà en place.
Aucune modification du JSON n'était donc nécessaire.

En revanche, `BRIDGE_AGENT_DOC.md` §16.1 (tableau « Repères de dates »)
n'avait pas été mis à jour lors du fix #452 et affichait encore les
anciennes dates de la VM. Corrigé :
- « Date d'installation Windows » : 2026-07-19 → **2026-08-17**
- « Expiration éval Windows (90 j) » : 2026-10-17 → **2026-11-15**

Non touché (hors périmètre de l'issue) :
- §16, tableau `provisioning/windows/` (ligne `eval-expiration.json`) :
  mentions 2026-07-19/2026-10-17 explicitement présentées comme historique
  de l'ancienne VM VirtualBox (issue #167), conservées telles quelles.
- §16.1, ligne « Expiration token GitHub » (≈ 2026-10-17) : concerne
  l'expiration d'un token GitHub fine-grained réel, non recalculable depuis
  la mesure Windows fournie — signalé pour vérification manuelle éventuelle,
  non modifié.

## #501 — finaliser_projet_ccw.ps1 : clarification du prompt de confirmation du token

Le message `Read-Host 'Appuie sur Entrée une fois le token créé et copié'` prêtait à
confusion : il pouvait être lu comme une demande de coller le token à cet endroit,
alors qu'il ne fait qu'attendre une touche Entrée pour continuer — le vrai collage
du token a lieu juste après, dans `mettre_a_jour_tokens_ccw.ps1` (« Collez la valeur
de GH_TOKEN »). Un utilisateur a déjà collé son token par erreur à cette invite.

Reformulé en : `'Ne colle RIEN ici : une fois le token créé et copié, appuie juste
sur Entrée pour continuer (le collage se fera à l'étape suivante)'`.

Le script personnel `creer_projet_ccw_complet.ps1` (hors dépôt officiel) n'est pas
accessible depuis ce worktree — la même formulation cohérente y est recommandée
manuellement si un message similaire y existe.

## 18 août 2026 — issue #454

FEATURE — Bandeau d'avertissement d'échéance de l'éval Windows CCW dans
`new_issue.py`.
- `app/eval_windows.py` (nouveau) : `etat_eval_windows()` lit
  `provisioning/windows/eval-expiration.json`, recalcule la date
  d'expiration (`date_installation` + `eval_jours`, même logique que
  `provisioning/windows/verifier_expiration_ccw.py`) et retourne `None`
  si le fichier est absent/invalide ou si l'échéance est encore lointaine
  (> 14 jours), sinon un état `{jours_restants, date_expiration, niveau,
  message}` avec `niveau` = `orange` (≤ 14 j) ou `rouge` (≤ 5 j ou
  échéance dépassée).
- `app/vues.py` : la route `index()` passe `eval_windows=etat_eval_windows()`
  au gabarit.
- `templates/index.html` : bandeau `{% if eval_windows %}` inséré juste
  après l'en-tête, en dehors des panneaux d'onglets → visible sur tous
  les onglets sans dupliquer le HTML.
- `static/css/style.css` : styles `.bandeau-eval-windows.orange` (fond
  `#fff3cd`) et `.rouge` (fond `#f8d7da`), cohérents avec les couleurs
  d'alerte déjà utilisées ailleurs dans l'interface.
- Vérifié par test manuel (`create_app()` + `test_client`) avec état
  forcé orange/rouge/absent : bandeau présent avec le bon texte et la
  bonne classe, absent quand l'échéance est lointaine (cas réel actuel :
  89 jours restants au 18/08/2026) ou quand le fichier est absent/invalide.

## 18 août 2026 — issue #452

CONFIG — `provisioning/windows/eval-expiration.json` mis à jour pour
refléter l'échéance réelle du PC fixe physique (remplaçant l'ancienne VM
VirtualBox, cf. #449/#450), installé le 17 août 2026.
- `date_installation` : `2026-07-19` → `2026-08-17`.
- `date_expiration` : `2026-10-17` → `2026-11-15` (date_installation +
  eval_jours = 90 jours, conforme à la note du fichier).

## 18 août 2026 — issue #451

DOC — nouveau fichier `provisioning/windows/REINSTALLATION_CCW.md` :
procédure complète de réinstallation du PC fixe CCW, aux côtés des scripts
qu'elle utilise (`autounattend.xml`, `provisionner.ps1`,
`mettre_a_jour_tokens_ccw.ps1`), plutôt que dans `BRIDGE_AGENT_DOC.md` qui
est destiné aux agents CCL/CCW et non à la procédure d'installation
Windows. Couvre dans l'ordre : réinstallation Windows via
`autounattend.xml`, configuration SSH (`configurer_ssh_ccw.ps1`),
vérification de la connexion SSH depuis CCL, provisioning logiciel
(`provisionner.ps1`), topic ntfy + tokens
(`mettre_a_jour_tokens_ccw.ps1`), vérification du service `CCW-Watcher`.
Précise que la clé privée CCL (`~/.ssh/ccl_ccw`) reste sur le ThinkPad
entre les réinstallations — seule la clé publique est à réinstaller sur le
nouveau Windows.
- `BRIDGE_AGENT_DOC.md` : §16 complété d'une ligne de référence vers ce
  nouveau fichier.

**Point d'attention signalé (pas corrigé, hors périmètre de cette
issue) :** `configurer_ssh_ccw.ps1`, référencé à l'étape 2 de la
procédure, n'existe pas dans `provisioning/windows/` au moment de la
rédaction — il devra être créé (script PowerShell côté Windows qui active
OpenSSH Server et installe la clé publique fournie dans
`authorized_keys`) avant que l'étape 2 soit exécutable telle quelle. Une
note l'indique en bas du nouveau fichier.

## 7 septembre 2026 — issue #518

DOC — retrait de toute mention du copier-coller comme méthode de création
d'issue à partir de contenu produit par Claude Chat, dans
`BRIDGE_AGENT_DOC.md`. Depuis #483, Claude Chat ne doit produire que des
fichiers `.txt` déposés dans `issues_inbox/` (§3) ; la doc présentait
encore, notamment au §20, le copier-coller dans le formulaire web comme un
usage normal pour du contenu de Claude Chat.
- §20 : le bloc « Format du corps pour copier-coller depuis Claude Chat »
  et son exemple sont reformulés en « Format du corps reconnu par le
  formulaire » — présenté comme un format de saisie manuelle (Alain) plutôt
  que comme une cible de copier-coller. « Envoi en lot (plusieurs issues
  d'un seul copier-coller) » renommé « Envoi en lot (plusieurs issues dans
  un même corps) ». Le bloc « Convention de présentation côté Claude Chat »
  (issues #153/#443) devient « Regroupement des blocs pour le mode lot » et
  précise explicitement que Claude Chat ne doit plus jamais produire de
  texte destiné à être copié-collé dans ce formulaire. Mentions résiduelles
  de « corps collé » reformulées en « corps du formulaire »/« corps saisi
  dans le champ ».
- §11 (conventions de code) : la règle « Alain colle le tout dans le champ
  Corps de new_issue.py — un seul copier-coller » remplacée par un renvoi
  au flux `issues_inbox/` (§3).
- §3.3 : « Même format qu'une issue produite par Claude Chat pour le
  formulaire web (§20) » reformulé en « Même format que celui reconnu par
  le formulaire web (§20) », pour ne plus laisser entendre que Claude Chat
  produit du contenu pour ce formulaire.
- Usages légitimes du formulaire web laissés inchangés : aperçu de la
  commande `gh issue create` avant envoi, création manuelle par Alain
  directement depuis l'interface, repli si le watcher `issues_inbox` est
  indisponible.
- Pied de page de `BRIDGE_AGENT_DOC.md` mis à jour (glissement des trois
  dernières entrées d'un cran, la plus ancienne sort du pied de page).

## 25 août 2026 — issue #483

Watcher `issues_inbox` centralisé + onglet « Résultats inbox » : nouveau
flux de création d'issues sans passage par le formulaire web. La
volumétrie d'issues créées à la main (copier-coller depuis Claude Chat
dans `new_issue.py`) montait et demandait des allers-retours ; ce watcher
automatise le dépôt → création → nettoyage.
- `scripts/watcher_issues_inbox.py` (nouveau) : scrute
  `~/Bridge_Agent/issues_inbox/` en continu (polling, 5s par défaut),
  parse l'en-tête de chaque fichier `.txt` (`PROJET`, `TIMEOUT`, `MODELE`,
  `MODE`, `LABELS`, `#Titre:` — mêmes regex que `static/js/app.js`), valide
  (`PROJET` existe dans `configs/`, titre non vide, `MODELE`/`TIMEOUT`
  bien formés si fournis), crée l'issue via `gh issue create` (même
  format de body/labels que `app/issues.py`), supprime le fichier traité.
  Fichier invalide ou échec de `gh` → déplacé vers `issues_inbox/rejected/`
  (suffixe `__REJETE-<motif>`), jamais retraité automatiquement. Ignore un
  fichier modifié il y a moins d'1s (protection contre une lecture en
  cours d'écriture). Dossiers `issues_inbox/` et `issues_inbox/rejected/`
  créés automatiquement au premier lancement. Config optionnelle
  `configs/watcher_issues_inbox.conf` (non créée par CCL — garde-fou §11 :
  CCL ne modifie/crée jamais `configs/*.conf`, à créer à la main par Alain
  s'il veut surcharger les défauts).
- Journalisation : `logs/issues_inbox.log`, une ligne par traitement
  (`<horodatage> | <projet> | OK|REJECTED | <titre>`), rotation par
  **nombre de lignes** (défaut 50 — distincte de la rotation par taille
  des autres watchers).
- `app/issues_inbox.py` (nouveau) : route `GET /issues-inbox/etat`, pure
  lecture disque (aucun appel `gh`) — renvoie l'état de `rejected/`
  (déclenche l'alarme) et les dernières lignes du log (historique
  informatif, sans effet sur l'alarme).
- `templates/index.html` / `static/js/app.js` / `static/css/style.css` :
  nouvel onglet « Résultats inbox », badge 🚨 clignotant sur l'onglet
  piloté **uniquement** par la présence de fichiers dans
  `issues_inbox/rejected/` (jamais par un parsing de log), tableau des
  fichiers rejetés (nom + date), historique de log affiché à titre
  informatif, rafraîchissement en polling continu (7s, indépendant de
  l'onglet actif) + bouton « Rafraîchir ».
- `.gitignore` : ajout de `issues_inbox/` (état transitoire, pas du code).
- `BRIDGE_AGENT_DOC.md` : nouveau §20 « Watcher `issues_inbox` centralisé »
  (structure disque, format de fichier, validation, journalisation,
  concurrence, config, onglet web, workflow utilisateur final) ; §10
  (structure du dépôt) complété avec `app/issues_inbox.py` et
  `issues_inbox/`. Pied de page mis à jour (glissement des trois dernières
  entrées d'un cran, la plus ancienne — #435 — sort du pied de page).

## 13 août 2026 — issue #443

DOC — extension de la convention de présentation des issues (issue #153)
au cas mono-issue. Le §3 de `BRIDGE_AGENT_DOC.md` ne formulait la règle du
bloc de code unique que pour le mode lot ; en pratique Claude Chat enveloppe
aussi une issue unique dans un bloc de code afin qu'Alain puisse utiliser le
bouton copier du bloc, mais ce n'était pas explicite dans la doc.
- `BRIDGE_AGENT_DOC.md` : §3 « Convention de présentation côté Claude Chat
  (issue #153) » complétée pour couvrir explicitement le cas mono-issue —
  une issue unique est elle aussi présentée dans un bloc de code, pas
  seulement un lot de plusieurs issues.
- `BRIDGE_AGENT_DOC.md` : §11 « Conventions de code », bullet « Issues »,
  précise désormais que le corps est toujours présenté dans un bloc de
  code, qu'il s'agisse d'une issue seule ou d'un lot.
- Pied de page mis à jour (glissement des trois dernières entrées d'un
  cran).

## 10 août 2026 — issue #434

Champ `COMPLEXITE` dans les issues : 4e dimension de la clé EWMA de
calibration TIMEOUT. La clé `projet|TYPE|mode` mélangeait des populations
incompatibles (ex. une issue de doc de 250s et une refonte de 1800s dans
la même case).
- `watcher.py` : nouvelle fonction `extraire_complexite(body)` (même
  pattern que `extraire_timeout`/`extraire_modele`) — lit `| COMPLEXITE |
  ... |` dans l'en-tête, valeurs reconnues `rapide`/`court`/`normal`/`lourd`
  (insensible à la casse), toute valeur non reconnue ou champ absent →
  `normal`. `_cle_combinaison()` prend désormais un 4e paramètre
  `complexite` et produit `f"{projet}|{type_issue}|{mode}|{complexite}"`
  au lieu de `f"{projet}|{type_issue}|{mode}"`. `maj_calibration_timeout()`
  et `lire_timeout_suggere()` reçoivent un nouveau paramètre optionnel
  `complexite` (défaut `"normal"`) répercuté dans la clé ; les trois sites
  d'appel (succès, tentative expirée, échec définitif) calculent
  `extraire_complexite(body)` au même endroit que `deduire_type_issue`/
  `_etiquette_calibration` et le transmettent. Nouvelles clés distinctes
  par complexité — l'historique existant (sans ce champ) n'est pas
  affecté, recalibration progressive.
- `consignes/globales.md` : nouvelle consigne demandant à CCL/CCW d'inclure
  `| COMPLEXITE | <niveau> |` dans l'en-tête de toute issue chef/ouvrier
  qu'il crée lui-même. Ne concerne pas les issues rédigées par Claude
  Chat — géré côté doc/prompt, hors de ce fichier.
- `BRIDGE_AGENT_DOC.md` : §6 (table des champs spéciaux) documente le
  nouveau champ `COMPLEXITE` ; §19.1 et §19.3 (calibration TIMEOUT)
  mentionnent son rôle de 4e dimension de la clé EWMA et le changement de
  format de la clé dans `etat_timeout.json`.

## 10 août 2026 — issue #432

Alerte accumulation de worktrees : depuis l'issue #337, les worktrees
créés pour la parallélisation mode_write ne sont jamais supprimés
automatiquement (nettoyage manuel par Alain) et pouvaient s'accumuler
silencieusement, sans aucun signal.
- `watcher.py` : nouvelle fonction `_lister_worktrees_secondaires()`
  (parse `git worktree list --porcelain` dans `REP_TRAVAIL`, exclut le
  worktree principal) et `verifier_accumulation_worktrees()`, appelée en
  début de chaque cycle de polling juste après `rafraichir_depot()`
  (`git pull --ff-only`). Au-delà de `SEUIL_ALERTE_WORKTREES` worktrees
  secondaires actifs (nouvelle clé `.conf`, entier, défaut **3**),
  émet un `log.warning` listant chemin + branche de chacun — visible
  dans l'onglet Journal watcher de l'interface. En dessous du seuil,
  silence total ; clé absente du `.conf` → défaut 3, aucune erreur.
  Pas de notification ntfy/bureau, volontairement — un warning dans le
  log suffit.
- `WORKTREES.md` (§5) et `BRIDGE_AGENT_DOC.md` (§13, sous-section
  parallélisation mode_write) documentent le mécanisme ; la limite
  « pas d'alerte sur l'accumulation de worktrees » de `WORKTREES.md`
  §5 est levée.

## 8 août 2026 — issue #401

Onglet Résultats : les titres des issues ne s'alignaient pas horizontalement,
la zone d'icônes à gauche (case à cocher, pastille, badges Diff/All, etc.)
ayant une largeur variable selon le nombre d'icônes présents sur chaque ligne.
- `static/css/style.css` : `.ligne-issue .ligne-gauche` (préfixe type/OS +
  badges ✏️/✅/⚠️/○/Diff/All + pastille projet) reçoit un `min-width:130px`
  — largeur fixe couvrant le cas le plus chargé (chef/ouvrier + for-windows +
  mode_write+done+Diff+All), tous les titres démarrent désormais à la même
  position, les icônes restant alignées à gauche (flex-start).

## 7 août 2026 — issue #389

Fix `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x82` lors de la
finalisation d'un projet CCW : la sortie de `powershell.exe` exécuté dans
la VM invitée est encodée en CP1252 (page de code Windows par défaut), pas
en UTF-8.
- `app/ccw.py` : `_executer_ps` et `_executer_commande_ps` (même schéma —
  toutes deux lancent `powershell.exe` via `guestcontrol run`) décodent
  désormais `stdout`/`stderr` en `encoding="cp1252"` avec `errors="replace"`
  en filet de sécurité, au lieu de `text=True` (UTF-8 implicite côté hôte
  Linux). `_copier` (guestcontrol `copyto`, ne lance aucun processus dans
  la VM) n'était pas concernée, laissée inchangée.

## 6 août 2026 — issue #384

Panneau flottant actions : toggles `notif_pc`/`notif_gsm`/`notif_tous` sur
l'issue sélectionnée, sans passer par GitHub — ces labels peuvent être
modifiés pendant le traitement, le watcher les relit au moment de la
clôture.
- Nouvelle route `POST /modifier-label-notif` (`app/issues.py`,
  `modifier_label_notif`) : `gh issue edit --add-label`/`--remove-label`
  selon `actif`, whitelist stricte sur `notif_pc`/`notif_gsm`/`notif_tous`
  (constantes `LABEL_NOTIF_*` de `watcher.py`, réutilisées telles quelles) —
  aucun autre label ne peut être modifié via cette route. Protégée par
  `login_requis`, enregistrée dans `app/__init__.py`.
- `rendrePanneauLateralActions()` (`static/js/app.js`) : bloc « 🔔
  Notifications » (3 checkboxes) inséré sous le mode de l'issue, affiché
  seulement si l'issue est interrompible (ouverte, ni `done` ni
  `needs-human` — même condition que les boutons d'interruption). État
  initial coché/décoché lu depuis `listeIssuesResultats`. Au clic :
  appel `/modifier-label-notif`, mise à jour locale de
  `listeIssuesResultats` + re-rendu du panneau si succès ; en cas
  d'échec, la checkbox revient à son état précédent et un message
  d'erreur discret (`#pl-notif-erreur`, sans `alert()`) s'affiche puis
  s'efface après 4 s.
- CSS : `.pl-notifs`/`.pl-notifs-titre`/`.pl-notif-ligne`/`.pl-notif-erreur`
  (`static/css/style.css`).

## 6 août 2026 — issue #383

Correctif suite #381/#382 : les pastilles de notification des boutons de
filtre projet comptaient les issues **OPEN** ni `done` ni `needs-human`
(état GitHub), au lieu des issues **décochées** localement — la case à
cocher libre (issue #154), persistée en `localStorage` via
`cleCocheResultat`/`estResultatCoche`, indépendante de l'état GitHub.
- `majPastillesFiltres()` : remplacement du filtre `state`/labels
  (`OPEN`/`done`/`needs-human`) par `estResultatCoche(it.projet, it.number)`
  — une issue est comptée si elle n'est PAS cochée, quel que soit son état
  GitHub. Le filtre GitHub est supprimé entièrement (une issue décochée
  reste décochée quel que soit son état). La portée courante
  (`limiteIssuesProjet()`, issue #382) est conservée inchangée.
- Effet de bord nécessaire : ni `basculerCocheResultat()` (case individuelle)
  ni `cocherToutesVisibles()` (bouton « Tout cocher ») n'appelaient
  `majPastillesFiltres()` — sans ce fix, une pastille basée sur les cases
  restait figée jusqu'au prochain rendu complet de la liste après un clic
  sur une case. Ajout de l'appel dans les deux fonctions pour un
  rafraîchissement immédiat.
- Fichier touché : `static/js/app.js` (`majPastillesFiltres`,
  `basculerCocheResultat`, `cocherToutesVisibles`).

## 6 août 2026 — issue #382

Correctif suite #381 : les pastilles de notification des boutons de filtre
projet ne respectaient pas la portée courante.
- Investigation des deux causes suspectées par l'issue : l'attribut
  `data-projet` posé sur `.filtre-projet` (`construireBoutonsFiltre`) et
  l'ordre d'appel de `majPastillesFiltres()` après le peuplement de
  `listeIssuesResultats` (`appliquerListeIssues`, `rendreListeIssues`,
  `remplacerLigneIssue`) étaient déjà corrects — aucune des deux ne causait
  l'absence de pastilles.
- **Cause réelle** : `majPastillesFiltres()` comptait sur la totalité de
  `listeIssuesResultats`, sans tenir compte de la portée du champ
  « par projet : N » (`limiteIssuesProjet()`) — un compte pouvant dépasser ce
  que l'utilisateur voit réellement dans la liste dès que N est abaissé sans
  cliquer sur ↻ (la saisie seule n'invalide que le cache, pas les données déjà
  en mémoire). Le comptage se limite désormais aux N premières issues de
  chaque projet (même lecture de la limite que le téléchargement), avant
  d'appliquer le filtre ouvert/ni-done/ni-needs-human.
- Fichier touché : `static/js/app.js` (`majPastillesFiltres`).

## 6 août 2026 — issue #381

Améliorations de confort du panneau flottant (suite #380), sans changement
de layout ni de mécanique existante :
- **Monitoring watchers CCL** (`rendrePanneauLateralMonitoring`) : bouton
  global renommé « ↺ Relancer tous les éteints » → « ▶ Lancer les éteints »
  + nouveau bouton « ↺ Relancer tous les CCL » (`sidebarRelancerTousCCL`) qui
  relance TOUS les watchers CCL, actifs ou éteints — même mécanique que
  `sidebarRelancerTousEteints` mais sans filtrer sur l'état. Les deux boutons
  sont côte à côte (`.pl-boutons-ccl`).
- **Résumé par projet** (`resumeProjetMonitoring`) : sous chaque watcher CCL,
  une ligne « X en cours, Y en file » (`.pl-sous-projet`) — calculée
  uniquement depuis les données déjà en mémoire (`listeIssuesResultats` +
  `timingIssues`), sans nouveau fetch réseau automatique (pour ne pas
  reproduire la surconsommation de quota gh déjà corrigée par l'issue #270).
  Horodatage « Mis à jour à HH:MM:SS » ajouté en bas du monitoring.
- **Zone actions** (`rendrePanneauLateralActions`) : mode de l'issue
  sélectionnée affiché en haut (« 📖 Lecture seule » / « ✏️ Lecture active » /
  « ⚠️ Écriture », `libelleModeIssue`, lu depuis les labels via
  `modeEcritureDepuisLabels`) ; nouveau bouton « ⛔ Interrompre et relancer
  (watcher CCL/CCW) » (`interrompreEtRelancer`) qui enchaîne `/interrompre`
  puis la relance du watcher adapté au label de l'issue (for-linux → CCL,
  for-windows → CCW) — l'ancien bouton « ⛔ Interrompre l'issue » reste en
  dessous ; nouveau bouton « ✖ Fermer l'issue » quand l'issue porte le label
  `needs-human`, réutilisant exactement la route `/fermer-issue` déjà câblée
  par `fermerIssue()` dans le détail. `interrompreIssue()` retourne désormais
  un booléen de succès (annulation/échec → false) pour permettre à
  `interrompreEtRelancer()` de savoir s'il doit enchaîner sur la relance.
- **Pastilles de notification** (`majPastillesFiltres`) sur les boutons de
  filtre projet (`.filtres-projets`) : petit badge rouge (`.pastille-notif`)
  affichant le nombre d'issues ouvertes ni `done` ni `needs-human` du projet,
  visible même quand son filtre est masqué. Calcul purement local depuis
  `listeIssuesResultats`, rafraîchi à chaque (re)rendu de la liste
  (`rendreListeIssues`, `remplacerLigneIssue`, `construireBoutonsFiltre`).
- **Bouton « ✓ Cocher tout »** (`cocherToutesVisibles`) dans la barre de
  filtres, à côté du bouton rafraîchir : coche toutes les issues actuellement
  visibles (projet filtré, ou tous si filtre « Tous »), en réutilisant le
  mécanisme de case à cocher existant (issue #154, localStorage +
  `.resultat-traite`).
- Fichiers touchés : `static/js/app.js`, `static/css/style.css`.

## 6 août 2026 — issue #380

Refonte du panneau latéral de l'onglet Résultats (#375/#376/#377) en
**panneau flottant** (`position:fixed`, `.panneau-lateral`,
`static/css/style.css`), lisible et extensible :
- **Layout** : l'ancien layout flex `.resultats-layout` / `.resultats-liste-col`
  (colonne fixe 280px) est retiré — la liste des issues reprend toute la
  largeur. Le panneau devient un overlay ~360px, max-height 80vh scrollable,
  ombre portée, coin haut-droit. Nouveau bouton toggle fixe `#pl-toggle`
  (« 📊 Infrastructure », `basculerPanneauLateral`) toujours visible dans
  l'onglet, qui ouvre/ferme le panneau. Ouvert par défaut à chaque entrée
  dans l'onglet (`ouvrirPanneauLateralParDefaut`), sauf écran étroit
  (< 900px) où il reste fermé par défaut.
- **Monitoring lisible** (`rendrePanneauLateralMonitoring`, `static/js/app.js`) :
  fini les pastilles colorées par projet, illisibles en 280px — chaque
  watcher CCL a désormais sa propre ligne (`🟢`/`⚫` + nom + bouton individuel
  « ▶ Lancer » ou « ↺ Relancer », noir et blanc, sans couleur projet), même
  format pour les services CCW connus. VM CCW en ligne unique
  (« 🟢 VM allumée » / « 🔴 VM éteinte » + bouton Démarrer si éteinte). Bouton
  « ↺ Relancer tous les éteints » conservé si au moins un watcher CCL est
  éteint. Fonctions `pastillesInline`/`couleurEtatCcw` (obsolètes) retirées.
- **Zone réservée** `#pl-zone-extras` (`.pl-zone-extras`, vide, s'efface via
  `:empty` tant qu'inutilisée) ajoutée entre le monitoring et les actions
  contextuelles, prête à accueillir de futurs boutons sans restructurer le
  panneau — non remplie par cette issue.
- Zone actions contextuelles (`rendrePanneauLateralActions`) inchangée sur le
  fond, seule sa position dans le panneau flottant change.
- CSS : classes `.pl-chip`/`.pl-chips`/`.pl-dot`/`.pl-etat`/`.pl-synthese`
  devenues inutiles retirées, remplacées par `.pl-ligne`/`.pl-ligne-libelle`/
  `.pl-btn-mini`.

## 6 août 2026 — issue #377

Panneau latéral de l'onglet Résultats (#375/#376) : les deux états
mutuellement exclusifs (monitoring OU actions) deviennent **deux zones
empilées non exclusives**, chacune dans son propre conteneur DOM
(`#pl-zone-monitoring` / `#pl-zone-actions`, sous `#panneau-lateral-resultats`,
`templates/index.html`) :
- **Zone haute — monitoring, toujours visible**, même issue sélectionnée
  (`rendrePanneauLateralMonitoring`, `static/js/app.js`) : VM CCW inchangée ;
  watchers CCL désormais colorés **par projet** (`couleurProjetResultats`,
  et non plus vert/rouge générique — pastille sombre `#33322f` = éteint,
  couleur vive du projet = actif) avec un nouveau bouton « ↺ Relancer tous les
  éteints » (`sidebarRelancerTousEteints`) qui relit `/watchers` au clic puis
  relance séquentiellement, un par un via `/lancer-watcher`, chaque watcher
  éteint (une relance en échec n'interrompt pas les suivantes) ; services CCW
  inchangés. Le détail par projet (`.pl-projet`, pid, état CCW ligne par
  ligne) est retiré : redondant avec les pastilles par projet ci-dessus et
  avec la pastille projet désormais sur chaque ligne de résultat (voir
  ci-dessous).
- **Zone basse — actions contextuelles, visible uniquement si une issue est
  sélectionnée** (`rendrePanneauLateralActions`), avec un séparateur
  `<hr class="pl-sep">` et un titre unique « Actions — `<projet>` #`<numero>` »
  (fusion de l'ancien titre + de la référence séparée). Se vide (donc
  disparaît entièrement, séparateur compris) dès qu'aucune ligne n'est
  sélectionnée, au lieu de remplacer le monitoring. Boutons inchangés sur le
  fond (relancer watcher CCL, interrompre l'issue si ouverte et ni `done` ni
  `needs-human`, relancer watcher CCW, verrous CCW désactivé en attendant
  #378), icône de relance alignée sur celle du monitoring (« ↺ » au lieu de
  « 🔁 »).
- `rafraichirPanneauLateralResultats()` rend désormais TOUJOURS le monitoring
  puis (re)rend/vide les actions, au lieu de choisir l'un OU l'autre — appelé
  sans changement par le SSE `fin_issue`, l'intervalle 30s et chaque
  changement de sélection de ligne.

La pastille colorée de projet sur chaque ligne de résultat
(`.pastille-ligne`, `construireLigneIssueDOM`) existait déjà (issue #66,
héritée de l'extraction du frontend) et couvrait déjà le besoin exprimé par
cette issue pour le filtre « Tous » — aucune modification nécessaire sur ce
point, vérifié seulement.

CSS (`static/css/style.css`) : classes `.pl-projet`, `.pl-projet-nom` et
`.pl-issue-ref` retirées (plus aucun appelant après la restructuration) ;
`.pl-synthese`, `.pl-chips`, `.pl-btn-vm`, `.pl-sep`, `.pl-actions`
inchangées, réutilisées telles quelles par les deux zones.

## 6 août 2026 — issue #376

Panneau monitoring de l'onglet Résultats (`rendrePanneauLateralMonitoring`,
`static/js/app.js`) : ajout d'une **vue synthétique de l'infrastructure** en
tête du panneau, avant le détail par projet (inchangé, désormais sous un
séparateur `<hr class="pl-sep">` titré « Détail par projet »). Trois blocs de
résumé, dans un encadré `.pl-synthese` :
- **VM CCW** — état allumée (pastille verte) / éteinte (rouge) / inconnu
  (gris), lu via l'endpoint existant `/ccw/vm-statut` (VBoxManage local, pas de
  guestcontrol) fetché en parallèle de `/watchers` (`Promise.all`). Si la VM est
  éteinte, un bouton « ▶ Démarrer la VM » appelle `/ccw/demarrer-vm`
  (`sidebarDemarrerVm`, même endpoint que le bouton de l'onglet CCW) puis
  re-rend le panneau.
- **Watchers CCL** — une ligne « N/M watchers CCL actifs » + liste inline des
  projets actifs (pastille verte) et éteints (rouge), sans répéter le détail du
  dessous (`pastillesInline`, `.pl-chips`).
- **Services CCW** — affiché seulement si `ccwProjetsConnus` est non vide :
  « N/M services CCW running » + liste inline ; sinon le lien « Vérifier les
  services CCW » existant. Le lien « Actualiser les services CCW » (cas connu)
  reste sous le détail.

Nouvelles classes CSS `.pl-synthese`, `.pl-resume-titre`, `.pl-chips`,
`.pl-chip`, `.pl-btn-vm`, `.pl-sep` (`static/css/style.css`). Aucun nouveau
polling réseau : la synthèse réutilise les fetchs locaux déjà en place et
`ccwProjetsConnus` (alimenté uniquement à la demande par `ccwChargerProjets`).

## 6 août 2026 — issue #375

Onglet Résultats : panneau latéral droit (~280px, scrollable, repasse sous la
liste en écran étroit) ajouté à droite de la liste des issues
(`.resultats-layout` / `.resultats-liste-col` / `.panneau-lateral`), qui
utilisait mal l'espace disponible dans la fenêtre (`.fenetre` élargie
860→1160px pour l'accueillir sans écraser la liste). Deux états, pilotés par
la sélection de ligne existante (`selectionnerLigne`) :
- **Aucune issue sélectionnée** : monitoring passif, tous les projets actifs —
  watcher CCL (actif/pid via `/watchers`, appel Flask local) et watcher CCW
  (état NSSM) pour les projets ayant un service CCW connu. Rafraîchi toutes
  les 30s et à chaque événement SSE `fin_issue` (#350), sans appel GitHub
  supplémentaire.
- **Issue sélectionnée** : actions contextuelles — relancer le watcher CCL
  (`/lancer-watcher`, comme l'onglet Watchers), interrompre l'issue (bouton
  identique à celui du détail, `/interrompre`, affiché seulement si l'issue
  est ouverte et ni `done` ni `needs-human`), relancer le watcher CCW
  (`ccwRedemarrerProjet`, réutilisée telle quelle depuis l'onglet CCW) et un
  emplacement pour « Nettoyer verrous CCW + redémarrer », désactivé en
  attendant l'issue #378 — ces deux derniers boutons seulement si le projet a
  un service CCW connu.
- L'état des services CCW (`ccwProjetsConnus`) n'est JAMAIS interrogé
  directement par ce panneau (guestcontrol coûteux) : il ne fait que lire le
  résultat du dernier appel à `ccwChargerProjets()` (onglet CCW ou lien
  manuel « Vérifier les services CCW » du panneau) — aucun nouveau polling.
- Aucune route Flask ajoutée : tout reprend les endpoints existants
  (`/watchers`, `/lancer-watcher`, `/interrompre`, `/ccw/projets`,
  `/ccw/redemarrer-projet`).

## 3 août 2026 — issue #370

Script PowerShell `surveiller_builds.ps1` (issu d'une session Claude Chat
précédente) committé dans `provisioning/windows/` : surveille en temps réel,
pendant un build CCW (PyInstaller/ISCC), les processus de build et la
croissance du dossier de sortie (taille + delta par passage et depuis le
début). Paramètre `-Dossier` obligatoire, `-Processus` et
`-IntervalleSecondes` optionnels. Documenté au §16 de `BRIDGE_AGENT_DOC.md`
(tableau de provisioning), avec la note que le nom de process Claude Code
(`claude` par défaut) reste à confirmer via `Get-Process` pendant un build
réel.

## 3 août 2026 — issue #352

Le POST `/notifier-fin-issue` (#350) était déclenché via `notifications.bip()`,
donc uniquement pour les issues portant un label `notif_pc`/`notif_gsm`/
`notif_tous` — le rafraîchissement SSE de l'onglet Résultats restait soumis
au ↻ manuel pour toutes les autres. Il doit être universel, indépendamment
des labels notif.

- `watcher.py` : import direct de `scripts/traitement_fin.py` (ajout de
  `scripts/` au `sys.path`, ce dossier n'étant pas un package) et nouvelle
  enveloppe `notifier_fin_sse(numero)` qui appelle
  `traitement_fin.notifier_fin_issue(CFG.nom, numero)` sans passer par
  `notifier()`/`bip()` — donc sans dépendre des labels `notif_*`. Appelée
  dans `_traiter_issue_synchrone` aux trois points de fin définitive d'une
  issue : succès, échec définitif (garde-fou lecture active niveau 2, issue
  #327), échec définitif après épuisement des tentatives (`max_essais`, non
  critique). Non appelée sur les fins non définitives (retry différé d'une
  issue critique, commentaire de résultat non posté) — l'issue reste ouverte
  et sera retraitée.
- Le bip et les labels `notif_*` restent inchangés — seul le POST est
  découplé, comme demandé par l'issue.

## 3 août 2026 — issue #350

Renommage de `scripts/bip.py` en `scripts/traitement_fin.py` et ajout d'un
canal SSE de rafraîchissement instantané (< 1 s) de l'onglet Résultats, sans
polling supplémentaire.

- `scripts/traitement_fin.py` : après le bip habituel, POST **best-effort**
  (timeout 1 s, échec silencieux si `new_issue.py` n'est pas lancé) vers
  `http://localhost:5100/notifier-fin-issue` avec `{"projet": ..., "numero": ...}`,
  lus depuis deux nouveaux arguments CLI `--projet`/`--numero`. La clé de
  config reste `SCRIPT_BIP` (renommer la clé impliquerait de modifier les
  `configs/*.conf` gitignorés, hors périmètre agent) — **Alain doit mettre à
  jour manuellement le chemin dans ses `configs/*.conf` existants**
  (`.../scripts/bip.py` → `.../scripts/traitement_fin.py`).
- `notifications.py` (`bip()`/`notifier()`) et les enveloppes correspondantes
  de `watcher.py` et `app/notifications_poller.py` : ajout d'un paramètre
  `numero` transmis en CLI au script, pour que le POST identifie précisément
  l'issue concernée. Comme le bip lui-même, ce déclenchement reste opt-in via
  les labels `notif_*` — sans label, la ligne reste soumise au ↻ manuel ou au
  fetch post-TIMEOUT de #334.
- `app/fin_issue.py` (nouveau module) : route `POST /notifier-fin-issue`
  (sans authentification, appelée par le script local) qui pousse un
  événement SSE `event: fin_issue\ndata: {"projet": ..., "numero": ...}` à
  tous les onglets Résultats ouverts, et route `GET /stream` (protégée par
  `login_requis`) qui les diffuse — une `queue.Queue` par connexion active
  (ajoutée/retirée de `app.config["FIN_ISSUE_ABONNES"]`), pas de broadcast
  global, car plusieurs onglets peuvent être ouverts simultanément. Ping
  `: ping\n\n` toutes les 30 s pour maintenir la connexion ; nettoyage propre
  de l'abonné à la déconnexion (`GeneratorExit`).
- `static/js/app.js` : `demarrerStreamFinIssue()`/`arreterStreamFinIssue()`
  ouvrent/ferment un `EventSource('/stream')` à l'entrée/sortie de l'onglet
  Résultats (`basculerOnglet`). Sur réception d'un événement `fin_issue` dont
  le numéro figure dans `listeIssuesResultats`, réutilise directement
  `verifierIssueApresDepassement()` (issue #334) — même fetch de vérification,
  même `remplacerLigneIssue()`, sans dupliquer la logique. Reconnexion
  automatique gérée nativement par `EventSource`.
- `BRIDGE_AGENT_DOC.md` : §17 mis à jour (mentions de `bip.py` →
  `traitement_fin.py`), nouvelle sous-section 17.3 documentant le mécanisme
  SSE complet.
- Testé sans `new_issue.py` lancé (bip normal, POST en échec silencieux,
  aucune exception) et avec un client de test Flask (`app.test_client()`) :
  `POST /notifier-fin-issue` livre bien l'événement à une connexion
  `GET /stream` active, et la liste des abonnés est correctement nettoyée à
  la déconnexion.

## 2 août 2026 — issue #343

`WORKTREES.md` §3 « Workflow normal d'Alain » (étape 3) et §4
« Procédures de récupération » : précisions suite à un cas vécu lors du
premier workflow complet avec worktrees (issues #340/#341, session du
02/08/2026) — `fusionner_changelog.py` lancé depuis `master` avant le
merge n'a rien trouvé, car le script scanne la racine du dépôt qu'on lui
indique et `CHANGELOG-341.md` n'existait alors qu'à la racine du
worktree ; le fichier s'est donc retrouvé dans `master` via le merge
sans être intégré, nécessitant un commit de rattrapage. L'étape 3
documente désormais l'ordre impératif (script avant merge) et deux
méthodes : lancer `--repo .` depuis le worktree lui-même (recommandé),
ou copier `CHANGELOG-<N>.md` dans master avant de fusionner depuis
`REP_TRAVAIL`. Le §4 précise la procédure de rattrapage si le merge a
eu lieu avant le script (relancer le script depuis `REP_TRAVAIL`,
vérifier `git diff CHANGELOG.md`, committer).

## 2 août 2026 — issue #341

Ajout dans `TACHES.md`, juste après le bloc d'en-tête, d'une section
« Worktrees en production — points de surveillance » listant les deux
limites connues restantes après correction de #340 : pas d'alerte sur
l'accumulation de worktrees (nettoyage manuel requis) et
`issues_en_cours` sans verrou explicite inter-process.

## 2 août 2026 — issue #342

§11 « Conventions de code » de `BRIDGE_AGENT_DOC.md` : deux notes ajoutées
pour informer les projets utilisant Bridge_Agent des conséquences
pratiques de la parallélisation `mode_write` par worktrees (issue #337),
jusqu'ici documentée uniquement pour l'infrastructure elle-même (§13 du
DOC, `WORKTREES.md`). Première note : deux issues `mode_write` touchant
les mêmes fichiers ou zones de code peuvent désormais générer un conflit
de merge à résoudre manuellement — recommandation de scoper chaque issue
sur un périmètre de fichiers aussi distinct que possible. Deuxième note :
le workflow de vérification/push d'Alain inclut désormais deux étapes
supplémentaires après une ou plusieurs issues `mode_write` en parallèle —
`git worktree list` pour repérer les worktrees à traiter,
`python3 scripts/fusionner_changelog.py` avant tout merge ou push (intègre
les `CHANGELOG-N.md` des worktrees dans `CHANGELOG.md`), puis merge manuel
de chaque branche `worktree-issue-<N>` et nettoyage
(`git worktree remove` + `git branch -d`) ; renvoi vers `WORKTREES.md` pour
le détail complet plutôt qu'une duplication intégrale. Pied de page du DOC
mis à jour en conséquence (glissement des trois entrées, #327 sort du pied
de page).

## 2 août 2026 — issue #340

Suite #338 : le bouton ⛔ « Interrompre » (`app/interruption.py::interrompre_linux()`)
nettoie désormais aussi les verrous des worktrees actifs, pas seulement
celui de `REP_TRAVAIL`. Nouvelle fonction `_lister_worktrees_actifs()` :
scanne le répertoire parent de `REP_TRAVAIL` à la recherche de
répertoires frères `<NOM_PROJET>-issue<N>` (même convention que
`_chemin_worktree` dans `watcher.py`) ; pour chacun, le chemin de verrou
est recalculé via `_chemin_verrou()` (déjà importé de `watcher.py`) et le
fichier `.lock` supprimé s'il existe — uniquement une fois l'arbre de
process confirmé mort, même garde-fou que pour le verrou de
`REP_TRAVAIL`. Ces suppressions apparaissent dans le rapport de statut
renvoyé à l'interface (une étape `suppression_verrou_worktree_<nom>` par
worktree détecté, ou `suppression_verrous_worktrees` en `rien_a_faire`
si aucun). `WORKTREES.md` §4 mis à jour : la limite « verrou non libéré »
documentée depuis #338 est corrigée, plus besoin d'intervention manuelle
après un « Interrompre » pendant qu'un worktree tournait.

## 2 août 2026 — issue #339

Nettoyage de `TACHES.md` : suppression de trois items devenus obsolètes.
« Parallélisation en mode_write via git worktrees » est implémenté depuis
l'issue #337. « Rafraîchir une seule fois la ligne d'une issue quand son
décompte atteint zéro » est implémenté depuis l'issue #334. « Concurrence
limitée aux issues mode_lecture » est abandonné : le cas d'usage est trop
rare pour justifier une implémentation séparée, et le sujet sera
naturellement couvert par le système de worktrees si le besoin se
confirme. Restent inchangés : « Projet dédié à la communication CCL ↔
CCW » et « Calibration automatique du TIMEOUT — trois défauts à
corriger ».

## 2 août 2026 — issue #338

Documentation dédiée à la parallélisation mode_write via git worktrees
(#337) : nouveau fichier `WORKTREES.md` à la racine du dépôt, distinct de
`BRIDGE_AGENT_DOC.md` (manuel commun à tous les projets) pour ne pas
l'alourdir d'internals d'infrastructure. Couvre le pourquoi du mécanisme,
son design (`MAX_WRITE_PARALLELE`, premier slot sans worktree, verrou par
chemin de travail effectif, auto-extinction différée), le workflow normal
d'Alain (création d'issues, `git worktree list`, `fusionner_changelog.py`
avant merge, merge manuel branche par branche, nettoyage
`git worktree remove` + `git branch -d`), les procédures de récupération
(worktree orphelin, verrou non libéré — y compris la limite du bouton
« Interrompre », qui ne nettoie que le verrou de `REP_TRAVAIL` et pas ceux
des worktrees actifs —, `CHANGELOG-N.md` oublié, conflit de merge) et les
limites connues (`issues_en_cours` sans verrou explicite, pas d'alerte sur
l'accumulation de worktrees, `mode_lecture`/`mode_scratch` non
parallélisés). `BRIDGE_AGENT_DOC.md` §13 pointe désormais vers ce nouveau
fichier juste sous sa sous-section worktrees existante.

## 2 août 2026 — issue #337

Parallélisation des issues `mode_write` via `git worktree` : `watcher.py`
peut désormais traiter plusieurs tâches d'écriture **en parallèle**, chacune
dans un répertoire isolé sur sa propre branche, au lieu du traitement
strictement séquentiel historique. Les issues `mode_lecture`/`mode_scratch`
restent traitées séquentiellement dans `REP_TRAVAIL`, inchangées.

- Nouvelle clé `.conf` `MAX_WRITE_PARALLELE` (entier, défaut `2`) : nombre
  maximum de tâches `mode_write` concurrentes. `1` (ou `0`) = comportement
  séquentiel historique intégral, aucun thread ni worktree créé.
- `traiter_issue` (nouveau point d'entrée public) décide, pour chaque issue
  `mode_write` prête, entre traitement séquentiel classique et
  parallélisation : la première tâche détectée sans autre `mode_write` déjà
  en cours est dispatchée dans un thread ciblant `REP_TRAVAIL` directement
  (sans worktree, nécessaire pour que la boucle principale reste libre de
  détecter une deuxième tâche pendant que la première tourne) ; les
  suivantes, sous `MAX_WRITE_PARALLELE`, obtiennent chacune un worktree
  dédié (`<REP_TRAVAIL>/../<PROJET>-issue<N>`, branche
  `worktree-issue-<N>`, créés via `git worktree add`). Le corps de
  traitement existant (`_traiter_issue_synchrone`) est inchangé, à
  l'exception du chemin de travail effectif qu'il reçoit désormais en
  paramètre.
- Liste thread-safe (`threading.Lock` + liste) des tâches `mode_write`
  actuellement en thread (numéro, chemin du worktree ou `None`, thread
  Python), purgée des threads terminés à chaque décision de dispatch et en
  tête de boucle principale.
- Garde-fous à la création du worktree : chemin ou branche déjà existants,
  ou tout autre échec de `git worktree add` → repli propre sur le
  traitement séquentiel (l'issue attend qu'un slot se libère), jamais
  d'exception propagée.
- `lancer_claude` reçoit `chemin_worktree` : injecte dans le prompt, en
  worktree uniquement, un bloc d'avertissement (chemin, branche, consigne
  d'écrire l'entrée changelog dans `CHANGELOG-<N>.md` plutôt que
  `CHANGELOG.md` — voir `scripts/fusionner_changelog.py`, issue #336).
  Toutes les opérations déjà paramétrées par `cwd`/`perimetre` (backup,
  clause de périmètre du prompt, opérations git de garde-fou) reçoivent
  déjà le chemin de travail effectif (worktree ou `REP_TRAVAIL`) — aucun
  changement de signature nécessaire sur ces fonctions.
- Verrou anti-collision (#189/#322) posé par le chemin de travail effectif
  de la tâche (`REP_TRAVAIL` ou le worktree), et non plus systématiquement
  par `REP_TRAVAIL` seul : deux worktrees du même projet obtiennent deux
  verrous distincts et tournent sans s'attendre l'un l'autre.
- Fin de tâche en worktree : **aucune suppression automatique** (ni
  `git worktree remove`, ni suppression de branche) — Alain merge et pousse
  manuellement une fois le travail relu. Numéro d'issue, chemin du worktree
  et branche journalisés clairement.
- Auto-extinction (#199/#200) : ne se déclenche plus tant qu'un thread
  `mode_write` tourne encore, même au-delà de `DELAI_INACTIVITE_MIN` —
  réévaluée à chaque cycle.
- `BRIDGE_AGENT_DOC.md` §13 documente le mécanisme et `MAX_WRITE_PARALLELE`.
- Test de non-régression `tests/test_worktree_parallelisation_337.py` :
  nommage chemin/branche, création + replis (chemin/branche déjà pris),
  purge des threads terminés, scénario de bout en bout à deux issues
  `mode_write` concurrentes (première dans `REP_TRAVAIL`, seconde dans un
  worktree dédié, worktree conservé après coup), et non-régression avec
  `MAX_WRITE_PARALLELE = 1`.

## 2 août 2026 — issue #336

Création de `scripts/fusionner_changelog.py`, en préparation du futur
système de worktrees : quand CCL travaillera dans un répertoire isolé, il
écrira son entrée CHANGELOG dans `CHANGELOG-<N>.md` (N = numéro de l'issue)
plutôt que dans `CHANGELOG.md` directement, pour éviter les conflits
systématiques sur ce fichier unique quand plusieurs issues mode_write
tournent en parallèle. Ce script fusionne ces fichiers dans `CHANGELOG.md`
avant le push d'Alain.

- Scanne la racine du dépôt (`--repo`, défaut `.`) à la recherche de
  fichiers `CHANGELOG-<N>.md`, les trie par N décroissant (plus récent en
  tête, cohérent avec la convention de `CHANGELOG.md`, issue #252), et
  insère leur contenu tel quel en tête de `CHANGELOG.md`, juste après
  l'en-tête fixe (jusqu'à la ligne vide qui suit « Convention d'ajout :
  ... »). Les fichiers traités sont ensuite supprimés.
- Aucun `CHANGELOG-<N>.md` trouvé : message et sortie propre (code 0),
  `CHANGELOG.md` laissé inchangé — propriété qui rend une seconde exécution
  sans nouveaux fichiers idempotente de fait, puisque les sources du
  premier passage ont déjà été supprimées. Vérifié par test manuel (fichiers
  factices `CHANGELOG-338.md`/`CHANGELOG-340.md` dans un dépôt temporaire,
  hors du dépôt réel) : fusion correcte dans l'ordre #340 puis #338,
  suppression des fichiers sources, relance sans effet.
- Pas encore appelé automatiquement par `watcher.py` — le système de
  worktrees qui produira des `CHANGELOG-<N>.md` n'existe pas encore ;
  lancement manuel uniquement pour l'instant.

## 2 août 2026 — issue #335

Correction du radio Mode qui restait parfois figé sur « Lecture seule » après
un collage, alors que le corps collé portait bien `| MODE | écriture |` —
symptôme intermittent, corrigé par un simple F5 puis re-collage (observé à la
suite des issues #157 et suivantes).

- Cause racine : `viderFormulaire()` (appelée après chaque envoi réussi) remet
  le radio Mode sur *lecture* mais ne réinitialisait pas `dernierModeAutoDetecte`,
  la variable de garde de `detecterModeDansCorps()` (#326) qui évite de réécraser
  un choix manuel quand « rien de neuf » n'est détecté dans le corps. Si le
  corps collé ensuite portait le MÊME MODE que la détection précédente,
  `detecterModeDansCorps` voyait `valeurDetectee === dernierModeAutoDetecte` et
  ne touchait plus au radio — qui restait donc sur *lecture*, alors que ce
  n'était pas un choix manuel d'Alain mais le défaut posé de force par
  `viderFormulaire()` (qui vide aussi le corps par affectation directe de
  `.value`, sans déclencher d'événement `input`, donc sans repasser par la
  détection). Un rafraîchissement de page réinitialise cette variable JS à
  `null`, ce qui « corrigeait » silencieusement le symptôme au collage suivant.
- `static/js/app.js` (`viderFormulaire`) : ajout de `dernierModeAutoDetecte =
  null;` juste après la remise à *lecture* du radio, pour que le prochain
  collage soit toujours traité comme une détection neuve, quelle que soit la
  valeur MODE précédemment vue dans la session.
- Non modifié : `detecterProjetDansCorps`/`detecterTimeoutDansCorps`
  partagent le même schéma de garde-fou (`dernierProjetAutoDetecte`,
  `dernierTimeoutAutoDetecte`) et pourraient présenter la même faille — hors
  périmètre de cette issue, à traiter séparément si observé en pratique.

## 2 août 2026 — issue #334

Onglet Résultats : fetch unique de vérification 15s après le dépassement du
décompte TIMEOUT d'une issue — le watcher a besoin de quelques secondes après
son TIMEOUT pour poster le diagnostic et fermer l'issue ; jusqu'ici, la ligne
restait figée sur « ⌛ 0s — budget épuisé » même une fois l'issue close côté
serveur, jusqu'au prochain ↻ manuel. L'idée du `TACHES.md` (fetch au décompte
UI/médiane) est abandonnée au profit du décompte TIMEOUT réel, déjà présent
côté client, comme déclencheur — plus simple et plus fiable. Zéro polling
ajouté : un seul appel réseau par issue, une seule fois.

- `static/js/app.js` : dès que `formaterBadgeTempsRestant()` atteint la
  branche « budget épuisé », `programmerFetchDepassement()` pose un unique
  `setTimeout` de 15s (`DELAI_FETCH_DEPASSEMENT_MS`) qui appelle
  `verifierIssueApresDepassement()` — fetch de `/issue/<projet>/<numero>`
  (route existante). Un `Set` (`issuesFetchDepassementProgrammees`) garde-fou
  garantit une seule programmation par issue, même si le composant est
  rendu plusieurs fois (rendu de liste, tick/s de `majBadgesTempsRestant`).
- Issue fermée (`done`/`needs-human`) au moment du fetch : la ligne est mise
  à jour normalement (badge terminal, retrait du décompte), comme un ↻
  manuel restreint à cette seule ligne — nouvelle fonction
  `remplacerLigneIssue()`, qui reconstruit la ligne DOM via
  `construireLigneIssueDOM()` et rebranche ses gestes (clic/ctrl+clic/
  double-clic) via `brancherEvenementsLigneIssue()`, extraite de
  `rendreListeIssues()` pour être partagée sans dupliquer le câblage.
- Issue encore ouverte au moment du fetch (cas marginal de timing) : le
  badge devient « ⌛ dépassement — rafraîchir ↻ » (mémorisé dans le Set
  `issuesDepassementVerifie`, relu par `formaterBadgeTempsRestant`) et
  aucun autre fetch automatique n'est reprogrammé pour cette issue.

## 2 août 2026 — issue #333

Documentation : les deux boutons ⛔ « Interrompre » (CCL et CCW, issue
#323) sont désormais implémentés et fonctionnels — mise à jour de
`BRIDGE_AGENT_DOC.md` en conséquence, plus de renvoi mort vers
`TACHES.md`.

- `BRIDGE_AGENT_DOC.md`, §16.4 « Interrompre une issue CCW coincée » : la
  Note « un bouton [...] est prévu [...] (voir `TACHES.md`) » est
  remplacée par une description au présent de `interrompre_windows()`
  (`app/interruption.py`) : copie et exécution à distance (`VBoxManage
  guestcontrol`) de `provisioning/windows/interrompre_projet_ccw.ps1` —
  arrêt du service NSSM, vérification bornée (~5 s) que l'arbre de
  process est mort, suppression conditionnelle des `.lock` de
  `<RepDepot>\logs\verrous\`, label `needs-human` + commentaire de
  traçabilité systématiques, watcher jamais relancé automatiquement.
- `BRIDGE_AGENT_DOC.md`, §13 « Commandes utiles » : nouvelle sous-section
  « Interrompre une issue bloquée (issue #323, suite #320) », même niveau
  de détail que §16.4, pour le pendant côté CCL (`interrompre_linux()`) :
  arbre de process retrouvé par remontée `/proc/<pid>/status` (PPID),
  `SIGKILL`, attente de confirmation avant suppression du verrou —
  équivalent manuel (`kill -9` + suppression du `.lock`) inclus.
- `BRIDGE_AGENT_DOC.md`, pied de page : ligne « Dernière mise à jour »
  mise à jour (nouvelle entrée en tête, l'entrée #318 sort).
- Aucun changement de code — documentation uniquement.

## 2 août 2026 — issue #332

Le bouton « ⛔ Interrompre cette issue » (#323) tue par SIGKILL sans
prévenir que, si l'issue écrivait, le working tree du projet peut rester
PARTIEL (fichier à moitié écrit, backup présent sans le fix) — rien n'est
perdu ni poussé, mais l'état n'est pas nettoyé automatiquement et il faut
l'inspecter avant de relancer quoi que ce soit dessus.

- `static/js/app.js` — `interrompreIssue` : nouvelle `modeEcritureDepuisLabels`
  (mêmes labels que le pastillage `prefixeIssue`, ligne ~606, étendue à
  `mode_scratch`) détecte si l'issue écrivait (`mode_write` → 'ecriture',
  `mode_scratch` → 'lecture_active', aucun des deux → lecture seule, pas
  d'avertissement). Nouvelle `avertissementWorkingTree` formule le message
  (texte différent pour écriture pleine et pour lecture active — nuance :
  le garde-fou de restauration #327 tourne APRÈS claude, donc peut ne pas
  s'être exécuté avant un kill en pleine lecture active).
- Confirmation AVANT le kill (`confirm()`) : enrichie avec l'avertissement
  quand l'issue écrit — dernier moment pour renoncer. Comportement
  inchangé pour une issue en lecture seule.
- Modal de résultat APRÈS (`ouvrirModalInterrompre`, `modal-interrompre-rappel`) :
  reçoit désormais l'avertissement en paramètre et l'ajoute au rappel
  existant (relance manuelle du watcher) — `git status` dans le projet,
  annuler/repartir du commit `avant-XXX`, ne pas relancer d'issue sur ce
  projet avant working tree propre.

## 2 août 2026 — issue #330

Documentation du champ d'en-tête `MODE`, jusqu'ici absent de
`BRIDGE_AGENT_DOC.md` alors qu'il est auto-détecté depuis #326.

- **§3** — ajout de `MODE` à la liste des champs d'en-tête optionnels
  reconnus, avec un paragraphe dédié : `| MODE | … |` est détecté par
  `new_issue.py` (`detecterModeDansCorps`) exactement comme
  `TIMEOUT`/`PROJET`/`MODELE` — pré-sélectionne le radio Mode du
  formulaire puis la ligne est retirée du corps collé. Reconnaissance
  tolérante (insensible casse/accents, plusieurs libellés par valeur) et
  défaut LECTURE si le champ est absent ou non reconnu.
- **§6** — ajout d'une ligne `MODE` au tableau des champs spéciaux :
  valeurs `lecture`/`écriture`, effet (arme ou non le label `mode_write`
  via le radio du formulaire), renvoi au §5 pour le comportement des
  modes.
- **Ligne ~172 (§3, envoi en lot)** — précision : en mono-issue `MODE`
  est auto-détecté depuis l'en-tête du bloc, alors qu'en mode lot il
  reste commun à tout le lot (choisi une fois au radio du formulaire,
  jamais lu bloc par bloc).
- Volontairement **hors périmètre** : la troisième valeur (« lecture
  active » / `mode_scratch`) n'est PAS ajoutée à ces deux endroits — elle
  reste documentée uniquement au §5 (issue #327), car cette issue ne
  documente que les deux valeurs fonctionnelles au sens de la détection
  `new_issue.py`/formulaire.
- Pied de page de `BRIDGE_AGENT_DOC.md` mis à jour selon la convention
  §10 (nouvelle entrée en tête, glissement des deux précédentes ; l'entrée
  #299 sort du pied de page — déjà disponible dans `CHANGELOG.md`).

## 2 août 2026 — issue #327

Implémentation du mode « lecture active » (`mode_scratch`) côté
`watcher.py` — préparé formulaire/en-tête par #326, resté volontairement
inactif (une issue `mode_scratch` sans `mode_write` était traitée comme
lecture seule). Écriture confinée pour les outils d'analyse qui exigent un
vrai fichier de config sur disque (linters, eslint flat config ≥ 9, ...),
impossible à satisfaire en lecture seule.

**Mode à trois valeurs, plus un booléen empilé.** `autoriser_ecriture: bool`
pilotait CINQ points de décision (flag `--dangerously-skip-permissions`,
bloc de garde-fou du prompt, backup, garde-fou `configs/*.conf` #318,
étiquette de calibration TIMEOUT) — insuffisant pour un 3e mode. Remplacé
par `MODE_LECTURE`/`MODE_LECTURE_ACTIVE`/`MODE_ECRITURE` (nouvelle constante
`LABEL_SCRATCH = "mode_scratch"`), déduits des labels par la nouvelle
`_deduire_mode` (priorité `mode_write` > `mode_scratch` > lecture seule par
défaut) et lus par les cinq points ci-dessus — un futur 4e mode n'ajoutera
qu'une valeur, pas cinq retouches éparses. `lancer_claude` prend désormais
`mode` (plus `autoriser_ecriture`) et `chemin_scratch` ; les deux tests
existants qui l'appelaient directement (`test_nettoyage_arbre_247.py`,
`test_orphelin_verrou_perime_322.py`) sont mis à jour en conséquence.

**Chemin scratch** : `/tmp/bridge_scratch_<projet>/` (`<projet>` = `CFG.nom`,
validé strictement — aucun `../`, aucun séparateur de chemin — jamais dérivé
d'une valeur fournie par l'issue). Créé par le watcher juste avant le
premier lancement de claude en lecture active, supprimé dans un `finally`
(succès/échec/timeout confondus, même esprit que `_nettoyer_arbre_claude`).

**Défense en profondeur, niveau 1 + niveau 2** (même schéma que le
garde-fou `configs/*.conf`, #318) :
- **Niveau 1 (prompt)** : nouveau bloc de garde-fou dédié dans
  `lancer_claude`, distinct des deux blocs existants — chemin scratch exact,
  interdiction d'écrire ailleurs (notamment REP_TRAVAIL), interdiction de
  `git commit`/`git push`/commande destructrice, rappel que le scratch est
  éphémère et que le livrable reste un rapport de lecture.
  `--dangerously-skip-permissions` est ajouté (la lecture active doit
  pouvoir écrire dans le scratch), désarmant les mêmes protections claude
  que l'écriture libre — d'où le niveau 2.
- **Niveau 2 (détection technique a posteriori)** : nouvelles
  `_statut_git_rep_travail`/`_restaurer_rep_travail_modifie`, sur le modèle
  de `_empreinte_configs`/`_restaurer_configs_modifies` (#318) — empreinte de
  `git status --porcelain -uall` sur REP_TRAVAIL avant la première tentative,
  comparée après chaque tentative. Toute écriture détectée (fichier modifié,
  neuf ou supprimé) est restaurée (`git checkout`/`git clean` ciblés) et
  l'issue est marquée en échec définitif (`needs-human`, pas de nouvelle
  tentative) avec un message explicite. Le scratch (`/tmp`, hors REP_TRAVAIL)
  n'apparaît jamais dans cette empreinte par construction, donc n'est jamais
  emporté par la restauration.

**Backup et garde-fou configs** : aucun backup projet en lecture active
(comme la lecture seule — le filet est le niveau 2, pas un commit de
sauvegarde). Le garde-fou technique `configs/*.conf` (#318) est étendu : il
s'armait uniquement en mode écriture, il couvre désormais aussi la lecture
active (`mode != MODE_LECTURE`), cohérent avec le fait que ce mode arme
aussi `--dangerously-skip-permissions`.

**Calibration (§19)** : nouvelle étiquette `"scratch"` (fonction
`_etiquette_calibration`), distincte de `"read"`/`"write"`, appliquée aux
trois points de calibration (succès, timeout, échec définitif) —
`etat_timeout.json` et `historique_durees.json` gagnent une population
`projet|TYPE|scratch` propre, pour ne pas refaire le mélange de populations
que #326 avait corrigé côté UI. `app/issues.py` (estimation de durée d'une
issue ouverte, badge de progression) mis à jour en cohérence : `mode_scratch`
y était jusqu'ici classé à tort dans la population `"read"`.

`templates/index.html` : le radio « Lecture active » n'est plus marqué
« réservé » (le mode est désormais fonctionnel) ; `app/issues.py` (table
`MODES`) et le commentaire près de `LABEL_ECRITURE`/`LABEL_SCRATCH` dans
`watcher.py` mis à jour en conséquence.

Tests (`tests/test_lecture_active_327.py`, faux `claude` **et** faux `gh`,
aucun appel réseau) : déduction du mode depuis les labels (les quatre cas,
priorité `mode_write` > `mode_scratch`) ; validation stricte de
`_chemin_scratch` ; traitement complet (`traiter_issue`) d'une lecture
active qui n'écrit que dans le scratch → succès, REP_TRAVAIL inchangé,
scratch nettoyé ; traitement complet d'une lecture active qui écrit dans le
projet hors scratch → détecté, restauré (fichier modifié restauré à son
contenu d'origine, fichier neuf supprimé), `needs-human` posé, jamais
`done`.

`TACHES.md` : entrée « mode_scratch » retirée (implémentée).

## 2 août 2026 — issue #326

Détection automatique du MODE dans l'en-tête + mode à valeurs extensibles,
préparation lecture active/mode_scratch (issue #326). Deux problèmes réglés
ensemble : (1) contrairement à TIMEOUT/PROJET/titre, le champ `| MODE | … |`
était GÉNÉRÉ à l'envoi mais jamais LU depuis le corps collé — Alain cochait
« écriture » à la main par habitude même pour des tâches en réalité en
lecture seule, ce qui rangeait des lectures dans la population « write » et
faussait la calibration TIMEOUT (§19, clé projet|TYPE|mode) ; (2) le mode
était un booléen en dur (`autoriser_ecriture` déduit du seul label
`mode_write`), incapable de porter un futur 3e mode.

Frontend (`static/js/app.js`) : nouveau `detecterModeDansCorps`, calqué sur
`detecterTimeoutDansCorps`, branché sur l'input du corps — lit `| MODE | … |`
via `lireChampEntete` (aucune regex dupliquée), reconnaît la valeur de façon
tolérante (casse/accents, plusieurs libellés par mode : « écriture »/
« write »/`mode_write` ; « lecture active »/« scratch »/`mode_scratch` ;
« lecture »/« lecture seule »/« read »/`mode_read`), coche le bon radio,
retire la ligne MODE du corps (comme TIMEOUT/PROJET) et met à jour la
couleur du bouton d'envoi. **MODE absent ou non reconnu → LECTURE forcée**
(défaut sûr, cohérent avec le reset après envoi). Neutralisé en mode lot
(le MODE reste commun à tout le lot, DOC §3, inchangé).

`templates/index.html` : 3e radio `lecture_active` entre lecture et
écriture (ordre du moins au plus permissif), badge « scratch (mode_scratch,
réservé) » + tooltip précisant que ce mode n'est pas encore fonctionnel côté
watcher. Bouton d'envoi à 3 couleurs (`COULEURS_MODE`) : lecture → noir,
lecture active → bleu, écriture → rouge (inchangé, réservé à l'écriture
pleine, la plus risquée).

`app/issues.py` : nouvelle table `MODES` ({valeur radio → (libellé
français, label GitHub)}) lue à la fois par `construire_body` (champ
`| MODE | … |`) et `construire_labels` (pose du label technique) — remplace
les deux tests booléens en dur (`"ÉCRITURE" if mode == "ecriture" …` /
`if mode == "ecriture": labels.append("mode_write")`). Un futur 4e mode ne
demande qu'une ligne dans cette table.

**`mode_scratch` reste RÉSERVÉ, watcher.py non touché** : cette issue ne
porte pas l'implémentation de la lecture active côté watcher (issue séparée
à venir) — juste documenté (commentaire près de `LABEL_ECRITURE`) qu'une
issue portant `mode_scratch` sans `mode_write` est traitée comme lecture
seule par le watcher actuel (`autoriser_ecriture` ne teste que
`LABEL_ECRITURE`), comportement sûr. Backlog `TACHES.md` renommé en
cohérence (`mode_tmp_write` → `mode_scratch`, vocabulaire retenu par #326).

## 2 août 2026 — issue #325

Retrait de `TACHES.md` de l'entrée backlog « Bouton Interrompre dans
l'onglet CCW » (procédure manuelle nssm restart + suppression des
`.lock`), désormais implémentée — et dépassée — par #323 (suite #320) :
le bouton « ⛔ Interrompre cette issue » a été ajouté dans l'onglet
Résultats, pas l'onglet CCW, et couvre CCL comme CCW. Même convention de
retrait que #317 (retiré par #321) et les entrées PERIMETRE (#319) :
suppression pure de la section obsolète, rien d'autre touché.

## 2 août 2026 — issue #324

Ajout au backlog `TACHES.md` d'une entrée (pas d'implémentation) :
« Rafraîchir une seule fois la ligne d'une issue quand son décompte atteint
zéro ». Née d'une session où le décompte figé côté navigateur
(`majBadgesTempsRestant`, jamais re-fetché depuis #270) a fait douter à
répétition de l'état réel d'issues déjà closes (#320/#322/#323). Idée :
au passage à « ⌛ 0s — budget épuisé », déclencher UN SEUL fetch ciblé de
l'issue via la route existante `/issue/<projet>/<numero>` (`issue_detail`)
plutôt qu'un re-fetch périodique de toutes les issues comme avant #270 —
distinction explicitée dans l'entrée pour qu'une future implémentation ne
réintroduise pas le polling banni par #270 (~3840 pts/h de quota GraphQL,
cf. #263). Point de conception laissé ouvert : comportement au dépassement
légitime (re-fetch à intervalle long vs. badge « rafraîchir » manuel), avec
anti-abus à prévoir si l'option de re-fetch est retenue.

## 2 août 2026 — issue #323 (suite #320)

Bouton **« ⛔ Interrompre cette issue »** dans l'onglet Résultats, sur toute
issue ouverte ni `done` ni `needs-human` — remplace l'intervention manuelle
hors interface (kill + nettoyage de verrou à la main) qu'exigeait jusqu'ici
un watcher bloqué (verrou orphelin, process pendu). Reprise de #320,
abandonnée 3 fois faute de `TIMEOUT` suffisant (600s ne couvrait pas
`watcher.py` + route Flask + logique CCW + modal front) ; `TIMEOUT` porté à
1800s pour cette reprise. **Contrainte centrale** : interrompre UNE issue ne
sacrifie jamais les autres issues en file pour le même watcher — elles
restent ouvertes sur GitHub, simplement en attente d'une relance MANUELLE
(bouton « Lancer watcher » côté CCL, onglet CCW côté CCW-Watcher ; aucun
rallumage automatique ici, à la différence de #202).

- Nouvelle route **`POST /interrompre`** (`app/interruption.py`) : reçoit
  `{depot, numero, labels}`, résout le projet via `projet_par_depot` (nouveau
  dans `app/projets.py`) — **toujours par le champ DEPOT du `.conf`**, jamais
  déduit du nom projet ni du basename de `REP_TRAVAIL` (trois clés distinctes
  qui peuvent diverger, ex. projet « echecs » / dépôt `AlChess` / répertoire
  `~/NicLink`). Chaque étape renvoie un statut à **trois valeurs**
  (`succes`/`rien_a_faire`/`echec`) + message ; une étape en échec n'arrête
  pas les suivantes, sauf la suppression du verrou, volontairement **sautée**
  si l'arbre de process n'est pas confirmé mort. Statut global dérivé : `ok`
  / `succes_partiel` / `echec_critique` (arbre non tué → lock **non**
  nettoyé, pour ne jamais risquer un double traitement). Label `needs-human`
  + commentaire `⛔ Interrompu via new_issue.py` posés dans TOUS les cas
  (sortie du circuit + trace), avant même le résultat des étapes techniques.
  - **for-linux** : arbre de process du watcher (`logs/watcher-<nom>.pid` +
    toute sa descendance, dont l'éventuel claude en session séparée,
    §13/#247) énuméré par **remontée `/proc` via PPID** — jamais par nom
    d'exécutable — puis `SIGKILL`, attente bornée (~5s) de disparition
    effective avant de supprimer le verrou par **nom exact**
    (`watcher._chemin_verrou` réutilisée telle quelle, jamais redupliquée),
    puis re-vérification (verrou frais réapparu → signalé comme course #202
    probable, jamais resupprimé en boucle). Piège découvert en testant :
    le process watcher est un enfant DIRECT du process Flask
    (`app/watchers.py:demarrer_watcher`) jamais attendu (`wait()`) — après
    `SIGKILL` il reste **zombie** et `os.kill(pid, 0)` le signale encore
    vivant indéfiniment ; `_reaper_best_effort` (`os.waitpid(..., WNOHANG)`)
    corrige ce faux positif. `FileNotFoundError` sur le verrou = `rien_a_faire`
    (libéré normalement), pas un échec.
  - **for-windows** : nouveau script `provisioning/windows/
    interrompre_projet_ccw.ps1` (poussé + exécuté via guestcontrol, pattern
    `app/ccw.py` — service et répertoire du projet résolus dynamiquement via
    `_lister_projets_vm`, jamais codés en dur malgré l'exemple `CCW-Watcher`
    / `C:\CCW\Bridge_Agent` de l'issue) : arrêt du service NSSM, vérification
    + kill ciblé de l'arbre resté vivant (remontée par `ParentProcessId`,
    même logique PPID que côté Linux), suppression des `.lock` du dossier
    `logs\verrous` du projet **seulement** si l'arbre est confirmé mort.
    Non exécuté contre une VM réelle (pas d'environnement CCW disponible ici
    — comme `finaliser_projet_ccw.ps1` en son temps).
- `templates/index.html` / `static/js/app.js` : bouton `interrompreIssue()`
  dans `construireHtmlIssue` (dépôt lu depuis le `<select id="projet">`
  peuplé côté serveur « nom — depot », jamais déduit du nom ; labels lus
  depuis le cache localStorage du détail déjà affiché). Modal dédiée
  (`#modal-interrompre`) détaillant **chaque étape** (statut + message), pas
  seulement le résultat global, avec rappel de la relance manuelle adapté à
  l'agent (CCL vs CCW) et alerte explicite en cas de `succes_partiel` /
  `echec_critique` (« vérifier avec ps/Gestionnaire des tâches avant de
  relancer »). Avertissement discret si la VM CCW n'est pas démarrée
  (`vm_running` dans la réponse).
- Testé (hors modal/CCW, sans VM disponible) : arbre de process réel
  (`sh` + enfant `sleep`) tué + confirmé mort + verrou nommé supprimé +
  re-vérifié ; cas `rien_a_faire` (aucun watcher, aucun verrou) ;
  `projet_par_depot` contre les `.conf` réels du dépôt.

## 2 août 2026 — issue #322

Dernier trou résiduel du cycle de vie verrou/claude comblé : si le watcher
meurt BRUTALEMENT (kill -9, coupure de courant, plantage Python non
capturé) pendant qu'un claude tourne, aucun `finally` ne s'exécute — le
claude devient orphelin ET le verrou reste posé. Au démarrage suivant, le
watcher voyait ce verrou, le déclarait périmé et le REPRENAIT sans
vérifier qu'un claude orphelin de l'ancien contexte tournait encore,
risquant de lancer un second claude dans le même `REP_TRAVAIL` pendant que
l'orphelin y écrivait toujours (le périmètre empêche de sortir du dossier,
pas deux process d'y entrer en collision). Fermé PAR CONSTRUCTION, au seul
moment qui compte (la reprise d'un verrou périmé) — pas par une
surveillance externe (cron), aveugle quand le watcher est éteint.

- `watcher.py` :
  - `lancer_claude` accepte un paramètre `verrou` optionnel ; une fois le
    `Popen` du claude réussi, `_maj_verrou_pgid` consigne son pgid
    (== pid, `start_new_session=True`) dans le fichier verrou via un
    nouveau champ `claude_pgid=<n>`, en préservant les champs existants
    (`pid=`/`projet=`/`rep=`). Le verrou est posé par `acquerir_verrou`
    AVANT le lancement de claude : le pgid n'est donc connu qu'après le
    `Popen`, d'où cette mise à jour a posteriori plutôt qu'à la pose.
  - `_lire_pgid_verrou` : lit ce champ, `None` si absent (ancien format,
    ou watcher mort avant même le lancement de claude) — traité sans
    erreur, aucun kill tenté dans ce cas.
  - `_nettoyer_orphelin_verrou_perime` (appelée depuis `acquerir_verrou`,
    juste avant `verrou.unlink()`, uniquement sur la branche verrou
    PÉRIMÉ) : garde-fou anti-reboot à trois conditions cumulées avant
    tout kill — verrou périmé (déjà garanti par l'appelant), un process
    de ce pgid existe encore (`_lister_processus_pgid`, réutilisée telle
    quelle), et sa ligne de commande contient bien « claude » (identifier
    par ce que le process EST, jamais tuer aveuglément, même esprit que
    #247 point 4). Si les trois sont réunies : `os.killpg(pgid,
    SIGKILL)` sur ce seul groupe, un `log.warning` par process tué
    (PID + ligne de commande), attente bornée (5s) de la disparition
    effective. Un pgid mort ou recyclé après un reboot (PID/pgid
    réattribués) ne provoque aucun kill. POSIX uniquement, gardé par
    `os.name != "nt"` côté appelant (sous Windows, objet Job — pas de
    pgid, la question ne se pose pas dans les mêmes termes).
    Best-effort strict, comme `_nettoyer_arbre_claude` (#249) : toute la
    logique est enveloppée dans un garde-fou total (`_lister_processus_
    pgid` peut lever `OSError`, `os.killpg` une `PermissionError`) — une
    erreur du nettoyage journalise et laisse la reprise du verrou suivre
    son cours normal, jamais de remontée qui ferait échouer l'acquisition
    du verrou ni le traitement de l'issue.
  - `traiter_issue` : passe désormais le verrou courant à `lancer_claude`.
- `tests/test_orphelin_verrou_perime_322.py` (nouveau, sur le modèle de
  `tests/test_nettoyage_arbre_247.py`) : orphelin réellement tué à la
  reprise d'un verrou périmé (et journalisé) ; garde-fou anti-reboot sur
  pgid vivant mais pas un claude, et sur pgid mort/recyclé — aucun kill
  dans ces deux cas ; verrou d'ancien format (sans `claude_pgid`) repris
  sans erreur ; `lancer_claude` consigne bien le pgid dans le verrou
  fourni.

## 2 août 2026 — issue #321

Champ de recherche par TITRE dans l'onglet Résultats de `new_issue.py`,
répondant au backlog ouvert par #317 suite au doublon #315/#316 — sous
une forme différente de l'idée initiale (titre ET corps) : décision de
#321 de rester sur le titre seul, plus rapide et suffisant pour
retrouver un sujet déjà traité. Entrée backlog correspondante retirée
de `TACHES.md`.

- `app/issues.py` : nouvelle route `recherche_issues` (une par projet,
  comme `issues_liste`) — `gh issue list --state all --limit <portée>`
  (state `all` : on cherche justement une issue déjà fermée/done),
  `--limit` réutilisant `_limite_issues_requete`/`LIMITE_ISSUES_MIN`/
  `LIMITE_ISSUES_MAX` sans dupliquer de borne. Filtrage sur le titre
  uniquement, insensible casse+accents via `_normaliser_recherche`
  (NFKD + suppression des diacritiques + casefold). Même gestion
  d'erreur (timeout/gh introuvable/returncode) qu'`issues_liste`.
- `app/__init__.py` : route `/recherche-issues/<nom_projet>`.
- `static/js/app.js` : champ texte + champ « portée » (défaut 15/projet,
  borné à `LIMITE_ISSUES_MAX`, réglage DISTINCT de la limite d'affichage
  de l'onglet) dans la barre de contrôles, déclenchement au clic (ou
  Entrée) uniquement — jamais à la frappe, cohérent avec #270. La
  recherche porte sur les projets actuellement sélectionnés dans les
  filtres (un appel `gh` par projet, portée non cumulative), ratisse
  toute la portée sans s'arrêter au premier match, respecte le filtre
  « 👷 Ouvriers », et agrège les échecs par projet sans annuler les
  autres. `construireLigneIssueDOM` extrait de `rendreListeIssues` pour
  être partagée avec la nouvelle fenêtre de résultats, qui réutilise
  telles quelles `copierReponseDepuisBadge`/`copierDiffDepuisBadge`/
  `copierToutEtDiffDepuisBadge` (badges ✅/Diff/All) et une nouvelle
  `afficherIssueRecherche` (double-clic) chargeant dans sa PROPRE zone
  de détail (`#zone-issue-recherche`), autonome de celle de l'onglet —
  plusieurs corps peuvent s'enchaîner sans se fermer mutuellement.
  `demarrerRedimTitre`/`finRedimTitre` adaptés pour redimensionner la
  colonne titre de la fenêtre indépendamment de celle de l'onglet, sans
  persister ce redimensionnement en localStorage.
- `templates/index.html` : barre de recherche statique dans l'onglet
  Résultats + modal `#modal-recherche-titre` (liste + zone de détail
  propres, bouton Fermer).
- `static/css/style.css` : styles de la barre et du modal.
- `TACHES.md` : retrait de l'entrée de backlog « Champ de recherche
  texte dans l'onglet Résultats » (#317), désormais implémentée.

La limite d'affichage par défaut de l'onglet (`LIMITE_ISSUES_DEFAUT`,
30) reste inchangée — le 15 par défaut ne concerne que la portée de
recherche, un réglage distinct.

## 2 août 2026 — issue #319

`TACHES.md` : retrait de l'entrée de backlog « Garde-fou technique sur
la modification de PERIMETRE » (diagnostic du 31/07/2026, issue #298),
désormais implémentée — sous une forme différente de l'idée initiale
(détection/confirmation) : décision finale du 02/08/2026 d'interdire
purement et simplement toute modification de `configs/*.conf` par
CCL/CCW (issue #318, commit 65e81c5). Suppression simple, même
convention que les issues #310/#312. Reste du fichier inchangé,
notamment « Champ de recherche texte dans l'onglet Résultats de
new_issue.py » (#317), toujours en attente sans implémentation.

## 2 août 2026 — issue #318

Interdiction totale de modification de `configs/*.conf` par CCL/CCW, y
compris en mode_write (diagnostic #298, décision du 02/08/2026 : pas de
mécanisme de détection/confirmation, interdiction pure et simple —
seul Alain modifie ces fichiers à la main ou via l'onglet Configuration
de `new_issue.py`).

- `consignes/globales.md` : nouvelle règle explicite — CCL/CCW ne
  modifie JAMAIS `configs/*.conf`, même si une issue le demande en
  toutes lettres ; en cas de demande de ce type, refuser cette partie
  de la tâche, l'expliquer dans le rapport de clôture, ne rien
  committer sur ce point.
- `watcher.py` : garde-fou technique en deux temps.
  - `_detecter_demande_modif_configs` : repérage best-effort (regex sur
    un chemin `configs/*.conf` dans le corps) juste avant le lancement
    de claude en mode_write — purement informatif (WARNING journalisé),
    ne bloque rien.
  - `_empreinte_configs` / `_restaurer_configs_modifies` : instantané
    intégral (contenu brut) de `configs/*.conf` pris une seule fois
    avant la première tentative de `traiter_issue`, comparé après
    CHAQUE tentative (succès ou échec). Toute modification, création ou
    suppression détectée est annulée automatiquement (restauration du
    contenu d'origine, ou suppression d'un fichier apparu), avec un
    WARNING explicite par fichier concerné — sans jamais faire échouer
    le reste du traitement de l'issue (best-effort, aucune exception
    propagée). `configs/` est commun à tous les projets (partagé par ce
    `watcher.py`), donc l'ensemble du dossier est protégé, pas
    seulement le `.conf` du projet en cours de traitement.
- `BRIDGE_AGENT_DOC.md` (§12) : le paragraphe « Exception » sur
  `configs/*.conf` précise désormais que cette exception vaut
  uniquement pour Alain (à la main ou via l'onglet Configuration),
  jamais pour CCL/CCW, même en mode_write, et renvoie vers le
  garde-fou technique de `watcher.py`.

## 2 août 2026 — issue #315

`BUILD_WINDOWS_CCW.md` : ajout de la checklist Rummikub (build validé),
insérée avant l'entrée Scrabble (plus récente en premier) — clone
`Z:\CCW\rummikub`, script `build\rebuild_rummikub.bat` (6 étapes),
`rummikub.spec` en liste explicite des `datas` (`src/rummikub/ui/web/`,
aucun `collect_tree` en bloc), TIMEOUT de référence 1200s (build réel
~333s), et les deux garde-fous de taille distincts introduits par
l'issue #57 (dist non compressé vs installeur compressé étant deux
grandeurs différentes) : `dist\Rummikub\` non compressé 28 712 051
octets (~28,7 Mo, fourchette 20-45 Mo) et `Rummikub-Setup.exe`
compressé 12 778 092 octets (~12,18 Mo, fourchette 5-25 Mo).

## 2 août 2026 — issue #314

`BRIDGE_AGENT_DOC.md` (§12.1, juste après le tableau des trois couches
de consignes) : ajout d'un renvoi explicite pour un Claude en
conversation (celui qui rédige une issue avant envoi, ex.
ClaudeRummikub) vers `consignes/globales.md` via `curl`, sur le même
modèle que le renvoi déjà existant vers `BRIDGE_AGENT_DOC.md` lui-même
(§9). Jusqu'ici le tableau décrivait l'injection automatique par
`watcher.py` à l'exécution (CCL/CCW) sans jamais pointer un Claude en
conversation vers le contenu réel de `globales.md` — notamment le
garde-fou backup/reset ajouté par l'issue #313, invisible avant que
l'issue parte à l'exécution.

## 2 août 2026 — issue #313

`consignes/globales.md` : ajout de deux garde-fous mutualisés à tous les
projets (injection automatique, aucune modification de `CONTEXTE.md` par
projet nécessaire). (1) Garde-fou backup/reset : le commit de sauvegarde
(`git add -A`) peut faire passer sous suivi git des dossiers auparavant
non trackés (ex. `.tools/`, `installeur/output/`) ; si le script exécuté
ensuite se termine par une opération git destructive (`reset --hard`,
`clean -fd`), ces dossiers seraient effacés du disque — vérifier via
`git status`/`git show --stat` et détracker (`git rm --cached`) avant de
lancer un tel script. Problème constaté et corrigé au cas par cas sur
Scrabble et Rummikub (issues #306, #311). (2) Renvoi vers
`BUILD_WINDOWS_CCW.md` (dépôt bridge_agent, racine) avant de proposer une
issue de build ou de modification de pipeline sur un projet ayant un
script de build Windows (PyInstaller/Inno Setup) — documente le pattern
de staging local et l'extension du PÉRIMÈTRE associée (issue #297/#299).

## 2 août 2026 — issue #312

`TACHES.md` : retrait des trois entrées de backlog désormais
implémentées — « Capture stderr CCL dans watcher.py » et « Vérification
pre-flight de la validité du token CCL » (issue #309, commit bcd3a11)
et « Archivage de logs/historique_durees.json » (issue #310, commit
6df2f44). Suppression simple, sans section « Terminé » : c'est déjà la
convention établie pour ce fichier (cf. commit dcecb85). Reste du
fichier inchangé, notamment « Garde-fou technique sur la modification
de PERIMETRE » (#298) et « Concurrence limitée aux issues mode_lecture »,
toujours en attente sans implémentation.

## 2 août 2026 — issue #310

Nouveau script `scripts/archiver_historique.py`, lancement manuel
uniquement — jamais appelé par `watcher.py` (issue #310) — pour purger
`logs/historique_durees.json`, qui accumule toutes les entrées depuis
mai 2026 sans purge et grossit à chaque clôture d'issue. Diagnostic
préalable (lecture du code, pas de conséquence sur ce script) :
`maj_calibration_timeout` (EWMA, calibration TIMEOUT réelle, issue
#221, `watcher.py`) est purement incrémentale et ne lit/écrit jamais
`historique_durees.json` (seulement `etat_timeout.json` et
`etat_ambiance.json`) — l'archivage n'a donc aucun impact sur elle ;
`estimer_duree` (badge de fiabilité à la création d'une issue, issue
#108, `app/issues.py`) recalcule en revanche une médiane à partir de
tout l'historique transmis, filtré par projet/type/mode, donc un
archivage réduit potentiellement le nombre d'échantillons par
catégorie.

Fonctionnement : pour chaque combinaison (projet, type, mode), les
`--n-min` entrées les plus récentes (défaut 20) sont TOUJOURS
conservées quelle que soit leur ancienneté ; au-delà de ce plancher,
les entrées antérieures à `--seuil-mois` (défaut 6) sont déplacées
vers `logs/historique_durees_archive_<année>.json` (une entrée va
dans le fichier de SON année ; fusion avec l'archive existante si déjà
présente). Les entrées à date illisible/absente sont conservées par
prudence, jamais archivées. N_MIN_DEFAUT = 20 choisi en cohérence avec
`SEUIL_ESTIM_SUR = 15` (`app/issues.py`) : une catégorie déjà au badge
"sûr" (vert, n > 15) avant archivage y reste après, avec une marge de
confort de 5. Le rapport console liste, par catégorie, le nombre total
avant, archivé et conservé, avec une alerte si une catégorie repasse
sous le seuil "sûr". `--dry-run` simule sans rien écrire. Écriture
atomique (`tempfile` + `os.replace`, même motif que `watcher.py`) ;
`etat_timeout.json` et `etat_ambiance.json` ne sont ni lus ni écrits
par ce script.

Testé sur une copie temporaire (`/tmp`, hors dépôt) avec des seuils
réduits pour valider le mécanisme (archivage, fusion sur double
exécution, conservation du total d'entrées) avant exécution réelle sur
`logs/historique_durees.json` : avec les valeurs par défaut (6 mois),
aucune entrée n'est encore assez ancienne (données depuis le
24/05/2026 seulement) — 774 entrées conservées, 0 archivée, fichier
inchangé après exécution. `etat_timeout.json` vérifié inchangé (même
empreinte MD5) ; `etat_ambiance.json` n'existe pas encore sur cette
machine et n'a pas été créé par ce script.

## 2 août 2026 — issue #309

Diagnostic CCL amélioré dans `watcher.py`, zone `lancer_claude()` (issue
#309) — suite à l'incident #279 où plusieurs issues avaient échoué en
~1,2s avec le message générique "Erreur inconnue" (cause réelle : token
CCL expiré), sans aucune indication exploitable dans le log. Deux ajouts
dans la même zone de code : **A)** capture stderr — au retour de
`communicate()`, si le process claude échoue (code de retour non nul),
les 2000 premiers caractères de son stderr sont journalisés en WARNING
(`_extrait_stderr`, tronque avec mention du nombre total de caractères
au-delà de cette limite, pour éviter un dump de plusieurs Mo tout en
gardant de quoi diagnostiquer une panne d'auth/réseau) ; **B)**
vérification pre-flight du token — nouvelle fonction
`verifier_preflight_token()`, appelée une seule fois par issue dans
`traiter_issue()` juste avant la boucle de tentatives (pas à chaque
tentative), qui lance un `claude --print` court (stdin vide, timeout 5s)
et recherche dans stdout+stderr des signatures d'authentification
manquante/expirée (`SIGNATURES_TOKEN_EXPIRE` : "not logged in", "/login",
"invalid api key", etc.) ; si détecté, WARNING explicite invitant à
relancer `claude` interactivement et taper `/login`. Choix délibéré de
passer une entrée vide via **stdin** plutôt que l'exemple littéral de
l'issue (`claude -p ""`) : un argument positionnel vide est rejeté
immédiatement par la validation d'arguments du CLI ("Input must be
provided...") AVANT toute vérification d'authentification, quel que
soit l'état du token — inutilisable comme sonde ; passé en stdin, l'appel
atteint bien le contrôle d'authentification. Le pre-flight ne bloque
jamais le traitement (toute exception — timeout, `claude` introuvable —
est avalée silencieusement, aucune tentative n'est empêchée) et est
sauté en dry-run. Comportement nominal (issues qui réussissent) inchangé
: vérifié par exécution manuelle de `verifier_preflight_token()` sur
l'environnement courant (aucune exception, aucun faux positif avec un
token valide) et simulation d'un échec de process (stderr correctement
tronqué et journalisé). Commit local, pas de push.

## 1er août 2026 — issue #299

Crée `BUILD_WINDOWS_CCW.md` à la racine du dépôt (issue #299), dédié au
contenu spécifique-projet des builds Windows délégués à CCW — jusqu'ici en
voie d'accumulation dans `BRIDGE_AGENT_DOC.md` (§16.3) à chaque nouveau
projet buildé (Scrabble déjà, Rummikub en préparation). Le fichier reprend
le pattern général de staging local documenté par l'issue #297 (corruption
de fichiers sur `\\VBOXSVR\CCW_Share`, contournement via
`C:\Temp\<Projet>Build`, extension obligatoire du `PERIMETRE` dans
`configs\ccw.conf`), ajoute une checklist type à remplir par projet
buildé (clone CCW, script de build, `.spec` — datas explicites ou
`collect_tree` en bloc avec mise en garde suite à l'incident dump
wiktionnaire 8,2 Go sur Scrabble du 31/07/2026 —, TIMEOUT de référence,
taille/hash de l'artefact final), et une première entrée déjà remplie
pour Scrabble (`Z:\CCW\scrabble`, `build\rebuild_scrabble.bat` en 7
étapes fix #338, `scrabble.spec` corrigé en liste explicite, TIMEOUT
1200s, installeur de référence 26 546 846 octets, SHA256
`d52e101f8758a1b107011adf0bc1a04102bce48d3283248650019ba101ef3254`).
En contrepartie, la note « staging local » ajoutée au §16.3 de
`BRIDGE_AGENT_DOC.md` par l'issue #297 est remplacée par un renvoi de
deux lignes vers ce nouveau fichier ; pied de page de `BRIDGE_AGENT_DOC.md`
glissé (#299 en tête, #287 conservée, #297 conservée en dernière position
avec note du remplacement, #285 sorti).

## 31 juillet 2026 — issue #297

Documente au §16.3 « Procédure — builder un projet Windows » de `BRIDGE_AGENT_DOC.md` le pattern de staging local pour les builds Windows CCW (issue #297), jusqu'ici décrit uniquement dans le `CONTEXTE.md` propre au projet Scrabble et donc invisible pour toute autre instance CCL/CCW ayant le même besoin (ex. Rummikub, même stack PyInstaller + Inno Setup, prévoit ce pattern dès son premier script de build). Contexte : diagnostic du 31/07/2026 sur Scrabble — les builds PyInstaller + Inno Setup produisaient des fichiers tronqués/corrompus lorsqu'ils tournaient directement sur le partage VirtualBox `\\VBOXSVR\CCW_Share` (fix #338). Nouvelle note ajoutée juste après le paragraphe « Note safe.directory », avant la sous-section 16.4 : **contournement standard** — le script de build copie les sources vers un répertoire local à la VM (`C:\Temp\<Projet>Build` ou équivalent), construit entièrement là, puis ne recopie vers le partage que l'artefact final ; **conséquence obligatoire** — ajouter ce chemin local au `PERIMETRE` de `configs\ccw.conf` (liste séparée par virgules), sans quoi CCW refuse à juste titre d'en sortir et bloque légitimement le build ; **rappel** — avant d'ajouter un nouveau projet à builder sous Windows, vérifier si son script de build suit déjà ce schéma et, si oui, étendre le `PERIMETRE` en conséquence. Pied de page de `BRIDGE_AGENT_DOC.md` glissé (issue #297 en tête, #287 et #285 conservées comme les deux entrées les plus récentes parmi les issues modifiant cette doc, #281 sorti). Aucun fichier `.py`/`.js` modifié (documentation seule), aucune section renumérotée.

## 30 juillet 2026 — issue #287

Documente au §16 « Agent Windows CCW » de `BRIDGE_AGENT_DOC.md` la procédure d'interruption d'une issue CCW coincée (issue #287), jusqu'ici purement manuelle et non écrite nulle part. Nouvelle sous-section **16.4 « Interrompre une issue CCW coincée »** insérée après la note sur `safe.directory` (fin du §16), avant le §17 : **symptôme** — le watcher `CCW-Watcher` détecte bien l'issue à chaque cycle mais log en boucle, sans jamais progresser, « Issue différée : un autre traitement détient déjà le verrou sur `\\VBOXSVR\CCW_Share\` » ; **cause** — un fichier verrou laissé dans `C:\CCW\Bridge_Agent\logs\verrous\` n'a pas été nettoyé (process tué brutalement, ou redémarrage NSSM du service sans libération propre du verrou en cours), le watcher refusant alors de retraiter l'issue tant que ce fichier existe, même après redémarrage ; **procédure manuelle** en deux étapes — `nssm restart CCW-Watcher` (nécessaire mais pas suffisant seul), puis lister et supprimer le(s) fichier(s) `.lock` restant(s) dans `C:\CCW\Bridge_Agent\logs\verrous\` via `Get-ChildItem ... -Filter "*.lock"` et `Remove-Item` ; **note** — un bouton « Interrompre » dans l'onglet CCW de `new_issue.py` est prévu pour automatiser cette procédure à distance depuis Linux (voir `TACHES.md`, backlog ajouté par l'issue précédente be4cae0). Pied de page de `BRIDGE_AGENT_DOC.md` glissé (issue #287 en tête, #285 et #281 conservées comme les deux entrées les plus récentes parmi les issues modifiant cette doc, #279 sorti). Aucun fichier `.py`/`.js` modifié (documentation seule), aucune section renumérotée.

## 30 juillet 2026 — issue #285

Documente au §3 « Créer une issue — la méthode normale » de `BRIDGE_AGENT_DOC.md` le comportement exact du bouton **« Aperçu de la commande »** de l'onglet Nouvelle issue (issue #285), jusqu'ici non décrit malgré sa présence de longue date dans le formulaire. Nouveau paragraphe inséré juste après la description du lancement (`new_issue.py`/`lancer_new_issue.sh`) et avant le « Format du corps pour copier-coller » : le bouton appelle la route `/apercu` (fonction `apercu()` de `app/issues.py`), qui construit à partir des champs actuellement remplis dans le formulaire la commande `gh issue create` exacte qui serait exécutée (dépôt, titre, labels, `--body-file`), suivie en commentaire du corps complet qui serait envoyé, renvoyée en JSON. `afficherApercu()` (`static/js/app.js`) affiche ce texte tel quel dans la zone `zone-apercu` sous le formulaire. Point clé : c'est un aperçu pur — aucune issue n'est créée, aucune commande n'est réellement exécutée, rien n'est modifié tant que le bouton d'envoi n'est pas cliqué séparément. Pied de page de `BRIDGE_AGENT_DOC.md` glissé (issue #285 en tête, #281 et #279 conservées comme les deux entrées les plus récentes parmi les issues modifiant cette doc, #268 sorti). Aucun fichier `.py`/`.js` modifié (documentation seule), aucune section renumérotée.

## 30 juillet 2026 — issue #281

Ajoute au §11 « Conventions de code » de `BRIDGE_AGENT_DOC.md` le paragraphe **« Niveau de détail des issues »** (issue #281), en réponse à une tendance observée chez Claude Chat à rédiger du code complet dans le corps des issues (blocs Avant/Après, implémentations entières) alors que CCL est capable de lire les fichiers source et d'implémenter lui-même à partir d'une description claire. La règle posée : Claude Chat décrit le problème, la cause et l'intention du fix, sans rédiger le code complet — CCL fait l'implémentation. **Exception tolérée** : un snippet de 1-2 lignes si la syntaxe est non-triviale ou si l'intention serait ambiguë sans exemple. **Mauvais exemple** donné : fournir les trois méthodes complètes Avant/Après pour un fix pywebview de navigation différée. **Bon exemple** : « Dans `api.py`, pour les trois méthodes de navigation, différer l'appel dans un thread daemon avec `time.sleep(0.05)` avant de naviguer. » Pied de page de `BRIDGE_AGENT_DOC.md` glissé (issue #281 en tête, #279 et #268 conservées comme les deux entrées les plus récentes parmi les issues modifiant cette doc, #263 sorti). Aucun fichier `.py` modifié, aucune section renumérotée.

## 30 juillet 2026 — issue #279

Documente dans §13 de `BRIDGE_AGENT_DOC.md` le diagnostic du symptôme « Erreur inconnue » observé la nuit du 29/07/2026 (issue #279) : plusieurs issues avaient échoué en ~1,2 s, 3 tentatives et passe diagnostique comprises, le message générique masquant totalement la cause réelle — une session CCL expirée. Nouveau bloc **« Diagnostic — CCL ne démarre pas »** ajouté en fin de §13 (après le paragraphe sur les services systemd abandonnés) : **symptôme** (échec quasi immédiat sur toutes les issues → cause systémique, pas liée au contenu d'une tâche précise) ; **première vérification** (`claude -p "test" 2>&1` — une réponse « Not logged in » signe un token de session CCL expiré) ; **résolution** (lancer `claude` en session interactive, puis taper `/login`) ; **autres causes possibles** (réseau indisponible/DNS, installation `claude` corrompue) ; et le **critère de distinction** entre ces causes par le temps d'échec — un token expiré échoue en moins de 2 secondes (observé le 29/07/2026), un problème réseau échoue en général bien plus tard, proche du `TIMEOUT` configuré dans l'en-tête de l'issue (l'appel reste bloqué à attendre une réponse qui ne vient jamais). Pied de page de `BRIDGE_AGENT_DOC.md` glissé (issue #279 en tête, #268 et #263 conservées comme les deux entrées les plus récentes parmi les issues modifiant cette doc, #257 sorti). Aucun fichier `.py` modifié, aucune section renumérotée.

## 29 juillet 2026 — issue #272

Consignation dans `TACHES.md` de deux sujets diagnostiqués en conversation le 29/07/2026 (issue #272), qui auraient été perdus à la fermeture du fil sans cette entrée : tous deux relèvent du backlog (pistes à mûrir, aucun développement lancé). Ajoutées en tête du fichier, avant « Concurrence limitée aux issues mode_lecture », les entrées existantes n'ont pas été modifiées. **Entrée 1 — calibration automatique du TIMEOUT (§19), trois défauts** : (1) `_detecter_tag_reseau()` retourne toujours `None`, donc le facteur d'ambiance `F` (F_reseau/F_local) n'influence jamais la suggestion malgré la formule qui le prévoit ; (2) même corrigé, `maj_calibration_timeout` retomberait toujours sur `F_local` par défaut sans lire le tag — bug distinct du premier ; (3) la clé `projet|TYPE|mode` mélange des populations de durée incompatibles (une doc de 250s et une refonte avec tests de 1800s dans la même case), produisant des suggestions sans sens (observé : 2794s suggérés pour une issue ayant pris 351s). Piste retenue : séparer le coût de la TÂCHE (proxy : le TIMEOUT déclaré en en-tête, que Claude Chat estime déjà à la rédaction) de l'état de la MACHINE (latence réseau mesurée au démarrage, pour enfin alimenter `tag_reseau`), en conservant une composition en PRODUIT et non en somme. **Entrée 2 — archivage de `logs/historique_durees.json`** : 682 entrées, 112 Ko au 29/07/2026, jamais purgé depuis mai ; les 13 entrées `ff_galerie` (projet piloté par EmailJS, pas d'usage bridge réel) ne polluent aucun calcul mais brouillent la lecture manuelle. Point de vigilance impératif pour toute implémentation future : ne pas archiver naïvement par mois — l'EWMA de calibration a une demi-vie de 15 issues, une bascule mensuelle repartirait de zéro à chaque mois pour les projets les plus actifs. Aucune urgence à 112 Ko ; à traiter avant plusieurs Mo. `BRIDGE_AGENT_DOC.md` non modifié par cette issue (aucune section ne couvre `TACHES.md`), donc pied de page non glissé (condition de #10 non remplie).

## 29 juillet 2026 — issue #271

Résultats : nombre d'issues chargées par projet rendu configurable (issue #271), pour accélérer le bouton rafraîchir et réduire le volume rapatrié — jusqu'ici `issues_liste()` (`app/issues.py`) appelait `gh issue list --limit 30` en dur, **par projet** (jusqu'à 240 issues téléchargées avec 8 projets), alors que l'affichage était déjà plafonné par le quota adaptatif d'`appliquerFiltresListe()` (issue #136). **Backend** : `issues_liste()` accepte désormais un paramètre de requête optionnel `limite` (`_limite_issues_requete()`), entier borné entre 1 et 50 — toute valeur absente, non entière ou hors bornes retombe sur 30 (`LIMITE_ISSUES_DEFAUT`), comportement strictement inchangé pour tout appelant qui ne passe pas le paramètre (vérifié : `?limite=5`→5, `?limite=999`→50, `?limite=0`→1, `?limite=abc`→30, absent→30, via `test_client()` bout-en-bout contre `gh` réel). **Frontend** (`static/js/app.js`, `static/css/style.css`) : champ numérique `#limite-issues-projet` ajouté dans la ligne de filtres, juste avant le bouton rafraîchir, `title` explicite (« Nombre d'issues chargées par projet (pas un total). Ex. 5 → 5 issues par projet affiché. ») pour éviter la confusion nombre-par-projet / total — un total obligerait à diviser par le nombre de projets actifs, qui change à chaque clic sur un filtre. Persisté dans `localStorage` (`bridge_limite_issues_projet`), défaut **5** (besoin réel dans 70% des cas d'après l'issue, et non 30 : l'ancienne valeur reste atteignable en remontant le champ). `chargerListeIssues()` transmet la valeur courante (`limiteIssuesProjet()`) à chaque appel `/issues-liste/<projet>`. Changer la valeur du champ ne déclenche **aucun** rechargement automatique (cohérent avec la décision de #270) : seul le bouton rafraîchir applique la nouvelle limite ; en revanche `changerLimiteIssuesProjet()` invalide immédiatement `CLE_CACHE_ISSUES`, sans quoi un cache constitué à l'ancienne limite continuerait d'afficher une profondeur d'historique incohérente avec le réglage visible. Quota adaptatif de #136 (`appliquerFiltresListe()`) **non touché** : les deux mécanismes sont complémentaires (celui-ci plafonne ce qui est TÉLÉCHARGÉ, celui-là ce qui est MONTRÉ) ; commentaire ajouté pour expliciter que si la limite de téléchargement est plus basse que le quota d'affichage, ce dernier n'a simplement rien de plus à masquer — sans conséquence. **Mesure du coût GraphQL** (méthode #263 : deux `gh api rate_limit` encadrant un appel isolé de `gh issue list --json ...`, 3 répétitions, delta minimal retenu) sur `--limit 30/10/5` : les trois deltas minimaux mesurés valent **1 point** (identique au coût unitaire déjà mesuré par #263 pour cet appel) — résultat inattendu : le coût GraphQL par appel ne varie PAS avec `--limit` dans la plage testée, contrairement à l'intuition de l'issue ; le gain réel n'est donc pas une réduction du quota GraphQL (le nombre d'appels — un par projet — reste le facteur dominant, inchangé par cette issue) mais une réduction du volume de données transférées/parsées (23 113 → 3 445 octets entre `--limit 30` et `--limit 5` sur ce dépôt, soit -85%), donc du temps de traitement `gh`/JS et du risque de timeout sur un historique profond. Détail complet et tableau des mesures dans le rapport de clôture de l'issue #271 (non dupliqué ici). Route `/issues-liste/<projet>` non documentée dans `BRIDGE_AGENT_DOC.md` (aucune section ne la décrit) : aucune mise à jour de ce fichier, pied de page non glissé (condition de #10 non remplie — cette issue ne modifie pas `BRIDGE_AGENT_DOC.md`).

## 29 juillet 2026 — issue #270

Badges de temps restant : suppression du rafraîchissement périodique (issue #270, remplace #269 fermée sans correctif — mesure infaisable dans le TIMEOUT, décisions non tranchées). `intervalFetchTiming` (re-fetch de `/issues-en-attente/<projet>` toutes les 15s pour tous les projets configurés, ~3840 pts/h mesurés par #263, premier poste de consommation du quota GraphQL) supprimé ; `intervalTempsRestant` conservé (décompte purement client, recalcul chaque seconde, sans coût réseau). `chargerTimingIssues()` n'est plus appelée qu'au chargement initial de l'onglet Résultats et depuis `rafraichirResultats()` (bouton rafraîchir), pour qu'un seul geste mette à jour liste ET badges. Décision sur le décompte (point 3 de #269, laissé en suspens) : une fois le budget total épuisé, le badge se fige à « ⌛ 0s — budget épuisé » au lieu d'un compteur de dépassement qui grossissait indéfiniment (`⌛ dépassement +Xs`) — jamais de valeur négative, jamais de message spéculatif du type « terminé ? » (l'état réel n'est pas connu sans re-fetch), badge visible jusqu'au prochain rafraîchissement manuel. Retrait de deux résidus d'une tentative précédente non commitée proprement : un `console.error('[DEBUG-269-TRACE]', …)` dans `chargerTimingIssues()` et un bloc `<script>` de harnais temporaire dans `templates/index.html` (auto-bascule vers l'onglet Résultats après 800ms) qui portait lui-même la mention « à retirer avant commit ». Second appelant de `/issues-en-attente` (~ligne 2735, garde-fou avant l'envoi d'une nouvelle issue) : hors périmètre de cette issue, laissé strictement tel quel. Aucune mesure de gain (hors périmètre, cf. #269 : nécessite un navigateur ouvert 5+ minutes, invérifiable depuis l'agent) — à faire par Alain avec `scripts/mesurer_api.py`.

## 29 juillet 2026 — issue #268

Corrige la corruption du § 10 provoquée par #263 (issue #268) : l'entrée de #263, destinée au vrai pied de page (dernière ligne du fichier), avait été insérée à la place du `<date> — ...` du modèle explicatif du §10 — remplacement effectué sur la première occurrence de « Dernière mise à jour » dans le fichier, qui est cet exemple, pas le pied de page situé bien plus bas. Deux dégâts cumulés : le §10 affichait un modèle cassé (phrase du point 2 disloquée par le texte de #263 inséré en son milieu) et le vrai pied de page n'avait PAS reçu l'entrée de #263 — il avait seulement perdu #252, passant de trois entrées (#257, #253, #252) à deux (#257, #253), contredisant le rapport de clôture de #263 qui affirmait à tort « Footer glissé (#263 en tête, #257 et #253 conservées, #252 sorti) ». **Correctifs** : (1) §10 restauré au mot près dans son état d'origine (`*Dernière mise à jour : <date> — ...*`) ; (2) pied de page reconstruit avec l'entrée #263 en tête suivie de #257 et #253 (les trois entrées les plus récentes parmi les issues modifiant cette doc), puis complété dans la même opération par cette propre entrée #268, faisant sortir #253 ; (3) garde-fou ajouté au §10 (nouveau point 3) : le format n'apparaît qu'à la toute dernière ligne du fichier, une recherche sur « Dernière mise à jour » remontant d'abord l'exemple du §10 — toujours viser la fin du fichier, jamais la première occurrence. **Test (point 4)** : regex de `nouveau_projet.py` (`(\*Dernière mise à jour : )[^—]*( —)`) rejouée réellement (`re.sub`) contre la première ligne du pied de page corrigé — match confirmé, substitution de la date vérifiée avec succès. Aucun fichier `.py` modifié, aucune section renumérotée.

## 28 juillet 2026 — issue #263

Mesure et attribution de la consommation du quota GraphQL GitHub (issue #263, suite à l'épuisement complet du 28/07 vers 3h — 5000/5000, `remaining: 0`) — aucun correctif, mesure seule. Ajout de `scripts/mesurer_api.py` : échantillonne `gh api rate_limit` (REST, **gratuit** — vérifié empiriquement par une rafale de 40 appels sans effet sur `graphql.used`) à intervalle réglable et journalise dans `logs/mesure_api.csv` (déjà gitignoré via la règle `logs/`), arrêtable par Ctrl+C sans perte. **Coûts unitaires mesurés** (delta minimal sur 2-5 répétitions, pour s'affranchir du bruit de fond) : `gh issue list --json ...` (l'appel du polling) = 1 point, `gh issue view --json comments` = 2, `gh issue comment` = 2, `gh issue edit --add-label` = 3, `gh issue close` = 2 (plancher, variance 2-4). **Résultat principal, inattendu** : sur la fenêtre mesurée (baseline ≈ 4045 points/heure, 1 seul watcher CCL actif), la première cause identifiée n'est ni la boucle CCW, ni le délai d'inactivité de 20 min, ni le polling à 10s des watchers (chacun ≈ 360 points/heure, confirmé par calcul coût-unitaire × fréquence) — c'est **l'interface web laissée ouverte dans un navigateur** : `/issues-en-attente/<projet>` interroge deux fois (labels for-linux ET for-windows) CHAQUE projet configuré toutes les ~15s pour rafraîchir les badges du sélecteur, soit environ 3840 points/heure à elle seule avec les 8 projets actuels — avant même qu'un watcher ou le poller de notifications (`app/notifications_poller.py`, ≈ 960 points/heure pour 8 projets) n'entre en jeu. Protocole en phases A-D adapté : la phase « tout arrêté » n'a pas pu être mesurée en conditions réelles (le watcher CCL traitant cette issue de mesure, et `new_issue.py` dont il dépend, ne peuvent pas être arrêtés depuis CCL sans interrompre l'exécution en cours — même limite que le watcher CCW, inaccessible depuis le ThinkPad) ; contournement par deux watchers de test supplémentaires (`rummikub`, `scrabble`, `--dry-run`, 0 issue en attente donc aucun risque d'exécution réelle) pour isoler la contribution marginale d'un watcher au repos. §13 de `BRIDGE_AGENT_DOC.md` complété avec la méthode reproductible ; pied de page glissé (issue #257 et #253 conservées, #252 sorti — déjà dans ce fichier). Classement des leviers correctifs et chiffres complets : rapport détaillé posté en commentaire de clôture de l'issue #263 (non dupliqué ici) — aucun changement de comportement du bridge n'a été apporté, les correctifs éventuels feront l'objet d'issues séparées.

## 28 juillet 2026 — issue #262

Transforme le bouton « Tous » de l'onglet Résultats en véritable interrupteur à deux états, après que #259 a établi que le comportement inconditionnel qu'il évoluait n'était pas un bug : le besoin réel est un basculement rapide entre « tout afficher » et « tout masquer », le bouton « Tous » et la case de marquage étant les deux gestes les plus fréquents de cet onglet (le détail d'une issue y est presque jamais consulté, cf. #261).

**Nouvelle fonction** : `reactiverTousLesFiltres()` renommée `basculerTousLesFiltres()` (`static/js/app.js`), commentaire d'en-tête réécrit pour décrire le toggle plutôt que la remise à zéro inconditionnelle. Règle : `noms.every(nom => projetsFiltresActifs.has(nom))` vrai (tout affiché) → passe à l'ensemble vide (tout masqué) ; faux (état partiel OU tout masqué) → passe à l'ensemble complet (tout affiché). Un seul état bascule vers « tout masqué », tout le reste revient à « tout affiché », conformément à l'énoncé.

**Garde-fou de #259** : supprimé purement et simplement (`if (!noms.length) return;`), sans réécriture ni remplacement — l'ensemble vide qu'il interdisait est désormais l'état « tout masqué », volontaire et légitime, exactement ce que la fonction doit pouvoir produire. Le garder aurait bloqué le nouveau comportement dans le cas `noms` vide (aucun projet configuré), un cas de toute façon sans conséquence réelle (aucun bouton projet à masquer).

**Persistance `localStorage`** (`CLE_FILTRES_RESULTATS`) : asymétrique, à dessein. Vers « tout affiché » → `localStorage.removeItem(...)`, comme avant #262 (retour au défaut — tout actif — au prochain chargement). Vers « tout masqué » → `sauvegarderFiltresProjets(noms)`, la même fonction qu'utilise déjà `basculerFiltreProjet()`, qui écrit `{nom: false, ...}` pour chaque projet : sans cette persistance explicite, un rechargement de page aurait silencieusement annulé le masquage volontaire (retour à tout affiché par défaut, cf. `restaurerFiltresProjets()`).

**État visible sur le bouton** : `majClassesBoutonsFiltre()` (qui ne traitait jusqu'ici que les boutons `[data-projet]`) traite désormais aussi `.filtre-projet.tous` — classe `inactif` (grisée, CSS déjà existante) et `title` reflétant l'action du **prochain** clic (« Tout masquer » quand tout est affiché, « Tout afficher » sinon), pas l'état courant. Effet de bord nécessaire : dans `construireBoutonsFiltre()`, l'appel à `majClassesBoutonsFiltre()` se faisait juste après la boucle des boutons projet, donc **avant** la création du bouton « Tous » — déplacé après sa création (juste avant le bouton rafraîchir), sinon la mise à jour de son état visuel n'aurait rien trouvé dans le DOM à la construction initiale ni après reconstruction de la ligne de filtres.

**Point 5 (cas limite tout masqué)** : `appliquerFiltresListe()` masque bien toutes les lignes (`projetVisible` faux pour tout projet quand l'ensemble est vide), `selectionnerPremiereVisible()` ne trouve aucune ligne visible et affiche proprement « Aucune issue à afficher », sans erreur. Défaut trouvé en vérifiant ce chemin : la ligne précédemment sélectionnée gardait sa classe `.selectionnee` (invisible mais toujours marquée) même masquée — au retour à « tout afficher », cette ligne redevenait visible et le code de resynchronisation (`if (!sel || sel.style.display === 'none')`), la trouvant déjà « sélectionnée » et visible, sautait la resélection : la zone de détail restait bloquée sur le message « Aucune issue à afficher » malgré une ligne visiblement en surbrillance. Ce chemin était déjà latent via `basculerFiltreProjet()` (désactiver le dernier projet actif un par un y menait aussi) mais quasi inatteignable en pratique ; le nouveau toggle le rend trivial (un clic). Corrigé dans `selectionnerPremiereVisible()` : la branche « aucune ligne visible » retire désormais aussi la classe `.selectionnee` de toute ligne qui la porterait encore et réinitialise `projetCourant`/`numeroCourant` (miroir du comportement déjà présent dans `selectionnerLigne()` pour son propre cas « aucune issue »). Effet : au retour à « tout afficher », plus aucune ligne ne porte `.selectionnee`, la resynchronisation se déclenche normalement et sélectionne proprement la première ligne visible.

**Point 6 (rechargement / reconstruction)** : vérifié par lecture du chemin d'appel — `appliquerListeIssues()` recalcule toujours `projetsFiltresActifs = restaurerFiltresProjets(noms)` avant `construireBoutonsFiltre(noms)`, aussi bien au chargement initial qu'à toute reconstruction (ajout de projet). Après un masquage total persisté, un rechargement restaure bien un ensemble vide (chaque projet marqué `false` dans l'état sauvegardé) : le bouton affiche correctement l'état « inactif »/« Tout afficher » dès la construction, premier clic correct. Ajout d'un nouveau projet pendant un masquage total : ce projet, absent de l'état `localStorage` sauvegardé, est actif par défaut (`etat[nom] !== false` vrai pour une clé absente) — l'ensemble devient donc partiel plutôt que resté totalement vide ; le bouton reflète alors correctement « Tout afficher » (état partiel), et un premier clic affiche bien tout, conformément à la règle générale (tout état partiel bascule vers tout affiché).

**Vérification** : `node --check static/js/app.js` → OK. Vérifications des points 5 et 6 faites par relecture attentive du chemin d'exécution réel du fichier (accès à un bac à sable DOM complet non disponible dans cette session — le fichier charge de nombreux `document.getElementById(...).addEventListener` en haut niveau, un stub minimal aurait été trompeur) ; le raisonnement s'appuie sur le code effectivement livré, ligne par ligne, pas sur une hypothèse.

## 28 juillet 2026 — issue #261

Dans l'onglet Résultats, `afficherIssue()` (`static/js/app.js`) lançait un `fetch('/issue/<projet>/<numero>')` systématique — y compris pour un clic simple réflexe (sélectionner une ligne sans vouloir lire son détail) et pour la sélection automatique (`selectionnerPremiereVisible()`, déclenchée à l'ouverture de l'onglet, à chaque changement de filtre projet, après « Tous » et après chaque rafraîchissement de liste). Le TTL du cache `localStorage` (issue #52) ne dispensait que l'affichage immédiat : le fetch d'arrière-plan partait quand même. Dans l'usage réel, ce détail n'est presque jamais consulté ; chaque clic réflexe et chaque changement de filtre coûtaient donc un aller-retour GitHub inutile — autant d'occasions d'erreur/lenteur sur un réseau instable (issue #261).

**Solution retenue** : séparation stricte sélection / chargement. Nouvelle `selectionnerLigne(nom, numero)` — met en évidence la ligne (classe `.selectionnee`), mémorise `projetCourant`/`numeroCourant`, affiche un état neutre (« Double-cliquez une issue pour afficher son détail. ») dans `#zone-issue`, **sans fetch**. `afficherIssue()` (comportement de fetch/cache inchangé) délègue désormais la partie sélection à `selectionnerLigne()` et ne s'en distingue plus que par le chargement effectif. `selectionnerPremiereVisible()` appelle `selectionnerLigne()` au lieu de `afficherIssue()` : la sélection automatique ne charge donc plus rien. Sur chaque ligne, `onclick` (clic simple) appelle `selectionnerLigne()` ; un nouveau `ondblclick` appelle `afficherIssue()` — seul geste, avec le Ctrl+clic (identique à avant, demande explicite de détail + défilement vers le résultat CCL), qui charge encore. `title="Double-cliquez pour afficher le détail de cette issue"` posé sur chaque ligne pour rendre le geste découvrable (point 6).

**Bouton rafraîchir (issue #56, point 4)** : `rafraichirResultats()` mémorisait `projetCourant`/`numeroCourant` avant rechargement pour rouvrir l'issue affichée — mais ces variables sont désormais renseignées même par une simple sélection, jamais chargée. Nouveau drapeau `detailCourantCharge` (true uniquement après un chargement réel via `afficherIssue()`, remis à `false` par `selectionnerLigne()`) : `rafraichirResultats()` ne recharge le détail après rafraîchissement que si `detailCourantCharge` valait `true` juste avant — sinon, aucune issue n'ayant été explicitement ouverte, rien n'est chargé de force.

**Non modifié** : la checkbox de marquage, les badges « ✅ »/« Diff »/« All » (fetch à la demande explicite, inchangés), le filtrage par projet, `annulerIssue()`/`fermerIssue()` (leurs boutons ne sont rendus que dans une issue déjà explicitement chargée — rappeler le détail après leur action reste la continuation directe d'un geste explicite, pas un chargement réflexe). Aucune sélection au clavier n'existe dans ce fichier pour la liste des issues (point 7 : rien à adapter).

**Vérification** : `node --check static/js/app.js` → OK. Comportement rejoué dans un bac à sable Node (`vm`, mêmes stubs DOM/localStorage/fetch que pour #259) chargeant le fichier réel tel quel : sélection automatique et clic simple → zéro appel `fetch('/issue/...')` ; double-clic → exactement un appel ; `rafraichirResultats()` après une simple sélection → zéro appel ; après un double-clic préalable → un appel. Script de vérification non persisté (ad hoc, comme pour #259).

## 28 juillet 2026 — issue #260

Corrige la façon dont `initialiser_git()` (`nouveau_projet.py`) détecte le contenu préexistant d'un `REP_TRAVAIL` non versionné, en la faisant porter sur ce que git suivrait réellement plutôt que sur le contenu brut du disque (issue #260, suite #258). **Défaut** : `_fichiers_preexistants()` (livrée par #258) listait le répertoire via `rglob("*")` **avant** toute écriture — choix délibéré pour que le futur `.gitignore` ne fausse pas le constat — mais comptait de ce fait aussi tout ce que ce même `.gitignore` exclurait. Le cas typique d'un `REP_TRAVAIL` préexistant est un projet Python déjà commencé, contenant donc un `venv/` et des `__pycache__/` : le scan remontait alors potentiellement des milliers d'entrées, le compte-rendu annonçait un nombre de « fichiers préexistants » sans rapport avec la réalité, et le push était retenu pour des fichiers qui n'auraient de toute façon jamais été committés — un garde-fou qui se déclenche presque systématiquement pour de mauvaises raisons finit par être ignoré, ce qui annule le bénéfice recherché par #258. Point mineur de même famille : `rglob("*")` parcourait l'arborescence entière sans borne, au sein d'une requête Flask, alors que #258 venait précisément de poser des timeouts sur les appels git pour cette raison — un `venv/` volumineux aurait pu rendre la création anormalement lente.

**Solution retenue** : réordonnancement de `initialiser_git()` — `git init`, `remote add`, écriture du `.gitignore` minimal (comportement inchangé), PUIS `git add -A`, PUIS détection sur l'index réel (`git diff --cached --name-only`), PUIS commit. Nouvelle `_fichiers_suivis_preexistants(rep_path, git_runner)` remplace `_fichiers_preexistants()` (supprimée, aucune coexistence des deux mécanismes) : liste les fichiers indexés par `git add -A`, exclut ceux que le script crée lui-même (`CONTEXTE.md`, fichiers Specs, `.gitignore` — `FICHIERS_CREES_PAR_SCRIPT`, inchangée), triés, chemins relatifs. Un `venv/`/`__pycache__/` exclu par le `.gitignore` minimal n'atteint jamais l'index et ne compte donc plus comme contenu préexistant. Sémantique de sortie strictement conservée : `contenu_preexistant` (liste triée), `push_ok=None` en cas de retenue volontaire (distinct de `False` = échec réel), `commande_manuelle`, `detail` expliquant le pourquoi — seule la manière de constituer la liste change. `_fichiers_suivis_preexistants()` réutilise le `_git()` local de l'appelant (déjà borné par `TIMEOUT_GIT_LOCAL` et tolérant au dépassement) pour le `git diff --cached` : pas de second mécanisme de timeout à maintenir.

**Test** (`tests/test_init_git_local_258.py`) : scénario « contenu préexistant » (#258) inchangé, continue de passer. Nouveau scénario `scenario_venv_ignore_par_gitignore_pas_de_retenue` : répertoire non versionné contenant un `venv/lib/module.py` et un `__pycache__/module.cpython-311.pyc`, aucun fichier réellement suivi → `contenu_preexistant` vide et push tenté normalement (`push_ok:false`, dépôt distant inexistant — pas `None`). Vérifié comme échouant sur le code d'avant correction (`git stash` du seul `nouveau_projet.py`, test relancé : `venv/lib/module.py` et `__pycache__/module.cpython-311.pyc` remontaient tous les deux) puis passant sur le code corrigé. Les 4 autres scénarios de ce fichier ainsi que `test_nettoyage_arbre_247.py`, `test_auto_extinction_217.py`, `test_verification_commentaire_237.py` repassés sans régression.

**Doc** : §13 étape 5 reformulé — le garde-fou porte désormais explicitement sur les fichiers que git suivrait après `git add -A`, pas sur un inventaire brut du répertoire.

## 28 juillet 2026 — issue #259

Ajoute un garde-fou d'idempotence à `reactiverTousLesFiltres()` (bouton « Tous » de l'onglet Résultats, `static/js/app.js`), suite à un signalement de second clic masquant tous les projets (issue #259). **Diagnostic** : la piste envisagée (`nomsProjetsDisponibles()` retournant vide au second appel, faisant écrire un `Set` vide) ne s'est pas confirmée. `nomsProjetsDisponibles()` lit `[...document.getElementById('projet').options]` — le `<select>` global, peuplé une seule fois côté serveur par `lister_projets()` et jamais vidé/reconstruit côté client (seul `ajouterProjetAuSelecteur()` y ajoute une option, sans jamais en retirer) ; il est donc déjà indépendant de l'état d'affichage/filtre de l'onglet Résultats — `appliquerFiltresListe()` ne fait que masquer des LIGNES d'issues (`ligne.style.display`), jamais les options du select, et `localStorage.removeItem` ne touche pas non plus le DOM. Vérifié par exécution directe du fichier réel (`static/js/app.js` chargé tel quel dans un bac à sable `vm` Node, sans modification) : deux appels consécutifs à `reactiverTousLesFiltres()`, partant d'un état partiellement ou totalement désactivé, produisent chacun l'ensemble complet des projets — aucune régression vers un `Set` vide observée sur ce chemin. Seuls trois points du fichier réaffectent `projetsFiltresActifs` (déclaration initiale, `appliquerListeIssues()` via `restaurerFiltresProjets()`, et `reactiverTousLesFiltres()`) ; les deux derniers ont été rejoués sous test sans reproduire le symptôme. Le symptôme décrit (plus aucune issue affichée, récupérable seulement en recliquant chaque projet un par un) correspond en revanche exactement au comportement déjà connu et documenté de `basculerFiltreProjet()` lorsqu'on désactive le dernier projet actif restant (vérifié : le `Set` devient bien vide dans ce cas précis) — plausiblement la manipulation réellement en cause, plutôt qu'un second clic sur « Tous ».

**Solution retenue** : aucune correction de source nécessaire pour `nomsProjetsDisponibles()`, déjà appuyée sur une source stable. Garde-fou ajouté en second rideau dans `reactiverTousLesFiltres()` : si `nomsProjetsDisponibles()` retourne une liste vide (cas normalement inatteignable dans l'onglet Résultats, `chargerListeIssues()` court-circuitant déjà l'absence de projet), la fonction retourne immédiatement sans toucher à `projetsFiltresActifs` — état laissé inchangé plutôt que vidé. Vérifié par test direct (select vidé artificiellement) : l'état actif reste intact après le clic.

**Non modifié, signalé seulement (point 4)** : `basculerFiltreProjet()` désactivant le dernier projet actif produit bien un `Set` vide et un affichage sans aucune issue — confirmé par test. Comportement volontairement laissé tel quel : désactiver explicitement tous les projets un par un est une action délibérée de l'utilisateur, à la différence d'un second clic sur « Tous ».

**Vérifications (point 5)**, par exécution directe du fichier réel dans un bac à sable Node (`vm`) : **rechargement de page** — filtres partiellement désactivés puis persistés en `localStorage`, `appliquerListeIssues()` (chemin de chargement) restaure correctement l'état partiel, puis deux clics consécutifs sur « Tous » réactivent et maintiennent l'ensemble complet ; **reconstruction de la ligne de filtres** — ajout d'un projet au `<select>` puis `appliquerListeIssues()`/`construireBoutonsFiltre()` reconstruits, `nomsProjetsDisponibles()` inclut bien le nouveau projet, deux clics consécutifs sur « Tous » restent corrects et incluent le projet ajouté. `node --check static/js/app.js` → OK.

## 28 juillet 2026 — issue #258

Corrige deux défauts de `initialiser_git()` livrée par #257 : publication involontaire d'un répertoire préexistant, et absence de timeout sur les appels git (issue #258). **Défaut 1** : `creer_depot()` crée le dépôt GitHub en `--public`, et `initialiser_git()` fait `git add -A` puis pousse automatiquement — sans risque sur un répertoire neuf (cas nominal), mais si `REP_TRAVAIL` désigne un dossier **existant et non versionné** (cas explicitement couvert par le script, qui gère « création ET installation »), l'intégralité de son contenu était publiée sans confirmation ni aperçu ; le `.gitignore` minimal (`venv/`, `__pycache__/`, `*.pyc`, `*.log`, `.env`) ne protège que quelques cas. **Défaut 2** : `_git()` appelait `subprocess.run` sans `timeout=`, alors que le reste du code en pose un partout ailleurs (30s pour `commenter_issue`, 120s pour le push des pièces jointes) — un `git push` qui pend sur un réseau instable bloquait la requête Flask indéfiniment.

**Solution retenue — timeouts (point 1)** : `_git()` accepte désormais un `timeout` par appel, `TIMEOUT_GIT_LOCAL = 15` (secondes) pour `init`/`remote`/`add`/`commit`, `TIMEOUT_GIT_PUSH = 60` pour le push — seul appel réseau du lot, cohérent avec les timeouts déjà en place ailleurs. `subprocess.TimeoutExpired` est capturé et transformé en un `CompletedProcess` factice (`returncode=124`, `stderr` explicite) : le reste de la logique (qui ne fait déjà que tester `returncode != 0`) traite un timeout exactement comme un échec réseau ordinaire, sans exception qui remonterait et sans faire échouer la création — `commande_manuelle` renvoyée comme pour tout échec de push.

**Solution retenue — contenu préexistant (points 2/3)** : nouvelle `_fichiers_preexistants(rep_path)`, appelée AVANT toute écriture (avant que le futur `.gitignore` ne fausse le constat) : liste les fichiers du répertoire autres que ceux que le script crée lui-même (`CONTEXTE.md`, les 3 fichiers Specs MVC, `.gitignore` — constante `FICHIERS_CREES_PAR_SCRIPT`). Répertoire vide ou ne contenant que ces fichiers → comportement inchangé (init + commit + push automatiques). Contenu préexistant détecté → `git init`/remote/`.gitignore`/commit exécutés normalement, mais **le push n'est PAS déclenché** : `push_ok` reste `None` (distinct de `False`, qui signale un échec réel), nouveau champ `contenu_preexistant` (liste triée des chemins relatifs) renvoyé par `initialiser_git()` et propagé par `creer_projet()` (`git_contenu_preexistant`), `commande_manuelle` fournissant le `git push -u origin master` à lancer après relecture, et le `detail` explicitant pourquoi (dépôt public, contenu non relu) — pas un échec, une retenue volontaire.

**CLI** (`etape_git()`, résumé final de `main()`) : affiche la liste des fichiers préexistants détectés, tronquée à une dizaine (« … et N autre(s). »), et le message « push NON déclenché » distinct du message d'échec de push.

**Web** (`static/js/app.js`) : `afficherRappelProjet()` distingue désormais trois branches (déjà-git / poussé / **retenu volontairement** — contenu préexistant, avec la liste tronquée et l'explication « ce n'est pas un échec » — / échec de push), au lieu de fusionner la retenue volontaire avec l'échec de push comme le ferait un simple `else`.

**Doc** : §13 étape 5 réécrite en deux temps (push automatique si répertoire réellement vide ; garde-fou supplémentaire sinon) et complétée des deux timeouts. §18.2 : le paragraphe sur la seconde exception (#257) précisé — le raisonnement d'origine (« le dépôt distant vient d'être créé, rien à emporter ») est exact mais ne couvrait que le dépôt distant, pas le contenu local préexistant ; l'exception ne s'applique donc en pratique qu'aux répertoires réellement vides.

**Test** : nouveau `tests/test_init_git_local_258.py` (persisté — le test de #257 avait été fait sur des répertoires `/tmp` jetables puis supprimés, rien n'était resté sous `tests/`), quatre scénarios : répertoire neuf vide (comportement #257 inchangé, push tenté et échoue proprement sur un dépôt distant inexistant) ; déjà-git (strictement inchangé) ; contenu préexistant (issue #258 — `CONTEXTE.md` déjà présent n'est PAS compté, un fichier tiers l'est, aucun appel `git push` n'est tenté — vérifié en espionnant `subprocess.run` — et la commande manuelle est renvoyée) ; timeout de push (faux `git` en tête de `PATH` qui dort 2s sur `push` avec `TIMEOUT_GIT_PUSH` temporairement réduit à 0.3s — la création aboutit quand même, `push_ok:false`, pas d'exception). `python3 tests/test_init_git_local_258.py` → ✅ (4/4). Suites existantes repassées sans régression : `test_nettoyage_arbre_247.py`, `test_auto_extinction_217.py`, `test_verification_commentaire_237.py` → ✅. Aucune section renumérotée.

## 28 juillet 2026 — issue #257

Ajoute l'initialisation git du répertoire de travail à la création de projet, sans quoi le projet créé était inutilisable (issue #257). Contexte : `creer_projet()` (CLI et route Flask) créait le dépôt GitHub distant, le `.conf`, les labels, le répertoire de travail, `CONTEXTE.md` et mettait à jour la doc — mais ne faisait jamais `git init`/`git remote add` : aucun appel à `git` dans les 784 lignes du script, seule commande externe `gh`. Sur un projet réellement neuf (REP_TRAVAIL non versionné), `git pull --ff-only` en début de cycle du watcher échoue, et le commit de sauvegarde obligatoire avant toute modification en mode écriture ne peut pas s'exécuter — toute issue `mode_write` part en erreur. Cause probable : le script avait été écrit pour installer des dépôts déjà clonés de longue date, pas pour en créer de zéro ; le cas « projet neuf » n'avait jamais été parcouru jusqu'au bout avant `rummikub` (27 juillet 2026), initialisé à la main. **Aggravation** : après une création réussie, l'encart web `afficherRappelGit()` (`static/js/app.js`) affichait « ⚠ Action requise — pousser la doc sur GitHub » avec 3 commandes portant sur le dépôt **Bridge_Agent** (pousser `BRIDGE_AGENT_DOC.md`) — un encart « action requise » plein de commandes git juste après la création laissait croire à tort que rien d'autre n'était à faire, alors que deux étapes manquaient (init git + rédaction de `CONTEXTE.md`), non mentionnées nulle part.

**Solution retenue** : nouvelle étape « Dépôt git local » dans `creer_projet()` (`nouveau_projet.py`), entre « Fichiers contexte » et « Documentation », couvrant les deux cas : **déjà un dépôt git** (installation sur un projet existant, le cas de tous les projets actuels) → rien n'est fait, signalé « déjà un dépôt git — inchangé » ; **répertoire non versionné** (projet réellement neuf) → `git init -b master`, `git remote add origin` en **HTTPS** (`https://github.com/<owner>/<repo>.git`, jamais SSH — toute l'installation `gh` est en HTTPS), `.gitignore` minimal s'il est absent, commit initial, puis **push**. Nouvelle fonction `initialiser_git(rep, depot)`, réutilisée telle quelle par le CLI (`etape_git()`, avec confirmation comme les autres étapes, titre renuméroté « 8. » — Specs MVC en 7, doc en 9, résumé en 10) et par la route Flask (`creer_projet()`, sans confirmation individuelle, cohérent avec les autres étapes du flux web).

**Exception documentée à la règle « CCL/le script ne pousse jamais »** (issue #257, point 2) : ce push initial est déclenché par la création de projet elle-même, toujours à l'initiative d'Alain (terminal ou bouton web), jamais par un agent — même raisonnement que la route pièces jointes (§18.2, où une seconde exception du même type est désormais documentée explicitement). Un échec du push (réseau, droits) **ne fait pas échouer la création** : le commit reste local, `ok:true` mais `push_ok:false`, et une commande manuelle (`git push -u origin master`, ou la séquence complète si `git init` lui-même a échoué) est renvoyée dans `git_commande_manuelle` — affichée dans le récapitulatif CLI et dans un nouvel encart web dédié.

**Web** (`static/js/app.js`, `templates/index.html`, `static/css/style.css`) : nouvel encart `afficherRappelProjet()` (`#np-rappel-projet`, bordure bleue), **visuellement distinct** de l'encart existant `afficherRappelGit()` (bordure orange, dépôt Bridge_Agent uniquement, dont le titre est reformulé pour préciser « dépôt Bridge_Agent ») — c'est précisément la confusion entre les deux dépôts qui avait fait passer le problème inaperçu. Le nouvel encart rappelle systématiquement que `CONTEXTE.md` est créé **VIDE** (injecté dans chaque prompt CCL, plafonné à 4000 caractères) et affiche, le cas échéant, la commande git manuelle restante.

**Doc** : §13 « Commandes utiles » réécrit — décrivait auparavant seulement la commande de lancement sans aucune étape suivante ; détaille maintenant les 6 étapes réelles de bout en bout (dépôt GitHub, `.conf`, labels, contexte, **dépôt git local**, doc Bridge_Agent) et ce qui reste manuel dans tous les cas. §18.2 complété d'un paragraphe documentant cette seconde exception à la règle de push. Docstring d'en-tête de `nouveau_projet.py` mise à jour (« Zéro dépendance externe (stdlib + `gh`) » ne tenait plus, `git` est désormais requis pour le cas dépôt neuf).

**Test (point 6)** : sur des répertoires jetables sous `/tmp` (jamais de vrai dépôt GitHub créé, `depot_existe`/`creer_labels` court-circuités) : cas répertoire neuf → dépôt bien initialisé (`.git` présent, branche `master`, remote `origin` HTTPS correct, un commit), push échoue proprement (dépôt distant inexistant) sans faire échouer `creer_projet()` (`succes:true`), `git_commande_manuelle` renvoyée ; cas déjà-git → fichier préexistant intact, aucun remote ajouté, comportement strictement inchangé. Répertoires de test supprimés après vérification. Aucune section renumérotée.

## 27 juillet 2026 — issue #253

Étend la convention `CHANGELOG.md` à toute issue qui modifie le dépôt, pas seulement celles qui touchent la doc, et rattrape l'entrée manquante de #250 (issue #253, suite #252). Contexte : le texte introduit par #252 limitait l'obligation d'ajouter une entrée aux « issue[s] qui modifi[ent] cette doc » — restriction reconduisant, sous une autre forme, le trou que #240 avait dû combler à la main (issues #237/#238/#239, du code sans modification de doc, restées sans trace plusieurs jours) ; premier cas depuis #252 : #250 (correctif de contraste CSS pur, `static/css/style.css`) n'avait d'entrée ni dans `CHANGELOG.md` ni dans le pied de page, seulement dans l'historique git. **§10** reformulé : l'obligation d'ajouter une entrée en tête de `CHANGELOG.md` porte désormais sur **toute issue qui modifie le dépôt** (code, CSS, consignes, tests, documentation, quel que soit le fichier touché) ; le pied de page de cette doc reste, lui, réservé aux **trois entrées les plus récentes parmi les seules issues qui modifient cette doc elle-même** — comportement inchangé, une issue purement CSS comme #250 n'y figure donc pas. **Entrée rétroactive de #250** ajoutée dans `CHANGELOG.md`, à sa place chronologique (entre #252 et #251) : trois atténuations cumulées sur `.filtre-projet.inactif` (`opacity:.4` + fond `#f2f2f0` + texte `#999`) rendaient le nom des projets désélectionnés illisible (contraste `#999` sur `#f2f2f0` : 2,54:1, sous le seuil WCAG AA de 4,5:1, avant même l'effet de l'opacity) ; `opacity` globale supprimée — elle délavait aussi la pastille de couleur et l'emoji du bouton Ouvriers, pas seulement le texte — ne restent que fond et texte, `#5a5a5a` sur `#f2f2f0`, ratio 6,15:1. **Vérification des écarts (point 3)** : comparaison des numéros d'issue présents dans `CHANGELOG.md` à la liste des issues `done` fermées depuis #240 (13 issues, #240 à #252) — seules #241, #242 et #246 sont également absentes du changelog, mais légitimement : trois relances de build Windows Scrabble, `PROJET=bridge_agent` uniquement par la convention d'exception #233 pour les issues `for-windows`, ne modifiant aucun fichier du dépôt Bridge_Agent lui-même (build exécuté dans un partage CCW distinct) — hors du périmètre de la nouvelle règle, pas un oubli. Aucun autre écart trouvé. Aucune section renumérotée, aucun fichier `.py` modifié.

## 27 juillet 2026 — issue #252

Extrait l'historique du pied de page de `BRIDGE_AGENT_DOC.md` vers un `CHANGELOG.md` dédié (issue #252). Contexte : le pied de page (paragraphe « Dernière mise à jour : ... ») avait fini par contenir l'intégralité de l'historique du projet depuis l'issue #96, chaîné par 34 occurrences du connecteur « Précédemment » (suivi d'un tiret cadratin), soit 55523 caractères sur une seule ligne logique — coût de lecture (la doc est lue intégralement par Claude Chat à chaque conversation impliquant Bridge_Agent), coût d'écriture (chaque issue de doc réécrivait le bloc entier pour y insérer une entrée en tête), et risque de perte silencieuse (rien ne signalerait une troncature, un `git diff` sur une ligne de cette taille étant illisible). **Solution retenue** : nouveau fichier `CHANGELOG.md` à la racine du dépôt, contenant les 35 entrées historiques (de cette issue #252 jusqu'aux issues #135/#101/#97, suite #96) reformatées en sections `## <date> — issue #N`, contenu de chaque entrée repris **tel quel** — déplacement et reformatage, pas de résumé ni de réécriture. Extraction faite par script Python : séparation du pied de page d'origine sur la chaîne de connexion (« Précédemment » + tiret cadratin), avec vérification programmatique que la concaténation des segments reconstitue exactement le texte de départ (aucune perte possible) ; dates des 34 entrées antérieures (absentes du texte lui-même, seule la plus récente portait une date explicite) retrouvées sans ambiguïté via `git log` (recherche de `issue #N` dans les messages de commit, un seul jour de commit trouvé par numéro d'issue). Pied de page de `BRIDGE_AGENT_DOC.md` réduit aux **trois entrées les plus récentes** (celle-ci, #251, #249), suivies d'un renvoi vers `CHANGELOG.md` pour l'historique complet. **Vérification de non-perte (point 4)** : 34 occurrences du connecteur « Précédemment » avant modification, 35 entrées dans `CHANGELOG.md` après (34 + l'entrée « Dernière mise à jour » elle-même comptée à part) — décompte exact, aucun écart, confirmé avant livraison. **Vérification des dépendances (point 5)** : recherche de tout fichier s'appuyant sur le format du pied de page — une dépendance réelle trouvée dans `nouveau_projet.py` (deux occurrences, mise à jour de la date des projets §2/§7) : le script repère la ligne par `ligne.startswith("*Dernière mise à jour :")` puis remplace la date via le regex `(\*Dernière mise à jour : )[^—]*( —)`, insensible à tout ce qui suit le tiret cadratin — compatible tel quel avec le nouveau pied de page réduit, à condition que sa toute première ligne conserve exactement ce préfixe suivi d'un tiret cadratin juste après la date (vérifié, conservé sans changement). Aucun test (`tests/*.py`) ni aucun autre script ne référence ce pied de page ou la chaîne « Précédemment ». **§10** complété avec la nouvelle convention : toute issue modifiant la doc ajoute désormais son entrée en tête de `CHANGELOG.md` et fait glisser les trois entrées du pied de page (la plus ancienne des trois sortant du pied de page, elle reste disponible dans `CHANGELOG.md`). Aucune section renumérotée, aucun fichier `.py` modifié.

## 27 juillet 2026 — issue #250

Corrige le contraste illisible des pastilles de filtre projet désélectionnées (issue #250). Contexte : la règle `.filtre-projet.inactif` cumulait trois atténuations — `opacity:.4` global, fond `#f2f2f0`, texte `#999` — rendant le nom des projets désélectionnés difficile à lire, de façon inégale selon rendu/zoom du fait de l'`opacity` mêlée au fond de page sous-jacent ; contraste `#999999` sur `#f2f2f0` : 2,54:1, déjà sous le seuil WCAG AA (4,5:1) avant même l'effet de l'opacity. **Solution retenue** : suppression de l'`opacity` globale héritée de `.filtre-projet` — elle délavait aussi la pastille de couleur et l'emoji du bouton Ouvriers (`#filtre-ouvriers`, qui porte la même classe `.inactif` par défaut), pas seulement le texte du bouton ; ne restent atténués que le fond et le texte, ciblant uniquement ce qui doit l'être : `.filtre-projet.inactif{background:#f2f2f0;color:#5a5a5a}`. Contraste `#5a5a5a` sur `#f2f2f0` : 6,15:1, marge confortable au-dessus du seuil AA. La distinction sélectionné/désélectionné reste portée par trois signaux non corrélés — fond, texte, bordure (celle-ci retombant sur la valeur par défaut `1px solid #ccc`). Seul `static/css/style.css` modifié, aucun changement JS/HTML. Entrée ajoutée rétroactivement par l'issue #253 : cette issue, purement CSS, ne modifiait pas la doc et était donc restée hors du champ de la convention #252 alors en vigueur.

## 27 juillet 2026 — issue #251

Déclare restype/argtypes des appels ctypes kernel32 de l'objet Job Windows (issue #251, suite #249). Contexte : `_creer_job_windows_kill_on_close`/`_assigner_job_windows` appelaient `CreateJobObjectW`, `SetInformationJobObject`, `OpenProcess`, `AssignProcessToJobObject`, `CloseHandle` sans déclarer `restype`/`argtypes` — ctypes suppose alors par défaut un retour `c_int` (32 bits signés), alors que `CreateJobObjectW`/`OpenProcess` retournent un `HANDLE` (64 bits sur Windows x64) : le handle était donc tronqué silencieusement (fonctionnel en pratique tant que sa valeur reste petite, ce qui est le cas courant pour un handle noyau, mais rien ne le garantit), puis retronqué à chaque réutilisation en argument des appels suivants, eux aussi non déclarés — défaut structurellement invisible au test #249, qui mocke `ctypes.windll`. **Solution retenue** : nouvelle `_declarer_prototypes_kernel32_windows`, déclarant les cinq prototypes avec les types de `ctypes.wintypes` (`HANDLE`, `BOOL`, `DWORD`, `LPVOID`, `LPCWSTR`), appelée **une seule fois** à l'import du module sous la garde `if os.name == "nt":` — et non répétée à chaque appel, car le test `tests/test_nettoyage_arbre_windows_249.py` mocke `kernel32` par des méthodes liées Python (qui n'admettent pas l'affectation `.restype`/`.argtypes`) et ne force `os.name` qu'après l'import : une déclaration répétée aurait cassé ce mock. `python3 -c "import watcher"` vérifié toujours fonctionnel sous Linux (la garde empêche tout accès à `ctypes.windll`, absent hors Windows). **Point 2** : `_PROCESS_ALL_ACCESS = 0x1F0FFF` (valeur pré-Vista, toujours fonctionnelle) remplacé par les deux seuls droits documentés par Microsoft pour `AssignProcessToJobObject` — `PROCESS_SET_QUOTA | PROCESS_TERMINATE` (`_PROCESS_ACCES_JOB`). **Tests** : `tests/test_nettoyage_arbre_windows_249.py` et `tests/test_nettoyage_arbre_247.py` repassés sans modification (le mock ne traverse jamais la déclaration des prototypes, appelée seulement à l'import réel) — les deux passent. **§13** complété (sous-section « Nettoyage de l'arbre de process ») : nouveau paragraphe sur cette révision, et note sur les jobs imbriqués Windows 8+ sous NSSM (le service `CCW-Watcher` peut déjà être dans un job — l'assignation du process `claude` au job créé par `_preparer_job_windows` doit donc réussir même imbriquée ; si ce n'était pas le cas, le `log.warning` de `_preparer_job_windows` le signalerait — à vérifier lors de la prochaine validation réelle sur la VM CCW). Aucune section renumérotée..

## 27 juillet 2026 — issue #249

Remplace, sous Windows, le `taskkill /PID <pid> /T /F` de `_nettoyer_arbre_claude` par un objet Job noyau (issue #249, suite #247). Contexte : le nettoyage livré par #247 était correct sous POSIX mais très probablement inopérant sous Windows — la seule plateforme où le problème d'origine (`cmd.exe` orphelin verrouillant `Scrabble-Setup.exe` après un build CCW) avait été observé. `_nettoyer_arbre_claude` s'exécute dans le `finally` de `lancer_claude`, donc APRÈS le retour de `proc.communicate()` : à cet instant le process `claude` est déjà terminé et réapé, or `taskkill /PID <pid> /T /F` exige que le PID cible existe ENCORE pour parcourir son arbre généalogique — sur un PID mort il échoue immédiatement (« process not found ») sans toucher un seul descendant, exactement le scénario d'origine. `CREATE_NEW_PROCESS_GROUP` ne comble pas l'écart (sous Windows les groupes de process ne servent qu'au routage Ctrl+C/Ctrl+Break, pas à la terminaison d'une arborescence). Aggravation : seul le succès du `taskkill` produisait un `log.warning`, rendant l'échec totalement silencieux sous Windows ; le test de non-régression #247, exécuté sous Linux, ne couvrait que la branche POSIX. **Solution retenue** : objet Job noyau Windows (`CreateJobObjectW` + `SetInformationJobObject(JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)` + `AssignProcessToJobObject`), implémenté en `ctypes` pur (pas de nouvelle dépendance, pas de `pywin32`) — nouvelles fonctions `_creer_job_windows_kill_on_close`/`_assigner_job_windows`/`_preparer_job_windows`. Le job est créé et le process `claude` y est assigné **immédiatement après son démarrage** (`lancer_claude`, juste après le `Popen`, pendant que le process est encore vivant — seul moment où l'assignation est possible) ; fermer le handle du job dans `_nettoyer_arbre_claude(proc, job_windows)` termine alors toute la descendance encore assignée, PID vivant ou non. La branche POSIX (`start_new_session` + `os.killpg`) n'a **pas été touchée** : déjà correcte et testée. **Journalisation des échecs (point 3)** : `_preparer_job_windows` journalise tout échec de création/assignation du job, et `_nettoyer_arbre_claude` journalise tout échec de fermeture du handle (ou l'absence de job disponible) — la plateforme Windows ne peut plus rester silencieuse, succès ou échec. **Garde-fou (point 4)** : l'intégralité du corps de `_nettoyer_arbre_claude` est désormais enveloppée dans un `try/except Exception` — `_lister_processus_pgid` (OSError sur `iterdir()`), `os.killpg` (PermissionError) et les appels `ctypes` Windows ne peuvent plus s'échapper d'une fonction appelée depuis un `finally`, ce qui aurait masqué la valeur de retour de `lancer_claude`. **Test** : nouveau `tests/test_nettoyage_arbre_windows_249.py` — le scénario Windows réel n'étant pas exécutable sur le ThinkPad (Linux), mock de `ctypes.windll` (+ `os.name` forcé à `"nt"`) vérifiant l'ordre des appels ctypes (`CreateJobObjectW` → `SetInformationJobObject` → `OpenProcess` → `AssignProcessToJobObject` → `CloseHandle`), la journalisation succès/échec à chaque étape, et qu'une exception pendant le nettoyage n'est jamais remontée ; `tests/test_nettoyage_arbre_247.py` (POSIX) repassé sans modification — les deux passent (`python3 tests/test_nettoyage_arbre_247.py` et `python3 tests/test_nettoyage_arbre_windows_249.py` → ✅). ⚠️ **Ce mock ne remplace pas une validation réelle sur la VM CCW** : il vérifie que le code ctypes fait les bons appels, pas que Windows tue effectivement l'arbre de process en pratique — validation par build réel sur CCW encore nécessaire avant de considérer le correctif éprouvé en conditions réelles. **§13** réécrit (sous-section « Nettoyage de l'arbre de process ») : la justification de #247 (« symétrie CCL/CCW préférée à l'objet Job, script unique partagé ») est explicitement invalidée — cette symétrie coûtait la correction sous Windows, un objet Job en `ctypes` pur restant parfaitement compatible avec un script unique CCL/CCW (branche POSIX inchangée, aucune divergence de dépendance). Aucune section renumérotée.

## 27 juillet 2026 — issue #248

Isole le push de la route pièces jointes sur une branche orpheline dédiée, `pieces-jointes` (issue #248). Contexte : la route `POST /joindre-image` (§18, issue #191) terminait par `git push origin HEAD:<branche_courante>` — or git ne peut pas publier un commit sans ses ancêtres, ce push emportait donc AVEC l'image tous les commits locaux non encore poussés de la branche de travail, c'est-à-dire tout travail que CCL avait committé et qu'Alain n'avait pas encore relu : brèche dans le garde-fou central « CCL ne pousse jamais, Alain vérifie puis pousse » puisque rien d'autre n'était censé pousser à sa place ; aggravé par la propagation automatique aux autres clones (watchers en `git pull --ff-only` de début de cycle, dont la VM CCW, en quelques secondes) et par le fait que le fichier était écrit et committé DANS `REP_TRAVAIL` — l'arbre de travail qu'un watcher peut être en train d'utiliser pour une tâche `mode_write` au même instant. **Solution retenue** : commit construit par PLOMBERIE git (`hash-object -w` sur un fichier temporaire hors dépôt, puis `read-tree`/`update-index --cacheinfo`/`write-tree` sur un index TEMPORAIRE isolé via `GIT_INDEX_FILE`, puis `commit-tree`), sans jamais toucher à l'arbre de travail, à l'index réel ni à `HEAD` du dépôt ; racine sans parent à la première publication, sinon enfant du tip précédent (`git fetch origin pieces-jointes` best-effort) ; poussé isolément (`git push origin <sha>:refs/heads/pieces-jointes`) sur une branche **orpheline** ne contenant que `issue-attachments/` — par construction, aucun commit de code ne peut plus jamais être emporté, quel que soit l'état de la branche de travail. URL adaptée en conséquence (`.../pieces-jointes/issue-attachments/<fichier>`) ; le fichier n'est plus jamais écrit dans `REP_TRAVAIL` (transite par un fichier temporaire, nettoyé dans un `finally`). Le repli « garde-fou minimal » (refus si `rev-list --count` > 0) n'a pas été nécessaire, la plomberie s'étant révélée simple à implémenter proprement. **§18 réécrit** (nouvelle sous-section **§18.1bis** détaillant le mécanisme, **§18.2** complété : la justification de l'exception `push` ne repose plus seulement sur l'intention d'Alain mais aussi sur l'impossibilité technique désormais garantie de publier du code par cette voie). **Testé de bout en bout** sur un dépôt jetable (bare + clone) : un commit local « FIX CCL non relu » jamais poussé reste totalement absent d'origin après upload d'image (objet introuvable sur le bare, branche de travail inchangée, `HEAD`/index/arbre de travail du clone intacts — `git status --porcelain` vide) ; branche `pieces-jointes` créée avec un unique fichier sous `issue-attachments/`, sans ancêtre commun avec la branche de travail (`git merge-base` échoue, confirmant l'historique orphelin) ; deuxième upload vérifié en accumulation (2 commits, 2 fichiers, parenté correcte). Aucune section renumérotée hors les ajouts internes au §18.

## 26 juillet 2026 — issue #247

Garantit qu'aucun descendant du process `claude` ne survit au retour de `lancer_claude` (issue #247). Contexte : un `cmd.exe` de build Windows (CCW, `rebuild_scrabble.bat`) était resté vivant après la fermeture de l'issue, verrouillant `Scrabble-Setup.exe` jusqu'à un `taskkill` manuel — sans le moindre signal dans le journal ; défaut de fond, générique : rien ne garantissait qu'un process lancé pendant une tâche soit mort à la fin de celle-ci. **`lancer_claude`** (`watcher.py`) lance désormais `claude` via `subprocess.Popen` (plutôt que `subprocess.run`, pour garder la main sur le PID) avec `start_new_session=True` (POSIX) / `CREATE_NEW_PROCESS_GROUP` (Windows), isolant ce process dans un groupe/une session à lui ; un bloc **`finally`** — donc exécuté quel que soit le mode de sortie (succès, échec, `TimeoutExpired`, exception), et **avant** `commenter_resultat_avec_retry`/`fermer_issue` — appelle la nouvelle `_nettoyer_arbre_claude(proc)` : sous POSIX, `_lister_processus_pgid` énumère (lecture directe de `/proc`, sans dépendance externe) les process vivants du pgid de ce `claude`, journalise chacun en `log.warning` (PID + ligne de commande) puis `os.killpg(pid, SIGKILL)` sur ce seul groupe ; sous Windows, `taskkill /PID <pid> /T /F`. **Solution retenue** (justifiée en détail dans la nouvelle sous-section **§13** « Nettoyage de l'arbre de process après une tâche ») : terminaison de l'arbre après coup plutôt qu'un objet Job Windows (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`) — ce dernier est natif et sans fenêtre de course, mais une API Windows pure (`ctypes`/`pywin32`) sans équivalent POSIX, alors que `watcher.py` est le script UNIQUE partagé par CCL et CCW ; fenêtre de course résiduelle de quelques millisecondes entre la fin de `communicate()`/le timeout et l'appel de nettoyage, jugée négligeable et strictement meilleure que l'absence totale de garantie d'avant #247. **Point 4 (critique), vérifié explicitement** : le nettoyage ne cible **jamais** par nom d'exécutable, seulement le pgid/l'arbre du PID de CE `claude`, garanti distinct de celui du watcher et de tout watcher frère par construction (`start_new_session`/nouvelle session) — une erreur ici aurait pu arrêter tous les watchers d'une même machine. **Journalisation, pas critère d'échec** : chaque orphelin tué produit un `log.warning` explicite ; le nettoyage ne fait jamais échouer la tâche, c'est une garantie de fin de traitement. **Test de non-régression** : nouveau `tests/test_nettoyage_arbre_247.py` — un faux `claude` (script en tête de PATH) lance un vrai enfant bloqué sur lecture (FIFO jamais écrite, équivalent stdin qui n'aboutit jamais) puis termine ; le test vérifie que l'enfant est mort après le retour de `lancer_claude`, que le nettoyage est journalisé (PID présent dans un `log.warning`), et que le process de test (rôle du watcher) n'est jamais affecté — passe (`python3 tests/test_nettoyage_arbre_247.py` → ✅). Aucune section renumérotée.

## 26 juillet 2026 — issue #245

Aligne le texte historique du §14 sur l'amendement #244 (issue #245). Contexte : le paragraphe « ⚠️ Contrainte d'exécution synchrone (rappel) », hérité de #208 et volontairement laissé intact par #244 comme référence documentaire, interdisait encore catégoriquement « un mécanisme d'attente différée, de tâche en arrière-plan ou de "je répondrai plus tard" » — formulation contredite par le texte en vigueur de `consignes/globales.md` depuis #244 (l'arrière-plan encadré, avec interrogation de la sortie en boucle DANS la même exécution, y est permis ; seul conclure son tour de parole avant la fin réelle et vérifiée de l'opération reste proscrit). Un Claude Chat consultant le §14 en premier — cas fréquent, section de référence sur la délégation — pouvait lire l'interdiction absolue sans descendre jusqu'à l'encart d'injection qui la nuançait déjà, et reconduire dans une issue de build une consigne que le système n'applique plus. **§14** : le paragraphe est reformulé pour dire une seule chose, alignée sur `globales.md` — proscrit : conclure son tour de parole avant la fin réelle et vérifiée de l'opération ; permis : l'arrière-plan encadré (interrogation de la sortie en boucle DANS la même exécution) ; restent interdits sans changement : « monitor », notification, rappel programmé, formulations « je répondrai plus tard ». Reste du paragraphe conservé tel quel (aucune reprise possible après réponse, boucle `sleep` + `gh issue view` pour l'attente d'un ouvrier) ; l'encart d'injection qui suit (issues #209/#243) n'a pas été touché, sa nuance restant exacte. Recherche `arrière-plan`/`monitor`/`attente différée` sur tout le fichier : une autre occurrence trouvée hors §14 et hors pied de page — **§12.1** (ligne « Globale » du tableau des trois couches : « contrainte d'exécution synchrone et bloquante, sans attente différée, universelle depuis #243 ») — laissée telle quelle, ce résumé reste exact (l'interdit qu'elle nomme est bien l'attente différée pour conclure, pas l'arrière-plan comme technique) ; le pied de page (historique de #244 et antérieurs) laissé tel quel par consigne explicite. Aucune section renumérotée, aucun fichier `.py` ni `consignes/*.md` modifié.

## 26 juillet 2026 — issue #244

Amende la contrainte d'exécution universelle de #243 pour lever une contradiction qu'elle introduisait avec le plafond de timeout de l'outil Bash (issue #244). Contexte : le texte issu de #243 interdisait catégoriquement l'arrière-plan (« Ne lance jamais une commande en arrière-plan ») et proposait comme repli de relancer avec un timeout explicite plus long — or l'outil Bash a un timeout MAXIMUM par appel (de l'ordre de dix minutes) qu'aucun paramètre ne permet de dépasser ; si un build excède ce plafond (hypothèse plausible pour #241/#242, probablement à l'origine du basculement en arrière-plan qui avait motivé #243), l'agent se retrouvait pris entre deux interdits — attendre en un seul appel ou lancer en arrière-plan — et improviserait. Second défaut, dans la même phrase : le repli « boucle sur sa sortie DANS cette même exécution » SUPPOSE une exécution en arrière-plan (on lance, puis on interroge la sortie en boucle) ; la consigne décrivait donc le bon comportement tout en interdisant le mécanisme qui le rend possible. Le fautif n'est pas l'arrière-plan en soi, c'est de conclure son tour de parole sans avoir attendu la fin réelle de l'opération. **`consignes/globales.md`** : la fin du bullet « Contrainte d'exécution » (à partir de « Si une opération dépasse le timeout d'un appel d'outil… ») est réécrite — ce qui est interdit, c'est de CONCLURE le tour de parole avant que l'opération soit terminée et son résultat vérifié, pas l'arrière-plan comme technique ; en cas de dépassement du timeout d'un appel d'outil, deux voies restent permises : relancer avec un timeout explicite plus long tant que le plafond de l'outil le permet, OU lancer en arrière-plan À CONDITION IMPÉRATIVE d'interroger sa sortie en boucle DANS cette même exécution jusqu'à complétion réelle ; restent interdits sans changement le « monitor », la notification, le rappel programmé et toute formulation « je répondrai/j'attends… » en guise de conclusion ; rappel inchangé qu'aucune reprise n'existe (le watcher ferme l'issue dès la réponse postée). **`consignes/type_chef.md`** vérifié : sa formulation (« aucune attente différée, aucun monitor ») reste cohérente avec le nouveau texte — non touché. **§12.1** (ligne « Globale ») et **§14** (encart d'injection automatique) vérifiés : leurs résumés restent exacts sans qu'il soit besoin d'y ajouter la précision arrière-plan/plafond — non touchés. Aucune section renumérotée, aucun fichier `.py` modifié.

## 26 juillet 2026 — issue #243

Généralise l'interdiction d'attente différée à toute issue et distingue opération longue légitime du blocage sans progrès (issue #243). Contexte : les issues #241/#242 (builds Scrabble, CCW) se sont fermées `done` avec un rapport annonçant attendre une notification de fin de build ou un rappel programmé, alors que le build avait réellement abouti (`Scrabble.exe` et `Scrabble-Setup.exe` présents, datés du jour) — pas un échec de build, un rapport ne reflétant pas la réalité, produit par un agent sorti avant la fin. Deux consignes en cause, inversées par rapport à ce qu'exige une tâche longue : `consignes/globales.md` (injecté dans TOUTE issue) demandait d'abandonner toute commande « boucle/tarde anormalement (> 30s sans progrès net) » — écrit pour #214 (commande refusée par le système de permissions, bouclage réel), mais assez général pour couvrir aujourd'hui un build PyInstaller + Inno Setup (plusieurs minutes, peu de sortie visible), appliqué à la lettre ; l'interdiction qui aurait dû s'appliquer (ne jamais recourir à une attente différée, un « monitor », etc.) vivait dans `consignes/type_chef.md`, injecté SEULEMENT pour le TYPE `chef` — une issue de build n'en est pas une. Le mode de défaillance n'ayant rien de spécifique au rôle de chef (il guette toute tâche dont une étape dépasse le timeout d'un appel d'outil), la contrainte est rendue universelle. **`consignes/globales.md`** : le rappel issu de #214 est reformulé pour distinguer une commande refusée par les permissions ou bloquée SANS AUCUN PROGRÈS (→ abandon immédiat, comportement inchangé) d'une opération longue mais qui PROGRESSE normalement (build, compilation, installation de dépendances, suite de tests, clonage volumineux — → ce n'est PAS une anomalie, il faut attendre sa fin) ; le seuil de 30s ne s'applique plus qu'à l'absence de progrès, plus à la durée en soi. Nouveau rappel généralisé depuis `type_chef.md` : accomplir la tâche en une seule exécution synchrone et bloquante, jamais de commande en arrière-plan / « monitor » / notification / rappel programmé / « je répondrai quand… », relancer avec un timeout explicite plus long ou boucler DANS la même exécution en cas de dépassement du timeout d'un appel d'outil, jamais conclure sur une attente — rappel qu'aucune reprise n'existe, le watcher fermant l'issue dès la réponse postée. **`consignes/type_chef.md`** : allégé pour éviter la redondance — ne garde que la spécificité chef (boucler `sleep` + `gh issue view` en attendant la fermeture des issues ouvrières, puis synthèse finale), la contrainte générale étant désormais dans `globales.md`. **TYPE `build`** : vérification de `watcher.deduire_type_issue`/`TYPES_ISSUE` — `build` n'est PAS une valeur reconnue (`TYPES_ISSUE` = chef/ouvrier/spec_vue/spec_metier/spec_persistance/normal, et `_classer_valeur_type` n'a aucune branche pour « build » : même un en-tête explicite `| TYPE | build |` retomberait sur `normal`) ; `consignes/type_build.md` n'a donc PAS été créé — le mécanisme ne s'y prête pas sans modifier `watcher.py` (hors périmètre de cette issue), et de toute façon le vrai correctif (la contrainte universelle dans `globales.md`) couvre déjà le cas des builds sans dépendre d'un TYPE dédié. **§12.1** : la parenthèse résumant les rappels globaux (ligne « Globale ») mise à jour pour refléter la distinction blocage/progrès et la contrainte d'exécution synchrone désormais universelle. **§14** : le bloc « Contrainte d'exécution impérative » renommé « rappel » et son encart d'injection automatique mis à jour pour pointer vers `globales.md` (universel depuis #243) plutôt que `type_chef.md`, qui n'ajoute plus que la spécificité chef. **§1** : rattrapage d'une omission de #240 — la réécriture du paragraphe sur le pull automatique avait fait disparaître la parenthèse sur les projets à **périmètre dynamique** (dépôt-cible défini par issue, dépôts d'audit non rafraîchis par le pull automatique, distincts du clone de travail du watcher) ; réintroduite, adaptée au nouveau texte. Aucune section renumérotée.

## 26 juillet 2026 — issue #240

Correctif documentaire §1/§14/§16 et rattrapage de trois issues committées sans mise à jour du DOC (issue #240). Incident du 26/07 : le clone `C:\CCW\Bridge_Agent` de la VM (celui d'où s'exécute réellement `watcher.py`) avait **80 commits de retard** sur `origin/master`, sans aucun signal — le service tournait avec du code antérieur à l'issue #195, cause probable de l'incident #236 (issue fermée `done` sans commentaire de résultat). **§1** réécrit : le `git pull --ff-only` automatique de début de cycle porte bien sur `REP_TRAVAIL` avec la même logique CCL/CCW, mais ne met à jour le CODE du watcher que lorsque `REP_TRAVAIL` coïncide avec le clone du dépôt Bridge_Agent — vrai côté CCL, **faux** côté CCW en modèle unifié (#231), où `REP_TRAVAIL = \\VBOXSVR\CCW_Share` n'est même pas un dépôt git et où le clone contenant `watcher.py` (`C:\CCW\Bridge_Agent`) vit ailleurs, mis à jour par personne. L'ancienne affirmation « comportement identique CCL et CCW » est supprimée car trompeuse sur ce point précis. **§16** gagne un bloc d'avertissement opérationnel : ce clone n'est **jamais** mis à jour automatiquement ; procédure obligatoire après tout push touchant `watcher.py` — `git pull --ff-only` dans `C:\CCW\Bridge_Agent` **puis redémarrage du service** `CCW-Watcher` (`nssm restart`, un pull seul ne suffit pas : un process Python déjà démarré garde en mémoire le code chargé à son lancement) — avec la commande de contrôle rapide `git status -sb` (ne doit jamais afficher `behind`), et le cas réel des 80 commits de retard comme justification. **§14** corrigé : dans le bloc « Quand NE PAS passer par un chef » (#225), la référence au service `CCW-Watcher-<Projet>` — nom venant du modèle multi-projets abandonné par #231 — est remplacée par `CCW-Watcher`. Rattrapage de trois issues committées sans entrée de pied de page : **#237** — `commenter_issue`/`editer_dernier_commentaire` passent par `--body-file` (fichier temporaire UTF-8) au lieu de `--body`, supprimant la limite argv Windows de 32767 caractères ; `commenter_resultat_avec_retry` vérifie désormais la publication par relecture de l'issue (un exit code 0 de `gh` ne suffit plus, la présence effective du commentaire est exigée) ; nouveau marqueur `MARQUEUR_RESULTAT` (`<!-- bridge:resultat -->`) en tête du commentaire de résultat, utilisé aussi par `resultat_deja_poste` à la place de l'ancienne sous-chaîne `"## Résultat"` qui matchait à tort `"## Résultat attendu"` ; test `tests/test_verification_commentaire_237.py` ; deux effets de bord assumés — deux appels `gh` par tentative, et possibilité d'un commentaire en double si la publication réussit mais que la relecture échoue transitoirement (perte silencieuse échangée contre doublon visible). **#238** — `fermer_issue` inspecte désormais les codes de retour de `close` et `add-label`, retourne un booléen, et journalise explicitement les états incohérents (fermée sans label / label sans fermeture) sans compensation automatique. **#239** — libellé d'agent de l'ACK déduit automatiquement de `platform.system()` (« agent Linux » / « agent Windows »), avec champ optionnel `LIBELLE_AGENT` pour forcer un libellé explicite si la détection automatique ne convient pas ; le §16 avait déjà été modifié par cette issue mais aucune entrée de pied de page n'avait été ajoutée — rattrapée ici. Aucune section renumérotée.

## 26 juillet 2026 — issue #233

§3 « Créer une issue » : ajout d'une **exception `PROJET`** pour les issues `for-windows` (issue #233, suite #231). Rapport remonté par le Claude du projet `actualise` : lors de la génération d'une issue de build Windows, le champ `PROJET` avait été renseigné avec `actualise` au lieu de `bridge_agent`, en appliquant par erreur la règle générale du §3 (« nom exact du projet cible »). Or le §16.3 (modèle CCW unifié, #231) applique correctement `PROJET=bridge_agent` dans son template — c'est la config du watcher CCW unique qui compte, pas le projet réellement construit — mais le §3, consulté en premier par Claude Chat, ne mentionnait pas cette exception. Ajout d'un second bloc d'avertissement juste après celui existant (« Claude Chat doit toujours inclure `| PROJET | <nom> |` ») précisant que pour les issues `for-windows`, `PROJET` reste toujours `bridge_agent`, le nom du projet cible s'exprimant en texte dans le corps (chemins, `git clone`/`git pull`), avec renvoi au template du §16.3. Aucune section renumérotée.

## 26 juillet 2026 — issue #231

§16 « Agent Windows CCW » : documentation du **modèle CCW unifié** (issue #231), qui remplace le modèle multi-projets (#170, un service NSSM par projet). Un seul service NSSM `CCW-Watcher` surveille désormais les issues `for-windows` de `AlainDelree/Bridge_Agent`, `REP_TRAVAIL = \\VBOXSVR\CCW_Share` (accessible depuis Linux à `/home/alain/Bridge_Agent_CCW_Share/`), chaque projet buildé étant cloné dans un sous-dossier dédié `\\VBOXSVR\CCW_Share\CCW\<projet>\` — séquencement strict des builds par construction (un seul process `watcher.py`), zéro contention CPU/RAM entre builds parallèles. Validé en production avec le build PyInstaller d'`actualise`. Introduction du §16 réécrite (titre « (en préparation) » retiré, devenu opérationnel) ; nouvelle sous-section **§16.3 « Procédure — builder un projet Windows »** détaillant le template d'issue en 4 étapes (exception `git config --global --add safe.directory` sur le chemin UNC — obligatoire une seule fois par sous-dossier —, clone ou `git pull --ff-only`, `pip install -r requirements.txt`, build `python -m PyInstaller --noconfirm --onedir --noconsole`), la récupération manuelle des artefacts côté Linux et le rappel qu'aucun token GitHub Contents n'est requis (dépôts publics, seul le token Issues du service `CCW-Watcher` sert). Les scripts `ajouter_projet_ccw.ps1` et `finaliser_projet_ccw.ps1` (tableau de provisioning) marqués **« obsolète — modèle multi-projets abandonné, conservé à titre historique »** — ne plus les utiliser, mais conservés dans le dépôt sans suppression. Reste du §16 (§16.1 maintenance 90 jours, §16.2 onglet CCW, description historique du modèle multi-projets #170) laissé inchangé, hors du périmètre de cette issue.

## 26 juillet 2026 — issue #225

§14 « Délégation Chef → Ouvrier » : ajout d'un bloc **« Quand NE PAS passer par un chef »** (issue #225), inséré juste après le paragraphe « Principe » et avant « Ce n'est pas déclenché automatiquement… ». Contexte : sur le projet `actualise`, une tâche entièrement Windows avait donné lieu à une issue chef CCL dont le seul travail était de créer immédiatement un ouvrier CCW et d'attendre sa fermeture — sans étape réelle côté Linux, correct mais coûteux (deux issues, deux invocations `claude`, TIMEOUT long, attente synchrone bloquante payée pour rien). Le nouveau bloc pose le **critère de décision** : le chef se justifie quand la tâche comporte du travail réel côté Linux (avant et/ou après) dans la même unité de travail ; si la TOTALITÉ de la tâche s'exécute sous Windows, créer directement l'issue avec `| LABELS | for-windows |` (§3) plutôt qu'un chef. **Contre-exemple explicite** : un chef qui se contente de créer un ouvrier puis d'attendre sa fermeture, sans orchestration réelle, est du surcoût pur. Rappel que l'**exemple validé** plus bas dans la section (dictionnaire déposé côté Linux puis rebuild côté Windows) reste un cas où le chef EST justifié — la nouvelle règle ne le contredit pas. **⚠️ Contrepartie opérationnelle** ajoutée dans le même bloc : le rallumage automatique du watcher à la création d'une issue (§13, mécanisme 2) ne vaut QUE pour les issues `for-linux` — une issue `for-windows` directe ne démarre rien, donc vérifier dans l'onglet CCW (§16.2) que la VM `CCW-Build` tourne et que le service `CCW-Watcher-<Projet>` est démarré avant d'en envoyer une, sinon elle reste ouverte sans aucun signal. En miroir, **§3** (paragraphe décrivant le champ `LABELS`, juste après la phrase sur le cas d'usage `| LABELS | for-windows |`) gagne une phrase de renvoi croisé vers ce bloc du §14. Aucune section renumérotée ; reste du §14 (contrainte d'exécution impérative, format des titres, timeout du chef, exemple validé) et reste du §3 inchangés.

## 25 juillet 2026 — issue #224

Nouvelle section **§19 « Calibration automatique du TIMEOUT »** (issue #224), documentant de bout en bout le système mis en place par les issues #220 (extension d'`historique_durees.json`), #221 (mécanique EWMA `etat_timeout.json`/`etat_ambiance.json`), #222 (exposition du `TIMEOUT_suggéré` dans le commentaire de clôture GitHub) et #223 (exclusion des `expiree=true` du badge d'estimation de l'interface). Jusqu'ici ce système n'était documenté nulle part dans `BRIDGE_AGENT_DOC.md` — seul `CONTEXTE.md` en gardait une trace partielle, ajoutée par #221 et jamais mise à jour depuis, de toute façon plafonnée par sa limite de taille pour l'injection prompt (§12.1). La nouvelle section couvre, à partir d'une lecture du code réel de `watcher.py`/`app/issues.py` (pas une paraphrase des rapports d'issue) : l'objectif et le principe d'inspiration (RTO TCP, Jacobson/Karels), la formule complète et chacun de ses termes, les deux fichiers d'état (`logs/etat_timeout.json`, `logs/etat_ambiance.json` — partagés entre watchers, verrouillés, écriture atomique), le tableau des constantes actuelles en soulignant explicitement qu'elles sont des valeurs de DÉPART non backtestées, le canal d'exposition (bloc `⏱️/📊` dans le commentaire de clôture, sans aucune application automatique — le TIMEOUT réellement utilisé reste celui de l'en-tête, `extraire_timeout`), et une liste explicite des limitations connues (`tag_reseau` jamais peuplé donc `F_reseau`/`F_local` neutres, incohérence inerte de `lire_timeout_suggere` sur échec définitif, démarrage à froid trompeusement optimiste, aucun backtest des constantes, distinction avec le badge `estimer_duree` de #223). Aucune autre section renumérotée ni modifiée.

## 24 juillet 2026 — issue #217

Correctif horloge d'auto-extinction (issue #217) : le watcher pouvait s'éteindre **immédiatement après un traitement réel** lorsque celui-ci s'étirait au-delà du délai d'inactivité (`DELAI_INACTIVITE_MIN`, défaut 20 min). Cause : `derniere_activite` (horloge monotone d'inactivité, #200) n'était réarmée qu'**en tête de cycle**, juste après `lister_issues()` et **avant** de lancer `traiter_issue()` — donc jamais pendant le traitement (potentiellement long : plusieurs timeouts de 300 s + retries en cascade). Si le traitement d'une seule issue dépassait le délai (cas réel `watcher-scrabble.log` du 24/07/2026 : #237/#238 traités sans interruption de 08:59 à 09:22, puis extinction à 09:23:08 — 14 s après le succès de #238), l'horloge restait figée à l'instant du **début** du cycle ; le test d'extinction du cycle suivant se déclenchait alors sur une horloge périmée, ne reflétant pas le travail réellement effectué. **Correctif** (`watcher.py`, boucle principale) : réarmement de `derniere_activite` **aussi APRÈS** la boucle de traitement, dès qu'au moins une issue traitable a été traitée ce cycle (option a du diagnostic — réarmer sur le travail réel, préférée à l'option b « revérifier `lister_issues()` avant `sys.exit` » car elle satisfait plus directement l'objectif « ne jamais éteindre si du travail vient d'avoir lieu », sans appel réseau supplémentaire ni cas où une issue devenue fermée entre-temps laisserait l'extinction filer). Le flag `travail_a_faire` (calculé une fois) conditionne les deux réarmements ; l'extinction reste possible quand plus rien n'est traitable. **Test de non-régression** : `tests/test_auto_extinction_217.py` pilote le vrai `watcher.main()` avec horloge mockée (`time.monotonic`/`time.sleep` patchés) sur 3 scénarios — (1) traitement long ~23 min + issue restante → **pas** d'extinction prématurée (échoue sur le code d'avant #217, passe sur le code corrigé), (2) inactivité réelle → extinction bien déclenchée, (3) issue non-traitable (`done`) → n'empêche pas l'extinction. §13 (mécanisme 3 « Extinction automatique ») mis à jour pour décrire le double réarmement avant/après.

## 24 juillet 2026 — issue #214

Nouveau rappel global « abandon immédiat au refus de permission » (issue #214) : ajout, à la fin de `consignes/globales.md`, d'un rappel systématique — si une commande/un outil est **refusé par le système de permissions** (session non-interactive, aucune approbation possible) ou **boucle/tarde anormalement** (> 30s sans progrès net), CCL doit **abandonner immédiatement** l'approche et le signaler dans son rapport plutôt que de retenter, en basculant si possible sur un repli plus simple (lecture directe, `grep`, analyse manuelle) et sans jamais insister sur une commande déjà refusée. Motivation : comparaison des issues Scrabble #235 (timeout à 300s, bouclage sur une commande refusée) et #238 (succès) — la seule différence significative était la présence, dans #238, d'une consigne explicite d'abandon-au-lieu-de-retenter ; en session non-interactive, un refus de permission Claude Code est systématique et définitif (aucun utilisateur pour approuver), donc retenter est vain. Consigne volontairement **générale** (pas spécifique à Scrabble ni à JS/eslint) car le problème touche toute commande nécessitant une approbation (installation de paquet, exécution d'un binaire, etc.), quel que soit le projet ou le langage. §12.1 : la parenthèse résumant les rappels globaux dans le tableau des trois couches est complétée (ajout d'« abandon immédiat au refus de permission / boucle anormale ») ; la liste complète des rappels n'étant pas reproduite ailleurs dans la doc, aucune autre duplication à mettre à jour.

## 23 juillet 2026 — issue #211

Déplacement de l'injection des consignes trois couches dans `watcher.py` — couverture universelle (issue #211). Les consignes (globales/type/projet, #209) ne sont plus écrites dans le **corps** de l'issue par `app/issues.py` (chemin qui ne couvrait QUE les issues créées via le formulaire web), mais injectées dans le **prompt donné à CCL au moment du traitement** par `watcher.py` (`lancer_claude` → nouvelles `_consignes_injectees`/`_lire_consigne`, reprises de `app/issues.py`), exactement sur le modèle de `CONTEXTE.md`/`FICHIER_CONTEXTE`. Le point de passage devient **unique** : peu importe le chemin de création — formulaire web, `gh issue create` d'un chef (§14), création manuelle GitHub (§3) — `watcher.py` déduit le TYPE (`deduire_type_issue` sur le titre/corps réels) et le projet (`CFG.nom`), puis ajoute le bloc **après** le bloc `CONTEXTE` et **avant** la clause de périmètre / le garde-fou (regroupement des « règles » en fin de prompt, zone la mieux suivie). Cas particulièrement corrigé : les issues **ouvrières créées par un chef** (chemin 2, vraies tâches `mode_write`) recevaient auparavant zéro consigne — c'est justement là que les rappels de sécurité comptent le plus. `app/issues.py::construire_body` revient à un corps **en-tête + corps rédigé** seulement (suppression de `_consignes_injectees`/`_lire_consigne`/`DOSSIER_CONSIGNES` et de l'import `logging` devenu inutile) — source unique de vérité désormais côté watcher, plus de double injection. Garde-fous inchangés (#209) : `globales.md` absent → `log.warning` sans bloquer le traitement ; `type_*`/`projet_*` absents → silencieux. Conséquence assumée (comme pour `CONTEXTE.md`) : les consignes ne sont plus visibles dans le corps d'une issue sur GitHub. **§12.1 réécrite** (modèle prompt + couverture universelle des 3 chemins + emplacement dans le prompt) et **§10** mis à jour (`consignes/` = injecté dans le prompt CCL, plus « en tête de chaque issue »). Testé de bout en bout par une issue `TYPE=chef` `mode_write` créée **directement en CLI** (`gh issue create`, hors formulaire) : le prompt CCL assemblé par le watcher contient bien les consignes globales + `type_chef.md`.

## 23 juillet 2026 — issue #209

Architecture à trois couches d'injection de consignes (issue #209) : nouveau dossier `consignes/` à la racine, injecté **dans le corps de chaque issue** par `app/issues.py` (`construire_body` → `_consignes_injectees`), entre le tableau d'en-tête et le corps rédigé par Claude Chat. Trois couches, de la plus générale à la plus spécifique : **globales** (`consignes/globales.md`, **NON-optionnel** — rappels de sécurité transversaux : ne jamais pousser, backup avant modif, respect du périmètre — injecté dans TOUTE issue), **type** (`consignes/type_<type>.md`, **facultatif** — ex. `type_chef.md` reprenant la contrainte d'exécution synchrone du #208, injecté selon le TYPE déduit par `watcher.deduire_type_issue`), **projet** (`consignes/projet_<projet>.md`, **facultatif** — aucun créé par défaut). Ordre final : en-tête → globales → type (si présent) → projet (si présent) → corps. Vaut en **mono-issue comme en mode lot** (chaque bloc `#Titre:` passe par `construire_body` avec son propre TYPE). **Choix délibéré anti-piège de maintenance** : contrairement à `CONTEXTE.md`, les couches type/projet sont sans obligation de présence (un projet sans `projet_<nom>.md` fonctionne normalement, rien à créer/maintenir) et créées uniquement à la demande. Garde-fous : fichier `type_*`/`projet_*` absent → aucune injection **sans** log (normal, pas une anomalie) ; `globales.md` introuvable → `logging.warning` clair **sans jamais faire échouer** la création d'issue. Nouvelle sous-section **§12.1** décrivant l'architecture, mise à jour du **§10** (dossier `consignes/`) et du **§14** (la contrainte d'exécution synchrone du chef n'est plus à recopier manuellement — elle est injectée automatiquement via `consignes/type_chef.md`). Testé de bout en bout (issue `TYPE=chef` réelle : corps GitHub contenant, dans l'ordre, globales puis chef puis corps original).

## 23 juillet 2026 — issue #208

Finalisation du nettoyage doc MVC (issue #208, suite #207) : le §14 « Délégation Chef → Ouvrier » gagne un bloc **« ⚠️ Contrainte d'exécution impérative »** rappelant que le chef doit accomplir la TOTALITÉ de sa tâche (attente de fermeture des ouvriers + synthèse finale comprises) en **une seule exécution synchrone et bloquante** — aucune reprise n'étant possible après qu'une issue a été répondue/fermée, ne jamais recourir à une attente différée, une tâche en arrière-plan ou un « je répondrai plus tard » ; si une attente est nécessaire, boucler (`sleep` + `gh issue view`) DANS la même exécution. Cette finalisation confirme aussi l'absence des fichiers `CONTEXTE_VUE.md`/`CONTEXTE_METIER.md`/`CONTEXTE_PERSISTANCE.md` à la racine de bridge_agent (jamais créés ici ; seul `CONTEXTE.md` existe et est conservé).

## 23 juillet 2026 — issue #207

Nettoyage doc MVC (issue #207) : **suppression de l'ancien §15 « Pattern Chef + Specs MVC (évolution future) »**, purement prospectif et jamais implémenté (le watcher ne lit pas le champ `SPECS`, aucun routage par couche Vue/Métier/Persistance n'existe) ; les sections suivantes **ne sont pas renumérotées** (16, 17, 18 restent 16, 17, 18) pour préserver les références croisées existantes. Le **§14 est entièrement réécrit** et recadré « Délégation Chef → Ouvrier (changement d'environnement) » : on ne garde que l'usage réel validé — un CCL « chef » crée lui-même une issue « ouvrier » ciblant un autre environnement (typiquement CCL Linux → CCW Windows) via `gh issue create` et surveille sa fermeture avant de livrer, sur instruction explicite (pas de détection auto du rôle chef, pas de décomposition automatique générique) — avec conseil de `TIMEOUT` généreux côté chef et l'exemple validé du build Scrabble/ouvrier CCW. En complément, l'issue chef #207 délègue à 6 issues « ouvrier » (une par projet actif hors bridge_agent et ff_galerie) la suppression des fichiers `CONTEXTE_VUE.md`/`CONTEXTE_METIER.md`/`CONTEXTE_PERSISTANCE.md` — vestiges du §15 abandonné — `CONTEXTE.md` (mécanisme standard hors MVC) étant conservé partout.

## 20 juillet 2026 — issue #191

§18 (nouveau) « Pièces jointes image dans les issues » (issue #191) : l'onglet « Nouvelle issue » accepte désormais un **upload optionnel PNG/JPEG** (champ fichier + bouton « Joindre une image » à côté du corps). Nouvelle route **`POST /joindre-image`** (`app/issues.py`, `joindre_image()`) : valide le type (Content-Type **et** magic bytes) et la taille (**≤ 5 Mo**), sauvegarde dans **`issue-attachments/`** (racine du `REP_TRAVAIL`) sous un nom **horodaté** anti-collision (`AAAAMMJJ-HHMMSS-<nom>.ext`), puis `git add` + `commit` + **`git push origin HEAD:<branche>`** (branche déduite **dynamiquement**, jamais supposée master/main), et retourne l'URL **`raw.githubusercontent.com/<owner>/<repo>/<branche>/issue-attachments/<fichier>`** — format qui s'affiche correctement dans les issues GitHub. Le frontend (`static/js/app.js`, `joindreImage()`/`insererDansCorps()`) insère alors **automatiquement** `![<nom>](<url>)` dans le corps à la position du curseur. **Exception `push` assumée et documentée (§18.2)** : ce commit+push est déclenché par **ALAIN** via l'outil (son action manuelle), **pas par CCL/le watcher** — la règle « CCL ne pousse jamais » n'est donc pas violée (elle vise les modifications de code de l'agent, pas une image qu'Alain publie lui-même). Gestion d'erreurs (§18.4) : **push échoué → aucune URL insérée** (commit conservé en local, poussable plus tard), **projet sans dépôt git → message clair**, type/taille/contenu invalides refusés proprement. `issue-attachments/` volontairement **hors `.gitignore`** (les images doivent être suivies/poussées). Testé de bout en bout (dépôt jetable + remote bare : succès + URL correcte, et chemins d'échec type/taille/magic/push).

## 20 juillet 2026 — issue #187

§17 (nouveau) « Notifications centralisées — détection serveur des transitions » (issue #187) : `new_issue.py`, qui tourne en permanence sur le ThinkPad, détecte désormais LUI-MÊME par polling `gh` les transitions d'issues (fermeture `done` = succès ; label `needs-human` = échec définitif) de **tous** les projets (for-linux ET for-windows), et déclenche bip/`notify-send`/`ntfy` **localement**, y compris pour les issues traitées par la VM **CCW** — **sans aucun appel réseau initié par la VM** (la VM n'écrit que sur GitHub). Nouveau module partagé `notifications.py` (racine) factorisant `bip`/`notifier_bureau`/`notifier_ntfy`/`notifier`, importé par `watcher.py` (enveloppes minces déléguant, sites d'appel inchangés) ET par le nouveau poller `app/notifications_poller.py` (thread démon lancé par `new_issue.py`). Script bip **déplacé/recréé** de `~/NicLink/bip.py` vers `scripts/bip.py` (infrastructure partagée) ; défaut `SCRIPT_BIP` et `configs/*.conf` mis à jour. Anti-doublon (point 4) : réglage `NOTIFIER_LOCAL` (`.conf`, défaut `true`) coupant la notif du watcher + portée `BRIDGE_NOTIF_SCOPE` (env, défaut `for-windows`) du poller. **Défaut livré sans régression ni doublon** (CCL notifie via son watcher, CCW via le poller — variante propre de l'option b) ; **option (a) « centralisation complète » recommandée mais laissée au choix d'Alain** car elle fait de `new_issue.py` une dépendance dure de toute notification (or il n'a pas encore de service systemd) — implémentée et à un réglage près (`BRIDGE_NOTIF_SCOPE=all` + `NOTIFIER_LOCAL=false` partout). **Action requise côté VM CCW** : poser `NOTIFIER_LOCAL=false` dans `configs\*-ccw.conf` pour éviter un double `ntfy`. Bonus (point 5) : le poller lit les labels COURANTS à la fermeture, donc `notif_pc`/`notif_gsm` ajouté EN COURS de traitement est bien pris en compte. Filtre de récence (`BRIDGE_NOTIF_RECENCE_MIN`, défaut 30 min) + amorçage silencieux au 1er cycle évitent le spam de vieilles issues au démarrage ; état en mémoire process.

## 20 juillet 2026 — issue #186

§1 « Vue d'ensemble » : documentation du **`git pull --ff-only` automatique en début de cycle** de `watcher.py` (issue #186, suite du #185 qui l'a implémenté). Le watcher rafraîchit son clone (`REP_TRAVAIL`) au début de chaque cycle de polling, juste avant `lister_issues()` : fast-forward transparent en cas de succès ; en cas de commits locaux non poussés (divergence) le `--ff-only` échoue proprement sans RIEN écraser et le watcher poursuit sur le code local — donc aucun risque à oublier un `git push`. Comportement **identique CCL (Linux) et CCW (Windows)** puisque `watcher.py` est le script unique partagé ; les projets à périmètre dynamique (dépôt-cible par issue) ne sont pas concernés. Un `git pull`/relance manuel reste possible pour une mise à jour immédiate (confort, plus une nécessité). Aucune instruction obsolète de « git pull manuel obligatoire » à corriger dans le §16 (aucune ne subsistait).

## 19 juillet 2026 — issue #174

§16 « Agent Windows CCW » : **onglet « CCW » dans l'interface web** (issue #174, sous-section §16.2) — pilotage complet de la VM et des projets CCW depuis Linux, sans PowerShell manuel dans la VM. Backend `app/ccw.py` (routes `/ccw/*`) exécutant les scripts existants à distance via `VBoxManage guestcontrol` : état/démarrage de la VM (`demarrer_ccw.sh`), liste des projets (nouveau `lister_projets_ccw.ps1`, sortie JSON encadrée), ajout (`ajouter_projet_ccw.ps1`) et finalisation non interactive (nouveau `finaliser_projet_ccw_auto.ps1` + `mettre_a_jour_tokens_ccw.ps1` doté d'un mode `-FichierTokens`). Sécurité : tokens jamais passés en argument ni journalisés (fichier temporaire `0600` poussé puis supprimé des deux côtés dans un `finally`) ; mot de passe `ccw-admin` lu depuis `CCW_ADMIN_PASSWORD` ou `configs/ccw_admin.secret` (gitignoré). Nouvel onglet + panneau dans `templates/index.html`, fonctions `ccw*` dans `static/js/app.js`, classe `.message.avertissement` dans `style.css`.

## 19 juillet 2026 — issue #173

§16 « Agent Windows CCW » : **finalisation d'un projet CCW en une seule commande** (issue #173, suite #170) — ajout de `provisioning/windows/finaliser_projet_ccw.ps1` qui, à partir du seul `-NomProjet`, dérive le service/dossier/config (même logique qu'`ajouter_projet_ccw.ps1`), vérifie leur existence, demande `TOPIC_NTFY` et l'écrit directement dans le config (remplacement ciblé du placeholder `###TOPIC_NTFY_A_DEFINIR###`, reste du fichier préservé en UTF-8 sans BOM), rappelle avec une pause la marche à suivre pour créer le token GitHub dédié, puis **appelle** `mettre_a_jour_tokens_ccw.ps1` (pas de duplication) pour la saisie masquée + pose des tokens + redémarrage + vérif des logs, et conclut par un résumé ; `mettre_a_jour_tokens_ccw.ps1` gagne un paramètre `-NomLog` pour vérifier le bon log de service (`ccw-<nom>-service.log`) ; les rappels d'`ajouter_projet_ccw.ps1` (en-tête + fin de script) et le §16 pointent désormais vers cette commande unique au lieu des 3 étapes dispersées. Non exécuté contre une VM réelle (test manuel par Alain).

## 19 juillet 2026 — issue #172

§11 « Conventions de code » : **règle BOM UTF-8 obligatoire pour tout script `.ps1`** (issue #172) — ajout du BOM (`EF BB BF`) manquant sur `ajouter_projet_ccw.ps1` (#170) et `mettre_a_jour_tokens_ccw.ps1` (#168), qui plantaient sinon sous Windows PowerShell 5.1 avec des `UnexpectedToken` en cascade sur les accents (même signature que #151) ; règle généralisée en §11 + rappel en tête du §16 pour prévenir la récidive (`provisionner.ps1` déjà OK depuis #151).

## 19 juillet 2026 — issue #170

§16 « Agent Windows CCW » : **généralisation multi-projets de CCW** (issue #170) — ajout de `provisioning/windows/ajouter_projet_ccw.ps1` (un clone + un config `configs\<nom>-ccw.conf` + un service NSSM `CCW-Watcher-<NomProjet>` dédiés par projet, sur le modèle des watchers CCL ; paramétrable `-NomProjet`/`-Depot`, idempotent, `watcher.py` inchangé) ; documentation du modèle « un service par projet » et de la **règle d'expiration alignée** des tokens (un token fine-grained dédié par dépôt, mais tous à la même échéance ≈ 17 octobre 2026) ; commande exacte d'instanciation de Scrabble et marche à suivre pour créer son token dédié (Repository access → Scrabble uniquement, Issues read/write + Metadata read-only).

## 19 juillet 2026 — issue #169

§16 « Agent Windows CCW » : ajout de la sous-section **§16.1 Maintenance périodique (renouvellement à 90 jours)** (issue #169) — runbook séquentiel consolidé pour la fenêtre de maintenance d'octobre 2026 : tableau de repères de dates (install **2026-07-19**, expiration Windows **2026-10-17**, token GitHub aligné ~90 j mais non stocké), puis procédure en 3 étapes renvoyant aux scripts existants — vérifier (`verifier_expiration_ccw.py`), recréer la VM (`creer_vm_ccw.py --recreate` + ré-attacher un ISO frais + `lancer_provisioning.py`), renouveler les tokens (`mettre_a_jour_tokens_ccw.ps1`) — sans dupliquer le détail technique déjà présent dans le §16.

## 19 juillet 2026 — issue #168

§16 « Agent Windows CCW » : ajout du script `provisioning/windows/mettre_a_jour_tokens_ccw.ps1` (issue #168) — renouvellement des tokens `GH_TOKEN`/`CLAUDE_CODE_OAUTH_TOKEN` du service `CCW-Watcher` sans reconstruire à la main la chaîne `AppEnvironmentExtra` : saisie masquée (`Read-Host -AsSecureString`), séparateur `` `n`` impératif entre les deux paires (un espace corrompt `GH_TOKEN` → « Bad credentials »), `nssm set`/`nssm restart`, puis affichage automatique des 10 dernières lignes de `logs\ccw-service.log` pour confirmer l'absence d'erreur d'auth.

## 19 juillet 2026 — issue #167

§16 « Agent Windows CCW » : alerte d'expiration de l'éval 90 jours (issue #167) — ajout de `provisioning/windows/eval-expiration.json` (date d'installation **2026-07-19**, expiration **2026-10-17**) et du script `provisioning/windows/verifier_expiration_ccw.py` (côté Linux : calcule les jours restants, alerte + code de sortie 2 à ≤ 10 j, sinon confirmation calme ; `python3 provisioning/windows/verifier_expiration_ccw.py`) ; rappel `cron` + `ntfy` hebdomadaire proposé mais laissé à l'activation d'Alain.

## 19 juillet 2026 — issue #166

§16 « Agent Windows CCW » : ajout du script `provisioning/windows/demarrer_ccw.sh` (issue #166), wrapper de démarrage de la VM `CCW-Build` depuis CCL (headless par défaut, `--gui`/`--fenetre` pour une fenêtre, `--status` pour l'état sans rien démarrer).

## 19 juillet 2026 — issue #153

§3 « Créer une issue » : ajout d'une note sur la **convention de présentation côté Claude Chat** pour l'envoi en lot (issue #153) — quand Claude Chat prépare plusieurs issues, il les présente toutes à la suite dans un seul bloc de code (pas un bloc par issue) pour un copier-coller en un clic.

## 18 juillet 2026 — issue #149

§16 « Agent Windows CCW » : `REP_TRAVAIL` généré par `provisionner.ps1` pointe désormais vers le **chemin UNC** `\\VBOXSVR\CCW_Share` (et non la lettre automontée `$LettrePartage`), seul accessible au service `CCW-Watcher` tournant sous LocalSystem (issue #149, suite #148) ; `$LettrePartage` conservé pour référence mais plus utilisé pour construire `REP_TRAVAIL`.

## 18 juillet 2026 — issue #148

le watcher CCW tourne comme **vrai service Windows** enregistré via NSSM (issue #148, suite #147) — `provisionner.ps1` installe `NSSM.NSSM` (winget) et enregistre le service `CCW-Watcher` (`SERVICE_AUTO_START` + `AppExit Default Restart` + `AppRestartDelay 5000`, stdout/stderr → `logs\ccw-service.log`, idempotent via `nssm stop`/`remove`), en remplacement de l'ancienne tâche planifiée `-AtLogOn` qui ne redémarrait pas au boot sans session ; équivalent direct des services systemd du §13.

## 18 juillet 2026 — issue #147

provisioning **phase 2** (issue #147, suite #146) — ajout de `provisioning/windows/provisionner.ps1` (installe l'outillage dans la VM via winget + Claude Code natif, clone le dépôt, écrit `ccw.conf`, enregistre la tâche planifiée `CCW-Watcher`) et `lancer_provisioning.py` (pousse/exécute ce script depuis CCL via `VBoxManage guestcontrol`) ; `watcher.py` inchangé (portable, `LABEL` paramétrable) ; limite Task Scheduler vs `Restart=always` documentée.

## 18 juillet 2026 — issue #146

ajout du §16 et du label `for-windows` (issue #146) : provisioning phase 1 de la VM Windows CCW (`provisioning/windows/creer_vm_ccw.py` + `autounattend.xml`) destinée aux builds .exe délégués par CCL.

## 17 juillet 2026 — issues #135, #101, #97 (suite #96)

Bridge_Agent v1, 4 projets actifs. §3 « Créer une issue » : ajout de l'**envoi en lot** (issue #135) — coller plusieurs blocs `#Titre:` à la suite dans le même corps déclenche le mode lot (bouton « Envoyer le lot (N issues) »), chaque bloc étant envoyé en séquence comme une issue indépendante (avec ses `PROJET`/`TIMEOUT`/`MODELE` optionnels), sans validation intermédiaire, suivi d'un résumé listant le résultat de chacune. Ajout du projet `ecole` (AlainDelree/Ecole, ~/Ecole) aux tableaux §2 et §7 (issue #101). Section 15 « Chef + Specs MVC » : champ `SPECS` (pluriel, minuscules, combinable en une ligne) — correction du champ `SPEC` introduit par erreur (issue #97, suite #96).
