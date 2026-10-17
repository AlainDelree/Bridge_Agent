# CHANGELOG-765 — à fusionner dans CHANGELOG.md

## 17 octobre 2026 — issue #765

Garde-fou dans `tests/lancer_tous_les_tests.py` : refus de lancer la suite
hors de l'environnement virtuel du projet, avec un message explicite.

- **Défaut corrigé.** Lancé hors du `venv` du projet, le lanceur de tests
  faisait échouer d'un coup une quarantaine de fichiers (ceux qui dépendent
  de l'interface web, via `flask`) sans qu'aucune cause ne soit indiquée —
  pris deux fois le même jour pour une régression grave après une fusion,
  alors qu'il fallait ouvrir un test au hasard pour découvrir une simple
  erreur d'import.
- **Détection retenue : disponibilité réelle des dépendances, pas un
  chemin `venv/` en dur.** Nouvelle fonction `dependances_manquantes()`
  qui teste par `importlib.util.find_spec` l'importabilité de `flask`,
  `werkzeug` (`requirements.txt`, interface web) et `pytest`
  (`requirements-dev.txt`) dans l'interpréteur courant (`sys.executable`).
  Choix motivé par le point de conception de l'issue : comparer
  l'interpréteur courant à celui d'un dossier `venv` fixe aurait produit un
  faux positif pour quiconque travaille dans un environnement équivalent
  installé ailleurs — c'est précisément le cas du provisioning Windows
  (`provisionner_new_issue_local.ps1`), qui installe directement dans
  l'interpréteur système sans `venv` du tout.
- **Message et code de retour.** `main()` vérifie ces dépendances AVANT de
  lister le moindre fichier `test_*.py` : si une ou plusieurs manquent, un
  message nommant les paquets absents, la cause probable (environnement
  virtuel non activé) et la commande d'activation (Linux/macOS et Windows),
  plus le repli `pip install -r requirements.txt -r requirements-dev.txt`
  pour un environnement sans `venv`, est affiché sur stderr — et le lanceur
  s'arrête avec le code `2` (`CODE_ENVIRONNEMENT_INVALIDE`), distinct de
  `0` (succès) et `1` (échec de test), pour qu'un script appelant ne
  confonde pas ce refus avec une régression.
- **Documentation.** `provisioning/windows/NEW_ISSUE_LOCAL_WINDOWS.md` §3
  (« Vérifier l'installation ») mentionne désormais `requirements.txt` en
  plus de `requirements-dev.txt`, et les trois codes de retour possibles.
- **Tests.** Nouveau `tests/test_garde_fou_venv_765.py` (3 scénarios) :
  détection sans faux positif (paquet de la stdlib toujours présent, nom de
  paquet inexistant systématiquement signalé) ; dépendance requise manquante
  (dépendances et dossier de tests monkeypatchés) → `main()` retourne le
  code dédié `2` AVANT tout appel à `glob()` (aucun fichier exécuté), avec
  un message citant le paquet absent et la commande d'activation ;
  non-régression — dans l'environnement réel de ce test (donc pourvu des
  dépendances), le garde-fou ne signale rien, confirmant qu'il ne gêne pas
  une exécution légitime depuis un environnement correctement configuré.
  Suite complète rejouée dans le `venv` du dépôt : 68 fichiers, tous
  réussis ; rejouée avec l'interpréteur système (hors `venv`) : refus
  immédiat, code `2`, message attendu, aucun fichier exécuté.
