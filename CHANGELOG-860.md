## 8 novembre 2026 — issue #860

Service CCW Windows d'un projet : compte de service configurable (plus
LocalSystem par défaut), pour que l'agent Vibe (Mistral) retrouve sa
connexion dans le trousseau Windows.

**CONSTAT** (test réel Vibe sous Windows) : `ajouter_projet_ccw.ps1` ne
posait jamais `ObjectName` sur les services NSSM qu'il crée — comportement
par défaut de NSSM, donc `LocalSystem`. Vibe range sa connexion dans le
trousseau Windows (Credential Manager / DPAPI) du compte utilisateur
(`provisioning/vibe/README.md` §3) : sous `LocalSystem`, ce trousseau est
invisible, même si `~\.vibe\…` existe bien sur le disque. Le service doit
tourner sous le compte qui POSSÈDE `~\.vibe` (ou `~\.claude`).

**`provisionner.ps1`** : la valeur par défaut de `-CompteService` devient le
compte qui lance le script (`$env:USERNAME`) au lieu du nom codé en dur
`'AlainW'` — ne convenait qu'au PC fixe d'Alain, pas à une autre machine CCW.

**`ajouter_projet_ccw.ps1`** : nouveaux paramètres `-CompteService` (défaut
`$env:USERNAME`) et `-ConserverLocalSystem` (switch). Par défaut, le service
créé OU reconfiguré (script idempotent) tourne désormais sous
`-CompteService`, mot de passe demandé en saisie masquée (`Read-Host
-AsSecureString`), jamais affiché ni écrit dans un journal. Avec
`-ConserverLocalSystem`, le comportement historique (`LocalSystem`) est
gardé explicitement — nécessaire pour ne pas casser un service Claude Code
déjà en place (pas de problème de trousseau pour cet agent, ses jetons étant
posés en clair dans `AppEnvironmentExtra`).

**Compatibilité des flux automatisés (sans console interactive) —
régression évitée** : trois appelants de `ajouter_projet_ccw.ps1` l'exécutent
sans terminal capable de répondre à l'invite de mot de passe (`app/ccw.py`
via SSH `BatchMode=yes`, `watcher.py` pour le bootstrap « Projet CCW » issue
#554, et `creer_projet_ccw_complet.ps1`) — sans correctif, ces trois flux
seraient restés bloqués jusqu'au timeout. Les trois passent désormais
`-ConserverLocalSystem` explicitement (ils ne créent que des projets Claude
Code). Un projet Vibe se crée en lançant `ajouter_projet_ccw.ps1
-CompteService <compte>` directement, à la main, sur le PC CCW.

**`mettre_a_jour_tokens_ccw.ps1`** : même généralisation du défaut de
`-CompteService` (`$env:USERNAME` au lieu de `'AlainW'`), pour que la ligne
`PATH` reconstruite dans `AppEnvironmentExtra` reste correcte sur une autre
machine. `finaliser_projet_ccw.ps1` et `finaliser_projet_ccw_auto.ps1`
reçoivent un nouveau paramètre `-CompteService` (même défaut), transmis à
`mettre_a_jour_tokens_ccw.ps1` — ni l'un ni l'autre ne touchent `ObjectName`
(`nssm restart` est indifférent au compte de service), donc compatibles sans
changement de fond, seulement pour garder la ligne `PATH` cohérente.

Documentation : `provisioning/windows/REINSTALLATION_CCW.md` (étapes 4 et 7)
et `provisioning/vibe/README.md` §3 mentionnent le nouveau défaut et
`-ConserverLocalSystem`.

**NON EXÉCUTABLE SOUS LINUX** (aucun PowerShell/NSSM disponible dans cet
environnement) : vérifié par relecture rigoureuse de chaque script modifié
et des trois appelants Python (`app/ccw.py`, `watcher.py`,
`creer_projet_ccw_complet.ps1`), plus la suite de tests Python complète
(102 fichiers, 0 échec). **Reste à tester à la main sur le PC CCW** :
création/reconfiguration réelle d'un service avec `-CompteService` (saisie
du mot de passe, démarrage effectif sous ce compte), bascule d'un service
Vibe existant de `LocalSystem` vers un compte nommé et vérification que
`vibe` y retrouve sa connexion, et non-régression des trois flux automatisés
(`-ConserverLocalSystem`).
