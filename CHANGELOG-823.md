## Issue #823 — Onglet En attente : bouton « copier » à côté du titre de chaque issue

Pour relancer/corriger une issue déjà mise de côté (`issues_inbox/en_attente/`,
champ `ATTENTE`, #713), Alain devait sélectionner le titre à la main dans
l'onglet « En attente » pour le recopier dans le Chat de projet (ex. relance
#820). Chaque ligne pose désormais un petit bouton 📋 juste après le titre
(`static/js/attente.js::construireLigneDOM`, `data-action="attente-copier-titre"`),
qui copie le titre EXACT du fichier dans le presse-papier.

Aucun nouveau mécanisme de copie : le bouton réutilise le moteur déjà en place
pour les copies de l'onglet Résultats. Deux fonctions de `resultats_coches.js`
sont désormais **exportées** pour cet usage :

- `copierTexteConnu(texte, feedback)` — même choix de mode que `lancerCopie`
  (`modeCopie`/`decisionModeCopie`, #636) : ClipboardItem chaîné
  (`chaineCopieModerne`) en contexte sécurisé, `execCommand('copy')` en repli
  HTTP non-localhost (`--lan`, cas fréquent signalé par l'issue) — mais SANS
  la couche fetch/cache (`textesPrepares`/`precharger`), inutile ici puisque
  le titre est déjà connu avant le clic (lu dans le fichier, aucune requête
  serveur). `succes()` n'est appelé que si l'écriture a réellement eu lieu —
  jamais de faux succès.
- `signalerEchecCopie(texte)` — même filet qu'ailleurs (#782) : un échec de
  copie joint le texte dans une zone sélectionnable du toast d'erreur, pour
  un Ctrl+C manuel, plutôt que de le perdre.

Logique pure ajoutée à `attente.js` : `texteACopierAttente(item)` renvoie le
titre EXACT tel qu'écrit dans le fichier, jamais le repli `(sans titre)` de
`descriptionLigneAttente` — `null` si l'élément n'a pas de titre, et dans ce
cas `construireLigneDOM` ne pose AUCUN bouton (pas seulement masqué/désactivé).

Le titre est transmis au clic via `element.dataset.titreCopie` (propriété DOM,
jamais concaténé dans le `innerHTML` de la ligne — même précaution que le
reste de la ligne, posé en `textContent`). Le gestionnaire délégué
(`dom.surAction`) appelle `evenement.stopPropagation()` pour qu'un clic sur
ce bouton ne puisse jamais être réinterprété comme Lancer/Supprimer/↑/↓.

Tests : `static/js/tests/attente.test.js` (`texteACopierAttente` — titre
repris tel quel, absence de bouton si titre vide/absent/blanc, item absent
sans exception, espaces internes préservés). Documentation : `ARCHITECTURE.md`
(nouvelle note dédiée + mentions dans les tableaux CSS/modules JS) —
`BRIDGE_AGENT_DOC.md` non touché, hors périmètre de cette issue.
