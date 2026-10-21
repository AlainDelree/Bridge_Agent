## 21 octobre 2026 — issue #782

Les boutons de copie de l'onglet Résultats échouaient (« Copie impossible —
le presse-papier n'a pas pu être écrit »), le décompte entre parenthèses du
toast correspondant au nombre de copies tentées. Diagnostic établi par
reproduction directe (Firefox piloté par WebDriver, sur une page minimale
reprenant exactement le mécanisme de `lancerCopie`) : `navigator.
clipboard.write()` ANNULE (`NotAllowedError`) une écriture encore PENDANTE
dès qu'une NOUVELLE écriture est lancée avant que la précédente ait abouti —
seule la plus récente survit. Cocher plusieurs cases rapprochées (chacune
fetchant son contenu avant d'écrire, comme conçu par l'issue #636) laissait
donc plusieurs écritures en vol simultanément, et toutes sauf la dernière
échouaient. Confirmé reproductible et corrigible par un test identique :
3 écritures lancées en même temps avec un texte prêt à l'instant T échouent
(2 sur 3) avec le texte « prêt avant écriture puis chaînées », les 3
réussissent. Reste supposé (non vérifiable depuis ce poste) : le comportement
exact d'un VRAI clic souris humain (décroissance de l'activation utilisateur)
au-delà de ce que WebDriver a permis de tester — les deux hypothèses de
l'issue (appel trop tardif après le clic, permission navigateur invisible
dans l'IU de Firefox) n'ont PAS reproduit d'échec isolément et ne sont pas
retenues comme cause.

- **`static/js/resultats_coches.js` — mode « moderne » du moteur de copie
  (issue #636) sérialisé** : le texte (réponse/diff/all) est désormais
  intégralement prêt (`await producteur(...)`) AVANT de demander l'écriture
  — plus de `Blob` confié en promesse pendante à `ClipboardItem` — et les
  appels sont chaînés (`chaineCopieModerne`) pour qu'une seule écriture soit
  en vol à la fois, même si plusieurs textes deviennent prêts au même
  instant. Le mode repli (`--lan`, `execCommand`) n'était pas concerné
  (texte déjà préchargé, écriture synchrone) et reste inchangé. Les symboles
  `ERREUR_VIDE`/`ERREUR_AUCUN`, devenus sans objet avec cette restructuration
  (le second était déjà mort avant ce correctif), ont été retirés.
- **Échec de copie désormais utilisable, quelle que soit sa cause** : le
  texte qui n'a pas pu être copié est joint au toast d'erreur dans une zone
  `<textarea>` sélectionnable (pré-sélectionnée, pour un Ctrl+C immédiat) au
  lieu d'être simplement perdu — `feedback.echec(e, texte)` dans
  `resultats_coches.js`, nouvelle option `texteSecours` sur `toasts.erreur`
  (`static/js/socle/toasts.js`). Ces toasts ne sont jamais fusionnés par le
  mécanisme anti-empilement (issue #635, compteur « ×N ») : la fusion
  remplace le contenu affiché, ce qui effacerait silencieusement un texte de
  secours précédent — nouvelle fonction pure `cleToast` (clé unique dès
  qu'un texte de secours est présent), testée.
- **Tests** (`static/js/tests/toasts.test.js`) : 4 nouveaux cas sur
  `cleToast` (fusion conservée sans texte de secours, clé toujours unique
  avec un texte de secours). Le moteur de copie asynchrone lui-même
  (dépendant du navigateur) n'est pas unitairement testable — voir le
  rapport de l'issue pour le détail de la reproduction manuelle.
