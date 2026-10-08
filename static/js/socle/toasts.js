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
//     (issue #730, voir `dureeAffichage`).
//   - toasts.confirmer(...) : LA seule modale, réservée aux confirmations
//     d'actions destructives (remplaçant de confirm(...)). Renvoie une Promise
//     qui se résout à true (confirmé) ou false (annulé).
//   JAMAIS de boîte à fermer avec « OK » pour info/succes/erreur/avertissement
//   (fini les alert()) — ce sont les remplaçants de alert(...) et
//   afficherToast(...).
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

/** Ajoute `entree` en fin de `journal`, en retirant les plus anciennes au-delà
 * de `tailleMax` (FIFO). Pure — ne modifie pas le tableau reçu. */
export function ajouterEntreeJournal(journal, entree, tailleMax = JOURNAL_TAILLE_MAX) {
  const suite = [...journal, entree];
  return suite.length > tailleMax ? suite.slice(suite.length - tailleMax) : suite;
}

/** Nombre de messages non consultés après l'ajout d'un nouveau message :
 * remis à zéro si le panneau du journal est actuellement ouvert (l'utilisateur
 * le voit tout de suite), sinon incrémenté. */
export function majNonLusApresAjout(nombreActuel, panneauOuvert) {
  return panneauOuvert ? 0 : nombreActuel + 1;
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
    journal = Array.isArray(donnees.entrees) ? donnees.entrees : [];
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
function journaliser(texte, type) {
  compteurIdJournal += 1;
  const entree = { id: compteurIdJournal, type, texte, horodatage: Date.now() };
  journal = ajouterEntreeJournal(journal, entree, JOURNAL_TAILLE_MAX);
  nonLus = majNonLusApresAjout(nonLus, panneauJournalOuvert);
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
    const heure = d.createElement('span');
    heure.className = 'socle-journal-heure';
    heure.textContent = formaterHeureJournal(new Date(entree.horodatage));
    const texte = d.createElement('span');
    texte.className = 'socle-journal-texte';
    texte.textContent = entree.texte;
    ligne.appendChild(heure);
    ligne.appendChild(texte);
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
.socle-journal-ligne{display:flex;gap:8px;padding:7px 14px;font-size:12px;
  border-bottom:1px solid #f3f3f1;align-items:baseline}
.socle-journal-ligne:last-child{border-bottom:none}
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
// (erreur/avertissement, issue #730 — fermeture manuelle uniquement).
function definirContenuToast(toast, texte, avecFermeture, onFermer) {
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
}

function afficher(texte, type) {
  const d = doc();
  if (!d) { return; }
  injecterStyles();
  journaliser(texte, type);

  const duree = dureeAffichage(type);
  const cle = type + ' ' + texte;
  const actif = toastsActifs.get(cle);
  if (actif) {
    actif.compteur += 1;
    definirContenuToast(actif.element, texte + ' (×' + actif.compteur + ')', duree === null, () => fermerToast(cle));
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
  definirContenuToast(toast, texte, duree === null, () => fermerToast(cle));
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
    // (info/succes) — erreur/avertissement n'ont que le bouton « × » explicite.
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
  info: (texte) => afficher(texte, 'info'),
  succes: (texte) => afficher(texte, 'succes'),
  erreur: (texte) => afficher(texte, 'erreur'),
  avertissement: (texte) => afficher(texte, 'avertissement'),
  confirmer,
};
