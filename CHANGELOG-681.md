## Issue #681 — rep_defaut() sensible à l'OS + which→shutil.which dans nouveau_projet.py

`nouveau_projet.py` : `rep_defaut()` utilise désormais `Path.home() / nom.capitalize()`
au lieu du chemin `/home/alain/...` câblé en dur — résout correctement sous
Windows comme sous Linux. La détection de `gh` (ligne ~939) utilise désormais
`shutil.which("gh")` au lieu de `subprocess.run(["which", "gh"], ...)`, alignée
sur le pattern déjà utilisé ailleurs dans le dépôt (`app/tunnel.py`,
`app/projet_ccw.py`, `watcher.py`, `provisioning/windows/*.py`). Comportement
inchangé sous Linux.
