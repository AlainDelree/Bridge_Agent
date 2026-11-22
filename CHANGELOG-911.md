# Issue #911 — réparer les 11 erreurs de tests de test_signature_attente_825.py

- Cause : le fichier n'avait jamais été écrit pour pytest — ses 11
  fonctions `test_*` prenaient un paramètre `tmp_dir_factory`, nom d'une
  fonction locale définie seulement dans son propre `main()` (exécution
  directe `python3 tests/...py`). Pytest, qui collecte toute fonction
  `test_*` d'un fichier qu'il importe, interprète ce paramètre comme une
  demande de fixture ; comme aucune fixture `tmp_dir_factory` n'existe
  (le nom natif est `tmp_path_factory`, une fixture-objet avec `.mktemp()`,
  pas un simple rappel), les 11 tests échouaient en erreur de collecte.
  L'hypothèse de l'issue (faute de frappe `tmp_path_factory`) était
  incomplète : renommer seul le paramètre sans fournir la fixture, ou
  utiliser directement `tmp_path_factory`, ne suffit pas — il faut une
  fixture locale au fichier qui l'enveloppe.
- Correction (fichier de tests seulement) : ajout d'une fixture
  `@pytest.fixture def _tmp_dir_factory(tmp_path_factory)` (même motif déjà
  utilisé par `test_decoupage_lot_en_attente_855.py`,
  `test_instance_unique_et_reclamation_881.py`, `test_prise_de_relais_883.py`),
  et renommage du paramètre `tmp_dir_factory` → `_tmp_dir_factory` dans les
  11 fonctions de test. L'exécution directe (`main()`, sa propre fonction
  locale homonyme) reste inchangée et fonctionne toujours.
- Pas de défaut dans le code applicatif : uniquement un défaut du fichier
  de tests lui-même.
- Suite complète : 721 passés / 0 échec / 11 erreurs avant → 732 passés /
  0 échec / 0 erreur après.
