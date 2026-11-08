## 8 novembre 2026 — issue #858

Copie du rapport (case à cocher, onglet Résultats) : retour à l'écriture
presse-papier **engagée au clic** avec contenu différé, comme avant l'issue
#782 — pour que Firefox accepte une préparation arbitrairement longue, au
lieu d'échouer (NotAllowedError) une fois la fenêtre d'activation du geste
dépassée.

**CAUSE CONFIRMÉE** par relecture du code et de l'historique (pas une simple
hypothèse) : depuis #782 (21 octobre), `navigator.clipboard.write()` n'est
appelé qu'une fois le texte du rapport ENTIÈREMENT préparé (fetch /issue,
/diff, /inventaire-commit depuis #788) — potentiellement bien après la fin
de la fenêtre d'activation ouverte par le clic. Firefox refuse alors
l'écriture, comme diagnostiqué sur un cas réel à 10,1s de préparation (issue
#824). Avant #782, l'appel à `write()` était SYNCHRONE au clic — seul le
contenu (confié au `ClipboardItem` via une promesse) pouvait arriver après
coup — et Firefox l'acceptait quelle que soit la durée. #782 avait abandonné
cet engagement différé pour une AUTRE cause, elle aussi réelle : plusieurs
cases cochées très vite annulaient les écritures précédentes (Firefox annule
une écriture encore pendante dès qu'une nouvelle est lancée avant qu'elle
n'aboutisse). #832/#835/#839 ont ensuite contourné le SYMPTÔME (précharger
avant le clic) sans toucher à la cause : un clic trop rapide pour un rapport
pas encore préchargé restait exposé.

**RESTE UNE HYPOTHÈSE**, non vérifiable depuis cet environnement : que
Firefox accepte RÉELLEMENT un contenu différé après plusieurs secondes,
comme c'était le cas avant #782. Les tests Node ne font que SIMULER ce
comportement (mock de `clipboard.write`) — essai manuel ajouté à
`VERIFICATIONS_MANUELLES.md`.

### Le correctif

