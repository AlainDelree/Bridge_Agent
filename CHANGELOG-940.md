# Issue #940 — Interface new_issue : la ligne d'une nouvelle issue n'apparaît pas tant qu'une case à cocher garde le focus (rendu de la liste reporté indéfiniment)

Suite de l'issue #933 : son étude avait établi que les données arrivaient
bien (création à 17:51:27 UTC, rechargements à 17:51:37/17:51:40/17:51:48/
17:55:11 contenant déjà l'issue #939, aucun `avertissement_issue_absente`)
mais que la page, à 18:55, n'affichait toujours pas la ligne — symptôme
d'AFFICHAGE, pas de rechargement.

## Cause confirmée à la lecture du code

`static/js/app.js::rendreListeIssues` et `remplacerLigneIssue` portent la
garde posée par l'issue #878 (`coucheResultatEnInteraction`) : si une case
`.coche-resultat` détient le focus du navigateur, le rendu demandé est
DIFFÉRÉ jusqu'au `focusout` de cette case, plutôt que de détruire son nœud
DOM en plein clic (ce qui annulerait le clic — « copie du rapport sans
effet », le défaut original de #878). Ce report n'avait AUCUNE limite de
durée : un `focusout` ne survient que si quelque chose d'autre prend le
focus (un autre clic, une touche) — une case cochée par un clic garde donc
le focus INDÉFINIMENT si rien d'autre n'est touché ensuite, exactement le
geste d'Alain pour marquer des issues comme traitées. Tout rendu demandé
pendant ce temps (liste complète au rechargement, ligne remplacée à
`debut_issue`/`fin_issue`) restait alors en attente SANS LIMITE, jusqu'au
prochain clic ↻ (qui déplace le focus et libère tous les rendus en attente
d'un coup — d'où l'impression que la ligne « apparaît directement après le
clic sur ↻ »).

Seuls deux endroits portent cette garde (vérifié par relecture complète de
`static/js/*.js`, aucun autre usage de `coucheResultatEnInteraction` ni de
`focusout`) : `rendreListeIssues` et `remplacerLigneIssue`. Un troisième
endroit lit aussi le focus de la case — `restaurerCasesCocheesResultats`
(issues #462/#463) — mais n'est PAS concerné : il ne fait que SAUTER la
resynchronisation visuelle de cette case précise (`checked`/classe), sans
jamais différer ni rater un rendu complet.

## Solution retenue

But de #878 inchangé : ne jamais détruire le nœud d'une case entre son
`mousedown` (qui lui donne le focus) et l'effet de son `click`/`change`. Le
défaut était que la garde restait active bien APRÈS cet effet, tant que le
focus n'était pas repris ailleurs. Deux mécanismes complémentaires, les deux
solutions suggérées par la tâche, combinées plutôt qu'un seul choix :

1. **Retirer le focus une fois le changement traité**
   (`basculerCocheResultat`, onchange de la case) : après avoir relayé
   l'événement à `resultatsCoches.basculer` — qui engage déjà,
   SYNCHRONEMENT, la copie presse-papier avant toute autre chose (dans la
   fenêtre d'activation utilisateur, inchangé) — la case reçoit `cb.blur()`.
   La garde #878 se dénoue donc dès que l'effet réel du clic a eu lieu, pas
   après. C'est le chemin NORMAL, qui couvre le cas réel observé (clic puis
   plus rien).
2. **Plafond de sécurité** (`differerRenduSurCoche`,
   `DELAI_MAX_REPORT_RENDU_MS` = 1000 ms) : pour les cas résiduels où ni
   `change` ni `focusout` ne surviennent (ex. case focalisée au clavier,
   Tab, sans être basculée), le rendu différé s'exécute quand même à ce
   plafond — FORCÉ, en appelant directement le corps du rendu
   (`executerRenduListeIssues`/`executerRemplacementLigneIssue`, extraits de
   `rendreListeIssues`/`remplacerLigneIssue`) plutôt que ces deux fonctions
   elles-mêmes, pour ne pas réarmer la même garde et retomber dans un report
   sans fin. Avec les données les plus fraîches connues à cet instant
   (`listeIssuesResultats`, relu au moment de l'exécution).

Solution la plus simple qui conservait l'objectif de #878 : pas de fenêtre
de temps additionnelle à calibrer pour « geste en cours » (une case qui
garde son focus 1h après un clic n'est plus en train d'agir, mais rien ne le
distinguait avant ce correctif) — le signal RÉEL de fin de geste
(`change`, déjà existant) suffit, complété par un filet de sécurité borné
pour ne jamais dépendre uniquement de lui.

## Journal (`logs/charge_interface.log`, issue #940 point 4)

Nouvelle ligne `rendu_differe` (`mesure_charge_interface.ligne_rendu_differe`,
POST `/journal-rendu-differe`, `app/charge_interface.py::route_rendu_differe`)
à CHAQUE rendu différé par la garde puis exécuté : `type_rendu` (`liste` ou
`ligne`) et `duree_report_ms` (durée RÉELLE du report). Sert à vérifier à
l'usage que ce report reste court — proche de 0 ms dans le cas normal
(blur immédiat après le `change`), jamais au-delà du plafond.

## Tests

- JS (`static/js/tests/app_rendu_differe_940.test.js`, logique pure, bac à
  sable vm sur le VRAI `app.js`, minuteurs contrôlables) : `differerRenduSurCoche`
  n'exécute rien avant `focusout`/plafond ; le plafond exécute et journalise
  même sans `focusout` ; un `focusout` précoce exécute une seule fois (pas de
  double exécution au plafond) et annule le minuteur ; `rendreListeIssues`/
  `remplacerLigneIssue` exécutent bien le rendu FORCÉ au plafond même si le
  focus ne bouge jamais ; `basculerCocheResultat` relaie puis retire le focus
  (et ne plante pas si le module dédié est absent).
- Python (`tests/test_journal_rendu_differe_940.py`, même patron que
  `tests/test_journal_reouverture_stream_937.py`) : format JSON de
  `ligne_rendu_differe` et validation stricte de `route_rendu_differe`
  (champs attendus, type_rendu connu, durée numérique >= 0, corps trop gros,
  connexion requise).
- Suite complète existante rejouée (`node --test static/js/socle/tests/
  static/js/tests/`, 633 tests, 0 échec) : aucune régression sur #878
  (`app_redessin_878.test.js` toujours au vert, les deux chemins focusout
  inchangés) ni sur le reste de l'interface.
- **Reste à vérifier à la main** (pas de navigateur réel dans le dépôt) :
  essais (a)/(b)/(c) ajoutés à `VERIFICATIONS_MANUELLES.md` — (a) cocher une
  case puis déposer une issue sans rien toucher d'autre : la ligne apparaît
  d'elle-même ; (b) cocher une case pendant la fin d'une issue : le clic
  garde son effet (pas de régression #878) ; (c) durées `rendu_differe`
  réellement courtes dans `logs/charge_interface.log` à l'usage.

## Fichiers touchés

`static/js/app.js` (garde, `differerRenduSurCoche`, `journaliserRenduDiffere`,
`basculerCocheResultat`, extraction `executerRenduListeIssues`/
`executerRemplacementLigneIssue`), `mesure_charge_interface.py`
(`ligne_rendu_differe`), `app/charge_interface.py` (`route_rendu_differe`,
`TYPES_RENDU_CONNUS`), `app/__init__.py` (route `/journal-rendu-differe`),
`static/js/tests/app_rendu_differe_940.test.js` (nouveau),
`tests/test_journal_rendu_differe_940.py` (nouveau),
`docs/contexte/interface_rafraichissement.md` (§9ter, nouveau),
`VERIFICATIONS_MANUELLES.md` (essais (a)/(b)/(c) #940). Rien d'autre modifié
— ni les rechargements sur création/début/fin, ni le voile de veille, ni la
surveillance du flux, ni `watcher.py`. Aucun fichier `configs/*.conf`
touché. Aucun appel GitHub supplémentaire (route purement locale, comme
`/journal-reouverture-stream`).
