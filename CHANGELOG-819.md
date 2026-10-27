## Issue #819 — Onglet En attente : réordonner les issues à la main

L'onglet « En attente » (issue #713, interface #714) listait les éléments de
`issues_inbox/en_attente/` du plus ancien au plus récent, d'après la date de
modification du fichier — aucun moyen de choisir un autre ordre.

Chaque ligne porte désormais deux boutons **↑/↓** (`POST
/issues-attente/deplacer`, JSON `{id, sens: "haut"|"bas"}`) : échange avec
le voisin direct dans l'ordre affiché ; la première ligne n'a pas de ↑
actif, la dernière pas de ↓ (`decisionDeplacementAttente`, `attente.js`).

L'ordre choisi est persisté dans `issues_inbox/en_attente/.ordre/ordre.json`
— **jamais** un fichier directement dans `en_attente/` : un sous-dossier
n'est jamais un `chemin.is_file()`, donc `_nb_en_attente()`/la liste
l'ignorent déjà naturellement (même principe que `rejected/.motifs`, issue
#631) — rien n'est donc jamais compté, affiché, lancé ou supprimé comme une
issue en attente à cause de ce mécanisme, et un déplacement ne touche
jamais au contenu d'un fichier d'`en_attente/`.

`app/issues_inbox.py::fusionner_ordre_attente` (logique pure) recalcule
l'ordre affiché à chaque lecture (`GET /issues-attente` et `POST
.../deplacer`) à partir de ce fichier + de l'état réel du dossier : un
identifiant mémorisé disparu du dossier (élément lancé ou supprimé) est
abandonné sans laisser de trace ; un fichier présent mais absent de l'ordre
mémorisé (dépôt manuel, ancienne installation) est ajouté en fin de liste,
du plus ancien au plus récent — repli identique au comportement #713 pour
tout élément jamais encore déplacé. Le résultat fusionné est réécrit sur
disque à chaque lecture (auto-guérison), ce qui garantit la survie de
l'ordre au rechargement de la page ET au redémarrage de `new_issue.py`.

Tests ajoutés : `tests/test_ordre_attente_819.py` (fusion pure + routes
Flask `GET /issues-attente`/`POST /issues-attente/deplacer`) et
`static/js/tests/attente.test.js` (`decisionDeplacementAttente`).
Documentation technique mise à jour dans `ARCHITECTURE.md` (§6.5) —
`BRIDGE_AGENT_DOC.md` volontairement non touché (détail d'interface).
