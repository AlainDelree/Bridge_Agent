# CHANGELOG-663 — à fusionner dans CHANGELOG.md

## 27 septembre 2026 — issue #663

`static/js/resultats.js` (`reconcilierRejetes()`) : une ligne rouge « fichier refusé » reçue en direct (SSE, `source: 'sse'`) se referme désormais toute seule, sans recharger la page, dès que le fichier correspondant quitte `issues_inbox/rejected/` — même traitement que les lignes `source: 'etat'` (reconstruites au rechargement), sans distinction de source pour la purge. Avant cette issue, une ligne SSE restait affichée indéfiniment jusqu'au rechargement complet de la page, même après nettoyage manuel du fichier (constaté en usage réel par Alain — un geste d'entretien répétitif).

Pas de course critique sur un fichier tout juste refusé : `scripts/watcher_issues_inbox.py` déplace toujours le fichier vers `rejected/` AVANT d'émettre l'événement SSE `fichier_refuse` (`_rejeter`), donc au prochain cycle de polling `/issues-inbox/etat` (7 s, `POLL_INBOX_MS`) le fichier y est déjà listé — la ligne SSE fraîchement affichée y survit intacte, aucun délai de grâce supplémentaire à ajouter.

Point d'attention non traité (hors périmètre de cette issue, marquée « court ») : dans un lot multi-blocs partiellement réussi (`_traiter_lot`, `nb_ok > 0`), le fichier original est directement supprimé (`unlink()`) — jamais déplacé vers `rejected/` — donc la ligne SSE d'un bloc refusé au sein de ce lot ne figurera JAMAIS dans `rejetes` et disparaîtra désormais dès le premier cycle de polling suivant son apparition (≤ 7 s), au lieu de persister jusqu'au rechargement comme avant. Comportement inchangé pour un fichier mono-bloc ou un lot entièrement refusé (déplacés vers `rejected/` avant notification SSE).

Tests (`static/js/tests/resultats_fichiers.test.js`) : nouveaux cas couvrant explicitement la purge d'une ligne SSE dont le fichier a quitté `rejetes`, sa conservation tant qu'il y reste, et la non-purge d'une ligne « reçu » (statut `recu`, jamais concernée). `VERIFICATIONS_MANUELLES.md` mis à jour (fin de la mention « persistance jusqu'au rechargement » pour les lignes SSE, nouvelle case de vérification manuelle dédiée).
