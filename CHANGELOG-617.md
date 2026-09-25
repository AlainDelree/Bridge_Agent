## 25 septembre 2026 — issue #617

Diagnostic #579 (bas niveau, points 1/2/3.4) : trois petites duplications
niveau 3 éliminées, sans changement fonctionnel visé.

- **`_ecrire_json_atomique` dupliquée** (`watcher.py` et
  `scripts/archiver_historique.py`, même logique fichier temp +
  `os.replace`) : extraite vers `scripts/utils.py::ecrire_json_atomique`,
  nouveau module bas niveau partagé. `watcher.py` (déjà `sys.path.insert`
  sur `scripts/` pour `traitement_fin`) l'importe sous l'alias
  `_ecrire_json_atomique` pour ne rien changer aux appelants internes ;
  `scripts/archiver_historique.py` fait de même. Un seul exemplaire du
  code, deux points d'entrée inchangés.
- **`os.system(aplay)` → `subprocess.run`** (`scripts/traitement_fin.py`,
  fonctions `bip_plat()` et `bip()`, ~l.91 et ~l.113) : les deux appels
  `os.system(f'aplay {tmp} 2>/dev/null')` remplacés par
  `subprocess.run(["aplay", tmp], capture_output=True)` — même résultat
  (échec silencieux, pas d'exception si `aplay` absent ou en erreur), sans
  passer par un shell, cohérent avec `scripts/bip_Cloche.py`.
- **Sonde PID inline** (`app/watchers.py::watcher_actif()`) : le
  `os.kill(pid, 0)` inline remplacé par un appel à `watcher._pid_vivant`
  (déjà importé sans cycle — `app/watchers.py` importait déjà `Config` et
  `taches_en_cours` depuis `watcher`), fonction cross-plateforme
  POSIX/Windows (issue #584) plutôt qu'un troisième exemplaire de sonde de
  process. Note : `_pid_vivant` traite `PermissionError` comme « vivant »
  par prudence (asymétrie volontaire documentée dans `watcher.py`, contre
  un faux négatif en cas de PID recyclé), alors que l'ancien code local le
  traitait comme « inactif » — différence mineure, cohérente avec l'usage
  qu'en fait déjà `watcher.py` pour ses propres verrous.

Vérification : `py_compile` OK sur les 5 fichiers touchés/ajoutés, import
réel de `watcher`, `app.watchers` et `scripts/archiver_historique.py`
testé (pas seulement compilation syntaxique), les 21 scripts de `tests/`
passent (code de sortie 0), et un test manuel de `bip_plat()`/`bip()` via
`subprocess.run` confirme que le son de fin d'issue continue de fonctionner.
