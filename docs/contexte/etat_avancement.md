# État d'avancement — bridge_agent

Quand lire : avant de toucher au socle web (`static/js/socle/`), à la
calibration automatique du TIMEOUT, aux consignes à trois couches (§12.1),
aux pièces jointes d'issue, aux notifications, à l'onglet CCW, ou au champ
`ATTENTE` d'`issues_inbox/`. Historique complet : changelog en bas de
`BRIDGE_AGENT_DOC.md`.

- #625→#652 (refonte web) : socle `static/js/socle/` + modules par
  fonctionnalité sortis d'app.js, communiquant par le store. #643 :
  retrait du son par projet. #644 : migration `localStorage` terminée,
  fuite corrigée. #649→#652 : onglets CCW/Journal/Configuration (+
  suppression de projet #587) et le formulaire Nouvelle issue sortis en
  modules dédiés. Détail : `ARCHITECTURE.md §6`.
- #221 (calibration TIMEOUT, 2/3) : `watcher.py` journalise `TIMEOUT_suggéré`
  à la clôture (EWMA par projet+TYPE+mode dans `logs/etat_timeout.json` +
  `logs/etat_ambiance.json` pour F_reseau/F_local) — n'affecte pas encore le
  TIMEOUT appliqué (en-tête seul décisif).
- §12.1 (#209/#211) : `consignes/` (globales/type/projet) injecté dans le
  PROMPT CCL par `watcher.py` (point de passage unique) ; `globales.md`
  obligatoire, le reste facultatif.
- §18 (#191/#192) : pièces jointes image → `issue-attachments/` + URL raw.
- §17 (#187) : notifications centralisées via `new_issue.py` (tous projets).
- §16 (#174…) : onglet « CCW », démarrage à la demande fini (#709/#711).
  #717 : natif Windows sans SSH → `nssm` direct (droits `sc.exe sdset`).
- §3.16 (#713, 1/2) : champ `ATTENTE` dans `issues_inbox/` met une issue de
  côté (`en_attente/`) au lieu de la créer ; routes `/issues-attente`
  (liste/lancer/supprimer), `nb_en_attente` sur `/issues-inbox/etat` ;
  AUCUNE vérif auto de la condition. Onglet web = issue 2/2 (à venir).
