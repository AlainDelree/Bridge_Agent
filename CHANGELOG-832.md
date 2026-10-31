## Issue #832 — Résultats : préparer le texte à l'avance aussi en mode moderne (expiration du geste dans Firefox) et corriger la phrase de l'état échec

La case « traité » copiait fiablement en `--lan` (texte préparé AVANT le
clic, issue #636/#782) mais pas en mode moderne (`http://localhost`) : le
texte y était préparé APRÈS le clic (détail d'issue, inventaire des
fichiers modifiés), puis écrit. Firefox n'accepte l'écriture dans le
presse-papier que quelques secondes après le geste utilisateur — quand la
préparation dépassait ce délai, l'écriture était refusée
(`NotAllowedError`, diagnostiqué par l'issue #824 sur un cas réel à 10,1s).
Corrige aussi une phrase trop affirmative de l'issue #830.

- **`static/js/resultats_coches.js`** :
  - `cleValiditeIssue`/`texteEstValide`/`AGE_MAX_TEXTE_PREPARE_MS` :
    validité d'un texte préparé — clé tirée de `state`+`labels` (TOUT ce que
    `/issues-liste` expose côté serveur : ni nombre de commentaires ni date
    de mise à jour n'y figurent, voir `_enrichir_modele`, `app/issues.py`),
    plus un âge maximum de secours (3 min) pour un changement que la clé ne
    voit pas (ex. nouveau commentaire sans changement d'état/label). Un
    texte périmé n'est plus jamais écrit tel quel.
  - `candidatsPrechargement` (pure) + `precharderVisibles` (renommée depuis
    `precharderVisiblesRepli`, qui ne disait plus la vérité) : préparation
    en tâche de fond de la variante `reponse` (celle que la case copie,
    #787) étendue aux **deux modes**, une préparation à la fois
    (`chainePrechargement`), rien si `document.hidden`. Mode repli :
    prépare en plus `all`, comme avant (Diff/All inchangés). **Écart
    confirmé et corrigé** : le préchargement repli ne préparait jusqu'ici
    que `all`, alors que la case copie `reponse` depuis #787 — la première
    case cochée répondait donc toujours « en préparation ».
  - `copierModerne` : chemin rapide quand le texte est déjà préparé et
    valide — écrit directement, SANS attendre aucune préparation (ni la
    sienne, ni celle d'une autre copie en cours) ; seul l'appel au
    presse-papier reste enfilé dans `chaineCopieModerne`
    (`ecrireApresPreparation`), découplé du fetch (qui bloquait jusqu'ici
    toute la chaîne, y compris les copies déjà prêtes).
  - `gesteExpireOuPreparationLente`/`MESSAGE_PREPARATION_TROP_LONGUE` :
    quand l'écriture est refusée pour `NotAllowedError` OU que la
    préparation a dépassé 4s, le texte obtenu est conservé dans le cache
    (clic suivant immédiat) et le message principal du toast devient «
    Préparation trop longue pour le presse-papier : copie manuelle
    ci-dessous (Ctrl+C) ; le texte est maintenant prêt, décoche puis
    recoche la case. » — toute autre erreur garde le message existant.
    `signalerEchecCopie`/`envelopperFeedbackEchec`/`feedbackToast`/
    `feedbackBadge` : message principal paramétrable, détail technique
    (#824) et zone de secours (#782) inchangés.
  - `texteSectionFichiers`, état `'echec'` (#830) : nouvelle phrase qui
    n'affirme ni le moment de l'échec ni l'absence d'anomalie — « Cette
    issue est en échec (needs-human) : son commentaire de clôture ne
    contient pas de ligne « Commits », donc aucun inventaire des fichiers
    n'est possible. »
- **Tests** (`static/js/tests/resultats_coches.test.js`,
  `resultats_coches_variantes.test.js`) : validité des textes préparés
  (clé changée, âge dépassé), sélection du préchargement (non cochées,
  bornes par projet, une fois par issue/variante, deux modes), seuil de
  geste expiré/préparation lente, texte exact du message 4b ; chemin
  rapide (écriture sans attendre une préparation lente en cours ailleurs),
  chemin lent avec refus du geste (cache conservé, message 4b, détail
  technique conservé, second clic sans nouvelle requête), autre erreur
  (message inchangé), mode repli (écart comblé), `document.hidden`
  (rien lancé), texte exact de l'état `echec`. 397→419 côté
  `static/js/tests/` (+22), `static/js/socle/tests/` inchangé (34).
- **`VERIFICATIONS_MANUELLES.md`** : deux points pour Firefox — copie
  immédiate sans fenêtre rouge une fois le préchargement terminé ; fenêtre
  rouge du point 4 provoquée en cochant juste après avoir vidé le cache de
  l'onglet, avec le texte exact attendu.

**Non traité** (hors périmètre explicite de l'issue) : le comportement
réel de Firefox face à une écriture dont le texte arrive plus tard
(piste mentionnée dans l'issue, à ne pas implémenter ni tester ici).
