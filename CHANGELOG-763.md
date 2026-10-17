# CHANGELOG-763 — à fusionner dans CHANGELOG.md

## 17 octobre 2026 — issue #763

Deux correctifs indépendants, issus chacun d'un incident survenu le même
jour (tous deux touchant `watcher.py`, d'où leur traitement conjoint).

- **Point 1 — `_verdict_final` retient désormais le PREMIER marqueur ✅/❌ en
  tête de ligne, plus le dernier (corrige #757).** Incident déclencheur :
  issue #56 du projet apiselect, rapport annonçant ✅ en toute première
  ligne, mais contenant plus loin, dans sa section « lacunes de tests », des
  puces portant le marqueur ❌ — c'est l'une de ces puces qui a été retenue
  comme verdict, la tentative a été reclassée en échec et une seconde
  exécution complète a été consommée pour rien. Le gabarit de prompt impose
  que le verdict OUVRE la réponse finale (« Réponds avec ce format exact » +
  ✅/❌ en première ligne) : rien ne justifiait de préférer la DERNIÈRE
  occurrence, choix qui s'appuyait sur une analogie avec le garde-fou #581
  (présence d'un marqueur n'importe où dans le texte) que l'étude de l'issue
  #762 a invalidée — #581 ne porte que sur la PRÉSENCE d'un marqueur, jamais
  sur sa position ni sa valeur. Correctif d'attente : la convention de
  verdict encadrée (étudiée par #762) le rendra inutile à terme — une issue
  dédiée suivra et attendra la clôture de celle-ci (même fichier touché).
- **Point 2 — nouveau garde-fou : arrêt immédiat d'une issue dont la
  tentative échoue anormalement vite.** Incident déclencheur : issue #762
  elle-même, trois tentatives échouées en moins de dix secondes chacune
  parce que l'agent n'était pas authentifié sur la machine — le pré-vol
  (`verifier_preflight_token`) n'a rien détecté (ses formulations ne
  correspondaient plus au message d'erreur alors émis par le CLI), les
  trois tentatives ont été consommées pour rien, et l'issue a fini abandonnée
  avec un message technique illisible ne mentionnant jamais
  l'authentification. Nouveau seuil `SEUIL_DUREE_TENTATIVE_ANORMALE_S = 10`
  (secondes) : constaté directement sur l'énoncé de l'incident (« moins de
  dix secondes ») et confirmé en conditions réelles (sonde manuelle,
  authentification absente sur cette même machine : échec en ~0,8s — voir
  point 3 ci-dessous). Une SEULE tentative sous ce seuil suffit à arrêter
  (pas deux) : aucun échec légitime connu ne descend sous dix secondes — le
  moindre aller-retour LLM réel (nécessaire pour produire le rapport de
  clôture imposé par le gabarit) prend largement plus longtemps, les
  dépassements de délai sont par construction aussi longs que `timeout`
  (toujours ≥ plusieurs minutes en pratique), et les deux autres causes
  rapides connues (binaire introuvable, authentification absente) relèvent
  déjà, elles aussi, d'un problème d'environnement justifiant le même
  traitement. `_duree_tentative_anormale` (nouvelle fonction) ne s'applique
  qu'aux échecs constatés au niveau du PROCESS (`stderr_brut` non `None`,
  même restriction que `_detecter_erreur_bloquante`/#761) — jamais à un
  rapport rédigé par l'agent et reclassé en échec après coup par les
  garde-fous #581/#757, qui implique lui un aller-retour LLM réel. Réutilise
  tel quel le mécanisme d'arrêt immédiat de l'issue #760
  (`_gerer_tentative_anormalement_rapide`, sur le modèle de
  `_gerer_erreur_bloquante`) : arrêt dès la première tentative concernée,
  sans consommer les tentatives restantes, label `needs-human` posé, cause
  explicite dans le commentaire de clôture, qui invite cette fois
  explicitement à vérifier que l'agent est authentifié et que son binaire
  fonctionne plutôt que de se contenter de recopier l'erreur technique brute.
- **Point 3 — formulations du pré-vol mises à jour.** `SIGNATURES_TOKEN_EXPIRE`
  gagne `"no messages returned"` : message RÉELLEMENT constaté (sonde
  manuelle reproduisant l'incident #762 — `claude --print` + stdin vide,
  sans aucune authentification sur la machine, CLI 2.1.199) — "Error: No
  messages returned from query", qui ne mentionne l'authentification à aucun
  mot-clé évident, d'où son absence des variantes précédentes. Cette liste
  reste un best-effort qui VIEILLIT avec les versions du CLI (déjà constaté
  deux fois : #762 puis cette mise à jour) — c'est le nouveau garde-fou de
  durée anormale (point 2) qui sert de filet, lui totalement indépendant de
  tout vocabulaire.
- Mode simulation (dry-run) inchangé : aucune exécution réelle n'y a lieu
  (`lancer_claude` y retourne toujours `succes=True`), donc aucune durée à
  juger — `_duree_tentative_anormale` n'est jamais atteinte dans ce chemin.

- **`watcher.py`** : `_verdict_final` retient `occurrences[0]` au lieu de
  `occurrences[-1]` (commentaire attenant mis à jour, référence à #581
  retirée). Nouvelle constante `SEUIL_DUREE_TENTATIVE_ANORMALE_S` et nouvelle
  fonction `_duree_tentative_anormale(stderr_brut, sortie, duree_tentative)`.
  `_executer_une_tentative` mesure désormais la durée du seul appel à
  `lancer_claude` et retourne un 4e élément, `duree_tentative` (signature :
  `tuple[bool, str, str | None, float]` — seul appelant, dans
  `_traiter_issue_synchrone`, mis à jour). Nouvelle fonction
  `_gerer_tentative_anormalement_rapide`, appelée dans la boucle de
  tentatives juste après la vérification d'erreur bloquante existante
  (même priorité, avant la trace de timeout et l'abandon normal).
  `SIGNATURES_TOKEN_EXPIRE` : ajout de `"no messages returned"`.
- **`tests/test_premier_marqueur_et_arret_rapide_763.py`** (nouveau, 3
  scénarios) : premier marqueur retenu malgré une puce ❌ plus loin dans le
  texte (scénario apiselect #56 reconstitué, + contrôle inverse échec en
  tête) ; un vrai échec de process quasi instantané déclenche l'arrêt
  immédiat dès la première tentative (label `needs-human`, message
  invitant à vérifier authentification/binaire, tentatives restantes NON
  consommées) ; non-régression — un rapport d'agent reclassé par #581 et
  produit quasi instantanément par le faux exécutable de test continue de
  consommer normalement ses tentatives (pas de faux positif du nouveau
  garde-fou de durée).
