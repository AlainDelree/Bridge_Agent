# Issue #914 — mode interactif : reprise d'une session vivante sans nouveau commit de sauvegarde ni nouvel ACK, et badge « tentative » de l'interface

Essais manuels de l'étape de test #913 (22/11/2026) : la reprise d'une
session interactive déjà vivante après un redémarrage du watcher
(comportement voulu, issue #901) montrait trois effets de bord non prévus.

- **Cause commune aux deux premiers effets** : `_demarrer_traitement`
  (ACK + commit de sauvegarde watcher) était appelée par
  `_traiter_issue_synchrone` INCONDITIONNELLEMENT, avant même de savoir si
  l'issue était interactive — donc avant la détection de reprise déjà
  présente dans `_traiter_issue_interactive`. Chaque redémarrage pendant une
  session interactive vivante refaisait donc un second ACK et un second
  commit de sauvegarde, lequel engloutissait dans la « sauvegarde » le
  travail déjà fait par CCL avant le redémarrage.
- **Corrigé** : `watcher._interactif_deja_amorce(nom_projet, numero)`
  (rapport déjà présent, OU session tmux vivante, OU script de lancement
  orphelin — mêmes trois conditions déjà testées par
  `_traiter_issue_interactive`) est maintenant consultée par
  `_traiter_issue_synchrone` AVANT `_demarrer_traitement`, et lui transmise
  via le nouveau paramètre `reprise_interactive_vivante` — jamais vrai pour
  une issue automatique, donc sans aucun effet sur ce chemin (`RELANCE`
  #725 compris). Quand elle est vraie : pas de second ACK (le commentaire de
  reprise déjà posté par `_traiter_issue_interactive` suffit), pas de second
  commit de sauvegarde — `tete_avant_traitement`/`commit_sauvegarde_watcher`/
  `backup_watcher_nouveaux_suivis` sont relus depuis un état persisté au
  tout premier lancement réel (`_ecrire_etat_initial_interactif`/
  `_lire_etat_initial_interactif`, nouveau fichier
  `logs/interactif/<projet>-issue<numero>.etat.json`, même emplacement et
  même convention que le rapport/la sentinelle de pause) plutôt que
  recalculés : la référence « depuis la sauvegarde » continue ainsi de
  désigner la sauvegarde ORIGINALE, quel que soit le nombre de redémarrages
  intervenus depuis. Repli best-effort si cet état est introuvable : jamais
  de second commit pour autant, mais la référence devient indisponible
  (`None`) plutôt qu'inventée à partir du HEAD courant. Ce fichier d'état
  est nettoyé à chacune des trois fins de session (rapport, TIMEOUT, pause
  trop longue), comme le script de lancement et la sentinelle de pause.
- **Troisième effet (interface)** : la liste de l'onglet Résultats affichait
  un badge « tentative N/M » pour une issue interactive dès qu'une pause
  d'attente d'Alain (issue #909) faisait dépasser le premier cycle TIMEOUT —
  trompeur, puisqu'une session interactive n'a JAMAIS de deuxième tentative
  (invariant « aucune relance »). Corrigé dans
  `static/js/resultats.js::calculerBadgeTempsRestant` : un nouveau paramètre
  `opts.interactif` (calculé par `majBadges()` via la nouvelle fonction pure
  `estIssueInteractive(labels)`, vraie si le label `mode_interactif` est
  présent) fait afficher un indicateur sobre et fixe (« 🖥️ session
  interactive », classe CSS `tr-interactif`) à la place de tout le calcul
  tentative/budget — sans toucher à l'affichage d'une issue automatique.
- **Documentation** : `docs/contexte/mode_interactif.md` (nouvelle
  sous-section sous « Survie à un redémarrage du watcher », + nouvelle
  section « Interface — pas de badge « tentative » ») et la cellule
  `mode_interactif` du tableau des labels de `BRIDGE_AGENT_DOC.md` §4.
- **Tests** : nouveau fichier
  `tests/test_mode_interactif_reprise_vivante_914.py` (17 cas : détection de
  reprise, persistance/lecture de l'état initial, `_demarrer_traitement` en
  reprise — sans ACK, sans nouveau commit, référence relue ou repli best-
  effort —, chemin automatique inchangé, nettoyage de l'état aux trois fins
  de session, et un scénario bout en bout reproduisant l'essai manuel
  demandé par l'issue : travail de CCL avant un redémarrage simulé, puis fin
  sans rapport après la reprise — le commentaire liste bien ce travail).
  Côté interface, nouveaux cas dans `static/js/tests/resultats.test.js`
  (badge absent de tout compteur de tentatives pour une issue interactive,
  y compris budget épuisé ; issue automatique inchangée ; `estIssueInteractive`).
  Suite complète après ces ajouts : 749 tests Python (`pytest tests/`) et
  543 tests JS (`node --test static/js/tests/`), tous passants.
