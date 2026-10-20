## 20 octobre 2026 — issue #780

Le pré-vol sans appel réseau de l'agent `vibe` (`verifier_preflight_cle_api_vibe`,
introduit par l'issue #760) journalisait un avertissement à CHAQUE lancement
depuis l'abandon de l'authentification par clé API statique (facturée sur un
forfait distinct de celui du compte, épuisé — cf. issue #780) au profit
d'une connexion par compte (sign-in navigateur). Un avertissement qui se
déclenche toujours cesse d'être lu, et aurait masqué le jour venu une vraie
défaillance d'authentification.

- **Investigation (consigne explicite de l'issue : vérifier, ne pas
  supposer).** Lecture du code source installé de Mistral Vibe
  (`vibe.setup.auth.api_key_persistence.persist_api_key`,
  `vibe.setup.auth.auth_state`, `vibe.utils.keyring`) : les deux modes
  d'authentification (clé saisie à la main, ou connexion par compte)
  finissent persistés par le MÊME mécanisme, qui privilégie toujours le
  trousseau système de la machine (OS keyring, service `ai.mistral.vibe`)
  et ne retombe sur `~/.vibe/.env` en clair que si aucun trousseau n'est
  disponible — constaté sur la machine de développement : `~/.vibe/.env`
  existe mais est vide, la clé réelle vivant dans le trousseau (confirmé en
  y lisant la valeur via le paquet `keyring`, hors de tout code livré).
  `~/.vibe/whoami_cache.json` a aussi été examiné et écarté : simple cache
  d'appels réseau passés (TTL 6h), pas une preuve d'authentification
  utilisable maintenant.
- **Aucun indice local fiable, non bloquant, sans dépendance tierce.**
  Lire le trousseau système depuis `watcher.py` demanderait le paquet tiers
  `keyring` — une dépendance que ce fichier n'a jamais eue (bibliothèque
  standard uniquement, cf. `CONTEXTE.md`) — avec un risque réel de blocage
  si le trousseau est verrouillé sans agent de déverrouillage graphique
  disponible (cas plausible pour le service systemd `--user` de ce watcher,
  démarré via `enable-linger` avant toute connexion graphique) : précisément
  ce qu'un pré-vol n'a jamais le droit de faire. Conformément à la consigne
  explicite de l'issue (« mieux vaut un pré-vol qui ne vérifie plus rien
  qu'un avertissement systématique et faux »), ce pré-vol ne vérifie donc
  plus la présence d'une authentification pour cet agent.
- **`watcher.py` — `verifier_preflight_cle_api_vibe`** : l'absence de clé
  trouvable (ni `MISTRAL_API_KEY`, ni `~/.vibe/.env`) n'est plus signalée —
  seule la PRÉSENCE d'une valeur de forme suspecte (trop courte, avec un
  espace) reste signalée, cette anomalie restant valable indépendamment du
  mode d'authentification réellement actif. `_lire_cle_api_vibe` inchangée.
  Agent historique (`claude`) strictement inchangé : il ne définit toujours
  aucune clé `verifier_preflight`.
- **`provisioning/vibe/README.md` §3** : réécrit pour décrire la connexion
  par compte comme mode en usage, le mécanisme de persistance commun
  (trousseau système en priorité), et la raison du repli sur « plus rien
  vérifier » pour ce pré-vol.
- **`tests/test_preflight_vibe_compte_780.py`** (nouveau, 4 scénarios) :
  absence de clé -> plus aucun avertissement ; clé plausible -> aucun
  avertissement (inchangé) ; clé de forme suspecte (trop courte, espace) ->
  avertissement toujours émis ; agent historique (`claude`) toujours sans
  `verifier_preflight`. Aucun test existant n'exerçait directement cette
  fonction avant cette issue (vérifié par recherche dans `tests/`) — fichier
  entièrement nouveau, pas une adaptation d'un fichier préexistant. Les 76
  tests existants (`tests/lancer_tous_les_tests.py`) restent verts, plus ce
  nouveau fichier (77/77).
