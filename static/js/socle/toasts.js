// toasts.js — canal unique de notification non bloquant (issue #625, étape 1 ;
// journal consultable + pause au survol + erreurs persistantes, issue #730).
//
// RESPONSABILITÉ
//   Une seule façon de parler à l'utilisateur :
//   - toasts.info / succes : message éphémère qui s'efface tout seul après
//     DUREE_DEFAUT_MS, sauf si la souris est dessus (pause au survol, voir
//     mouseenter/mouseleave dans `afficher`).
//   - toasts.erreur / avertissement : restent affichés jusqu'à une fermeture
//     EXPLICITE (bouton « × » visible) — jamais de disparition automatique
//     (issue #730, voir `dureeAffichage`), SAUF si l'appelant fournit
//     explicitement une durée via `options.duree` (issue #807 : messages de
//     panne de connexion répétitifs, qui n'ont pas besoin d'une action de
//     l'utilisateur et sont déjà consultables dans le panneau « Messages »).
//   - toasts.confirmer(...) : LA seule modale, réservée aux confirmations
//     d'actions destructives (remplaçant de confirm(...)). Renvoie une Promise
//     qui se résout à true (confirmé) ou false (annulé).
//   JAMAIS de boîte à fermer avec « OK » pour info/succes/erreur/avertissement
//   (fini les alert()) — ce sont les remplaçants de alert(...) et
//   afficherToast(...).
//   - toasts.erreur(texte, comptabilise, {texteSecours}) (issue #782) : un
//     texte qu'une action a échoué à produire/écrire ailleurs (ex. presse-
//     papier refusé) peut être joint — affiché dans une zone <textarea>
//     sélectionnable (pré-sélectionnée) plutôt que simplement perdu. Ces
//     toasts ne sont JAMAIS fusionnés par l'anti-empilement (sinon le texte
//     d'un appel précédent serait effacé par le suivant) : chaque occurrence
//     reste un toast séparé.
//   - toasts.erreur/avertissement(texte, comptabilise, {duree, cle}) (issue
//     #807) : deux options facultatives, SANS EFFET par défaut.
//     * `duree` (ms) : impose une disparition automatique (la pause au
//       survol reste active) au lieu de la persistance par défaut — réservé
//       aux messages qui ne demandent aucune action (ex. pannes de connexion
//       répétitives), jamais aux erreurs à texteSecours.
//     * `cle` : remplace la clé anti-empilement calculée à partir du texte
//       (type + texte exact, voir `cleToast`) — utile quand le texte change à
//       chaque occurrence (ex. liste de projets en échec) et ne se fusionne
//       donc jamais naturellement. Un nouveau message avec la même `cle`
//       REMPLACE le contenu du toast déjà affiché (pas de compteur « ×N »,
//       contrairement à la fusion par défaut) et relance son compte à rebours.
//   - toasts.erreur/avertissement(texte, comptabilise, {detailTechnique}) (issue
//     #824) : ligne de détail technique discrète, affichée sous le message
//     principal (jamais le contenu d'un texte, voir l'appelant), écrite aussi
//     dans le panneau « Messages » (journal) sous l'entrée correspondante —
//     ne change ni le message principal ni `texteSecours`. Comme `texteSecours`,
//     rend la clé anti-empilement unique (jamais fusionnée/effacée).
//
//   Tous les messages affichés (quel que soit l'appelant) sont en outre
//   journalisés (voir `journaliser`) dans un historique borné
//   (JOURNAL_TAILLE_MAX entrées), consultable via une icône discrète posée
//   dans l'en-tête (`#toasts-journal-bouton`, voir templates/fragments/
//   entete.html) qu'ouvre/ferme `initJournalMessages()` — appelée une fois par
//   socle/index.js. Une pastille (`#toasts-journal-badge`) affiche le nombre de
//   messages non consultés depuis la dernière ouverture du panneau. Le journal
//   est persisté en sessionStorage (survit à un rechargement dans le MÊME
//   onglet ; pas au-delà — un nouvel onglet repart vide), jamais en
//   localStorage.
//
//   RÈGLE DE COMPTABILISATION DE LA PASTILLE (issue #747) : un message qui ne
//   fait que CONFIRMER une action que l'utilisateur vient lui-même de
//   déclencher et de voir à l'écran (ex. « Issue lancée », « Rapport copié
//   dans le presse-papier ») n'a pas sa place dans le COMPTEUR de la pastille
//   — l'utilisateur sait déjà. Tout le reste (ce qui peut arriver sans geste
//   de l'utilisateur, ou qui signale un problème) EST comptabilisé. En
//   pratique : `toasts.succes`/`toasts.info` acceptent un dernier argument
//   `comptabilise` (true par défaut) ; `toasts.erreur`/`toasts.avertissement`
//   restent TOUJOURS comptabilisés, quelle que soit la valeur passée. Un
//   toast non comptabilisé garde la même apparence, la même durée, la même
//   fermeture, et entre dans le journal comme les autres — seule la pastille
//   ne l'incrémente pas (voir `estComptabilise`, `majNonLusApresAjout`).
//
// CE QU'IL EXPOSE
//   export const toasts = { info, succes, erreur, avertissement, confirmer }
//   + initJournalMessages() et quelques fonctions PURES testables sans DOM
//   (dureeAffichage, ajouterEntreeJournal, majNonLusApresAjout,
//   calculerDelaiRestant, formaterHeureJournal — voir
//   static/js/tests/toasts.test.js).
//
// AUTONOMIE VISUELLE
//   Les styles sont injectés une seule fois, à la première utilisation, sous des
//   classes préfixées `socle-` : aucune dépendance à style.css, et rien ne
//   s'affiche tant qu'une fonction n'est pas appelée (le socle est inerte à
//   l'étape 1). L'accès au DOM est paresseux → l'import reste sûr sous Node.

