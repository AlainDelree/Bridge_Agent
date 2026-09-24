## 24 septembre 2026 — issue #603

Alignement de `creer_projet_ccw_complet.ps1` (racine du dépôt) sur les
conventions des 11 autres scripts `.ps1` de `provisioning/windows/`
(diagnostic #579, point 4) — 4 problèmes à risque réel corrigés :

- **BOM UTF-8** ajouté en tête du fichier (`EF BB BF`) — sans lui,
  PowerShell 5.1 plante silencieusement au premier accent ajouté.
- **`.conf` sans BOM** : remplacement de `Set-Content -Encoding UTF8`
  (qui écrit un BOM parasite) par `[IO.File]::WriteAllText(...,
  UTF8Encoding($false))`, comme `ajouter_projet_ccw.ps1` — évite de
  corrompre silencieusement la lecture par `watcher.py`.
- **Fuite de secret BSTR** : ajout de la fonction
  `ConvertFrom-SecureStringPlain` (try/finally +
  `Marshal::ZeroFreeBSTR`), même pattern que
  `mettre_a_jour_tokens_ccw.ps1`, appliquée aux deux tokens saisis.
- **Chemin codé en dur** : `$CheminClaude` dérivé dynamiquement de
  `$env:USERPROFILE` au lieu du compte `AlainW` en dur — ne casse plus
  silencieusement si le compte de service change.

Le point 5 du diagnostic (extraction d'un module commun
`provisioning/windows/ccw-commun.psm1` pour la dérivation de chemins
projet dupliquée entre ce script et `ajouter_projet_ccw.ps1`/
`finaliser_projet_ccw.ps1`) dépasse la COMPLEXITE `normal` de cette
issue — reporté à l'issue séparée #604, comme prévu par le corps de
#603.

Aucun test PowerShell direct (script non exécutable côté Linux) ; le
test statique existant `tests/test_ajouter_projet_ccw_env_558.py`
(cohérence `AppEnvironmentExtra` entre les 3 scripts qui le posent) et
l'ensemble des tests Python (`py_compile` + suite `tests/`) restent
verts.
