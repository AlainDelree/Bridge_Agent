## 22 octobre 2026 — issue #787

Depuis la correction de la reconnaissance des numéros de commit (issue #784),
cocher une issue dans l'onglet Résultats copie son résultat **et** le diff,
alors que la case doit copier le résultat seul (comportement voulu depuis
l'origine, #636) — le bouton **Diff** copie le diff seul, le bouton **All**
copie les deux.

- **Cause établie** : `static/js/resultats_coches.js::basculer()` (onchange
  de la case) appelait la **mauvaise variante** — `texteAll` (résultat +
  diff) au lieu de `texteReponse` (résultat seul) — et cela depuis la toute
  première version de ce module (issue #636). Les trois badges ✅/Diff/All
  appellent eux, et depuis l'origine, la bonne variante chacun
  (`copierReponseBadge`/`copierDiffBadge`/`copierAllBadge`) ; `texteReponse`
  elle-même n'a jamais ajouté de diff. Le défaut est resté invisible deux
  mois parce que la reconnaissance des hashes de commit était cassée :
  `texteAll` ne trouvait alors jamais de diff à ajouter, et son résultat
  était donc identique à celui de `texteReponse`. Une fois #784 corrigé,
  `texteAll` a commencé à réellement ajouter le diff — exposant l'appel à
  la mauvaise variante, resté sans effet visible jusque-là.
- **`static/js/resultats_coches.js`** : `basculer()` appelle désormais
  `texteReponse` au lieu de `texteAll`. Aucun autre changement — ni au
  moteur de copie (#636/#782), ni au texte de secours sur échec (#782), ni
  à la reconnaissance des commits (#784, `hashesDeCommit`, hors de ce
  fichier).
- **Tests** : nouveau fichier
  `static/js/tests/resultats_coches_variantes.test.js` (4 tests) — exerce le
  vrai chemin de production (case / badges → `lancerCopie` → clipboard) pour
  vérifier le contenu réellement copié par chacune des trois variantes :
  la case et le badge ✅ ne copient que le résultat (identité + corps, sans
  diff), le badge Diff ne copie que le diff (sans identité ni corps), le
  badge All copie les deux. Ce test aurait détecté la régression : rejoué
  contre le code buggé (`texteAll` dans `basculer`), il échoue bien sur
  l'assertion « la case ne doit pas copier le diff ». Suite complète :
  312/312 tests passés (`node --test static/js/tests/`).
