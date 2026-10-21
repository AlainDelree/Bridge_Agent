## 21 octobre 2026 — issue #785

Cause établie : le MODE réel d'une issue est exclusivement armé par les
labels GitHub (`mode_write` > `mode_scratch` > lecture seule par défaut,
`_deduire_mode`), jamais par le texte de l'en-tête — mais `mode_scratch`
(label qui arme la lecture active, issue #327) manquait de
`nouveau_projet.LABELS`, la liste des labels provisionnés d'office sur tout
nouveau dépôt. Exactement la même régression que `sans-redacteur` (#648) et
`agent-claude`/`agent-vibe` (#768) : sur un dépôt où ce label n'a jamais été
créé à la main, `creer_issue_gh` (app/issues.py, comportement #648) le
retire silencieusement de la liste faute d'exister plutôt que de faire
échouer toute la création — une issue déclarant `| MODE | lecture active |`
s'exécutait donc en lecture seule, sans dossier scratch ni consigne
correspondante, sans qu'aucune erreur ni avertissement ne le signale. Le
mode écriture, lui, fonctionnait car `mode_write` figurait bien dans cette
liste depuis l'origine. Vérification des autres champs d'en-tête traduits
en labels (`LABELS`, notifications, `REDACTEUR`→`sans-redacteur`,
agent-claude/agent-vibe) : tous présents dans `nouveau_projet.LABELS`,
`mode_scratch` était le seul absent.

- **`nouveau_projet.py` — `mode_scratch` ajouté à `LABELS`** : tout nouveau
  projet provisionne désormais ce label d'office, comme `mode_write`. Les
  dépôts déjà existants (dont celui à l'origine du signalement) nécessitent
  toujours un `gh label create` manuel une fois, même procédure que pour
  `sans-redacteur`/`agent-claude`/`agent-vibe` — à faire par Alain, hors
  périmètre de cette issue.
- **`watcher.py` — détection d'un écart entre le MODE déclaré dans l'en-tête
  et le MODE réellement retenu**, au moment même où le watcher déduit le
  mode au lancement (`_deduire_mode_et_logguer`) : `extraire_mode_entete`
  lit le champ `| MODE | … |` du corps (reconnaissance tolérante, jamais
  utilisée pour déterminer le mode réel — seulement pour le comparer) ;
  `_texte_ecart_mode` compare au mode déduit des labels. Un écart est
  désormais systématiquement **journalisé** (log.warning du watcher du
  projet) et **mentionné dans le commentaire de clôture de l'issue**,
  succès comme échec (`_finaliser_succes` et les quatre gestionnaires
  d'échec/abandon), au lieu de rester invisible jusqu'à ce que l'agent le
  découvre lui-même en tentant d'écrire. Le MODE réellement appliqué reste
  inchangé : toujours celui des labels, seul mécanisme sous contrôle
  d'accès — un écart est signalé, jamais corrigé à la volée.
- **`BRIDGE_AGENT_DOC.md`** — §4 : `mode_scratch` ajouté au tableau des
  labels disponibles et à la liste des labels provisionnés d'office
  (comme `sans-redacteur`/`agent-claude`/`agent-vibe`), avec la mention de
  l'écart désormais détecté pour tout dépôt où le label manquerait encore.
- **Garde-fous mode écriture et lecture seule : inchangés**, de même que le
  garde-fou technique niveau 2 de la lecture active (empreinte REP_TRAVAIL
  avant/après, restauration + `needs-human` sur écriture hors scratch,
  issue #327) — vérifié par les scénarios existants de
  `tests/test_lecture_active_327.py`, toujours au vert.
- **Test ajouté — `tests/test_ecart_mode_entete_785.py`** : régression
  directe sur `nouveau_projet.LABELS` (contient `mode_scratch`),
  reconnaissance tolérante de `extraire_mode_entete` (y compris la
  distinction avec le champ voisin `MODELE`), détection/silence de
  `_texte_ecart_mode` selon les cas, et journalisation + retour de l'écart
  par `_deduire_mode_et_logguer` sans changer le mode réellement appliqué.

Suite de tests réellement exécutée : `python3 tests/lancer_tous_les_tests.py`
→ 79 fichiers, 79 réussis, 0 échec ; `python3 -m pytest tests/` → 321 passed.