const DUREE_DEFAUT_MS = 4000;
const JOURNAL_TAILLE_MAX = 50;
const CLE_SESSION_JOURNAL = 'bridge_toasts_journal';
// Durée d'affichage par type — null = jamais de fermeture automatique
// (erreur/avertissement, issue #730) : seul le bouton « × » ferme.
const DUREES_PAR_TYPE = { info: DUREE_DEFAUT_MS, succes: DUREE_DEFAUT_MS, erreur: null, avertissement: null };
let stylesInjectes = false;

// Anti-empilement (issue #635) : une rafale de toasts IDENTIQUES (même type
// + même texte — ex. un événement /stream best-effort reçu en boucle pour un
// même projet/numéro) ne doit pas empiler un nouveau toast à chaque fois.
// Le toast déjà affiché est simplement réutilisé (compteur « ×N », minuteur
// de disparition relancé) au lieu d'en créer un second à l'identique.
const toastsActifs = new Map(); // "type texte" → { element, compteur, minuteur }

function doc() {
  if (typeof document === 'undefined') return null;
  return document;
}

// ─── Fonctions PURES (issue #730) — testables sans DOM, voir tests/toasts.test.js ──

/** Durée d'affichage (ms) d'un type de message, ou null si jamais de fermeture
 * automatique (erreur/avertissement — restent jusqu'à une fermeture explicite). */
export function dureeAffichage(type) {
  return Object.prototype.hasOwnProperty.call(DUREES_PAR_TYPE, type)
    ? DUREES_PAR_TYPE[type] : DUREE_DEFAUT_MS;
}

/** Durée d'affichage EFFECTIVE (ms), compte tenu d'une éventuelle durée
 * explicite fournie par l'appelant (`options.duree`, issue #807) — celle-ci
 * prime alors sur `dureeAffichage(type)`, y compris pour imposer une
 * disparition automatique à une erreur/avertissement normalement persistant.
 * Sans `dureeDemandee` (undefined/non numérique), comportement inchangé. */
export function dureeEffective(type, dureeDemandee) {
  return typeof dureeDemandee === 'number' ? dureeDemandee : dureeAffichage(type);
}

/** Contenu affiché/compteur après un nouvel appel `afficher` sur un toast déjà
 * actif (issue #635 par défaut, #807 pour le remplacement) :
 * - fusion par défaut (`remplacer` faux) : compteur incrémenté, texte suffixé
 *   « (×N) » — comportement d'avant #807, inchangé.
 * - remplacement (`remplacer` vrai, `options.cle` fourni par l'appelant) :
 *   le texte du toast actif est REMPLACÉ par le nouveau, sans compteur — le
 *   texte change à chaque occurrence (ex. liste de projets en échec), un
 *   compteur n'aurait ici aucun sens. */
