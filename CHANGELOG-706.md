## #706 — Issue H (suite) : `valider_repo_cible` sous Windows, test #584, lanceur verbeux sur échec

Suite à la validation réelle du lanceur de tests (#704) sur CCW le
03/10/2026 : 35/37 fichiers réussis, 2 échecs identifiés et corrigés ici.

- `watcher.py::valider_repo_cible` (~ligne 1694) : la vérification de
  propriétaire (`resolu.stat().st_uid != os.getuid()`) plantait sous Windows
  avec `AttributeError: module 'os' has no attribute 'getuid'`, faisant
  échouer tout `REPO_CIBLE` pourtant valide (`tests/test_champ_relance_516.py`,
  scénario « REPO_CIBLE valide accepté avec PERIMETRE_DYNAMIQUE »). Même
  garde que `valider_sous_dossier` : sous `os.name == "nt"`, la vérification
  de propriétaire est ignorée (les trois autres contrôles — absolu,
  canonique, dossier existant — restent appliqués). Comportement Linux
  strictement inchangé.
- `tests/test_verrou_refus_precoce_584.py` : les scénarios
  `scenario_refus_precoce_libere_verrou` et
  `scenario_echec_rapide_sans_travail_libere_verrou` fabriquent de faux
  `gh`/`claude` en scripts bash, non exécutables sous Windows — les vrais
  outils auraient été appelés contre un dépôt fictif. Ajout d'un garde
  `os.name == "nt"` en tête de ces deux scénarios (même style de message
  « ignoré : ... non applicable sous Windows » que `scenario_pid_mort_*`
  dans ce même fichier). Les deux autres scénarios (sonde PID, sans faux
  exécutable) restent inchangés et continuent de s'exécuter sous Windows.
- `tests/lancer_tous_les_tests.py` : pour un fichier en échec, affiche
  désormais les lignes portant le marqueur `✗` ou le résumé
  « scénario(s) en échec », ou à défaut les 15 dernières lignes de sa
  sortie — au lieu de la seule dernière ligne non vide, qui pouvait n'être
  que du bruit normal émis par un scénario qui passe (cas réel : 516
  affichait « configs/bridge_agent.conf illisible », pas la vraie cause).
  Les fichiers réussis gardent une seule ligne de résumé.

Validé sur Linux (37/37, suite complète + fichiers ciblés). CCL ne peut pas
exécuter Windows : validation réelle à faire à la main sur CCW.
