## Issue #814 — Documentation : fiche Actualise du guide de build, démarrage automatique des services, règles de reprise et de numéro imposé

`BUILD_WINDOWS_CCW.md` (89 insertions, 12 suppressions) : la fiche
Actualise devient une vraie fiche (commande exacte, dix étapes, Inno
Setup, artefacts et copie systématique vers `C:\CCW_Share\_derniers_builds\actualise\`,
garde-fou de numéro de build issue #71, archive 31 entrées, tailles de
référence « build 11 », durées, Release à deux fichiers, essais en
`--build 99`, particularité de la mise à jour automatique, remarque
PowerShell `NativeCommandError`), remplaçant l'avertissement qui
interdisait de rédiger une issue de build d'Actualise. La puce « Avant de
déposer l'issue » sur le démarrage du service est corrigée : démarrage
automatique par le formulaire web et par `issues_inbox/` (issues
#709/#711), échec silencieux possible, exceptions (`gh issue create`
direct, `new_issue.py` natif Windows) à démarrer à la main. Dans « Ce que
l'agent ne fait jamais » et le modèle d'issue, la règle d'arrêt
systématique en cas de vérification préalable échouée est remplacée par
la règle de reprise (arrêt seulement si la branche n'est pas celle de
l'issue ou si le commit de départ n'est pas un ancêtre de `HEAD` ;
travail déjà présent à vérifier, pas à refaire) et il est précisé que,
pour une issue de build, le numéro de build est toujours imposé
explicitement, et qu'une reprise relance le script entièrement. « Ce que
fait Alain ensuite » précise que la Release porte toujours deux fichiers
(installeur + archive).

`BRIDGE_AGENT_DOC.md` (11 insertions, 7 suppressions) : §14, la
« contrepartie opérationnelle » est corrigée dans le même sens (le
démarrage automatique existe depuis les issues #709/#711, avec ses
limites) ; dernière ligne du document mise à jour (25 octobre 2026).

`ARCHITECTURE.md` (7 insertions, 5 suppressions) : §2.6, le décompte
« trois points » qui appellent `etat_configs_legitimes.enregistrer()`
devient quatre, en nommant le quatrième — `app/projet_ccw.py`
(`_ecrire_rep_travail_ccw`), ajouté par l'issue #804.

Aucun autre fichier touché (`REINSTALLATION_CCW.md`, scripts de
provisioning, fiches Rummikub/Scrabble laissés en l'état, conformément à
la consigne). Aucun point marqué « à confirmer » n'a été nécessaire : tous
les constats fournis dans l'issue ont pu être recopiés ou recoupés avec
le contenu existant des trois fichiers. Suite de tests Python complète
(`tests/lancer_tous_les_tests.py`) : 82 fichiers exécutés, 82 réussis,
0 échec.