export function contenuRemplacement(texteNouveau, compteurActuel, remplacer) {
  return remplacer
    ? { texte: texteNouveau, compteur: compteurActuel }
    : { texte: texteNouveau + ' (×' + (compteurActuel + 1) + ')', compteur: compteurActuel + 1 };
}

/** Ajoute `entree` en fin de `journal`, en retirant les plus anciennes au-delà
 * de `tailleMax` (FIFO). Pure — ne modifie pas le tableau reçu. */
export function ajouterEntreeJournal(journal, entree, tailleMax = JOURNAL_TAILLE_MAX) {
  const suite = [...journal, entree];
  return suite.length > tailleMax ? suite.slice(suite.length - tailleMax) : suite;
}

/** Nombre de messages non consultés après l'ajout d'un nouveau message :
 * remis à zéro si le panneau du journal est actuellement ouvert (l'utilisateur
 * le voit tout de suite), sinon incrémenté — sauf si `comptabilise` est faux
 * (message de confirmation d'une action triviale, issue #747), auquel cas le
 * compteur n'est pas touché. Par défaut `true` (comportement d'avant #747,
 * et lecture d'une entrée de journal ancienne sans cette information). */
export function majNonLusApresAjout(nombreActuel, panneauOuvert, comptabilise = true) {
  if (panneauOuvert) return 0;
  return comptabilise ? nombreActuel + 1 : nombreActuel;
}

/** Un message d'erreur ou d'avertissement est TOUJOURS comptabilisé dans la
 * pastille, quelle que soit l'option demandée par l'appelant (issue #747) —
 * elle est ignorée pour ces deux types. Pour info/succes, l'option demandée
 * s'applique telle quelle. */
export function estComptabilise(type, comptabiliseDemande = true) {
  return (type === 'erreur' || type === 'avertissement') ? true : comptabiliseDemande;
}

/** Lit le statut de comptabilisation d'une entrée du journal — une entrée
 * ancienne (session antérieure à l'issue #747) n'a pas ce champ : elle est
 * alors lue comme comptabilisée, par compatibilité. */
export function entreeComptabilisee(entree) {
  return entree.comptabilise !== false;
}

/** Temps restant (ms, jamais négatif) avant fermeture automatique, compte tenu
 * du temps déjà écoulé dans la phase active en cours (`maintenantMs - debutMs`).
 * Appelée à la mise en pause (survol) pour geler le compte à rebours — à la
 * reprise, un nouveau `setTimeout` est reprogrammé avec cette valeur. */
export function calculerDelaiRestant(dureeRestanteMs, debutMs, maintenantMs) {
  return Math.max(0, dureeRestanteMs - (maintenantMs - debutMs));
}

/** Horodatage HH:MM:SS, zéro-rembourré (affichage dans le journal). */
export function formaterHeureJournal(date) {
  const deuxChiffres = (n) => String(n).padStart(2, '0');
  return `${deuxChiffres(date.getHours())}:${deuxChiffres(date.getMinutes())}:${deuxChiffres(date.getSeconds())}`;
}

// ─── État du journal (impur — session du navigateur) ──────────────────────

let journal = [];
let nonLus = 0;
let panneauJournalOuvert = false;
let compteurIdJournal = 0;

function sessionBackend() {
  try {
    return (typeof sessionStorage !== 'undefined') ? sessionStorage : null;
  } catch {
    return null;   // accès sessionStorage peut lever (cookies bloqués)
  }
}

function chargerJournalSession() {
  const s = sessionBackend();
  if (!s) return;
  try {
    const brut = s.getItem(CLE_SESSION_JOURNAL);
    if (!brut) return;
    const donnees = JSON.parse(brut);
    const entrees = Array.isArray(donnees.entrees) ? donnees.entrees : [];
    journal = entrees.map((e) => ({ ...e, comptabilise: entreeComptabilisee(e) }));
    nonLus = Number.isFinite(donnees.nonLus) ? donnees.nonLus : 0;
  } catch { /* session corrompue/vide — on repart d'un journal neuf */ }
}
chargerJournalSession();

