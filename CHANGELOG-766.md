# CHANGELOG-766 — à fusionner dans CHANGELOG.md

## 18 octobre 2026 — issue #766

Gestion du modèle de l'agent Vibe (`~/.vibe/config.toml`) depuis un nouvel
onglet **Agent Vibe** de l'interface web — choisir le modèle actif, en
déclarer un nouveau, en retirer un.

- **Placement : réglage de compte, pas de projet.** `~/.vibe/config.toml`
  s'applique à tous les projets qui tournent sur l'agent Vibe de cette
  machine. Nouvel onglet dédié (`fragments/onglet_vibe.html`,
  `static/js/vibe_modele.js`, backend `app/vibe_modele.py`), distinct de
  l'onglet Configuration (qui édite le `.conf` d'UN projet) — même famille
  que `/son-actif` (réglage global, pas de `<nom_projet>` dans les routes).
  Un bandeau rappelle dans la page que le choix s'applique à tous les
  projets de cet agent.
- **Écriture chirurgicale, au niveau ligne — jamais de régénération du
  fichier.** Vibe réécrit ce fichier à chaque démarrage, réconcilié avec le
  compte : toute écriture doit donc préserver ce qu'elle ne gère pas.
  Lecture : `tomllib` (stdlib). Écriture : seules les lignes concernées par
  l'opération (la ligne `active_model = ...`, ou les lignes d'un bloc
  `[[models]]`) sont modifiées — tout le reste (commentaires, réglages
  inconnus, autres blocs) est recopié tel quel. Le résultat est revalidé
  (TOML correct + modèle actif toujours présent) AVANT d'être écrit sur
  disque ; une écriture qui échouerait ce contrôle est purement et
  simplement annulée.
- **Aucune liste de modèles figée dans le code.** La liste déroulante et le
  formulaire d'ajout sont construits à partir des champs RÉELLEMENT présents
  dans le fichier (`_schema()`, intersection/union des clés des entrées
  `[[models]]` existantes) — déterminés en lisant le fichier réel et le code
  source de l'outil installé (`vibe.core.config.models`/`vibe_schema`,
  `_REQUIRED_MODEL_FIELDS`) pendant cette issue, pas supposés. `name` /
  `provider` / `alias` servent de repli tant qu'aucune entrée n'existe encore
  à introspecter (fichier absent ou vide — section inoffensive).
- **Collision d'alias : bloquée si certaine, signalée si probable.** Un
  doublon d'alias AU SEIN du fichier (certain : l'un écraserait l'autre) est
  rejeté sans confirmation possible. Un alias identique à un modèle intégré
  connu de Vibe (`mistral-medium-3.5`, le seul statiquement garanti sur
  toute installation — le compte peut en exposer d'autres, non énumérables
  sans appel réseau) renvoie 409 + `necessite_confirmation` : le modèle
  n'est écrit qu'après confirmation explicite côté interface (`forcer=true`),
  avec un message expliquant qu'il serait sinon écrasé silencieusement au
  prochain démarrage de Vibe.
- **Jamais de fichier sans modèle actif.** Retirer le modèle actif, ou le
  dernier modèle restant (même inactif), est refusé AVANT toute écriture —
  vérifié indépendamment côté serveur, pas seulement en désactivant le
  bouton côté interface.
- **Sauvegarde avant chaque écriture.** Copie datée dans
  `~/.vibe/bridge_sauvegardes/` avant toute modification (fichier non
  versionné, hors du dépôt) ; les 10 plus récentes sont conservées.
- **Absence du fichier ou de l'outil : section inoffensive.** `GET
  /vibe-modele/etat` ne lève jamais — `disponible: false` et message neutre
  dans l'interface tant qu'aucun projet n'utilise Vibe sur cette machine.
- **Tests** : `tests/test_modele_vibe_766.py` (11 scénarios : lecture sans
  fichier, lecture avec schéma introspecté, préservation du contenu non géré
  lors d'un changement de modèle actif et d'un ajout, refus de retirer le
  modèle actif, refus de retirer le dernier modèle, retrait d'un modèle
  inactif, rejet d'un doublon d'alias, collision avec un alias intégré
  bloquée puis acceptée sur confirmation, champ requis manquant, TOML
  invalide signalé proprement) + `static/js/tests/vibe_modele.test.js` (12
  scénarios, logique pure côté interface). Suite complète exécutée :
  `tests/lancer_tous_les_tests.py` → 69/69 fichiers Python réussis (aucune
  régression) ; `node --test static/js/tests/` → 282/282 tests JS réussis.
- **Fichiers touchés** : `app/vibe_modele.py` (nouveau), `app/__init__.py`
  (4 routes), `templates/fragments/onglet_vibe.html` (nouveau),
  `templates/fragments/onglets.html`, `templates/index.html`,
  `static/js/vibe_modele.js` (nouveau), `static/js/onglets.js`,
  `static/js/socle/index.js`, `tests/test_modele_vibe_766.py` (nouveau),
  `static/js/tests/vibe_modele.test.js` (nouveau), `provisioning/vibe/README.md`,
  `BRIDGE_AGENT_DOC.md` (§10 + pied de page).
