# CHANGELOG-764 — à fusionner dans CHANGELOG.md

## 17 octobre 2026 — issue #764

Remplacement du marqueur de verdict (✅/❌ en tête de ligne, issue #757) par
une ligne de verdict encadrée, et signalement best-effort d'un succès sans
commit en mode écriture (étude #762).

- **Point 1 — ligne de verdict dédiée.** Le gabarit de prompt impose
  désormais une ligne AUTONOME en tête du rapport de clôture, sur le motif
  déjà en usage dans ce dépôt pour `MARQUEUR_RESULTAT` (commentaire HTML
  invisible à l'affichage GitHub, issue #237) : un succès produit la ligne
  `<!-- bridge:verdict:succes -->`, un échec son pendant
  `<!-- bridge:verdict:echec -->`. Choix motivé par la cohérence avec la
  convention existante et par le fait qu'un rapport rédigé librement ne peut
  pas la produire par accident — contrairement au simple caractère ✅/❌ en
  tête de ligne, qui avait déjà produit un faux positif (un ❌ cité dans une
  liste de cas, par exemple). `_RE_LIGNE_VERDICT`/`_verdict_final` exigent
  désormais un match sur la LIGNE ENTIÈRE (espaces de bordure tolérés), plus
  un simple préfixe. **Aucun repli sur l'ancienne convention** : le
  changement est net, comme recommandé par l'étude #762 pour ne pas
  réintroduire la classe de faux positif que cette issue supprime.
  - Garde-fou #581 (sortie sans marqueur ⇒ échec) : adapté pour tester
    l'absence de la nouvelle ligne (`_verdict_final(sortie) is None`), au
    lieu de l'absence de tout caractère ✅/❌ dans le texte.
  - Garde-fou #757 (valeur du verdict) : adapté pour comparer contre le
    marqueur d'échec plutôt que contre le caractère ❌.
  - **Correction supplémentaire, reprise de l'issue #763** (prérequis
    énoncé par #764, mais son worktree ne contenait encore aucun commit au
    moment du traitement — correction donc intégrée directement ici plutôt
    que suspendue) : `_verdict_final` retient désormais la PREMIÈRE ligne de
    verdict trouvée, et non plus la dernière — le rapport réel de l'agent la
    produit en tête de sa réponse formatée ; une occurrence supplémentaire
    plus loin ne peut provenir que d'un texte qui la cite ou d'un tour
    tardif émis après le vrai rapport (cas #580/#581), qui ne doit jamais
    l'emporter. À vérifier si #763 est traitée séparément par la suite : son
    périmètre pourrait maintenant être entièrement couvert.
  - Tests mis à jour : les quatre fixtures qui simulaient une sortie
    d'agent (`test_reprise_worktree_725.py`, `test_worktree_parallelisation_
    337.py`, `test_lecture_active_327.py`, `test_verrou_refus_precoce_584.py`)
    émettent maintenant la ligne dédiée avant leur ✅/❌ habituel. Nouveau
    fichier `test_ligne_verdict_764.py` : détection stricte (ligne entière,
    motif cité en ligne ignoré), élimination du faux positif par liste de
    cas, priorité à la première occurrence.

- **Point 2 — signalement d'un succès sans commit en mode écriture.**
  Nouvelle fonction `_avertissement_succes_sans_commit`, appelée depuis
  `_finaliser_succes` : relève, SANS jamais en faire une décision (aucune
  tentative supplémentaire, aucun label, aucune incidence sur le succès), le
  cas d'un verdict de succès en mode écriture (hors dry-run) qui ne laisse
  aucun commit au-delà de celui de sauvegarde. Un simple avertissement — une
  ligne de log (`log.warning`) et une mention ajoutée au commentaire de
  clôture — pour que la relecture humaine s'y arrête ; le cas peut être
  parfaitement légitime (tâche n'impliquant pas d'écriture, bug non
  reproductible, correctif déjà présent) comme révéler un agent qui se
  déclare satisfait sans rien avoir produit — la distinction reste humaine.
  Le commit de sauvegarde est repéré par POSITION (le premier commit après
  `tete_avant_traitement`, déjà relevé avant tout traitement en mode
  écriture, issue #689), pas par son message : la convention de nommage
  (« avant-<description> ») n'est qu'une consigne de prompt, jamais imposée
  techniquement. Capture par `git rev-list --reverse` strictement
  best-effort (même modèle que `_tete_git`) : toute erreur ne prive que de
  ce signalement, jamais de la clôture par ailleurs réussie. Portée stricte
  (#764) : mode écriture hors simulation uniquement — lecture seule et
  lecture active n'attendent aucun commit, donc jamais concernées.