function sauvegarderJournalSession() {
  const s = sessionBackend();
  if (!s) return;
  try { s.setItem(CLE_SESSION_JOURNAL, JSON.stringify({ entrees: journal, nonLus })); }
  catch { /* quota / privé */ }
}

function majBadgeJournal() {
  const d = doc();
  if (!d) return;
  const badge = d.querySelector('#toasts-journal-badge');
  if (!badge) return;
  if (nonLus > 0) {
    badge.textContent = nonLus > 99 ? '99+' : String(nonLus);
    badge.hidden = false;
  } else {
    badge.hidden = true;
  }
}

// Consigne `texte`/`type` dans le journal — appelé par `afficher` pour TOUS
// les messages, sans exception ni action requise des appelants existants.
// `comptabilise` (issue #747) : entre dans le journal dans tous les cas,
// mais n'incrémente la pastille que si vrai.
// `detail` (issue #824) : ligne de détail technique facultative (ex. cause
// réelle d'un échec de copie) — consignée à part dans l'entrée pour être
// affichée comme une ligne discrète sous le message principal, sans altérer
// celui-ci (voir rafraichirListeJournal).
function journaliser(texte, type, comptabilise, detail) {
  compteurIdJournal += 1;
  const entree = { id: compteurIdJournal, type, texte, horodatage: Date.now(), comptabilise };
  if (detail) entree.detail = detail;
  journal = ajouterEntreeJournal(journal, entree, JOURNAL_TAILLE_MAX);
  nonLus = majNonLusApresAjout(nonLus, panneauJournalOuvert, comptabilise);
  sauvegarderJournalSession();
  majBadgeJournal();
  if (panneauJournalOuvert) rafraichirListeJournal();
}

function construirePanneauJournal(d) {
  let panneau = d.querySelector('#toasts-journal-panneau');
  if (panneau) return panneau;
  panneau = d.createElement('div');
  panneau.id = 'toasts-journal-panneau';
  panneau.className = 'socle-journal-panneau';
  panneau.hidden = true;
  const entete = d.createElement('div');
  entete.className = 'socle-journal-entete';
  const titre = d.createElement('span');
  titre.textContent = 'Messages';
  const fermer = d.createElement('button');
  fermer.type = 'button';
  fermer.className = 'socle-journal-fermer';
  fermer.setAttribute('aria-label', 'Fermer');
  fermer.textContent = '×';
  fermer.addEventListener('click', () => fermerPanneauJournal());
  entete.appendChild(titre);
  entete.appendChild(fermer);
  const liste = d.createElement('div');
  liste.className = 'socle-journal-liste';
  panneau.appendChild(entete);
  panneau.appendChild(liste);
  d.body.appendChild(panneau);
  return panneau;
}

function rafraichirListeJournal() {
  const d = doc();
  if (!d) return;
  const liste = d.querySelector('#toasts-journal-panneau .socle-journal-liste');
  if (!liste) return;
  liste.textContent = '';
  if (journal.length === 0) {
    const vide = d.createElement('div');
    vide.className = 'socle-journal-vide';
    vide.textContent = 'Aucun message pour l’instant.';
    liste.appendChild(vide);
    return;
  }
  // Plus récent en tête (ordre inverse de l'insertion, chronologique interne).
  for (const entree of journal.slice().reverse()) {
    const ligne = d.createElement('div');
    ligne.className = 'socle-journal-ligne ' + entree.type;
    const corps = d.createElement('div');
    corps.className = 'socle-journal-corps';
    const heure = d.createElement('span');
    heure.className = 'socle-journal-heure';
    heure.textContent = formaterHeureJournal(new Date(entree.horodatage));
    const texte = d.createElement('span');
    texte.className = 'socle-journal-texte';
    texte.textContent = entree.texte;
    corps.appendChild(heure);
    corps.appendChild(texte);
    ligne.appendChild(corps);
    if (entree.detail) {
      const detail = d.createElement('div');
      detail.className = 'socle-journal-detail';
      detail.textContent = entree.detail;
      ligne.appendChild(detail);
    }
    liste.appendChild(ligne);
  }
}

function ouvrirPanneauJournal() {
  const d = doc();
  if (!d) return;
  injecterStyles();
  const panneau = construirePanneauJournal(d);
  rafraichirListeJournal();
  panneau.hidden = false;
  panneauJournalOuvert = true;
  nonLus = majNonLusApresAjout(nonLus, true);
  sauvegarderJournalSession();
  majBadgeJournal();
}

