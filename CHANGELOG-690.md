## #690 — Provisioning pour new_issue.py natif sur Windows (plan hybride)

Suite à la première exécution native de `new_issue.py` sur le PC fixe
Windows (CCW) le 28/09/2026 (validation de l'issue D), faite entièrement à
la main : dépendances Python installées manuellement (aucun
`requirements.txt`), `gh auth login` fait à tâtons (session interactive
distincte du `GH_TOKEN` du service `CCW-Watcher`), règle de pare-feu créée
à la main pour le port 5100 entrant. Avant le changement de PC prévu d'ici
1-2 mois, capitalisation de cette expérience pour la prochaine machine.

- **`requirements.txt`** (nouveau, racine du dépôt) : dépendances Python
  propres à `new_issue.py`/`app/` — `flask>=3.1`, `werkzeug>=3.1` (seules
  dépendances non-stdlib trouvées après relecture des imports ; `watcher.py`
  n'en a besoin d'aucune, déjà couvert par `provisionner.ps1`).
- **`provisioning/windows/provisionner_new_issue_local.ps1`** (nouveau,
  BOM UTF-8) : script idempotent dédié à cet usage précis (distinct de
  `provisionner.ps1`, qui provisionne le service `CCW-Watcher` headless) —
  `pip install -r requirements.txt`, règle de pare-feu entrante TCP/5100
  (`Get-NetFirewallRule` avant `New-NetFirewallRule`), vérification de
  `gh auth status` avec invite à lancer `gh auth login` si besoin
  (authentification elle-même non automatisée — interaction humaine
  requise). Nécessite une console administrateur (`New-NetFirewallRule`) ;
  suppose Python et `gh` déjà installés (cf. `provisionner.ps1` sinon).
- **`provisioning/windows/NEW_ISSUE_LOCAL_WINDOWS.md`** (nouveau) :
  documente l'usage du script ci-dessus ainsi que l'alias PowerShell
  `bridge` (fonction dans `$PROFILE` lançant `new_issue.py --lan` d'une
  commande) — volontairement non automatisé (modification du profil
  personnel de l'utilisateur), commande prête à copier-coller.

Résultat : sur une machine Windows neuve, `provisionner_new_issue_local.ps1`
puis `gh auth login` (à la main) suffisent pour que `new_issue.py --lan`
fonctionne directement, sans repasser par le diagnostic pare-feu/dépendances
du 28/09/2026.

Fichiers touchés : `requirements.txt` (nouveau),
`provisioning/windows/provisionner_new_issue_local.ps1` (nouveau),
`provisioning/windows/NEW_ISSUE_LOCAL_WINDOWS.md` (nouveau).
