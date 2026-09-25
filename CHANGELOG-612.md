## 25 septembre 2026 — issue #612

Corrige trois incohérences laissées par #609/#611 : docstring obsolète,
commentaire erroné sur l'incident `relecture_bridge` #73, extension du
mécanisme de report aux autres déclencheurs de redémarrage.

- **Docstring `repli_rep_travail` déjà simplifiée par #611** (vérifié) :
  ne décrit plus qu'un seul cas — le repli en tout dernier recours après
  échec des 3 tentatives de création de worktree (#589). Aucune trace
  résiduelle du « Cas 1 » (premier slot dans `REP_TRAVAIL`) supprimé par
  #611.
- **Commentaire erroné sur #73 corrigé** (`app/watchers.py` ×3,
  `static/js/app.js` ×2, `BRIDGE_AGENT_DOC.md` ×2) : attribuaient
  l'incident au repli #589 (« reprise sur un worktree déjà pris, repli
  silencieux sur REP_TRAVAIL »). Diagnostic confirmé le 24/09/2026 :
  `#73` tournait dans son worktree dédié avec `MAX_WRITE_PARALLELE=1` ;
  Alain a changé la valeur à 2 et relancé le watcher ; `systemctl --user
  restart` a tué tout le cgroup (dont le process CCL en cours) ; le
  watcher a repris `#73` comme premier slot et l'a lancée directement
  dans `REP_TRAVAIL` — l'ancien comportement du premier slot, supprimé
  depuis par #611. Aucune ligne « déjà pris » dans les logs. Les
  commentaires décrivent maintenant la vraie cause (kill systemd du
  cgroup au redémarrage), distincte du repli #589.
- **`BRIDGE_AGENT_DOC.md`** : paragraphe « Signal d'interface (issue
  #609) » mis à jour — il ne subsiste plus qu'un seul cas de repli
  (#589), plus deux cas à distinguer comme avant #611 ; le bandeau ne
  s'allume donc plus à chaque tâche `mode_write` normale.
- **Extension aux autres déclencheurs (vérification, point 3)** :
  - Bouton « Relancer » du panneau Infrastructure/onglet Watchers :
    déjà couvert — passe par la même route `/lancer-watcher` →
    `demarrer_watcher_ou_differer` que « Enregistrer et relancer »
    (`sidebarRelancerWatcherCCL`/`actionWatchers`, `static/js/app.js`).
    Aucun code à ajouter, documenté explicitement dans
    `BRIDGE_AGENT_DOC.md`.
  - Redémarrage systemd sur crash (`Restart=on-failure`) : NE PEUT PAS
    être intercepté côté Python (le process CCL est tué avant d'avoir la
    main). Limite documentée explicitement dans `BRIDGE_AGENT_DOC.md`
    (§16 et §"Redémarrage forcé différé"), pour ne pas laisser croire que
    #609/#611 couvrent ce cas.
- Suite de tests existante toujours verte (14 tests pytest + 19 scripts
  autonomes, tous OK).