function fermerPanneauJournal() {
  const d = doc();
  if (!d) return;
  const panneau = d.querySelector('#toasts-journal-panneau');
  if (panneau) panneau.hidden = true;
  panneauJournalOuvert = false;
}

function basculerPanneauJournal() {
  const d = doc();
  if (!d) return;
  const panneau = d.querySelector('#toasts-journal-panneau');
  if (panneau && !panneau.hidden) fermerPanneauJournal();
  else ouvrirPanneauJournal();
}

/**
 * Branche l'icône du journal dans l'en-tête (`#toasts-journal-bouton`,
 * `templates/fragments/entete.html`) : clic pour ouvrir/fermer le panneau,
 * clic en dehors pour le refermer. Idempotent (appel unique prévu, depuis
 * socle/index.js). Affiche aussi la pastille restaurée depuis la session.
 */
export function initJournalMessages() {
  const d = doc();
  if (!d) return;
  injecterStyles();
  majBadgeJournal();
  const bouton = d.querySelector('#toasts-journal-bouton');
  if (bouton) {
    bouton.addEventListener('click', (evenement) => {
      evenement.stopPropagation();
      basculerPanneauJournal();
    });
  }
  d.addEventListener('click', (evenement) => {
    const panneau = d.querySelector('#toasts-journal-panneau');
    if (!panneau || panneau.hidden) return;
    if (panneau.contains(evenement.target) || (bouton && bouton.contains(evenement.target))) return;
    fermerPanneauJournal();
  });
}

function injecterStyles() {
  if (stylesInjectes) return;
  const d = doc();
  if (!d) return;
  stylesInjectes = true;
  const style = d.createElement('style');
  style.id = 'socle-toasts-styles';
  style.textContent = `
.socle-toasts{position:fixed;top:16px;left:50%;transform:translateX(-50%);
  z-index:3000;display:flex;flex-direction:column;gap:8px;align-items:center;
  pointer-events:none}
.socle-toast{pointer-events:auto;min-width:220px;max-width:80vw;padding:10px 16px;
  border-radius:8px;font-size:13px;font-weight:500;color:#fff;
  box-shadow:0 4px 16px rgba(0,0,0,.22);opacity:0;transform:translateY(-8px);
  transition:opacity .18s,transform .18s}
.socle-toast.visible{opacity:1;transform:translateY(0)}
.socle-toast.info{background:#334}
.socle-toast.succes{background:#22803a}
.socle-toast.avertissement{background:#8a6d00}
.socle-toast.erreur{background:#a32d2d}
.socle-modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.45);
  z-index:3100;display:flex;justify-content:center;align-items:flex-start;
  padding:70px 16px}
.socle-modal-carte{background:#fff;border-radius:12px;max-width:460px;width:100%;
  padding:22px 24px;box-shadow:0 10px 40px rgba(0,0,0,.28)}
.socle-modal-titre{font-size:15px;font-weight:600;line-height:1.4;margin-bottom:12px}
.socle-modal-message{font-size:13px;line-height:1.5;margin-bottom:18px;color:#333;
  white-space:pre-wrap}
.socle-modal-boutons{display:flex;justify-content:flex-end;gap:10px}
.socle-modal-boutons button{padding:7px 16px;border:1px solid #ccc;border-radius:6px;
  font-size:13px;cursor:pointer;background:#fff;color:#1a1a18}
.socle-modal-boutons button.danger{background:#a32d2d;color:#fff;border-color:#a32d2d}
.socle-toast-contenu{display:flex;align-items:center;gap:10px}
.socle-toast-secours{display:block;box-sizing:border-box;width:100%;margin-top:8px;
  max-height:160px;font-family:monospace;font-size:11px;line-height:1.4;
  padding:6px 8px;border:none;border-radius:6px;resize:vertical;
  color:#1a1a18;background:#fff}
.socle-toast-detail{display:block;margin-top:6px;font-size:10px;line-height:1.35;
  color:rgba(255,255,255,.75);word-break:break-word}
.socle-toast-fermer{pointer-events:auto;flex:0 0 auto;background:none;border:none;
  color:#fff;opacity:.8;cursor:pointer;font-size:15px;line-height:1;padding:0}
.socle-toast-fermer:hover{opacity:1}
.toasts-journal-bouton{position:relative;background:none;border:none;cursor:pointer;
  font-size:16px;line-height:1;padding:4px 7px;border-radius:6px;color:inherit}
.toasts-journal-bouton:hover{background:rgba(0,0,0,.08)}
.toasts-journal-badge{position:absolute;top:-3px;right:-3px;min-width:16px;height:16px;
  padding:0 4px;border-radius:8px;background:#a32d2d;color:#fff;font-size:10px;
  font-weight:700;line-height:16px;text-align:center}
.socle-journal-panneau{position:fixed;top:48px;right:16px;z-index:3050;width:320px;
  max-height:70vh;overflow:auto;background:#fff;border-radius:10px;
  box-shadow:0 10px 32px rgba(0,0,0,.28);color:#1a1a18}
.socle-journal-entete{display:flex;justify-content:space-between;align-items:center;
  padding:10px 14px;border-bottom:1px solid #eee;font-size:13px;font-weight:600}
.socle-journal-fermer{background:none;border:none;font-size:16px;cursor:pointer;
  color:#666;padding:0 4px}
.socle-journal-liste{padding:4px 0}
.socle-journal-vide{padding:16px 14px;font-size:12px;color:#888}
.socle-journal-ligne{padding:7px 14px;font-size:12px;border-bottom:1px solid #f3f3f1}
.socle-journal-ligne:last-child{border-bottom:none}
.socle-journal-corps{display:flex;gap:8px;align-items:baseline}
.socle-journal-detail{margin-top:3px;font-size:10px;color:#999;word-break:break-word}
.socle-journal-heure{flex:0 0 auto;color:#999;font-variant-numeric:tabular-nums}
.socle-journal-texte{flex:1 1 auto;word-break:break-word}
.socle-journal-ligne.erreur .socle-journal-texte{color:#a32d2d}
.socle-journal-ligne.avertissement .socle-journal-texte{color:#8a6d00}
.socle-journal-ligne.succes .socle-journal-texte{color:#22803a}
`;
  d.head.appendChild(style);
}

