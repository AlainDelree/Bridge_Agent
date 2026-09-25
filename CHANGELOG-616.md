## 25 septembre 2026 — issue #616

Depuis le passage au PC fixe physique (issue #446, août 2026), le §16 de
`BRIDGE_AGENT_DOC.md` (Agent Windows CCW) accumulait de nombreux blocs
marqués explicitement « obsolète — conservé à titre historique » décrivant
l'ancienne architecture VM VirtualBox (éval 90 jours, `VBoxManage`,
`creer_vm_ccw.py`, `autounattend.xml`, `lancer_provisioning.py`,
`demarrer_ccw.sh`, `eval-expiration.json`, `verifier_expiration_ccw.py`,
partage réseau `\\VBoxSvr\CCW_Share`) : dette documentaire payée en tokens
à chaque conversation Claude Chat chargeant la doc, et source de confusion
entre l'état révolu et l'état courant. Décision actée (issue) : supprimer
ces blocs, pas les extraire vers un fichier historique séparé.

- Tableau des scripts de provisioning (§16) : suppression des 6 lignes
  purement obsolètes (`creer_vm_ccw.py`, `autounattend.xml`,
  `lancer_provisioning.py`, `demarrer_ccw.sh`, `eval-expiration.json`,
  `verifier_expiration_ccw.py`) ; retrait des mentions « (dans la VM… )»
  sur les 6 scripts encore actifs (`mettre_a_jour_tokens_ccw.ps1`,
  `ajouter_projet_ccw.ps1`, `lister_projets_ccw.ps1`,
  `finaliser_projet_ccw_auto.ps1`, `finaliser_projet_ccw.ps1`,
  `surveiller_builds.ps1`) ; `provisionner.ps1` conservé comme référence
  des étapes d'installation logicielle, description nettoyée des mentions
  VM.
- Bloc « Lancer le provisioning (obsolète — via VM) » et son extrait bash
  (`lancer_provisioning.py`) supprimés.
- Sous-section entière **§16.1 Maintenance périodique (renouvellement à
  90 jours)** supprimée (recréation de VM, `eval-expiration.json`,
  `VBoxManage storageattach`, ré-attachement d'ISO) — le renouvellement des
  tokens GitHub/Claude, seule partie encore valide, était déjà documenté
  plus haut dans le §16 (script `mettre_a_jour_tokens_ccw.ps1`). Le renvoi
  `cf. §16.1` restant dans la description du token par projet a été retiré.
  La numérotation des sous-sections n'a pas été renumérotée (le §16 passe
  directement de son intro à 16.2, comme le document passe déjà du §14 au
  §16 sans §15).
- §16.3 : callout « Étape 0 et note safe.directory obsolètes » + bloc bash
  associé supprimés, ainsi que les deux notes historiques (safe.directory,
  staging local) mentionnant l'ancien partage VirtualBox ; reformulation
  mineure de la note « Récupération des artefacts » et de la note
  « staging local » pour retirer les mentions VirtualBox devenues sans
  objet.
- §16.4 (bouton « Interrompre ») : reformulation du callout et du
  paragraphe technique pour retirer les deux mentions `VBoxManage
  guestcontrol` (remplacées par « ancien mécanisme de pilotage à distance
  de la VM » / « à distance »), sans supprimer la documentation du
  fonctionnement actuel du bouton (`app/interruption.py::
  interrompre_windows`, toujours inopérant sur PC physique — pas de
  changement de code dans le cadre de cette tâche, doc uniquement).
- Renvoi orphelin « Specs MVC §15 » (§12) corrigé en « Specs MVC » (le §15
  n'existe plus dans le document).
- Conservé tel quel : l'encart « ⚠️ Changement de plateforme (depuis août
  2026, issue #446) » en tête du §16, qui explique en quelques lignes le
  passage VM → PC fixe — seul contexte minimal encore utile pour comprendre
  d'anciens commits mentionnant une VM.

Vérification : plus aucune mention de VirtualBox/VBoxManage/
`creer_vm_ccw.py`/`autounattend.xml`/`lancer_provisioning.py`/
`demarrer_ccw.sh`/`eval-expiration.json`/`verifier_expiration_ccw.py` dans
le §16 en dehors de l'encart « Changement de plateforme » conservé
volontairement (et d'une brève justification historique déjà concise sur
le compte NSSM `AlainW`, hors périmètre de nettoyage de l'issue). Fences
markdown et séquence des titres `###` du §16 vérifiées cohérentes après
coup. `py_compile` sans objet (fichier `.md`).
