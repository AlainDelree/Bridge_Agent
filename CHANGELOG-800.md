## Issue #800 — retrait des derniers mots « VM » (message de provisioning + nom de fonction CCW)

- `provisioning/windows/provisionner.ps1` : le commentaire et le message d'erreur
  de la fonction d'installation du Windows App Runtime ne mentionnent plus de VM
  ni de NAT (remplacement ciblé de 2 lignes, BOM UTF-8 et fins de ligne LF
  préservés).
- `app/ccw.py` / `app/interruption.py` : fonction `_lister_projets_vm` renommée
  `_lister_projets_ccw` (définition, 3 appels, 3 docstrings, import).
- `tests/test_demarrage_ccw_a_la_demande_709.py` et
  `tests/test_demarrage_ccw_windows_717.py` : chaînes `Patch(ccw, "_lister_projets_vm", ...)`
  mises à jour avec le nouveau nom.
- Non traité (hors périmètre de cette issue) : les scripts
  `provisioning/windows/creer_vm_ccw.py` et `provisioning/windows/lancer_provisioning.py`,
  qui parlent légitimement de la VM VirtualBox et relèvent d'une autre issue.
