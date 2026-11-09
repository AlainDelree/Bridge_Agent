## 9 novembre 2026 — issue #863

Notifications sous Windows : bulle de bureau et bip sans `notify-send` ni
`aplay`.

**CONSTAT** (audit de parité #862) : les notifications de bureau n'avaient
aucun chemin Windows — la bulle (`notifications.py::notifier_bureau`)
reposait sur `notify-send` et le bip (`scripts/traitement_fin.py`) sur
`aplay`, deux outils Linux. Sur une machine Windows seule, le bip restait
silencieux et une exception dans la lecture du son pouvait interrompre
`traitement_fin.py` avant le POST SSE de fin d'issue vers `new_issue.py`.

**`notifications.py`** : `notifier_bureau` dispatche désormais selon
`platform.system()`. Sous Windows, `_notifier_bureau_windows` pilote
l'assembly .NET `System.Windows.Forms.NotifyIcon` via PowerShell (balloon
tip), déjà présente sur tout Windows avec .NET Framework — aucune
dépendance Python ni module PowerShell externe (type BurntToast). Titre et
message sont transmis au sous-processus par variables d'environnement
(jamais interpolés dans le texte du script PowerShell), pour exclure toute
injection quel que soit leur contenu. L'urgence `critical` mappe sur
l'icône `Error` de la bulle. Toute erreur (PowerShell absent, timeout —
notamment le cas d'un watcher en SERVICE Windows sans session de bureau
ouverte, où la bulle ne peut physiquement pas s'afficher) est journalisée
et avalée, jamais levée. Sous Linux, comportement strictement inchangé
(`notify-send`).

**`scripts/traitement_fin.py`** : nouvelle fonction `_jouer_wav` qui joue
le WAV généré via `aplay` sous Linux (inchangé) ou `winsound.PlaySound`
sous Windows (bibliothèque standard, aucune dépendance ajoutée). `bip()`
et `bip_plat()` délèguent désormais à cette fonction, qui avale toute
erreur (outil absent, pas de session audio). Garde-fou supplémentaire dans
`main()` : l'appel au bip est maintenant entouré d'un `try/except` qui
garantit que le POST best-effort de fin d'issue (rafraîchissement SSE de
l'onglet Résultats) a toujours lieu, même si la lecture du son échoue pour
une raison imprévue — l'absence d'un outil de son ne peut plus faire
échouer la fin de traitement d'une issue, sous aucun système.

**Documentation** (`BRIDGE_AGENT_DOC.md` §4.1, nouveau) : les trois canaux
(bip, bulle, ntfy), leur comportement par plateforme, le cas du watcher en
service Windows sans session de bureau (ntfy reste disponible dans ce cas),
et le réglage `NOTIFIER_LOCAL` à garder à `true` côté CCW sur une machine
Windows seule (sans ThinkPad CCL centralisant via `new_issue.py`) — à
l'inverse de l'installation à deux postes, où `false` évite un doublon
ntfy. Ce réglage vit dans `configs/*.conf`, qu'un agent CCL/CCW ne modifie
jamais lui-même.

**Tests** (`tests/test_notifications_windows_863.py`, 10 cas) : simulent la
plateforme Windows en remplaçant la référence au module `platform` (et, côté
bip, `winsound`) dans l'espace de noms du module testé, puis interceptent
`subprocess.run` — aucune vraie notification ni lecture audio n'est
exécutée. Couvre le dispatch Windows/Linux pour la bulle et le bip, le
mapping d'urgence vers l'icône, l'absence de levée en cas d'outil
manquant/timeout, et surtout le scénario concret corrigé : un bip qui lève
une exception n'empêche plus le POST de fin d'issue.