`copierModerne` (`static/js/resultats_coches.js`) engage désormais
`navigator.clipboard.write()` SYNCHRONEMENT, au clic, avec un contenu
construit par une chaîne de promesses (`issuePreparation`/`blobP`) qui ne
REJETTE JAMAIS — elle résout toujours vers le rapport (si tout va bien) ou
une chaîne vide (texte vide, aucun diff, diff volumineux, échec de
préparation) : le FEEDBACK affiché (succès/vide/aucun/téléchargement/échec)
reste, lui, entièrement fidèle à la VRAIE cause, décidée séparément à partir
de l'issue de préparation et du sort réel de l'écriture — jamais de faux
succès (invariant #636/#782 conservé).

**Chemin rapide conservé** (issue #832 point 2) : quand le texte de la
variante est déjà préchargé et valide, la promesse de contenu est résolue
d'emblée — même mécanisme, aucune différence de code entre chemin rapide et
chemin lent au moment de l'engagement.

**Clics rapprochés (point 3 de l'issue)** : un compteur de génération global
(`generationCopieModerne`) remplace la sérialisation de #782
(`chaineCopieModerne`, qui faisait réussir toutes les copies mais hors
fenêtre d'activation pour les premières). Seule la DERNIÈRE copie demandée
(case ou badge, n'importe quelle issue — une seule écriture presse-papier
possible à la fois, comme le système lui-même) compte : une copie en vol
supplantée par une plus récente est désormais abandonnée **en silence** (ni
toast, ni fenêtre de secours, ni badge d'échec) — `copieSupplantee(monGen)`
vérifie, au règlement de CHAQUE copie, qu'elle est toujours la plus récente
avant d'émettre le moindre feedback. Un échec réel (toute autre cause) garde
l'affichage existant (toast, fenêtre de secours, ligne de détail technique
#824).

**Vidage du clic (#857) conservé**, avec un ajustement : une seule tentative
d'écriture vide, SANS repli sur un espace en mode moderne en cas d'échec —
un second appel `write()` à cet endroit serait lui-même une NOUVELLE
écriture, qui annulerait silencieusement le rapport déjà engagé juste après
dans le même geste (reproduit par un test Node simulant l'annulation
concurrente). Le repli sur un espace reste inchangé en mode `--lan`
(`execCommand`, synchrone, aucun risque de concurrence). Le vidage et
l'écriture du rapport ne passent plus par `chaineCopieModerne` (devenue
sans objet pour ce chemin) : les deux sont désormais engagés SYNCHRONEMENT,
l'un après l'autre, dans le même geste — si Firefox annule le vidage au
profit du rapport qui le suit immédiatement (hypothèse plausible, non
vérifiée en vrai navigateur), ce n'est pas grave : le contenu réellement
confié au presse-papier par le rapport est lui-même déjà garanti résoudre
vers le rapport ou une chaîne vide, jamais l'ancien contenu.

### Ce qui reste, ce qui devient superflu (point 5 de l'issue)

Rien n'est supprimé. `SEUIL_PREPARATION_LENTE_MS`, `gesteExpireOuPreparationLente`
et `MESSAGE_PREPARATION_TROP_LONGUE` restent exportés et testés, mais ne sont
plus branchés dans `copierModerne` : la cause qu'ils détectaient (préparation
lente → expiration du geste) ne peut plus se produire par construction,
l'écriture étant désormais engagée AVANT la préparation. Le préchargement en
tâche de fond (`precharger`, `candidatsPrechargement`, `precharderVisibles`,
le repère « prêt à copier » de #835) reste pleinement utile : il continue
d'alimenter le chemin rapide (copie immédiate sans même attendre la
construction de la promesse de contenu) — seule la dépendance ABSOLUE à ce
préchargement (sans lui, échec certain) disparaît.

`chaineCopieModerne` ne sert plus qu'à `copierTexteConnu` (bouton « copier »
du titre, onglet En attente, issue #823) — **non modifiée**, hors périmètre
de cette issue, tout comme le bouton Diff/All de l'onglet En attente et les
boutons « Copier résumé »/« Copier tout » du détail d'une issue.

### Tests JavaScript (`static/js/tests/resultats_coches_variantes.test.js`)

- **Préparation volontairement très lente** (fetch bloqué indéfiniment,
  REPRÉSENTANT une préparation de 15s ou plus sans ralentir la suite de
  tests) : l'écriture reste acceptée dès que la préparation se termine,
  aucune expiration de geste.
- **Clics rapprochés** : une copie LENTE (préparation en vol) puis
  IMMÉDIATEMENT une copie déjà prête — seule la seconde aboutit ; le
  déblocage tardif de la première ne produit AUCUN message supplémentaire
  (ni succès, ni échec) et AUCUNE fenêtre de secours. Simulé par un mock
  dédié (`creerClipboardAvecAnnulationConcurrente`) reproduisant le
  comportement RÉEL observé de Firefox (annulation d'une écriture encore
  pendante par une plus récente) — seul moyen, sous Node, de distinguer un
  abandon silencieux d'une simple absence de feedback alors que l'ancien
  contenu écraserait quand même le nouveau une fois résolu.
- **Échec réel** (ni NotAllowedError seul, ni clic plus récent) : message et
  fenêtre de secours inchangés (test existant, non modifié, toujours valide).
- Le test « badge ✅, échec RÉEL … NotAllowedError » (issue #824) est mis à
  jour : un NotAllowedError SOLITAIRE (aucun clic plus récent) affiche
  désormais le message GÉNÉRIQUE, pas celui de #832 point 4b (devenu sans
  objet — voir plus haut).
- Le test « chemin lent, écriture refusée pour geste expiré » (ancien,
  #832) est retiré : sa prémisse (NotAllowedError seul ⇒ geste expiré,
  texte mis en cache, message dédié) ne correspond plus au nouveau
  comportement voulu par cette issue ; remplacé par les deux tests
  ci-dessus.
- Tous les mocks `clipboard.write` du fichier sont ajustés :
  `items[0].data['text/plain']` est désormais une PROMESSE de `Blob` (retour
  au contrat d'avant #782), pas un `Blob` direct — chaque mock l'`await`
  avant d'en lire le texte.
- `fixerEnvironnement` complète son mock de `document` avec `head`
  (`appendChild`) : son absence masquait par hasard, dans l'ancien code, une
  exception de `toasts.js` (rattrapée à tort par le même `try/catch` que
  l'écriture presse-papier) — mise au jour par ce refactor, corrigée à la
  racine plutôt que de reproduire l'absorption accidentelle.

Suite complète (`node --test static/js/tests/*.test.js`) : 483 tests, tous
au vert.

### Vérifié / pas vérifié

Vérifié par les tests : le comportement de `copierModerne`/`viderPressePapier`
face à une préparation arbitrairement longue, à des clics rapprochés
(simulés), et à un échec réel — en environnement Node simulé uniquement.
**PAS vérifié par les tests** (nécessite un vrai navigateur) : que Firefox
accepte réellement un contenu différé après plusieurs secondes, et que son
mécanisme d'annulation d'écriture concurrente correspond bien à ce que les
tests simulent. Essais manuels ajoutés à `VERIFICATIONS_MANUELLES.md` :
préparation lente sans préchargement (attendre plus de 10s puis coller), et
plusieurs cases cochées très vite (un seul résultat, sans fenêtre rouge
intermédiaire).

Doc : `ARCHITECTURE.md` (section « Étape 5b », issue #636) mise à jour pour
refléter le retour à l'engagement synchrone et le compteur de génération ;
`VERIFICATIONS_MANUELLES.md` : l'essai #832 point 4 (fenêtre rouge provoquée
délibérément) est remplacé par les deux essais #858 ci-dessus (ce
comportement n'existe plus).
