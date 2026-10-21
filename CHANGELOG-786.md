## 21 octobre 2026 — issue #786

Suite directe de #785 : un label absent du dépôt était retiré silencieusement
à la création d'une issue, quel que soit ce qu'il pilotait — mécanisme déjà
responsable de quatre incidents (`sans-redacteur` #648, `agent-claude`/
`agent-vibe` #768, `mode_scratch` #785), le dernier ayant fait tourner un
agent une heure en lecture seule sur une tâche qui exigeait d'écrire, sans
la moindre trace avant le rapport de clôture de l'agent lui-même.

- **`app/issues.py` — `LABELS_CRITIQUES`** : répartition des labels posés à
  la création en deux catégories, établie d'après ce que chacun pilote
  RÉELLEMENT dans le code (pas d'après son nom) :
  - **critiques** (`for-linux`, `for-windows`, `mode_write`, `mode_scratch`)
    — décident quel watcher voit l'issue et quel mode d'exécution est armé ;
    absent du dépôt, `creer_issue_gh()` **refuse désormais la création**
    (un seul appel `gh`, pas de boucle de réessai), avec un message nommant
    la cause et la commande de correction :
    `Label « X » absent du dépôt D : ce label pilote le mode ou la
    destination de l'issue […] — création refusée […]. Pour corriger :
    gh label create "X" --repo D` ;
  - **confort** (notification, traçabilité, statut posé plus tard par le
    watcher — `bridge`, `notif_pc`/`notif_gsm`/`notif_tous`,
    `sans-redacteur`…) : comportement best-effort inchangé (#648), toujours
    journalisé (`log.warning`).
- **`scripts/watcher_issues_inbox.py`** : `_creer_issue()` remonte désormais
  `labels_omis` à `_traiter_bloc()`, qui l'ajoute au suffixe de la ligne
  `OK` écrite dans `logs/issues_inbox.log` (lue par l'onglet web,
  `app.issues_inbox.etat_inbox`) — l'omission d'un label de confort devient
  visible sans aller fouiller le journal du process, jusqu'ici jamais
  consulté en pratique.
- **`static/js/creation.js`** : `labels_omis` (déjà renvoyé par `/envoyer`
  mais jamais affiché) déclenche maintenant un toast à l'envoi mono-issue et
  une mention dans le récapitulatif de lot.
- **Aucune modification** de `nouveau_projet.LABELS` (liste provisionnée
  d'office, déjà complétée par #785) ni de la détection d'écart MODE
  déclaré/retenu de #785 (`_texte_ecart_mode`/`_deduire_mode_et_logguer`),
  qui reste un filet utile pour les issues déjà créées.
- **Tests** : `tests/test_label_critique_786.py` (refus sur label critique
  absent, y compris découvert après le retrait d'un label de confort ;
  non-régression du comportement best-effort pour les labels de confort ;
  message de refus). Six fichiers de tests existants mockaient
  `scripts/watcher_issues_inbox._creer_issue` avec l'ancienne signature à
  2 éléments (`succes, resultat`) — mis à jour pour le nouveau triplet
  (`succes, resultat, labels_omis`) : `test_champ_redacteur_599.py`,
  `test_label_sans_redacteur_647.py`, `test_demarrage_ccw_issues_inbox_711.py`,
  `test_champ_attente_713.py`, `test_decoche_relance_720.py`,
  `test_pas_de_ligne_fichier_recu_si_relance_719.py`,
  `test_pas_de_ligne_fichier_recu_si_attente_716.py`. Suite complète :
  327 tests passés (82 fichiers), plus 27/27 côté `node --test` sur
  `creation.test.js` (fonctions pures seulement — `afficherToast`/
  `afficherResumeLot` restent à vérifier manuellement, comme le reste des
  fonctions DOM de ce fichier).
- **Non vérifié** : l'éventuel dépôt de démonstration utilisé pour les tests
  manuels (`configs/` est gitignoré, absent de ce worktree) — le risque
  théorique est qu'un tel dépôt, provisionné avant l'ajout récent de
  `mode_scratch` à `nouveau_projet.LABELS` (#785), ne possède pas encore ce
  label et voie désormais ses créations en lecture active refusées au lieu
  d'être dégradées en lecture seule. Correctif à une commande si rencontré :
  `gh label create "mode_scratch" --repo <dépôt>` (message de refus exact).
