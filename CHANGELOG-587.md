## 22 septembre 2026 — issue #587

Flux de suppression de projet — côté CCL/local, symétrique à la création
(diagnostic #580). Décommissionner un projet exigeait jusqu'ici une
chirurgie manuelle sur au moins 8 cibles, avec un risque réel d'oubli ; cette
issue couvre volontairement les 4 cibles côté CCL/local, le dépôt GitHub et
le côté CCW faisant l'objet d'issues séparées.

- `supprimer_projet.py` (nouveau) : orchestrateur `supprimer_projet(nom,
  dry_run)` symétrique à `nouveau_projet.creer_projet()`, qui démonte dans un
  ordre sûr — répertoire de travail (contenu + dépôt git local, une seule
  opération de disque puisque `.git` y vit) puis `configs/<nom>.conf` puis
  régénération immédiate de §2/§7 de `BRIDGE_AGENT_DOC.md`
  (`regenerer_tableaux_projets.regenerer()`) — en s'arrêtant dès qu'une étape
  échoue plutôt que de continuer aveuglément. Ordre volontairement inverse de
  la création : le `.conf` n'est retiré qu'une fois le répertoire de travail
  effectivement supprimé, pour ne jamais laisser un répertoire orphelin sans
  trace de son existence en cas d'échec. Mode à blanc
  (`previsualiser_suppression`/`--dry-run`) : aucune écriture disque ni sur
  la doc. CLI interactif avec confirmation par saisie du nom (`--oui` pour
  l'usage scripté).
- `app/supprimer_projet.py` (nouveau) : réutilise ce script sans le
  dupliquer. `GET /supprimer-projet/verifier/<nom_projet>` (dry-run, 404 si
  absent) et `POST /supprimer-projet` (suppression réelle), toutes deux
  protégées par `login_requis`. La route POST revérifie indépendamment côté
  serveur que le champ `confirmation` reproduit exactement le nom du
  projet — la checklist côté interface, elle, peut être contournée par un
  appel direct.
- `app/__init__.py` : enregistrement des deux routes.
- `templates/index.html` : zone dangereuse dans l'onglet Configuration
  (bouton « 🗑 Supprimer ce projet… ») et modal de confirmation — aperçu
  chargé automatiquement, 3 cases à cocher (une par cible) + nom du projet
  retapé à l'identique, double garde-fou avant que le bouton de suppression
  définitive ne s'active.
- `static/js/app.js` : `ouvrirSupprimerProjet`/`fermerSupprimerProjet`,
  `spChargerApercu` (peuple l'aperçu depuis la route GET), `spMajBoutonEtat`
  (active le bouton seulement si les 3 cases + le nom retapé sont corrects),
  `soumettreSupprimerProjet` (appelle la route POST, affiche le compte-rendu
  par étape), `retirerProjetDuSelecteur` (symétrique de
  `ajouterProjetAuSelecteur`, retire l'option du sélecteur global au succès).
- `regenerer_tableaux_projets.py` : docstring mise à jour — elle admettait
  explicitement l'absence de flux de suppression automatisé (citée dans le
  diagnostic #580) ; documente désormais que `supprimer_projet.py` déclenche
  lui aussi la régénération, au même titre que `nouveau_projet.py`.
- `BRIDGE_AGENT_DOC.md` : nouvelle sous-section « Suppression de projet,
  côté CCL/local (issue #587) », symétrique de celle décrivant déjà la
  création (juste avant), plus la commande CLI dans §13.
- `tests/test_supprimer_projet_587.py` (nouveau) : aperçu (projet absent,
  projet présent — aucune écriture), dry-run (ne touche à rien), succès réel
  (ordre des étapes, `.conf` + répertoire supprimés, doc régénérée une seule
  fois), arrêt propre si la suppression du répertoire échoue (`.conf`
  conservé, doc jamais régénérée), nom vide, et les deux routes Flask
  (dry-run 404, confirmation incorrecte → 400, succès → 200).

Explicitement hors scope (décision actée dans le diagnostic #580) :
suppression du dépôt GitHub et de ses labels (geste manuel volontaire), et
tout le côté CCW (clone Windows, `configs\<nom>-ccw.conf`, service NSSM,
tokens, entrée `$Projets`, ligne `REINSTALLATION_CCW.md` §7).

Vérifié : `py_compile` sur tous les fichiers touchés, `create_app()` démarre
sans erreur et expose bien les deux nouvelles routes, les 9 scénarios de
`tests/test_supprimer_projet_587.py` passent, ainsi que l'intégralité des 16
autres suites de tests existantes (aucune régression). Non vérifié dans ce
worktree (pas d'accès réseau/GitHub authentifié) : test bout en bout réel
sur un projet jetable — demandé en vérification de l'issue, à faire par
Alain avant de considérer le flux entièrement validé.
