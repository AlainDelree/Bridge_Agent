## #710 — Garde-fou : les faux exécutables de tests ne peuvent plus laisser passer un appel vers le vrai GitHub

Suite à l'incident du 03/10/2026 (`test_projet_ccw_559.py` lancé sur CCW :
faux `gh` en script bash inopérant sous Windows → le vrai `gh.exe` a créé
deux VRAIES issues sur `AlainDelree/Bridge_Agent`, traitées ensuite par le
watcher). Les issues #704/#706 avaient déjà réglé le cas Windows (skip
`os.name == "nt"`) ; défense en profondeur ici pour toute AUTRE raison
possible (point de montage `noexec`, PATH inhabituel, future plateforme).

- Nouveau `tests/garde_fou_faux_executables.py` :
  `verifier_faux_executables_actifs(bin_dir, noms)` — à appeler juste après
  avoir placé `bin_dir` en tête du PATH, vérifie que CHAQUE commande de
  `noms` (`gh`, `git`, `claude`, `powershell`) résout bien DANS ce
  répertoire (`shutil.which` + comparaison du parent résolu). Échec fermé :
  lève `RuntimeError` avant le moindre appel réel si une seule commande
  échappe au faux. Intégré à `test_creation_bootstrap_ccw_556.py`,
  `test_projet_ccw_559.py`, `test_verrou_refus_precoce_584.py`,
  `test_init_git_local_258.py` (scénario faux `git`),
  `test_lecture_active_327.py`, `test_nettoyage_arbre_247.py`,
  `test_orphelin_verrou_perime_322.py` et
  `test_worktree_parallelisation_337.py` — tous les fichiers de tests
  s'appuyant sur un faux exécutable bash.
- `test_projet_ccw_559.py` et `test_creation_bootstrap_ccw_556.py` :
  remplacement du VRAI dépôt `AlainDelree/Bridge_Agent` par un dépôt
  fictif (`AlainDelree/depot-inexistant-test559`/`…test556`, même
  convention que `test_init_git_local_258.py`/`test_verrou_refus_precoce_584.py`)
  dans tous les scénarios concernés, y compris la config `bridge_agent`
  simulée (`_config_bridge_agent`) qui est le dépôt réellement ciblé par
  `gh issue create` dans le flux bootstrap — assertions adaptées en
  conséquence, aucun autre changement de logique.
- `test_projet_ccw_559.py`/`test_creation_bootstrap_ccw_556.py` : séparateur
  de PATH codé en dur (`:`) remplacé par `os.pathsep` (seule différence
  pratique sous Windows, déjà hors de portée de ces deux fichiers qui
  s'ignorent entièrement sous `os.name == "nt"` — corrigé par cohérence).
- Aucun code de production modifié. Suite complète (`lancer_tous_les_tests.py`)
  verte : 38/38 fichiers.
