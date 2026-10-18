# CHANGELOG-770 — à fusionner dans CHANGELOG.md

## 18 octobre 2026 — issue #770

Uniformisation des libellés du formulaire de déclaration de modèle de
l'agent Vibe (`templates/fragments/onglet_vibe.html` /
`static/js/vibe_modele.js` / `app/vibe_modele.py`) : le tableau des modèles
déclarés et le formulaire juste au-dessus désignaient la même donnée avec
deux vocabulaires différents (en-têtes français vs noms techniques du
fichier en anglais).

- **Libellés traduits**, dans le même vocabulaire que les en-têtes du
  tableau : `alias` → « Alias », `name` → « Modèle », `provider` →
  « Fournisseur », `input_price` → « Prix d'entrée », `output_price` →
  « Prix de sortie » (`LIBELLES_CHAMPS_AJOUT` / `libelleChampAjout` dans
  `static/js/vibe_modele.js`). Les noms techniques (clés écrites dans
  `config.toml`) restent inchangés — seul l'affichage change. Un champ
  introspecté qui ne figurerait pas dans cette table (future version de
  Vibe) se replie sur son nom technique tel quel, comme avant.
- **Ordre des champs** : ce qui identifie le modèle (alias, modèle,
  fournisseur) apparaît maintenant avant les champs accessoires (prix).
  Obtenu en retirant les champs de prix du calcul des champs requis côté
  serveur (voir point suivant) — `champs_requis` ne contient plus alors que
  alias/name/provider, triés alphabétiquement par `_schema()`, ce qui les
  place naturellement avant les champs de prix renvoyés en
  `champs_connus` (triés alphabétiquement eux aussi, en fin de formulaire).
  Avant ce correctif, les champs de prix pouvaient se retrouver promus
  « requis » (intersection des clés communes à tous les modèles déjà
  déclarés) et donc intercalés avant `name` dans le tri alphabétique
  global — d'où le prix affiché avant le nom du modèle signalé par
  l'issue.
- **Champs de prix rendus facultatifs** : `input_price`/`output_price` ne
  conditionnent pas le fonctionnement de Vibe (seuls `name`/`provider`/
  `alias` le sont — `_REQUIRED_MODEL_FIELDS` côté outil), seulement
  l'affichage d'un coût estimé. `CHAMPS_JAMAIS_REQUIS` dans
  `app/vibe_modele.py::_schema()` les exclut désormais explicitement du
  calcul par intersection, même lorsqu'ils sont présents sur toutes les
  entrées déjà déclarées dans le fichier — ils restent toujours dans
  `champs_connus` (optionnels), jamais dans `champs_requis`.
- **Indication sur le champ Alias** : courte note rappelant qu'un alias
  identique à un modèle intégré de Vibe est écrasé par l'outil à son
  prochain démarrage — le contrôle serveur existait déjà (confirmation
  requise, issue #766), cette note prévient avant la saisie plutôt que de
  laisser découvrir le refus après coup.
- Comportement inchangé à part la bascule facultatif/requis ci-dessus :
  aucun changement sur la lecture/écriture de `config.toml`, ni sur
  `watcher.py` (non concerné par cette issue).
- Tests adaptés : `tests/test_modele_vibe_766.py`
  (`test_etat_liste_modeles_et_schema_sans_liste_figee` attend maintenant
  `champs_requis == {name, provider, alias}` et `champs_connus ==
  {input_price: nombre, output_price: nombre}`) ; `static/js/tests/
  vibe_modele.test.js` complété par deux scénarios sur `libelleChampAjout`
  (vocabulaire du tableau, repli sur le nom technique pour un champ
  inconnu).
