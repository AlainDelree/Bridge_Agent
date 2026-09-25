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
