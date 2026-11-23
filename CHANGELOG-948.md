## 2026-11-23 — issue #948

Préparation de l'étude #939 (interruption d'UNE SEULE issue, sans toucher
aux autres), volontairement SANS effet visible : dans `lancer_claude`,
l'unique attente bloquante `proc.communicate(timeout=timeout)` sur le
process `claude` est remplacée par une boucle de sondage courte
(`_attendre_fin_claude`, tours d'environ 3s —
`INTERVALLE_SONDAGE_CLAUDE_S`) qui reproduit EXACTEMENT le comportement
observable d'avant : mêmes stdout/stderr/code retour dans tous les cas (fin
normale, échec, dépassement de délai), même message de timeout, même
nettoyage de l'arbre de process via `_nettoyer_arbre_claude`, même nombre de
tentatives qui s'ensuit.

Pendant chaque tour, `proc.wait(timeout=...)` retourne dès que `claude`
termine (jamais retardé jusqu'au tour suivant), et deux threads démons
drainent en continu stdout/stderr pour que `claude` ne se retrouve jamais
bloqué en écriture faute de lecteur, même pour un très gros volume de
sortie — exactement ce que faisait `proc.communicate()` en une seule fois.

Point d'extension ajouté pour l'issue suivante : `_verifier_demande_
interruption(numero)`, appelé à chaque tour de la boucle, ne fait encore
rien (retourne toujours `False`) — prévu pour que #939 y branche la
détection d'une demande d'interruption propre à l'issue, sans retoucher la
structure de `_attendre_fin_claude`.

Chemins non modifiés : mode interactif (session tmux, `mode_tmux=True`,
branche entièrement séparée), verrous, `/interrompre`, durées des délais,
calibration automatique du TIMEOUT, notifications.

Tests : `tests/test_boucle_attente_claude_948.py` — fin normale rapide, fin
normale après plusieurs tours, code retour non nul, dépassement de délai
avec arrêt de l'arbre de process (enfant lancé par le faux `claude` tué),
sortie très volumineuse sur les deux tubes sans blocage, sortie vide, délai
maximal respecté à un tour près, point d'extension appelé à chaque tour
sans effet sur le résultat. Suite complète (`pytest` + scripts `main()`
autonomes des tests qui lancent de vrais sous-process) rejouée sans
régression.

Documentation : `ARCHITECTURE.md` nouvelle sous-section §11.5.
