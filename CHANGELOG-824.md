## Issue #824 — Résultats : afficher la cause réelle et le contexte quand la copie dans le presse-papier échoue

Jusqu'ici, un échec de copie (`navigator.clipboard.write` ou `execCommand`)
affichait toujours le même message fixe (`MESSAGE_ECHEC_COPIE`), quelle que
soit la cause réelle — l'exception JavaScript (`e`) était reçue par les trois
callbacks `echec` existants (`feedbackToast`/`feedbackBadge` dans
`resultats_coches.js`, `feedbackCopieTitre` dans `attente.js`) puis
silencieusement ignorée, et rien n'apparaissait dans la console pour ce
chemin de copie. Aucune cause n'a été établie ni affirmée par cette issue :
elle se limite à faire parvenir le contexte disponible jusqu'à l'affichage.

`static/js/resultats_coches.js` :
- `detecterNavigateur(userAgent)` (pure) : famille + version du navigateur,
  best-effort par analyse de `navigator.userAgent` (Edge/Safari testés avant
  Chrome, dont la chaîne contient aussi « Chrome/ » et « Safari/ ») ;
- `formaterDetailEchecCopie(contexte)` (pure) : construit la ligne de détail
  technique — cause (nom + message de l'exception, ou « (aucune exception) »
  si absente), mode de copie, délai en ms depuis le début de la copie, focus
  de la fenêtre, contexte sécurisé, navigateur, longueur du texte. Chaque
  champ absent est omis plutôt que d'afficher une valeur mensongère. Ne reçoit
  et n'affiche JAMAIS le contenu du texte copié, seulement sa longueur ;
- `construireDetailEchecCopie(e, mode, debut, texte)` (impure) : lit
  `document.hasFocus()`/`window.isSecureContext`/`navigator.userAgent` au
  moment de l'échec et appelle `formaterDetailEchecCopie` ;
- `envelopperFeedbackEchec(feedback, mode, debut)` : enveloppe le `feedback`
  reçu par `copierModerne`/`lancerCopie`/`copierTexteConnu` pour que leur
  `echec(e, texte)` reçoive un 3e argument (la ligne de détail), sans toucher
  aux autres callbacks ni à la décision de mode de copie, au chaînage des
  écritures ni aux cas de succès — posé une fois par point d'entrée, propagé
  à `telechargerOuSignalerVolumineux` sans changer sa signature ;
- `signalerEchecCopie(texte, detail)` : journalise `detail` par
  `console.warn` et le joint au toast (`toasts.erreur(..., {detailTechnique})`),
  sans changer `MESSAGE_ECHEC_COPIE` ni `texteSecours` ;
- `feedbackToast`/`feedbackBadge` : leur `echec` transmet désormais `detail`
  à `signalerEchecCopie` au lieu de l'ignorer.

`static/js/attente.js` : `feedbackCopieTitre` (bouton « copier » du titre,
issue #823) transmet `detail` de la même façon — seul autre appelant de
`signalerEchecCopie`.

`static/js/socle/toasts.js` : nouvelle option `options.detailTechnique` pour
`toasts.erreur`/`avertissement` — ajoute une ligne discrète sous le message
principal du toast (`.socle-toast-detail`), la journalise dans l'entrée du
panneau « Messages » (`entree.detail`, affiché par `rafraichirListeJournal`
sous une nouvelle structure `.socle-journal-corps`/`.socle-journal-detail`),
et rend la clé anti-empilement unique comme `texteSecours` (jamais effacée
par la fusion). Le message principal et `texteSecours` restent inchangés.

Hypothèse non vérifiée évoquée dans l'issue (lien entre l'intermittence sous
Firefox et l'activation utilisateur) : ni confirmée ni infirmée ici — cette
issue donne seulement le moyen de l'observer la prochaine fois que l'échec se
reproduit.

Tests (`static/js/tests/resultats_coches.test.js`, 9 nouveaux) :
`detecterNavigateur` (Firefox/Chrome non confondu avec Safari/Edge non
confondu avec Chrome/UA absent) et `formaterDetailEchecCopie` (exception avec
nom+message, sans exception, sans délai, contenu du texte jamais inclus,
aucun contexte connu). `static/js/tests/resultats_coches_variantes.test.js`
(2 nouveaux, intégration DOM mockée) : échec RÉEL de
`navigator.clipboard.write` (NotAllowedError) → détail dans le toast ET
`console.warn`, message principal et zone de secours inchangés ; échec de
téléchargement sans exception → détail « (aucune exception) », sans
confusion avec une vraie erreur. Suite JS complète (dossiers `tests/` et
`socle/tests/`) : 420/420 (avant : 409/409). Suite Python
(`tests/lancer_tous_les_tests.py`, non modifiée) : 85/85 fichiers, inchangée.
