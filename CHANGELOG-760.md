# CHANGELOG-760 — à fusionner dans CHANGELOG.md

## 15 octobre 2026 — issue #760

Mistral Vibe comme second agent d'exécution choisissable par projet (clé
`AGENT = vibe` du `.conf`, suite de #759) — **aucun projet ne bascule dessus
par cette issue**, l'agent devient seulement disponible ; le basculement
reste manuel, projet par projet (voir `provisioning/vibe/README.md`). En
profite pour remplacer le pré-vol d'authentification par une vérification
propre à chaque agent, et pour détecter en cours d'exécution les erreurs
d'authentification/quota bloquantes (clé révoquée, crédit épuisé) communes
aux deux agents.

- **`watcher.py` — `AGENTS_CONNUS["vibe"]`** (nouvelle entrée) : binaire
  `vibe`, `_construire_cmd_vibe` (profil intégré `plan` en lecture seule —
  refuse par construction écriture de fichier et exécution de commande,
  constaté par essai manuel ; profil `bridge_ecriture`, versionné dans ce
  dépôt, en écriture et lecture active — pas d'option équivalente à
  `--dangerously-skip-permissions` côté Vibe), message d'erreur si le binaire
  est introuvable, et une clause « sous-agents » de gabarit de prompt propre
  à Vibe (mécanisme de délégation confirmé mais nom exact non vérifié ici,
  consigne explicite de l'issue de ne pas lancer de session Vibe réelle —
  formulation volontairement générique en attendant confirmation). Sortie en
  texte brut (format par défaut du CLI), pas `--output json`, pour rester
  compatible avec le parsing ✅/❌ existant de `watcher.py`. `MODELE` du
  `.conf` sans effet pour cet agent : pas de sélection de modèle équivalente
  à `--model` sur sa ligne de commande.
- **Pré-vol par agent** (`verifier_preflight_token`) : un agent peut
  désormais fournir un callable `verifier_preflight` (sans appel réseau),
  prioritaire sur la sonde réseau existante. Claude Code ne définit pas cette
  clé — comportement strictement inchangé. Pour `vibe`
  (`verifier_preflight_cle_api_vibe`) : authentification par clé API statique
  sans session expirable, donc pas de sonde réseau utile équivalente ; vérifie
  seulement, localement, que `MISTRAL_API_KEY` (variable d'environnement ou
  `~/.vibe/.env`) est présente et d'une forme plausible (longueur minimale,
  sans espace — best-effort, aucun préfixe de clé Mistral confirmé sans appel
  réseau). Best-effort au même titre que le pré-vol existant : ne bloque
  jamais le traitement, journalise seulement un avertissement.
- **Détection d'erreur bloquante en cours d'exécution**
  (`_detecter_erreur_bloquante` / `_gerer_erreur_bloquante`, nouveau) : une
  clé révoquée ou un quota/crédit épuisé ne se voient qu'au moment de l'appel
  réel, pas au pré-vol. Logique commune aux deux agents, signatures propres à
  chacun via `AGENTS_CONNUS[CFG.agent]["signatures_erreur_bloquante"]` :
  - Claude Code : réutilise les signatures d'auth déjà connues
    (`SIGNATURES_TOKEN_EXPIRE`, ex. `authentication_error`, `invalid api
    key`, `/login`) et ajoute le message de facturation Anthropic observé
    quand le crédit du compte est épuisé (`credit balance is too low`).
  - Vibe : vocabulaire générique d'API REST (`unauthorized`, `invalid api
    key`, `quota`) — liste best-effort, jamais vérifiée en conditions
    réelles (même consigne que ci-dessus), à affiner lors de la première
    bascule réelle d'un projet.
  - `rate limit` volontairement exclu des deux côtés : throttling transitoire
    par minute, pas un quota de compte épuisé — ne doit pas interrompre
    définitivement un traitement qu'un simple backoff aurait résolu.
  - Dès qu'une signature est reconnue dans la sortie d'une tentative
    échouée : arrêt **immédiat** du traitement de l'issue (avant la trace de
    timeout et avant l'abandon normal, et même pour une issue critique — pas
    de retry infini ici), label `needs-human` posé, cause explicite dans le
    commentaire de clôture. Aucune repasse diagnostique (la cause est déjà
    connue) et aucune tentative supplémentaire consommée. Un quota se
    régénère avec le temps mais sans délai fiable connu : une reprise
    différée serait prématurée, traité donc comme une clé révoquée pour
    l'instant (même issue).
- **`provisioning/vibe/`** (nouveau dossier) : `agents/bridge_ecriture.toml`
  (profil d'écriture versionné, copie de référence déployée vers
  `~/.vibe/agents/bridge_ecriture.toml`) et `README.md` (déploiement du
  profil, pré-remplissage des dossiers de confiance `~/.vibe/trusted_folders.toml`
  pour les `REP_TRAVAIL` de projets, authentification, marche à suivre pour
  basculer un projet existant sur Vibe). Mêmes raisons que `consignes/` ou
  `provisioning/windows/` : un fichier qui ne vivrait que dans le dossier
  personnel de l'utilisateur ne serait ni versionné, ni sauvegardé, ni relu.
- **`BRIDGE_AGENT_DOC.md` §10** : paragraphe de pointeur vers
  `provisioning/vibe/README.md`, footer mis à jour.
- **Garde-fous techniques inchangés** : protection de `configs/*.conf` et
  garde-fou niveau 2 (empreinte `REP_TRAVAIL` avant/après en lecture active)
  ne dépendent pas de l'agent — non touchés.
- **Hors périmètre, non touché** : interface web, calibration des TIMEOUT,
  agent Windows CCW (Vibe cible officiellement les environnements UNIX).
- **Point des essais manuels à nuancer** : aucun des faits constatés listés
  dans l'issue ne s'est révélé inexact à la lecture du code de `watcher.py`
  (ils portent tous sur le comportement du binaire `vibe` lui-même, hors
  périmètre de cette lecture). Un point reste non vérifié faute de session
  réelle autorisée : le nom exact du mécanisme de sous-agents de Vibe (la
  clause de prompt correspondante a donc été formulée en termes génériques,
  voir plus haut).
- **Vérification de non-régression** : `python3 -m py_compile watcher.py`
  propre ; les 64 fichiers `tests/test_*.py` du dépôt passés un par un (via
  `tests/lancer_tous_les_tests.py`) — tous verts, aucun test existant modifié.
  Vérifications ad hoc supplémentaires (non committées) sur
  `_construire_cmd_vibe`, `_detecter_erreur_bloquante` et
  `verifier_preflight_cle_api_vibe` (dispatch, env var, fallback
  `~/.vibe/.env`, bornes de longueur) — aucune session réelle de `claude` ni
  de `vibe` lancée pendant cette tâche.