// Ferme et retire le toast associé à `cle` — déclaration UNIQUE au niveau du
// module (pas recréée à chaque appel de `afficher`), pour que le minuteur
// programmé à la création reste valide même après une mise à jour ultérieure
// du compteur par un nouvel appel identique.
function fermerToast(cle) {
  const actif = toastsActifs.get(cle);
  if (!actif) return;
  toastsActifs.delete(cle);
  actif.element.classList.remove('visible');
  setTimeout(() => actif.element.remove(), 200);
}

// (Re)construit le contenu d'un toast : texte + bouton « × » si `avecFermeture`
// (erreur/avertissement, issue #730 — fermeture manuelle uniquement), + ligne
// de détail technique discrète optionnelle (`detailTechnique`, issue #824),
// + zone sélectionnable optionnelle (`texteSecours`, issue #782 — voir
// `afficher`).
function definirContenuToast(toast, texte, avecFermeture, onFermer, texteSecours, detailTechnique) {
  toast.textContent = '';
  const conteneur = doc().createElement('span');
  conteneur.className = 'socle-toast-contenu';
  const span = doc().createElement('span');
  span.textContent = texte;
  conteneur.appendChild(span);
  if (avecFermeture) {
    const bouton = doc().createElement('button');
    bouton.type = 'button';
    bouton.className = 'socle-toast-fermer';
    bouton.setAttribute('aria-label', 'Fermer');
    bouton.textContent = '×';
    bouton.addEventListener('click', (evenement) => { evenement.stopPropagation(); onFermer(); });
    conteneur.appendChild(bouton);
  }
  toast.appendChild(conteneur);
  if (detailTechnique) {
    const detail = doc().createElement('div');
    detail.className = 'socle-toast-detail';
    detail.textContent = detailTechnique;
    toast.appendChild(detail);
  }
  if (texteSecours) {
    const zone = doc().createElement('textarea');
    zone.className = 'socle-toast-secours';
    zone.readOnly = true;
    zone.value = texteSecours;
    zone.title = 'Texte non copié — sélectionne-le et copie-le manuellement (Ctrl+C).';
    zone.addEventListener('click', () => zone.select());
    toast.appendChild(zone);
    // Pré-sélectionné pour un Ctrl+C immédiat sans avoir à cliquer dedans.
    setTimeout(() => zone.select(), 0);
  }
}

