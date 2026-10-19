## 19 octobre 2026 — issue #777

Correction de trois défauts cumulés révélés par l'incident chesscoach #123 :
une tâche pourtant terminée (deux commits : sauvegarde + correctif) a été
abandonnée après TROIS tentatives identiques, faute d'une ligne de verdict
lisible — avec un diagnostic automatique ayant en plus inventé quatre causes
toutes fausses.

- **Point le plus important : ne plus relancer quand le worktree a déjà
  avancé.** Nouveau garde-fou `_commits_au_dela_sauvegarde` + `_gerer_
  verdict_illisible_avec_commits` (`watcher.py`) : quand une tentative
  échoue faute de ligne de verdict lisible (#581) ET que le worktree
  contient déjà des commits au-delà de celui de sauvegarde (repérés par
  POSITION, comme `_avertissement_succes_sans_commit` #764), le traitement
  s'arrête IMMÉDIATEMENT (dès la première tentative concernée, même pour une
  issue critique) au lieu d'enchaîner les tentatives restantes — état
  distinct (`needs-human`), commit(s) trouvé(s) listés dans le compte-rendu
  de clôture, aucune incidence sur le succès/échec lui-même (relecture
  humaine requise). Priorité la plus haute dans la boucle de tentatives,
  avant même la détection d'erreur bloquante (#760).
- **Diagnostic automatique corrigé** (`diagnostiquer_echec`) : ne peut plus
  invoquer un dépassement de délai contredit par les faits — la durée
  RÉELLE de la dernière tentative et le délai configuré sont désormais
  injectés dans son prompt, avec interdiction explicite de les contredire.
  L'ancien exemple trompeur (« tâche simplement trop volumineuse pour le
  timeout configuré »), qui orientait le modèle vers cette cause par simple
  suggestion même hors de propos, est retiré. Le modèle doit répondre `RAS`
  s'il ne trouve aucune cause concrète et vérifiable — traité comme une
  ABSENCE de diagnostic (préférée à une invention), jamais affiché. Les deux
  garde-fous #581/#757 joignent désormais la FIN brute de la sortie capturée
  (`LIMITE_STDERR_LOG` = 2000 car., pas 500) plutôt que son début — c'est
  cette fin qui aurait montré immédiatement la vraie cause dans l'incident
  chesscoach.
- **Reconnaissance du verdict assouplie, étroitement** (`_verdict_final`) :
  du texte AVANT le marqueur de clôture est désormais toléré, mais
  uniquement sur la toute PREMIÈRE ligne de la sortie capturée (celle qui,
  par gabarit, doit ouvrir la réponse — décision #763 inchangée : on garde
  toujours la PREMIÈRE occurrence, jamais la dernière). Hypothèse vérifiée
  dans le code avant correction (journaux de l'exécution chesscoach hors
  périmètre) : `_RE_LIGNE_VERDICT` exigeait bien la ligne ENTIÈRE, sans
  aucune tolérance de préfixe — confirmé. Portée volontairement étroite
  (restriction à la première ligne, pas à n'importe quelle ligne) pour ne
  pas réintroduire le défaut corrigé par #762/#763/#764 (marqueur cité en
  exemple ou en puce de liste pris pour un verdict) : un marqueur employé
  comme puce de liste ou cité en milieu de phrase ailleurs dans le rapport
  continue de ne déclencher aucun verdict.
- **Consignes globales** (`consignes/globales.md`) : nouvelle puce rappelant
  que la ligne de verdict doit toujours rester SEULE sur sa propre ligne,
  jamais combinée avec une phrase d'introduction — les agents n'avaient
  aucun moyen de deviner cette contrainte.
- **Tests** : 3 nouveaux fichiers (`test_verdict_texte_avant_marqueur_777.py`,
  `test_diagnostic_sans_invention_777.py`,
  `test_arret_verdict_illisible_commits_777.py`), dont un scénario bout en
  bout (worktree git réel, faux `claude`/`gh`) reproduisant l'incident
  chesscoach et son contrôle (aucun commit au-delà de la sauvegarde → les 3
  tentatives restent consommées normalement) ; `test_ligne_verdict_764.py`
  mis à jour pour refléter l'assouplissement. 75/75 fichiers de tests
  (72 existants + 3 nouveaux) au vert via `tests/lancer_tous_les_tests.py`.
