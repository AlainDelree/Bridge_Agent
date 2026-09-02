## 2 septembre 2026 — issue #516

Champ `RELANCE` dans `issues_inbox/` : corriger/relancer une issue
`needs-human` sans repasser par une édition manuelle sur GitHub. Jusqu'ici,
ajuster un `TIMEOUT` trop court après un échec par dépassement obligeait à
sortir du flux `issues_inbox` — redéposer un `.txt` avec le même titre
échouait systématiquement (anti-doublon §3.4, qui rejette tout titre déjà
porté par une issue OUVERTE, `needs-human` incluse).
- `scripts/watcher_issues_inbox.py` : nouveau champ d'en-tête optionnel
  `| RELANCE | #N |` (en cohérence avec `SUITE_DE`, §6). Présent, il
  détourne tout le bloc vers la correction de l'issue #N déjà ouverte —
  aucune création, anti-doublon court-circuité (n'a de sens que pour une
  création). Validation avant modification (`valider_relance`,
  `_recuperer_issue`) : `PROJET` résout le dépôt cible, `RELANCE` doit être
  un numéro exploitable, `gh issue view --repo` confirme l'existence et
  l'appartenance au bon dépôt, l'issue doit être OUVERTE — sinon rejet vers
  `rejected/`, même mécanique que les rejets existants. Champs corrigibles
  dans le corps : `TIMEOUT` et `MODELE` uniquement (`_fusionner_entete`/
  `_maj_ligne_entete` — corrige une ligne déjà présente, n'en insère jamais
  une nouvelle). `MODE` est exclu (le mode réel est armé par le label GitHub
  `mode_write`/`mode_scratch`, pas par le texte du corps — le
  resynchroniser depuis ce chemin est jugé hors-scope pour cette première
  itération) ; `LABELS` aussi (n'apparaît jamais dans le corps).
- `app/interruption.py` : logique de `route_relancer()` (bouton
  « 🔄 Relancer », issue #460) extraite dans `relancer_issue(depot, numero,
  commentaire=...)`, réutilisée telle quelle par le champ `RELANCE` — aucun
  retrait de label / pose de commentaire dupliqué entre les deux flux. Le
  commentaire posté depuis `issues_inbox/` mentionne explicitement RELANCE,
  résume les champs corrigés et reprend le texte libre éventuel du fichier
  déposé.
- `BRIDGE_AGENT_DOC.md` : nouveau §3.14, ligne `RELANCE` ajoutée au tableau
  §6.
- `tests/test_champ_relance_516.py` (nouveau) : extraction du champ,
  parsing du numéro, fusion des champs corrigibles (jamais d'insertion d'un
  champ absent), chemin complet `_traiter_relance` (succès, issue fermée,
  numéro invalide) — tous les appels `gh` substitués, aucun accès réseau.
- Formulaire web (`new_issue.py`) volontairement non modifié : il sert à
  **créer** des issues et dispose déjà d'un chemin dédié pour cibler une
  issue existante (bouton « 🔄 Relancer ») — dupliquer `RELANCE` là
  n'apporterait rien.