/** Clé de regroupement anti-empilement (issue #635) d'un toast. Un texte de
 * secours (issue #782, voir `definirContenuToast`) rend la clé UNIQUE —
 * `compteurUnique` doit être différent à chaque appel — car le mécanisme
 * anti-empilement REMPLACE le contenu affiché par le nouvel appel : sans
 * clé unique, le texte de secours d'un appel précédent (ex. un rapport
 * resté non copié) serait silencieusement effacé par le suivant. Pure —
 * testable sans DOM (voir toasts.test.js). */
export function cleToast(type, texte, texteSecours, compteurUnique) {
  return texteSecours ? `${type} ${texte} #${compteurUnique}` : `${type} ${texte}`;
}

/** Clé de regroupement EFFECTIVE, compte tenu d'une éventuelle clé explicite
 * fournie par l'appelant (`options.cle`, issue #807) — celle-ci prime alors
 * sur `cleToast(...)`, quel que soit le texte (donc même si celui-ci change
 * d'un appel à l'autre — ex. liste de projets en échec). Sans `cleDemandee`
 * (undefined/null), comportement inchangé. */
export function cleEffective(type, texte, texteSecours, compteurUnique, cleDemandee) {
  return cleDemandee != null ? cleDemandee : cleToast(type, texte, texteSecours, compteurUnique);
}

let compteurCleSecours = 0;

function afficher(texte, type, comptabiliseDemande = true, options = {}) {
  const { texteSecours, duree: dureeDemandee, cle: cleDemandee, detailTechnique } = options || {};
  const d = doc();
  if (!d) { return; }
  injecterStyles();
  journaliser(texte, type, estComptabilise(type, comptabiliseDemande), detailTechnique);

  // `options.duree`/`options.cle` (issue #807) : voir dureeEffective/
  // cleEffective ci-dessus — sans effet si absents (comportement inchangé).
  // `detailTechnique` (issue #824) rend aussi la clé UNIQUE, au même titre que
  // `texteSecours` (voir le commentaire de cleToast) : un détail technique
  // change à chaque occurrence (délai, focus...), il ne doit jamais être
  // silencieusement effacé par la fusion anti-empilement.
  const duree = dureeEffective(type, dureeDemandee);
  const remplacer = cleDemandee != null;
  const payloadUnique = texteSecours || detailTechnique;
  const cle = cleEffective(type, texte, payloadUnique, payloadUnique ? ++compteurCleSecours : undefined, cleDemandee);
  const actif = payloadUnique ? null : toastsActifs.get(cle);
  if (actif) {
    const { texte: texteAffiche, compteur } = contenuRemplacement(texte, actif.compteur, remplacer);
    actif.compteur = compteur;
    definirContenuToast(actif.element, texteAffiche, duree === null, () => fermerToast(cle));
    if (duree !== null) {
      clearTimeout(actif.minuteur);
      actif.dureeRestante = duree;
      actif.debutActif = Date.now();
      actif.minuteur = setTimeout(() => fermerToast(cle), duree);
    }
    return actif.element;
  }

  let conteneur = d.querySelector('.socle-toasts');
  if (!conteneur) {
    conteneur = d.createElement('div');
    conteneur.className = 'socle-toasts';
    d.body.appendChild(conteneur);
  }
  const toast = d.createElement('div');
  toast.className = `socle-toast ${type}`;
  definirContenuToast(toast, texte, duree === null, () => fermerToast(cle), texteSecours, detailTechnique);
  conteneur.appendChild(toast);
  // Forcer un reflow puis lancer la transition d'apparition.
  requestAnimationFrame(() => toast.classList.add('visible'));

  const entree = { element: toast, compteur: 1, minuteur: null, dureeRestante: duree, debutActif: null };
  if (duree !== null) {
    entree.debutActif = Date.now();
    entree.minuteur = setTimeout(() => fermerToast(cle), duree);
    // Pause au survol (issue #730) : la souris dessus gèle le compte à
    // rebours ; il repart du temps restant quand elle quitte le toast.
    toast.addEventListener('mouseenter', () => {
      if (entree.debutActif == null) return;
      clearTimeout(entree.minuteur);
      entree.dureeRestante = calculerDelaiRestant(entree.dureeRestante, entree.debutActif, Date.now());
      entree.debutActif = null;
    });
    toast.addEventListener('mouseleave', () => {
      if (entree.debutActif != null) return;
      entree.debutActif = Date.now();
      entree.minuteur = setTimeout(() => fermerToast(cle), entree.dureeRestante);
    });
    // Clic = fermeture immédiate, réservé aux messages déjà auto-effaçables
    // (info/succes, ou erreur/avertissement à durée explicite — issue #807) —
    // une erreur/avertissement SANS durée explicite n'a que le bouton « × ».
    toast.addEventListener('click', () => { clearTimeout(entree.minuteur); fermerToast(cle); });
  }
  toastsActifs.set(cle, entree);
  return toast;
}

