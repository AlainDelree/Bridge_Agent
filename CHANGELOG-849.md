## 3 novembre 2026 — issue #849

Onglet CCW, section **Finaliser un projet** : contrôle de forme d'un jeton
EN DIRECT, pendant la saisie ou le collage, avant toute écriture sur un
service Windows (issue #849). Sous les champs `GH_TOKEN`,
`CLAUDE_CODE_OAUTH_TOKEN` (« Finaliser un projet ») et le champ de la pose
groupée (« Poser ce jeton Claude sur tous les services CCW »), une seule
fonction paramétrée par le type de jeton (`static/js/ccw.js::controlerFormeJeton`,
repères isolés dans la constante `FORMES_JETONS_CONNUES` — `github_pat_`/93
caractères ou `ghp_`/40 pour GH_TOKEN, `sk-ant-oat01`/108 caractères pour
CLAUDE_CODE_OAUTH_TOKEN) affiche la longueur et le préfixe reconnu, jamais
la valeur. Un espace/retour à la ligne de bord est retiré automatiquement
et signalé ; un espace ou un caractère de contrôle qui subsiste au milieu
du jeton bloque la finalisation ; un préfixe inconnu ou une longueur
inhabituelle donne un simple avertissement, rappelé (longueur + préfixe de
chaque jeton fourni) dans la fenêtre de confirmation « Finaliser… ».
Défense en profondeur côté serveur (`app/ccw.py::ccw_finaliser_projet`,
`_nettoyer_bords_jeton`/`_jeton_a_caractere_bloquant`) : même retrait des
bords puis même refus bloquant en cas d'espace/caractère de contrôle au
milieu, sans jamais recopier le jeton dans la réponse, les journaux ou les
messages d'erreur — le contrôle navigateur pouvant être contourné par un
appel direct à la route. Inchangés : le contrôle de longueur existant
côté PowerShell (§10.1, issue #744, sur un jeton RECONDUIT) et la façon
dont les jetons sont posés sur les services. Documentation : ARCHITECTURE.md
§10.2. Tests : `tests/test_controle_forme_jetons_849.py` (10 scénarios) et
`static/js/tests/ccw.test.js` (10 scénarios ajoutés).
