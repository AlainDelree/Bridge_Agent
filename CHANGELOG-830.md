## Issue #830 — Résultats : ne plus signaler « Ligne Commits absente » pour une issue qui a échoué avant l'exécution

La section « Fichiers modifiés » ajoutée à la copie du rapport d'une issue
signalait systématiquement une anomalie (« ⚠ Ligne « Commits » absente ou
non reconnue … — anomalie à vérifier, pas un cas normal ») quand le dernier
commentaire n'avait pas de ligne « Commits » reconnue. Faux pour une issue
qui a échoué **avant** le lancement de CCL (ex. abandon de configuration
« périmètre dynamique sans REPO_CIBLE », issue #829) : le watcher poste
alors son propre commentaire de refus, sans ligne « Commits » puisqu'aucune
exécution n'a eu lieu — ce n'est pas une anomalie de CCL.

- **`static/js/app.js::etatCommitsDeclares`** : nouvel état `'echec'`,
  renvoyé quand la ligne « Commits » est absente ou non reconnue ET que
  l'issue porte le label `needs-human` (nouvelle fonction `estIssueEnEchec`,
  même motif que `estIssuePourWindows`). Un échec **avec** une ligne «
  Commits » reconnue garde `'hashes'`/`'aucun'` inchangés (l'échec est
  survenu après des commits). `'absente'` reste réservé à une issue SANS
  `needs-human` (réussie) — reste une vraie anomalie, texte inchangé.
  `'windows'` (label `for-windows`) reste prioritaire sur `'echec'`, comme
  sur tous les autres états.
- **`static/js/resultats_coches.js::texteSectionFichiers`** : nouvelle
  branche pour l'état `'echec'` — texte neutre, sans symbole d'alerte :
  « Cette issue a échoué avant l'exécution : son commentaire de clôture ne
  contient pas de ligne « Commits », donc aucun inventaire des fichiers
  n'est possible (ce n'est pas une anomalie de CCL). ». Commentaires
  d'en-tête des deux fichiers mis à jour pour décrire ce nouveau cas.
- **Tests** (`static/js/tests/hashes_commit.test.js`,
  `static/js/tests/resultats_coches.test.js`) : issue `needs-human` sans
  ligne « Commits » (nouvel état) ; sans commentaire du tout ; avec ligne
  présente mais non reconnue ; `needs-human` + ligne reconnue (hashes/aucun,
  inchangé) ; `needs-human` + `for-windows` (windows prioritaire) ; issue
  réussie sans ligne (reste `'absente'`, message d'anomalie inchangé) ;
  texte exact du nouveau message pour l'état `'echec'`.

Non traité : aucun constat de l'issue ne s'est révélé faux à la lecture du
code — tous les points relevés (emplacement de `texteSectionFichiers`,
comportement de `etatCommitsDeclares`, label `needs-human` déjà lu par
l'interface, lecture des labels comme pour `for-windows`) correspondaient
à l'état réel du code.