/**
 * LA modale de confirmation destructive (unique). Renvoie une Promise<boolean>.
 * @param {string} message
 * @param {{titre?:string, texteConfirmer?:string, texteAnnuler?:string}} [opts]
 */
function confirmer(message, opts = {}) {
  const {
    titre = 'Confirmer',
    texteConfirmer = 'Confirmer',
    texteAnnuler = 'Annuler',
  } = opts;
  const d = doc();
  if (!d) return Promise.resolve(false);
  injecterStyles();
  return new Promise((resoudre) => {
    const overlay = d.createElement('div');
    overlay.className = 'socle-modal-overlay';
    overlay.innerHTML =
      '<div class="socle-modal-carte" role="dialog" aria-modal="true">' +
      '<div class="socle-modal-titre"></div>' +
      '<div class="socle-modal-message"></div>' +
      '<div class="socle-modal-boutons">' +
      '<button data-role="annuler"></button>' +
      '<button class="danger" data-role="confirmer"></button>' +
      '</div></div>';
    overlay.querySelector('.socle-modal-titre').textContent = titre;
    overlay.querySelector('.socle-modal-message').textContent = message;
    const btnAnnuler = overlay.querySelector('[data-role="annuler"]');
    const btnConfirmer = overlay.querySelector('[data-role="confirmer"]');
    btnAnnuler.textContent = texteAnnuler;
    btnConfirmer.textContent = texteConfirmer;
    const fermer = (valeur) => { overlay.remove(); resoudre(valeur); };
    btnAnnuler.addEventListener('click', () => fermer(false));
    btnConfirmer.addEventListener('click', () => fermer(true));
    overlay.addEventListener('click', (e) => { if (e.target === overlay) fermer(false); });
    d.body.appendChild(overlay);
    btnConfirmer.focus();
  });
}

export const toasts = {
  // `comptabilise` (issue #747, défaut true) : passer `false` pour un message
  // qui ne fait que confirmer une action déclenchée et vue par l'utilisateur —
  // il s'affiche et se journalise normalement, mais n'incrémente pas la
  // pastille. Sans effet sur erreur/avertissement (toujours comptabilisés).
  info: (texte, comptabilise = true) => afficher(texte, 'info', comptabilise),
  succes: (texte, comptabilise = true) => afficher(texte, 'succes', comptabilise),
  // `options.texteSecours` (issue #782) : jointe au toast dans une zone
  // sélectionnable — pour qu'un texte qui a échoué à être copié (presse-papier
  // refusé, execCommand en échec…) reste accessible pour un Ctrl+C manuel,
  // au lieu d'être simplement perdu.
  // `options.detailTechnique` (issue #824) : ligne discrète ajoutée sous le
  // message principal (jamais le contenu d'un texte, seulement sa longueur et
  // le contexte de l'échec) — journalisée dans le panneau « Messages » comme
  // les autres messages, en plus du message principal inchangé.
  erreur: (texte, comptabilise = true, options) => afficher(texte, 'erreur', comptabilise, options),
  // `options.duree`/`options.cle` (issue #807) : voir le commentaire d'en-tête
  // du fichier — mêmes options facultatives que `erreur` ci-dessus.
  avertissement: (texte, comptabilise = true, options) => afficher(texte, 'avertissement', comptabilise, options),
  confirmer,
};
