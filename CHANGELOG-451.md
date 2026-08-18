## 18 août 2026 — issue #451

DOC — nouveau fichier `provisioning/windows/REINSTALLATION_CCW.md` :
procédure complète de réinstallation du PC fixe CCW, aux côtés des scripts
qu'elle utilise (`autounattend.xml`, `provisionner.ps1`,
`mettre_a_jour_tokens_ccw.ps1`), plutôt que dans `BRIDGE_AGENT_DOC.md` qui
est destiné aux agents CCL/CCW et non à la procédure d'installation
Windows. Couvre dans l'ordre : réinstallation Windows via
`autounattend.xml`, configuration SSH (`configurer_ssh_ccw.ps1`),
vérification de la connexion SSH depuis CCL, provisioning logiciel
(`provisionner.ps1`), topic ntfy + tokens
(`mettre_a_jour_tokens_ccw.ps1`), vérification du service `CCW-Watcher`.
Précise que la clé privée CCL (`~/.ssh/ccl_ccw`) reste sur le ThinkPad
entre les réinstallations — seule la clé publique est à réinstaller sur le
nouveau Windows.
- `BRIDGE_AGENT_DOC.md` : §16 complété d'une ligne de référence vers ce
  nouveau fichier.

**Point d'attention signalé (pas corrigé, hors périmètre de cette
issue) :** `configurer_ssh_ccw.ps1`, référencé à l'étape 2 de la
procédure, n'existe pas dans `provisioning/windows/` au moment de la
rédaction — il devra être créé (script PowerShell côté Windows qui active
OpenSSH Server et installe la clé publique fournie dans
`authorized_keys`) avant que l'étape 2 soit exécutable telle quelle. Une
note l'indique en bas du nouveau fichier.
