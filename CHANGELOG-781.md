## 20 octobre 2026 — issue #781

L'issue #127 de chesscoach s'est arrêtée juste avant d'écrire son rapport de
clôture (travail fait et committé une minute plus tôt, dernière ligne du
journal annonçant la production du rapport, puis plus rien). Le garde-fou
d'arrêt sur commits présents (issue #777) a bien joué, mais le diagnostic
s'est arrêté là : ni le code de retour du process ni la taille de sa sortie
capturée n'étaient journalisés, le second agent (`vibe`) n'avait aucun
plafond de session explicite, et le message d'arrêt reprenait à tort
l'hypothèse de l'issue #581 (réponse tardive d'un sous-agent) — manifestement
fausse dès que des commits sont déjà présents.

- **`watcher.py` — `lancer_claude`** : code de retour et taille de stdout/
  stderr désormais tracés dans le journal à CHAQUE tentative, succès comme
  échec (une seule ligne `log.info`, sans contenu — pas d'alourdissement).
  Avant cette issue, seul l'échec loggait le code de retour, et aucune
  taille de sortie n'était jamais journalisée : les deux premières choses
  qu'on cherche quand une tentative se termine anormalement n'étaient donc
  disponibles qu'en relançant manuellement l'agent.
- **`watcher.py` — `AGENTS_CONNUS["vibe"]["plafonds_session"]`** (nouveau) :
  plafonds de session explicites pour l'agent `vibe`, posés par
  `_construire_cmd_vibe` sur sa ligne de commande (`--max-turns 500`,
  `--max-price 25` ($), `--max-tokens 10000000`) — déterminés en lisant
  `vibe --help` (mode programmatique `-p`, seul utilisé par ce watcher).
  Avant cette issue, ces plafonds n'étaient jamais positionnés : vibe
  retombait sur ses propres valeurs par défaut, inconnues de ce dépôt, et
  pouvait interrompre une session longue sans qu'aucune erreur ne le
  signale — scénario plausible sur un projet (chesscoach) aux fichiers de
  plusieurs centaines de ko. Valeurs volontairement très larges : le but
  est de savoir ce qui contraint l'agent, pas de le contraindre pour une
  tâche normale. `--time-limit` délibérément absent de ces plafonds : le
  délai de la tentative est déjà géré par le watcher lui-même (`timeout=`
  de `proc.communicate`) — le dupliquer n'aurait apporté aucun bénéfice,
  seulement une seconde valeur à garder en cohérence avec la première.
  Un dépassement se manifeste de façon reconnaissable : code de retour 3
  (« stopped by a limit », documenté par l'outil lui-même), désormais
  visible dans le journal grâce au point précédent. Agent historique
  (`claude`) strictement inchangé : aucun de ces drapeaux ne lui est posé.
- **`watcher.py` — `_gerer_verdict_illisible_avec_commits`** : le message
  d'arrêt posté sur l'issue (garde-fou #777, verdict de clôture illisible
  mais commits déjà présents) ne reprend plus l'hypothèse de l'issue #581
  (réponse tardive d'un sous-agent en arrière-plan ayant écrasé le rapport)
  — hypothèse plausible en l'absence de commit, mais contredite dès qu'un
  commit existe : l'agent a bien travaillé, et s'est arrêté AVANT d'écrire
  son rapport, pas après. Le nouveau message dit ce qui est constaté :
  l'agent ne s'est pas rendu jusqu'à son rapport de clôture, le travail
  semble avoir eu lieu, il reste à le vérifier. La fin brute de la sortie
  capturée (seul élément factuel de l'ancien message) reste affichée,
  isolée de l'hypothèse via un nouveau marqueur partagé
  `_MARQUEUR_FIN_BRUTE_SORTIE`. Logique du garde-fou inchangée (détection
  des commits, arrêt immédiat, label `needs-human`) : seul le texte posté
  sur l'issue est corrigé.
- **`tests/test_plafonds_vibe_et_message_commits_781.py`** (nouveau, 5
  scénarios) : plafonds posés par `_construire_cmd_vibe` (MODE_LECTURE et
  MODE_ECRITURE) et absence de `--time-limit` ; agent `claude` toujours
  sans aucun de ces drapeaux ; plafonds reçus par un vrai subprocess `vibe`
  (faux exécutable capturant ses arguments) ; `lancer_claude` journalise
  bien le code de retour et la taille de sortie, succès et échec ; message
  de `_gerer_verdict_illisible_avec_commits` purgé de l'hypothèse #581
  tout en conservant les faits constatés (commits listés, fin brute de la
  sortie capturée).
- **`tests/test_corrections_erreurs_bloquantes_761.py`** : commande `vibe`
  de référence mise à jour pour inclure les nouveaux plafonds (lus dans
  `AGENTS_CONNUS["vibe"]["plafonds_session"]`, pas en dur) — comportement
  `claude` et reste du test inchangés.

Suite de tests complète exécutée après ces modifications : 78/78 fichiers
`tests/test_*.py` passent (0 échec), y compris les deux fichiers modifiés/
ajoutés par cette issue.
