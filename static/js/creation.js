// creation.js — onglet « Nouvelle issue » (formulaire de création), sorti
// d'app.js (issue #652, dernier chantier de la refonte web — ARCHITECTURE.md
// §6.7).
//
// RESPONSABILITÉ
//   Tout le formulaire « Nouvelle issue », conservé comme backup manuel (seul
//   moyen de joindre un fichier à une issue). Comportement STRICTEMENT
//   INCHANGÉ, objectif purement structurel :
//     - bibliothèque de templates d'issues récurrentes (issue #284) ;
//     - pièce jointe image (issue #191/#192) ;
//     - envoi en lot de plusieurs blocs « #Titre: » (issue #135/#505) ;
//     - détection automatique des champs d'en-tête collés dans le corps
//       (#Titre, PROJET #109, TIMEOUT #111, MODE #326) + résumé (#117) ;
//     - aperçu de la commande, envoi, modales de confirmation/incohérence ;
//     - mémorisation de notif_pc (issue #93), défaut coché de la case Bureau.
//
// INITIALISATION (issue #652) : par IMPORT DIRECT depuis onglets.js (voir
//   activerOnglet), plus par le pont. initCreation() est idempotente : elle
//   installe la délégation d'événements (remplace les onclick=/onchange= inline
//   du fragment templates/fragments/onglet_creation.html) et les détecteurs
//   d'en-tête à la frappe sur #corps, une seule fois, à la première activation
//   de l'onglet.
//
// LOGIQUE PURE (testée sous Node — voir static/js/tests/creation.test.js) :
//   zoneEntete, lireChampEntete, retirerLigneEntete, reconnaitreModeTexte,
//   detecterIncoherenceProjet, decouperCorpsEnBlocs, projetEffectifBloc,
//   modeEffectifBloc — aucune dépendance au DOM ni au réseau. Elles sont
//   exportées à cette seule fin ; le reste reste interne au module.
//
// PONT VERS L'ANCIEN app.js (à retirer avec le pont à la fin de la refonte) :
//   - creation → ancien : le sélecteur de projet global reste dans app.js ;
//     detecterProjetDansCorps y appelle onProjetChange(), viderFormulaire()
//     mettreAJourInfoProjet(), via appelerAncien (voir socle/pont.js).
//   - ancien → creation : app.js appelle encore par leur nom chargerTemplates()
//     (onProjetChange, au changement de projet) et afficherMessage()
//     (lancerWatcher) — publiés en globales window.* ci-dessous, comme le fait
//     panneau_lateral.js dans le sens inverse.

import * as dom from './socle/dom.js';
import { appelerAncien } from './socle/pont.js';
import * as persistance from './socle/persistance.js';
import { signalerEchecPossible } from './socle/panne_github.js';

// Échappement HTML : brique unique du socle (comme panneau_lateral.js), à la
// place de l'ancien escapeHtml d'app.js — même rôle, sécurisé identiquement.
const escapeHtml = dom.echapperHtml;

function collecterFormulaire() {
  const notifs = [...document.querySelectorAll('input[name=notifs]:checked')].map(c => c.value);
  return {
    projet:          document.getElementById('projet').value,
    titre:           document.getElementById('titre').value.trim(),
    priorite:        document.getElementById('priorite').value,
    timeout:         document.getElementById('timeout').value,
    mode:            document.querySelector('input[name=mode]:checked').value,
    notifs:          notifs,
    corps:           document.getElementById('corps').value.trim(),
    modele_ponctuel: document.getElementById('modele-ponctuel').value,
  };
}

// ─── Bibliothèque de templates d'issues récurrentes (issue #284) ──────────────
// Un template capture l'état complet du formulaire (mêmes clés que
// collecterFormulaire()) sous un nom choisi par l'utilisateur, pour recréer en
// un clic une issue qui revient régulièrement à l'identique (ex. build
// Scrabble). Liste rechargée à chaque changement de projet (onProjetChange).
let templatesProjetActuel = [];

async function chargerTemplates() {
  const select = document.getElementById('template-select');
  if (!select) return;
  const nomProjet = document.getElementById('projet').value;
  try {
    const rep = await fetch('/templates/' + encodeURIComponent(nomProjet));
    const json = await rep.json();
    templatesProjetActuel = Array.isArray(json) ? json : [];
  } catch(e) {
    templatesProjetActuel = [];
  }
  select.innerHTML = '<option value="">-- Aucun --</option>' +
    templatesProjetActuel.map(t =>
      '<option value="' + escapeHtml(t.id) + '">' + escapeHtml(t.nom) + '</option>'
    ).join('');
  onTemplateSelectChange();
}

function templateSelectionne() {
  const select = document.getElementById('template-select');
  if (!select || !select.value) return null;
  return templatesProjetActuel.find(t => t.id === select.value) || null;
}

// Sélectionner un template dans la liste déroulante pré-remplit tout le
// formulaire ci-dessous (titre, corps, priorité, timeout, mode, notifications,
// modèle) et active/désactive les icônes modifier/supprimer.
function onTemplateSelectChange() {
  const t = templateSelectionne();
  const btnMod = document.getElementById('btn-template-modifier');
  const btnSup = document.getElementById('btn-template-supprimer');
  if (btnMod) btnMod.disabled = !t;
  if (btnSup) btnSup.disabled = !t;
  if (t) chargerTemplateDansFormulaire(t);
}

function chargerTemplateDansFormulaire(t) {
  document.getElementById('titre').value = t.titre || '';
  document.getElementById('priorite').value = t.priorite || 'normale';
  document.getElementById('timeout').value = t.timeout || 300;
  const radio = document.querySelector('input[name=mode][value="' + (t.mode || 'lecture') + '"]');
  if (radio) radio.checked = true;
  document.querySelectorAll('input[name=notifs]').forEach(c => {
    c.checked = Array.isArray(t.notifs) && t.notifs.includes(c.value);
  });
  document.getElementById('corps').value = t.corps || '';
  document.getElementById('modele-ponctuel').value = t.modele_ponctuel || '';
  mettreAJourBoutonEnvoi();
  mettreAJourResumeEntete();
}

// Enregistre l'état actuel du formulaire comme NOUVEAU template du projet en
// cours (bouton « Créer le template »). Demande le nom via un prompt simple.
async function creerTemplate() {
  const nom = prompt('Nom du template :');
  if (!nom || !nom.trim()) return;
  const data = collecterFormulaire();
  data.nom = nom.trim();
  try {
    const rep  = await fetch('/templates', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
    const json = await rep.json();
    if (json.succes) {
      await chargerTemplates();
      document.getElementById('template-select').value = json.template.id;
      onTemplateSelectChange();
      afficherToast('Template « ' + nom.trim() + ' » créé.');
    } else {
      afficherMessage('Erreur : ' + (json.erreur || 'échec inconnu'), 'erreur');
    }
  } catch(e) {
    afficherMessage('Erreur réseau : ' + e.message, 'erreur');
  }
}

// Écrase le template actuellement sélectionné avec l'état courant du
// formulaire (icône crayon) — le nom reste modifiable via le prompt.
async function modifierTemplateSelectionne() {
  const t = templateSelectionne();
  if (!t) return;
  const nom = prompt('Nom du template :', t.nom);
  if (!nom || !nom.trim()) return;
  const data = collecterFormulaire();
  data.id  = t.id;
  data.nom = nom.trim();
  try {
    const rep  = await fetch('/templates', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
    const json = await rep.json();
    if (json.succes) {
      await chargerTemplates();
      document.getElementById('template-select').value = json.template.id;
      onTemplateSelectChange();
      afficherToast('Template « ' + nom.trim() + ' » mis à jour.');
    } else {
      afficherMessage('Erreur : ' + (json.erreur || 'échec inconnu'), 'erreur');
    }
  } catch(e) {
    afficherMessage('Erreur réseau : ' + e.message, 'erreur');
  }
}

// Supprime le template actuellement sélectionné (icône poubelle), après
// confirmation.
async function supprimerTemplateSelectionne() {
  const t = templateSelectionne();
  if (!t) return;
  if (!confirm('Supprimer le template « ' + t.nom + ' » ?')) return;
  const nomProjet = document.getElementById('projet').value;
  try {
    const rep  = await fetch(
      '/templates/' + encodeURIComponent(nomProjet) + '/' + encodeURIComponent(t.id),
      {method: 'DELETE'}
    );
    const json = await rep.json();
    if (json.succes) {
      await chargerTemplates();
      afficherToast('Template supprimé.');
    } else {
      afficherMessage('Erreur : ' + (json.erreur || 'échec inconnu'), 'erreur');
    }
  } catch(e) {
    afficherMessage('Erreur réseau : ' + e.message, 'erreur');
  }
}

function afficherMessage(texte, type) {
  const el = document.getElementById('message');
  el.textContent = texte;
  el.className = 'message ' + type;
  el.style.display = 'block';
}

// Bandeau temporaire non bloquant (issue #202) : information éphémère qui ne doit
// PAS interrompre le flux (contrairement à une modale) ni écraser le message
// principal (#message). Créé à la volée en bas de l'écran, il s'efface tout seul
// après quelques secondes. Sert notamment à signaler « Watcher démarré
// automatiquement » après la création d'une issue.
function afficherToast(texte) {
  let toast = document.getElementById('toast-info');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toast-info';
    toast.style.cssText =
      'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);'
      + 'background:#333;color:#fff;padding:10px 18px;border-radius:6px;'
      + 'font-size:13px;box-shadow:0 2px 8px rgba(0,0,0,.25);z-index:9999;'
      + 'opacity:0;transition:opacity .25s;pointer-events:none;';
    document.body.appendChild(toast);
  }
  toast.textContent = texte;
  // Deux images pour relancer la transition même si le toast existe déjà.
  requestAnimationFrame(() => { toast.style.opacity = '1'; });
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => { toast.style.opacity = '0'; }, 4000);
}

// ─── Pièce jointe image (issue #191) ──────────────────────────────────────────
// Active le bouton « Joindre une image » seulement quand un fichier est choisi.
function majEtatBoutonImage() {
  const input = document.getElementById('image-jointe');
  const btn   = document.getElementById('btn-joindre-image');
  if (!input || !btn) return;
  btn.disabled = !(input.files && input.files.length);
}

// Insère un texte à la position du curseur dans le champ Corps (ou en fin de
// corps à défaut de sélection connue). Préfixe d'un saut de ligne si la ligne
// courante n'est pas vide, pour que le Markdown de l'image tienne sur sa
// propre ligne.
function insererDansCorps(texte) {
  const corps = document.getElementById('corps');
  const debut = (typeof corps.selectionStart === 'number') ? corps.selectionStart : corps.value.length;
  const fin   = (typeof corps.selectionEnd === 'number') ? corps.selectionEnd : corps.value.length;
  const avant = corps.value.slice(0, debut);
  const apres = corps.value.slice(fin);
  const prefixe = (avant === '' || avant.endsWith('\n')) ? '' : '\n';
  const suffixe = (apres === '' || apres.startsWith('\n')) ? '' : '\n';
  const insert = prefixe + texte + suffixe;
  corps.value = avant + insert + apres;
  const pos = (avant + insert).length;
  corps.selectionStart = corps.selectionEnd = pos;
  corps.focus();
  // Notifie les écouteurs « input » (résumé d'en-tête, détection de titre…).
  corps.dispatchEvent(new Event('input', {bubbles: true}));
}

// Upload de l'image vers /joindre-image : le backend committe + pousse l'image
// sur le dépôt du projet sélectionné, puis renvoie l'URL raw.githubusercontent
// qu'on insère automatiquement dans le corps sous forme de ![nom](url).
async function joindreImage() {
  const input = document.getElementById('image-jointe');
  const btn   = document.getElementById('btn-joindre-image');
  const msg   = document.getElementById('image-jointe-msg');
  if (!input || !input.files || !input.files.length) return;
  const fichier = input.files[0];

  // Garde-fou côté client (le backend revalide) : limite 5 Mo, types image.
  // La liste des types acceptés est injectée par le serveur dans
  // window.MIMES_IMAGE_ACCEPTES (issue #192) depuis TYPES_IMAGE_ACCEPTES —
  // repli défensif sur PNG/JPEG/GIF si la variable est absente.
  const TAILLE_MAX = 5 * 1024 * 1024;
  if (fichier.size > TAILLE_MAX) {
    msg.style.color = '#c0392b';
    msg.textContent = 'Image trop lourde (' + (fichier.size / 1048576).toFixed(1) + ' Mo) — limite 5 Mo.';
    return;
  }
  const mimesAcceptes = window.MIMES_IMAGE_ACCEPTES
    || ['image/png', 'image/jpeg', 'image/gif'];
  if (mimesAcceptes.indexOf(fichier.type) === -1) {
    const libelles = mimesAcceptes.map(function (m) { return m.split('/')[1].toUpperCase(); });
    msg.style.color = '#c0392b';
    msg.textContent = 'Seuls les ' + libelles.join(', ') + ' sont acceptés.';
    return;
  }

  const projet = document.getElementById('projet').value;
  const form = new FormData();
  form.append('image', fichier);
  form.append('projet', projet);

  btn.disabled = true;
  const libelle = btn.textContent;
  btn.textContent = 'Envoi…';
  msg.style.color = '#888';
  msg.textContent = 'Commit + push en cours…';
  try {
    const rep  = await fetch('/joindre-image', {method: 'POST', body: form});
    const json = await rep.json();
    if (json.succes) {
      insererDansCorps('![' + json.nom_fichier + '](' + json.url + ')');
      msg.style.color = '#2e7d32';
      msg.textContent = '✓ Image jointe et lien inséré dans le corps.';
      input.value = '';           // réinitialise le champ (bouton se redésactive)
    } else {
      msg.style.color = '#c0392b';
      msg.textContent = 'Erreur : ' + (json.erreur || 'échec inconnu');
    }
  } catch (e) {
    msg.style.color = '#c0392b';
    msg.textContent = 'Erreur réseau : ' + e.message;
  } finally {
    btn.textContent = libelle;
    majEtatBoutonImage();
  }
}

function cacherRetours() {
  document.getElementById('message').style.display = 'none';
  document.getElementById('zone-apercu').style.display = 'none';
  const resumeLot = document.getElementById('resume-lot');
  if (resumeLot) resumeLot.style.display = 'none';
}

async function afficherApercu() {
  cacherRetours();
  const data = collecterFormulaire();
  if (!data.titre) { afficherMessage('Le titre est obligatoire.', 'erreur'); return; }
  const rep = await fetch('/apercu', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data)
  });
  const json = await rep.json();
  const zone = document.getElementById('zone-apercu');
  zone.textContent = json.commande;
  zone.style.display = 'block';
}

// Affiche le modal de confirmation et résout true (envoyer) / false (annuler).
function afficherModalConfirmation(issues) {
  return new Promise(resolve => {
    const overlay = document.getElementById('modal-confirmation');
    document.getElementById('modal-titre').textContent =
      '⚠️ ' + issues.length + ' issue(s) en attente sur ce projet :';
    document.getElementById('modal-liste').innerHTML = issues.map(it =>
      '#' + escapeHtml(String(it.number)) + ' — ' + escapeHtml(it.title || '(sans titre)')
    ).join('<br>');
    const btnOui = document.getElementById('modal-oui');
    const btnNon = document.getElementById('modal-non');
    function fermer(reponse) {
      overlay.classList.remove('actif');
      btnOui.onclick = null; btnNon.onclick = null;
      resolve(reponse);
    }
    btnOui.onclick = () => fermer(true);
    btnNon.onclick = () => fermer(false);
    overlay.classList.add('actif');
  });
}

// Nombre de lignes depuis le tout début du corps où chercher les champs
// d'en-tête (issue #512). Le bloc en-tête + #Titre: tient toujours largement
// dans cette marge ; au-delà, une mention d'un champ dans le texte explicatif
// (ex. exemple illustratif) n'est plus interprétée comme le véritable en-tête
// — seule la PREMIÈRE occurrence, proche du début, compte. Même constante et
// même logique que ZONE_ENTETE_LIGNES/_zone_entete de
// scripts/watcher_issues_inbox.py, pour ne jamais diverger.
const ZONE_ENTETE_LIGNES = 25;
export function zoneEntete(corps) {
  const texte = corps || '';
  let fin = 0;
  for (let i = 0; i < ZONE_ENTETE_LIGNES; i++) {
    const idx = texte.indexOf('\n', fin);
    if (idx === -1) return texte;
    fin = idx + 1;
  }
  return texte.slice(0, fin);
}

// Lecture d'un champ d'en-tête « | CHAMP | valeur | » dans le corps collé.
// Source unique de vérité pour tout le parsing d'en-tête côté formulaire :
// détection PROJET (#44/#109), TIMEOUT (#111) et résumé d'en-tête (#117)
// s'appuient tous dessus, pour éviter des regex divergentes.
//   • mot-clé insensible à la casse, espaces/tabulations tolérés autour des
//     séparateurs (PAS de saut de ligne — voir issue #512 ci-dessous) ;
//   • la valeur est la cellule entre le 2e et le 3e « | », nettoyée ;
//   • retourne la valeur (chaîne non vide) ou null (champ absent ou vide) ;
//   • la recherche est bornée à zoneEntete(corps) (issue #512) : une mention
//     du champ plus bas dans le texte explicatif (exemple illustratif) n'est
//     alors plus interprétée à tort comme le véritable en-tête.
export function lireChampEntete(corps, champ) {
  const re = new RegExp('^[ \\t]*\\|[ \\t]*' + champ + '[ \\t]*\\|([^|]*)\\|', 'im');
  const m = zoneEntete(corps).match(re);
  if (!m) return null;
  const valeur = m[1].trim();
  return valeur || null;
}

// Retire du corps la PREMIÈRE ligne d'en-tête « | CHAMP | … | » — exactement
// celle que lireChampEntete vient de lire (même regex), saut de ligne compris
// (issue #129). Contrairement à detecterTitreDansCorps qui retire toujours la
// première ligne du corps, on cible ici la ligne EXACTE où le champ a été
// trouvé, où qu'elle soit dans le tableau d'en-tête. Renvoie le corps modifié,
// ou le corps inchangé si le champ est absent.
//
// Champ dupliqué (ex. deux lignes TIMEOUT distinctes, cf. #11) : seule la
// première occurrence est retirée. Les doublons restants restent visibles dans
// le corps — c'est volontaire : ça signale à Alain qu'il y a un doublon à
// nettoyer, plutôt que de les faire disparaître silencieusement tous les deux.
//
// Issue #512 : la recherche du match (m.index) se fait dans zoneEntete(corps),
// un PRÉFIXE exact de corps — l'indice reste donc valide tel quel dans corps.
// L'ancienne regex (\s* au lieu de [ \t]*) laissait « ^ » matcher le début
// d'une ligne VIDE précédant la ligne du champ (\s* incluant le saut de
// ligne), typiquement quand #Titre: précède l'en-tête tabulaire avec une
// ligne vide entre les deux : le calcul de fin de ligne ci-dessous
// (corps.indexOf('\n', debut)) tombait alors immédiatement sur le saut de
// ligne de CETTE ligne vide (fin === debut), et seul ce caractère était
// retiré — la ligne du champ, elle, restait intacte dans le corps.
export function retirerLigneEntete(corps, champ) {
  const re = new RegExp('^[ \\t]*\\|[ \\t]*' + champ + '[ \\t]*\\|[^|]*\\|', 'im');
  const m = zoneEntete(corps).match(re);
  if (!m) return corps;
  const debut = m.index;                       // ^ ancre le début de la ligne
  let fin = corps.indexOf('\n', debut);        // fin de la ligne physique
  if (fin === -1) fin = corps.length;
  // Retire le saut de ligne qui suit la ligne ; à défaut (dernière ligne sans
  // « \n » final), celui qui la précède, pour ne pas laisser de ligne vide.
  if (corps[fin] === '\n') return corps.slice(0, debut) + corps.slice(fin + 1);
  if (debut > 0 && corps[debut - 1] === '\n')
    return corps.slice(0, debut - 1) + corps.slice(fin);
  return corps.slice(0, debut) + corps.slice(fin);
}

// Mémoire des champs d'en-tête extraits du corps vers le formulaire (issue #129).
// PROJET/TIMEOUT étant désormais RETIRÉS du corps après extraction, lireChampEntete
// ne les y retrouve plus : on conserve ici la valeur extraite pour que le résumé
// d'en-tête (#117) continue de les afficher (le résumé doit rester une
// confirmation visuelle fiable, pas se vider au fur et à mesure des retraits).
// Réinitialisée par viderFormulaire.
let champsEnteteExtraits = {};

// Détecte une incohérence entre le projet sélectionné et le champ PROJET de
// l'en-tête bridge. Fiable : on ne fait plus d'analyse textuelle (source de
// faux positifs) — on lit le champ « | PROJET | … | » que new_issue.py insère
// dans l'en-tête, et que Claude Chat reproduit dans le corps qu'il fournit.
// Retourne {projetIssue, projetSelectionne} si les deux diffèrent, sinon null
// (champ absent → pas de vérification ; identique → pas de modale).
//
// Changement de rôle depuis #129 : detecterProjetDansCorps RETIRE désormais la
// ligne « | PROJET | … | » du corps dès qu'elle correspond à un projet CONNU
// (le select est alors déjà synchronisé, donc cohérent). À l'envoi il ne reste
// donc de ligne PROJET dans le corps que dans le cas où le projet était INCONNU
// (typo, projet pas encore créé) : la ligne a été délibérément laissée en place
// et le select est resté à sa valeur par défaut. Cette vérification n'est donc
// plus un doublon de la synchro amont — elle attrape spécifiquement ce cas
// « projet d'en-tête non reconnu ⇄ select par défaut » avant l'envoi.
export function detecterIncoherenceProjet(data) {
  const projetIssue = lireChampEntete(data.corps, 'PROJET');
  if (!projetIssue) return null;                        // absent/vide : pas de vérif
  const projetSelectionne = (data.projet || '').trim();
  if (projetIssue.toLowerCase() === projetSelectionne.toLowerCase()) {
    return null;                                        // identique : pas de modale
  }
  return {projetIssue, projetSelectionne};
}

// Modal d'alerte d'incohérence projet ⇄ corps. Réutilise l'overlay des issues
// en attente pour un rendu cohérent ; restaure libellés et liste à la
// fermeture. Résout true (envoyer quand même) / false (annuler).
function afficherModalIncoherence(projetIssue, projetSelectionne) {
  return new Promise(resolve => {
    const overlay = document.getElementById('modal-confirmation');
    const liste   = document.getElementById('modal-liste');
    const btnOui  = document.getElementById('modal-oui');
    const btnNon  = document.getElementById('modal-non');
    const ouiAvant = btnOui.textContent;
    const nonAvant = btnNon.textContent;
    document.getElementById('modal-titre').textContent = '⚠️ Incohérence détectée';
    liste.style.display = '';
    liste.innerHTML =
      'L\'en-tête de l\'issue indique le projet « <b>' + escapeHtml(projetIssue) + '</b> » '
      + 'mais tu envoies sur <b>' + escapeHtml(projetSelectionne) + '</b>.'
      + '<br><br>Envoyer quand même sur <b>' + escapeHtml(projetSelectionne) + '</b> ?';
    btnOui.textContent = 'Envoyer quand même';
    btnNon.textContent = 'Annuler';
    function fermer(reponse) {
      overlay.classList.remove('actif');
      btnOui.onclick = null; btnNon.onclick = null;
      btnOui.textContent = ouiAvant;
      btnNon.textContent = nonAvant;
      resolve(reponse);
    }
    btnOui.onclick = () => fermer(true);
    btnNon.onclick = () => fermer(false);
    overlay.classList.add('actif');
  });
}

// Modale d'erreur générique (un seul bouton). Réutilise l'overlay
// #modal-confirmation comme afficherModalIncoherence, mais masque #modal-non
// (pas de choix oui/non) et relabelle #modal-oui en « OK ». Restaure ensuite la
// visibilité et les libellés d'origine des deux boutons avant de rendre la main.
// La promesse se résout à la fermeture (valeur sans importance : un seul bouton).
function afficherModalErreur(titre, message) {
  return new Promise(resolve => {
    const overlay = document.getElementById('modal-confirmation');
    const liste   = document.getElementById('modal-liste');
    const btnOui  = document.getElementById('modal-oui');
    const btnNon  = document.getElementById('modal-non');
    const ouiAvant     = btnOui.textContent;
    const nonAvant     = btnNon.textContent;
    const nonDispAvant = btnNon.style.display;
    document.getElementById('modal-titre').textContent = titre;
    liste.style.display = '';
    liste.textContent = message;
    btnOui.textContent = 'OK';
    btnNon.style.display = 'none';
    function fermer() {
      overlay.classList.remove('actif');
      btnOui.onclick = null; btnNon.onclick = null;
      btnOui.textContent = ouiAvant;
      btnNon.textContent = nonAvant;
      btnNon.style.display = nonDispAvant;
      resolve();
    }
    btnOui.onclick = () => fermer();
    overlay.classList.add('actif');
  });
}

// La modale bloquante « watcher inactif » (afficherModalWatcherInactif, issue
// #171) a été retirée avec l'issue #202 : le backend démarre désormais le watcher
// automatiquement à la création d'une issue for-linux (voir envoyer() dans
// app/issues.py). L'avertissement pré-envoi n'a donc plus lieu d'être — un simple
// bandeau discret (afficherToast) informe a posteriori que le watcher a été
// rallumé, sans interrompre le flux.

async function envoyerIssue() {
  // Anti-double-clic (issue #189) : on désactive le bouton dès le TOUT DÉBUT,
  // AVANT toute vérification, modale bloquante ou appel réseau — un double-clic
  // rapide (bouton perçu comme lent) ne peut alors physiquement pas déclencher
  // un second envoi pendant que le premier est en cours. La réactivation se fait
  // uniquement à la toute fin (bloc finally), succès comme échec, y compris si
  // l'utilisateur annule une modale en cours de route.
  const btn = document.getElementById('btn-envoyer');
  if (btn.disabled) return;   // envoi déjà en cours : on ignore ce clic
  btn.disabled = true;
  try {
    cacherRetours();
    const data = collecterFormulaire();
    if (!data.titre) {
      await afficherModalErreur('Titre manquant',
        'Le titre est obligatoire pour envoyer cette issue.');
      return;
    }

    // Avertit si des issues for-linux sont déjà en attente sur ce projet, pour
    // éviter les conflits quand plusieurs issues mode_write s'enchaînent.
    try {
      const repAttente = await fetch('/issues-en-attente/' + encodeURIComponent(data.projet));
      const enAttente  = await repAttente.json();
      if (Array.isArray(enAttente) && enAttente.length) {
        const confirmer = await afficherModalConfirmation(enAttente);
        if (!confirmer) return;   // l'utilisateur a annulé l'envoi
      }
    } catch(e) {
      // La vérification a échoué (réseau, gh…) : on n'empêche pas l'envoi.
    }

    // Garde-fou ciblé : alerte seulement si le champ PROJET de l'en-tête diffère
    // du projet sélectionné (issue partie sur le mauvais dépôt).
    try {
      const incoherence = detecterIncoherenceProjet(data);
      if (incoherence) {
        const ok = await afficherModalIncoherence(
          incoherence.projetIssue, incoherence.projetSelectionne);
        if (!ok) return;   // l'utilisateur a annulé l'envoi
      }
    } catch(e) {
      // La détection a échoué : on n'empêche pas l'envoi.
    }

    // Plus de garde-fou bloquant « watcher inactif » ici (issue #202) : le backend
    // démarre désormais le watcher automatiquement à la création d'une issue
    // for-linux (voir envoyer() dans app/issues.py). L'ancienne modale
    // afficherModalWatcherInactif() serait contradictoire — elle avertirait que
    // l'issue « ne sera traitée que plus tard » juste avant que le backend ne
    // rallume le watcher tout seul. On envoie donc directement ; si le watcher a
    // été (re)démarré, la réponse le signale par un message discret non bloquant.

    btn.textContent = 'Envoi…';
    try {
      const rep = await fetch('/envoyer', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
      });
      const json = await rep.json();
      if (json.succes) {
        afficherMessage('✓ Issue créée : ' + json.url, 'succes');
        // Info discrète non bloquante (issue #202) : le backend a rallumé le
        // watcher pour cette issue for-linux (il était éteint). watcher_demarre
        // vaut false s'il tournait déjà et null si non applicable (for-windows) ou
        // échec silencieux — dans ces cas on n'affiche rien.
        if (json.watcher_demarre === true) {
          afficherToast('Watcher démarré automatiquement pour cette issue');
        }
        viderFormulaire(false);
      } else {
        // Alerte explicite de panne GitHub (issue #732) : déclenchée seulement
        // si le serveur a classé cet échec de création comme « panne probable ».
        signalerEchecPossible(json);
        afficherMessage('Erreur : ' + json.erreur, 'erreur');
      }
    } catch(e) {
      afficherMessage('Erreur réseau : ' + e.message, 'erreur');
    }
  } finally {
    // Réactivation garantie (succès, échec, annulation d'une modale). Restaure le
    // libellé avec le projet cible plutôt qu'un texte générique.
    btn.disabled = false;
    btn.textContent = 'Envoyer sur ' + document.getElementById('projet').value;
  }
}

// Couleur du bouton d'envoi par mode — gradation cohérente avec l'ordre du
// moins au plus permissif (issue #326) : lecture (noir) → lecture active
// (bleu) → écriture (rouge, réservé à l'écriture pleine, la plus risquée).
const COULEURS_MODE = {
  lecture:        '#1a1a18',
  lecture_active: '#1a4d8f',
  ecriture:       '#a32d2d',
};
function mettreAJourBoutonEnvoi() {
  const mode = document.querySelector('input[name=mode]:checked').value;
  const couleur = COULEURS_MODE[mode] || COULEURS_MODE.lecture;
  const btn = document.getElementById('btn-envoyer');
  btn.style.background    = couleur;
  btn.style.borderColor   = couleur;
}

// Détection de « #Titre: … » n'importe où dans la zone d'en-tête du corps
// (issue #679 — auparavant limitée à la toute première ligne, incohérent avec
// detecterProjetDansCorps/TIMEOUT qui, via lireChampEntete, cherchent déjà
// n'importe où). Permet de coller titre + corps en un seul copier-coller dans
// le champ #corps, y compris quand l'en-tête tabulaire (PROJET/REDACTEUR/MODE)
// précède #Titre: (convention par ailleurs valide côté issues_inbox/) : si une
// ligne de la zone d'en-tête (zoneEntete, issue #512) commence par « #Titre: »
// (insensible à la casse, espaces tolérés après « : »), on déplace ce qui suit
// dans #titre et on retire cette ligne du corps. Le champ #titre reste
// éditable normalement ; taper directement dedans ne déclenche aucun
// comportement automatique (l'écouteur est sur #corps).
//
// Pas de garde-fou « valeur inchangée » façon detecterProjetDansCorps : la
// ligne #Titre: est toujours retirée du corps dès qu'elle est trouvée (pas de
// notion de valeur « inconnue » qui la laisserait en place), donc elle ne peut
// pas être redétectée telle quelle au prochain passage — une correction
// manuelle du champ #titre n'est ainsi jamais écrasée par la frappe suivante.
function detecterTitreDansCorps() {
  const corpsEl = document.getElementById('corps');
  // En mode lot (2+ blocs « #Titre: »), cette détection mono-titre n'a plus de
  // sens : c'est envoyerLot qui traite chaque bloc avec son propre titre. On la
  // neutralise tant que le lot est détecté (issue #135).
  if (enModeLot()) return;
  const valeur = corpsEl.value;
  const m = zoneEntete(valeur).match(/^#titre:\s*(.*)$/im);
  if (!m) return;

  // Mémorise le mode courant : la détection ne touche pas au mode, mais on
  // n'appelle mettreAJourBoutonEnvoi() que s'il a effectivement changé.
  const modeAvant = document.querySelector('input[name=mode]:checked').value;

  document.getElementById('titre').value = m[1].trim();

  // Retire la ligne #Titre: trouvée, où qu'elle soit dans le corps — même
  // logique que retirerLigneEntete (issue #512) pour ne pas laisser de ligne
  // vide si #Titre: est entouré d'une ligne vide, que ce soit avant ou après
  // l'en-tête tabulaire. zoneEntete(valeur) étant un préfixe exact de valeur,
  // m.index reste valide tel quel dans valeur.
  const debut = m.index;
  let fin = valeur.indexOf('\n', debut);
  if (fin === -1) fin = valeur.length;
  if (valeur[fin] === '\n') {
    corpsEl.value = valeur.slice(0, debut) + valeur.slice(fin + 1);
  } else if (debut > 0 && valeur[debut - 1] === '\n') {
    corpsEl.value = valeur.slice(0, debut - 1) + valeur.slice(fin);
  } else {
    corpsEl.value = valeur.slice(0, debut) + valeur.slice(fin);
  }

  const modeApres = document.querySelector('input[name=mode]:checked').value;
  if (modeApres !== modeAvant) mettreAJourBoutonEnvoi();
}

// Détection de « | PROJET | <nom> | » dans le corps → pré-sélection de la
// combobox projet (issue #109). Presque toutes les issues générées par Claude
// Chat portent cette ligne dans l'en-tête markdown (§6) : plutôt qu'obliger
// Alain à changer la combobox à la main, on la positionne automatiquement sur
// le projet cité, à condition qu'il existe dans la liste.
//
// Garde-fous (§ tâche demandée) :
//   • nom inconnu (typo, projet pas encore créé) → on ne touche à rien ;
//   • la combobox reste entièrement manuelle : on ne réapplique la détection
//     que si le nom détecté a CHANGÉ depuis la dernière fois. Ainsi, si Alain
//     corrige manuellement la combobox alors que le corps contient toujours la
//     même ligne PROJET, sa correction n'est pas écrasée à la frappe suivante.
let dernierProjetAutoDetecte = null;
function detecterProjetDansCorps() {
  // En mode lot, chaque bloc porte son propre PROJET, lu par envoyerLot : on ne
  // synchronise pas la combobox sur le premier bloc et on ne mute pas le corps
  // (issue #135).
  if (enModeLot()) { dernierProjetAutoDetecte = null; return; }
  // Réutilise lireChampEntete (source unique de parsing d'en-tête) plutôt qu'une
  // regex locale : mot-clé insensible à la casse, nom nettoyé de ses espaces.
  const corpsEl = document.getElementById('corps');
  const nomDetecte = lireChampEntete(corpsEl.value, 'PROJET');
  // Champ absent : on relâche le garde-fou (une même valeur recollée plus tard
  // pourra être redétectée) mais on NE touche PAS à champsEnteteExtraits — le
  // champ a pu être retiré du corps par cette fonction même, et le résumé #117
  // doit continuer à l'afficher.
  if (!nomDetecte) { dernierProjetAutoDetecte = null; return; }

  // Rien de neuf depuis la dernière détection : ne pas réécraser un éventuel
  // choix manuel d'Alain.
  if (nomDetecte === dernierProjetAutoDetecte) return;
  dernierProjetAutoDetecte = nomDetecte;

  // Le nom doit correspondre (insensible à la casse) à une option existante.
  const select = document.getElementById('projet');
  const option = [...select.options]
    .find(o => o.value.toLowerCase() === nomDetecte.toLowerCase());
  // Projet INCONNU (typo, projet pas encore créé) → on ne change rien ET on
  // laisse la ligne PROJET dans le corps : le select reste sur sa valeur par
  // défaut et detecterIncoherenceProjet (#44) pourra alerter à l'envoi.
  if (!option) return;

  if (select.value !== option.value) {
    select.value = option.value;
    appelerAncien('onProjetChange', false);   // applique accent, statut, infos —
                                       // SANS réinitialiser le timeout (#143) : le
                                       // TIMEOUT collé reste géré par
                                       // detecterTimeoutDansCorps.
  }

  // Projet connu et synchronisé : on mémorise la valeur retenue (pour le résumé
  // #117) puis on retire la ligne PROJET du corps, comme detecterTitreDansCorps
  // le fait pour #Titre — sinon construire_body empilerait un second tableau
  // d'en-tête sous celui qu'il reconstruit depuis les champs (issue #129).
  champsEnteteExtraits.PROJET = option.value;
  corpsEl.value = retirerLigneEntete(corpsEl.value, 'PROJET');
}

// Détection de « | TIMEOUT | <valeur> | » dans le corps → pré-remplissage du
// champ Timeout du formulaire (issue #111). Sans cette synchronisation, le
// tableau d'en-tête généré par l'interface portait le TIMEOUT par défaut du
// formulaire (300s), PLACÉ AVANT le corps collé. Comme watcher.extraire_timeout
// retient la PREMIÈRE occurrence de TIMEOUT, cette valeur du formulaire écrasait
// silencieusement le « | TIMEOUT | 1200s | » collé par Alain (cause de l'échec
// de #108). En recopiant la valeur collée dans le champ, les deux occurrences du
// corps final deviennent identiques : plus d'écrasement silencieux.
//
// Même garde-fou que detecterProjetDansCorps (#109) : on ne réapplique la
// détection que si la valeur détectée a CHANGÉ depuis la dernière fois. Ainsi,
// si Alain corrige ensuite le champ Timeout à la main (pour surcharger la valeur
// collée), sa correction n'est pas réécrasée à la frappe suivante dans le corps.
let dernierTimeoutAutoDetecte = null;
function detecterTimeoutDansCorps() {
  // En mode lot, chaque bloc porte son propre TIMEOUT, lu par envoyerLot : on ne
  // synchronise pas le champ sur le premier bloc et on ne mute pas le corps
  // (issue #135).
  if (enModeLot()) { dernierTimeoutAutoDetecte = null; return; }
  // Réutilise lireChampEntete (source unique de parsing d'en-tête). La cellule
  // « | TIMEOUT | <valeur>[s] | » peut porter un suffixe « s » (ex. 1200s) et
  // des espaces ; on ne retient que les chiffres.
  const corpsEl = document.getElementById('corps');
  const brut = lireChampEntete(corpsEl.value, 'TIMEOUT');
  const m = brut && brut.match(/^(\d+)\s*s?$/i);
  // Absent/invalide : on relâche le garde-fou sans toucher au résumé mémorisé
  // (la ligne a pu être retirée par cette fonction même, cf. detecterProjet).
  if (!m) { dernierTimeoutAutoDetecte = null; return; }

  const valeurDetectee = m[1];
  // Rien de neuf depuis la dernière détection : ne pas réécraser un éventuel
  // choix manuel d'Alain.
  if (valeurDetectee === dernierTimeoutAutoDetecte) return;
  dernierTimeoutAutoDetecte = valeurDetectee;

  // Mémorise la valeur (affichée telle quelle dans le résumé #117, ex. « 1200s »)
  // puis synchronise le champ formulaire.
  champsEnteteExtraits.TIMEOUT = brut.trim();
  const champ = document.getElementById('timeout');
  if (champ.value !== valeurDetectee) champ.value = valeurDetectee;

  // Retire la ligne TIMEOUT du corps (comme #Titre/PROJET) pour éviter que
  // construire_body empile un second tableau d'en-tête. Sans ça, si la
  // synchronisation du champ échouait (ex. TIMEOUT dupliqué, #11), c'est le
  // TIMEOUT du formulaire — souvent resté à 300s — que le watcher retiendrait
  // en premier, d'où les décalages 300s/1500s déjà observés (issue #129).
  corpsEl.value = retirerLigneEntete(corpsEl.value, 'TIMEOUT');
}

// Détection de « | MODE | <valeur> | » dans le corps → pré-sélection du radio
// mode (lecture / lecture active / écriture), calquée sur detecterTimeoutDansCorps
// (issue #326). Contrairement à PROJET/TIMEOUT, qui ignorent silencieusement un
// champ absent, MODE a un DÉFAUT explicite quand il est absent ou non reconnu :
// LECTURE (défaut sûr — cohérent avec le reset après envoi, ligne ~4090, et le
// principe qu'une issue déclare toujours explicitement son mode quand elle
// écrit, sinon c'est lecture). Corrige la calibration TIMEOUT (§19, clé
// projet|TYPE|mode) faussée par l'habitude de cocher « écriture » à la main
// même pour des tâches en réalité en lecture seule.
//
// Reconnaissance TOLÉRANTE (insensible casse/accents, plusieurs libellés par
// mode) — ordre du tableau significatif : « lecture active » doit être testé
// avant « lecture » pour ne pas être absorbé par ce synonyme plus court.
const MODE_SYNONYMES = [
  { valeur: 'ecriture',       motifs: ['écriture', 'ecriture', 'write', 'mode_write'] },
  { valeur: 'lecture_active', motifs: ['lecture active', 'scratch', 'mode_scratch'] },
  { valeur: 'lecture',        motifs: ['lecture seule', 'lecture', 'read', 'mode_read'] },
];

export function normaliserTexteMode(texte) {
  return texte.trim().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
}

// Traduit le texte brut de la cellule « | MODE | … | » en valeur de radio.
// Absent (chaîne vide/null) ou non reconnu → 'lecture' (défaut sûr).
export function reconnaitreModeTexte(brut) {
  if (!brut) return 'lecture';
  const normalise = normaliserTexteMode(brut);
  const trouve = MODE_SYNONYMES.find(({ motifs }) =>
    motifs.some(m => normalise.includes(normaliserTexteMode(m))));
  return trouve ? trouve.valeur : 'lecture';
}

// Même garde-fou « valeur détectée changée » que detecterProjetDansCorps/
// detecterTimeoutDansCorps : en régime stable (rien de neuf dans le corps), un
// choix manuel du radio n'est jamais réécrasé — seul un changement effectif du
// signal détecté (apparition/disparition/modification du champ MODE)
// déclenche une resynchronisation.
let dernierModeAutoDetecte = null;
function detecterModeDansCorps() {
  // Mode LOT : cette pré-sélection LIVE du radio pendant la frappe reste
  // désactivée — un lot peut mélanger plusieurs modes (issue #505), il n'y a
  // donc plus une seule valeur « détectée » à refléter sur le radio unique du
  // formulaire pendant la saisie. Le radio du formulaire garde son rôle de
  // repli (mode par défaut des blocs sans MODE propre) ; le mode RÉEL de
  // chaque bloc, lui, est lu par bloc à l'envoi (modeEffectifBloc, envoyerLot).
  if (enModeLot()) { dernierModeAutoDetecte = null; return; }
  const corpsEl = document.getElementById('corps');
  const brut = lireChampEntete(corpsEl.value, 'MODE');
  const valeurDetectee = reconnaitreModeTexte(brut);

  // Rien de neuf depuis la dernière détection : ne pas réécraser un éventuel
  // choix manuel d'Alain.
  if (valeurDetectee === dernierModeAutoDetecte) return;
  dernierModeAutoDetecte = valeurDetectee;

  const radio = document.querySelector(`input[name=mode][value="${valeurDetectee}"]`);
  if (radio && !radio.checked) radio.checked = true;

  // Retire la ligne MODE du corps (comme TIMEOUT/PROJET), pour éviter que
  // construire_body empile un second tableau d'en-tête — uniquement si le
  // champ était effectivement présent (rien à retirer sinon).
  if (brut) corpsEl.value = retirerLigneEntete(corpsEl.value, 'MODE');

  mettreAJourBoutonEnvoi();
}

// Résumé lecture seule des champs d'en-tête détectés dans le corps (issue #117).
// Sous le champ Titre, on affiche une petite série de badges listant, dans
// l'ordre du §6, les champs d'en-tête effectivement présents dans le corps
// collé — pour qu'Alain vérifie d'un coup d'œil ce qui a été reconnu (TIMEOUT,
// MODELE, etc.) sans rouvrir le textarea.
//
//   • un champ absent (ou vide) n'apparaît pas — pas de ligne « TIMEOUT : — » ;
//   • si aucun champ n'est reconnu (issue écrite à la main, hors workflow §12),
//     le bloc reste entièrement masqué ;
//   • le parsing réutilise lireChampEntete, la même logique que les détections
//     PROJET/TIMEOUT — aucune regex dupliquée qui pourrait diverger ;
//   • purement informatif : n'interfère pas avec l'alerte d'incohérence #44,
//     qui reste pilotée par detecterIncoherenceProjet à l'envoi.
const CHAMPS_ENTETE_RESUME = [
  'PROJET', 'PRIORITE', 'TIMEOUT', 'MODELE',
  'TYPE', 'SPECS', 'SUITE_DE', 'FICHIER_CONTEXTE', 'LABELS',
];
function mettreAJourResumeEntete() {
  const corps = document.getElementById('corps').value;
  const bloc  = document.getElementById('resume-entete');
  // En mode lot, ce résumé mono (qui ne lirait que le 1er bloc) serait trompeur :
  // on le masque, le récapitulatif du lot s'affiche après l'envoi (issue #135).
  if (enModeLot()) { bloc.style.display = 'none'; bloc.innerHTML = ''; return; }
  const badges = [];
  for (const champ of CHAMPS_ENTETE_RESUME) {
    // Lit d'abord le corps ; à défaut (PROJET/TIMEOUT désormais RETIRÉS du corps
    // après extraction, #129) retombe sur la valeur mémorisée à l'extraction —
    // ainsi le résumé reste une confirmation fiable même une fois la ligne ôtée.
    const valeur = lireChampEntete(corps, champ) || champsEnteteExtraits[champ];
    if (!valeur) continue;                 // champ absent/vide → pas de badge
    badges.push('<span class="badge-entete"><b>' + champ + '</b>'
                + escapeHtml(valeur) + '</span>');
  }
  if (!badges.length) {                    // aucun champ reconnu → bloc masqué
    bloc.style.display = 'none';
    bloc.innerHTML = '';
    return;
  }
  bloc.innerHTML = badges.join('');
  bloc.style.display = 'flex';
}

// ─── Envoi en lot de plusieurs issues (issue #135) ────────────────────────
// Un seul copier-coller peut contenir PLUSIEURS blocs « #Titre: … » à la
// suite : chacun devient une issue indépendante, envoyée en séquence sans
// validation intermédiaire. On généralise detecterTitreDansCorps (qui, depuis
// #679, ne traite qu'UNE seule occurrence de « #Titre: », n'importe où dans la
// zone d'en-tête) en appliquant la même règle à CHAQUE ligne « #Titre: », sur
// tout le corps, insensible à la casse, en début de ligne.

// Découpe le corps en blocs, un par ligne « #Titre: ». Chaque bloc va de son
// « #Titre: » jusqu'au « #Titre: » suivant (exclu) ou la fin du corps ; on en
// extrait le titre (texte après « #Titre: », trim) et le reste du bloc (la
// ligne « #Titre: » retirée), exactement comme le flux mono-issue mais appliqué
// à un fragment. Retourne un tableau de {titre, corps} — vide si aucune ligne
// « #Titre: » n'est trouvée (→ pas de mode lot, comportement inchangé).
export function decouperCorpsEnBlocs(corps) {
  const texte = corps || '';
  // Index de début de chaque ligne « #Titre: » (même règle que
  // detecterTitreDansCorps : ancré en début de ligne, casse ignorée).
  const debuts = [];
  const re = /^#titre:/gim;
  let m;
  while ((m = re.exec(texte)) !== null) {
    debuts.push(m.index);
    if (re.lastIndex === m.index) re.lastIndex++;   // garde anti-boucle infinie
  }
  if (!debuts.length) return [];                      // aucun #Titre: → pas de lot

  const blocs = [];
  for (let i = 0; i < debuts.length; i++) {
    const debut = debuts[i];
    const fin   = i + 1 < debuts.length ? debuts[i + 1] : texte.length;
    const fragment = texte.slice(debut, fin);
    // Même découpage que detecterTitreDansCorps, appliqué au fragment : la 1re
    // ligne porte « #Titre: … », le titre est ce qui suit (trim), le corps du
    // bloc est le reste du fragment, cette ligne retirée.
    const finLigne      = fragment.indexOf('\n');
    const premiereLigne = finLigne === -1 ? fragment : fragment.slice(0, finLigne);
    const titre = premiereLigne.replace(/^#titre:\s*/i, '').trim();
    const corpsBloc = finLigne === -1 ? '' : fragment.slice(finLigne + 1);
    blocs.push({titre: titre, corps: corpsBloc.trim()});
  }
  return blocs;
}

// Vrai dès que le corps contient 2 blocs « #Titre: » ou plus → mode lot. Sert de
// garde-fou aux détections mono (titre/projet/timeout) et pilote le bouton.
function enModeLot() {
  return decouperCorpsEnBlocs(document.getElementById('corps').value).length >= 2;
}

// Projet effectivement ciblé par un bloc de lot : son champ « PROJET » d'en-tête
// s'il est présent, sinon le projet du formulaire en repli. Source unique de
// cette logique de repli, partagée par mettreAJourBoutonLot (libellé du bouton)
// et envoyerLot (envoi réel) pour qu'elles ne puissent pas diverger (issue #142).
export function projetEffectifBloc(bloc, projetForm) {
  return lireChampEntete(bloc.corps, 'PROJET') || projetForm;
}

// Mode effectivement appliqué à un bloc de lot : son champ « MODE » d'en-tête
// s'il est présent (reconnu de façon tolérante, cf. reconnaitreModeTexte —
// les trois modes lecture/lecture active/écriture), sinon le mode du radio du
// formulaire en repli. Même principe de repli que projetEffectifBloc, source
// unique partagée par mettreAJourBoutonLot et envoyerLot (issue #505) : jusqu'ici
// le MODE restait commun à tout le lot (radio du formulaire uniquement) — un lot
// peut désormais mélanger les trois modes, un par bloc.
export function modeEffectifBloc(bloc, modeForm) {
  const brut = lireChampEntete(bloc.corps, 'MODE');
  return brut ? reconnaitreModeTexte(brut) : modeForm;
}

// Bascule le bouton d'envoi entre mode mono-issue et mode lot selon le contenu
// du corps. En lot : « Envoyer le lot (N issues) sur <projet(s)> » → envoyerLot ;
// sinon on restaure le bouton normal « Envoyer sur <projet> » → envoyerIssue.
// Les projets ET les modes ciblés sont calculés bloc par bloc (même repli que
// envoyerLot) pour donner à Alain la même confirmation visuelle qu'en mono-issue
// (issue #142, étendu au mode mixte par #505).
//
// Depuis l'issue #652 (sortie d'app.js) : ne réaffecte plus btn.onclick — le
// bouton porte data-action="creation-envoyer" et le gestionnaire délégué
// (installerDelegationCreation) choisit envoyerLot/envoyerIssue selon enModeLot()
// à chaque clic. Cette fonction ne pilote donc plus que le LIBELLÉ.
function mettreAJourBoutonLot() {
  const blocs = decouperCorpsEnBlocs(document.getElementById('corps').value);
  const btn   = document.getElementById('btn-envoyer');
  if (blocs.length >= 2) {
    const projetForm = document.getElementById('projet').value;
    const modeForm    = document.querySelector('input[name=mode]:checked').value;
    // Ensembles ordonnés des projets/modes distincts effectivement ciblés par le lot.
    const projets = [];
    const modes   = [];
    for (const bloc of blocs) {
      const p = projetEffectifBloc(bloc, projetForm);
      if (p && !projets.includes(p)) projets.push(p);
      const m = modeEffectifBloc(bloc, modeForm);
      if (m && !modes.includes(m)) modes.push(m);
    }
    let suffixe = '';
    if (projets.length === 1) {
      suffixe = ' sur ' + projets[0];
    } else if (projets.length > 1) {
      suffixe = ' sur plusieurs projets (' + projets.join(', ') + ')';
    }
    // Signale les modes mixtes (issue #505) : le lot n'utilise plus un mode
    // unique commun, chaque bloc peut porter le sien.
    if (modes.length > 1) {
      suffixe += ' — modes mixtes';
    }
    btn.textContent = 'Envoyer le lot (' + blocs.length + ' issues)' + suffixe;
  } else {
    btn.textContent = 'Envoyer sur ' + document.getElementById('projet').value;
  }
}

// Récapitulatif du lot : réutilise le style de #message (zone dédiée #resume-lot).
// Une ligne par bloc : ✓ titre → lien de l'issue créée, ou ✗ titre — erreur.
// Signale sans bloquer les blocs partis sur un PROJET différent du formulaire.
function afficherResumeLot(resultats, projetForm) {
  const zone  = document.getElementById('resume-lot');
  const ok    = resultats.filter(r => r.succes).length;
  const total = resultats.length;
  const lignes = resultats.map(r => {
    const titre = escapeHtml(r.titre || '(sans titre)');
    if (r.succes) {
      let l = '✓ ' + titre + ' → <a href="' + escapeHtml(r.url) + '" target="_blank">'
              + escapeHtml(r.url) + '</a>';
      if (r.incoherence) {
        l += ' <em>(envoyée sur « ' + escapeHtml(r.projet)
             + ' », ≠ projet sélectionné « ' + escapeHtml(projetForm) + ' »)</em>';
      }
      return l;
    }
    return '✗ ' + titre + ' — ' + escapeHtml(r.erreur);
  });
  zone.className   = 'message ' + (ok === total ? 'succes' : 'erreur');
  zone.innerHTML   = '<b>Lot terminé : ' + ok + '/' + total + ' issue(s) créée(s).</b><br>'
                     + lignes.join('<br>');
  zone.style.display = 'block';
}

// Envoi séquentiel du lot. Chaque bloc devient un objet data sur le modèle de
// collecterFormulaire : titre/corps propres au bloc, PROJET/PRIORITE/TIMEOUT/
// MODELE/MODE lus dans le bloc (repli sur le formulaire — MODE mixte par bloc
// depuis l'issue #505, seuls les notifs restent communs à tout le lot). Envoi
// UN PAR UN (await entre chaque, jamais en parallèle → pas de conflit gh). AUCUNE
// modale (issues en attente / incohérence projet) : le but du lot est d'enchaîner
// sans validation. Un bloc en échec n'interrompt pas le lot ; tout est reporté
// dans le résumé final. (issue #135)
async function envoyerLot() {
  // Anti-double-clic (issue #189) : même logique que envoyerIssue() — on
  // désactive le bouton dès le TOUT DÉBUT, avant même le découpage/validation des
  // blocs, et on ne le réactive qu'à la toute fin (bloc finally). Un double-clic
  // rapide ne peut donc pas relancer un second lot pendant le premier.
  const btn = document.getElementById('btn-envoyer');
  if (btn.disabled) return;   // envoi déjà en cours : on ignore ce clic
  btn.disabled = true;
  try {
    cacherRetours();
    const blocs = decouperCorpsEnBlocs(document.getElementById('corps').value);
    if (blocs.length < 2) return;                 // sécurité : bouton lot masqué sinon

    // Garde-fou titre : aucun bloc ne doit avoir un titre vide après « #Titre: ».
    // Si un ou plusieurs sont fautifs, on abandonne TOUT le lot (aucun envoi) et on
    // affiche la même modale d'erreur que le mono-issue, listant les blocs fautifs.
    const sansTitre = [];
    blocs.forEach((b, i) => { if (!b.titre) sansTitre.push(i + 1); });
    if (sansTitre.length) {
      const nums = sansTitre.map(n => 'le bloc ' + n);
      let liste;
      if (nums.length === 1) {
        liste = nums[0];
      } else {
        liste = nums.slice(0, -1).join(', ') + ' et ' + nums[nums.length - 1];
      }
      const verbe = sansTitre.length === 1 ? "n'a" : "n'ont";
      await afficherModalErreur('Titre manquant',
        liste.charAt(0).toUpperCase() + liste.slice(1)
        + ' ' + verbe + ' pas de titre après #Titre:. Aucune issue du lot n\'a été '
        + 'envoyée : corrige le corps puis relance.');
      return;
    }

    const base       = collecterFormulaire();     // valeurs communes/de repli
    const projetForm = base.projet;

    const resultats = [];
    // Comme en mono-issue (issue #202), le backend démarre le watcher des blocs
    // for-linux dont le watcher était éteint. On note simplement s'il y a eu au
    // moins un démarrage pour l'annoncer discrètement en fin de lot, sans jamais
    // bloquer l'envoi (aucune modale « watcher inactif » n'existait ici).
    let watcherDemarre = false;
    for (let i = 0; i < blocs.length; i++) {
      const bloc = blocs[i];
      btn.textContent = 'Envoi ' + (i + 1) + '/' + blocs.length + '…';

      // Champs d'en-tête lus dans le bloc ; repli sur les valeurs du formulaire.
      const projetBloc   = lireChampEntete(bloc.corps, 'PROJET');
      const timeoutBloc  = lireChampEntete(bloc.corps, 'TIMEOUT');
      const modeleBloc   = lireChampEntete(bloc.corps, 'MODELE');
      const prioriteBloc = lireChampEntete(bloc.corps, 'PRIORITE');
      const modeBloc     = lireChampEntete(bloc.corps, 'MODE');

      const projet = projetEffectifBloc(bloc, projetForm);
      // Mode mixte (issue #505) : chaque bloc peut porter son propre MODE,
      // repli sur le radio du formulaire — mêmes trois valeurs qu'en mono-issue.
      const mode   = modeEffectifBloc(bloc, base.mode);

      // Timeout : la cellule peut porter un suffixe « s » (ex. 1200s) ; on ne
      // conserve que les chiffres, comme detecterTimeoutDansCorps. Repli formulaire.
      let timeout = base.timeout;
      const mTimeout = timeoutBloc && timeoutBloc.match(/^(\d+)\s*s?$/i);
      if (mTimeout) timeout = mTimeout[1];

      // Corps du bloc : on retire les lignes d'en-tête effectivement lues (comme le
      // flux mono-issue) pour ne pas empiler un second tableau d'en-tête.
      let corpsBloc = bloc.corps;
      if (projetBloc)  corpsBloc = retirerLigneEntete(corpsBloc, 'PROJET');
      if (timeoutBloc) corpsBloc = retirerLigneEntete(corpsBloc, 'TIMEOUT');
      if (modeleBloc)  corpsBloc = retirerLigneEntete(corpsBloc, 'MODELE');
      if (modeBloc)    corpsBloc = retirerLigneEntete(corpsBloc, 'MODE');

      const data = {
        projet:          projet,
        titre:           bloc.titre,
        priorite:        prioriteBloc || base.priorite,
        timeout:         timeout,
        mode:            mode,
        notifs:          base.notifs,
        corps:           corpsBloc.trim(),
        modele_ponctuel: modeleBloc || base.modele_ponctuel,
      };

      // PROJET du bloc ≠ projet sélectionné : on envoie quand même sur le PROJET du
      // bloc (pas de modale bloquante en lot) et on le signale dans le résumé.
      const incoherence = !!projetBloc &&
        projetBloc.toLowerCase() !== (projetForm || '').toLowerCase();

      try {
        const rep = await fetch('/envoyer', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(data)
        });
        const json = await rep.json();
        if (json.succes) {
          if (json.watcher_demarre === true) watcherDemarre = true;
          resultats.push({succes: true, titre: bloc.titre, projet: projet,
                          url: json.url, incoherence: incoherence});
        } else {
          signalerEchecPossible(json);   // issue #732, même logique que l'envoi mono-issue
          resultats.push({succes: false, titre: bloc.titre, projet: projet,
                          erreur: json.erreur || 'erreur inconnue'});
        }
      } catch(e) {
        // Échec d'un bloc : on note et on continue le lot (ne pas interrompre).
        resultats.push({succes: false, titre: bloc.titre, projet: projet,
                        erreur: 'réseau : ' + e.message});
      }
    }

    afficherResumeLot(resultats, projetForm);
    if (watcherDemarre) {
      afficherToast('Watcher démarré automatiquement pour au moins une issue du lot');
    }
    // Vide le corps une fois le lot terminé (comme envoyerIssue après un succès),
    // sans masquer le récapitulatif qu'on vient d'afficher.
    viderFormulaire(false);
  } finally {
    // Réactivation garantie du bouton (succès, échec, ou sortie anticipée).
    btn.disabled = false;
    // Le corps a été vidé par programme (pas d'event « input ») : on rebascule
    // explicitement le bouton en mode mono.
    mettreAJourBoutonLot();
  }
}

function viderFormulaire(cacherMsg=true) {
  if (cacherMsg) cacherRetours();
  document.getElementById('titre').value = '';
  document.getElementById('corps').value = '';
  document.getElementById('priorite').value = 'normale';
  // Réinitialise le timeout sur la valeur TIMEOUT_CLAUDE du projet courant.
  appelerAncien('mettreAJourInfoProjet');
  document.querySelector('input[name=mode][value=lecture]').checked = true;
  // Réinitialise le garde-fou de detecterModeDansCorps (#335) : sans ça, coller
  // ensuite un corps portant le MÊME MODE que la détection précédente est vu
  // comme « rien de neuf » (ligne ~3812) et le radio — pourtant remis de force à
  // lecture juste au-dessus, pas par un choix manuel d'Alain — ne rebasculait
  // pas sur la valeur collée. D'où le symptôme intermittent (dépend de si le
  // MODE collé diffère du précédent) qu'un F5 « corrigeait » en réinitialisant
  // cette variable JS à null.
  dernierModeAutoDetecte = null;
  mettreAJourBoutonEnvoi();
  document.querySelectorAll('input[name=notifs]').forEach(c => c.checked = false);
  // notif_pc revient à l'état mémorisé (coché par défaut), pas à décoché.
  appliquerNotifPc();
  document.getElementById('modele-ponctuel').value = '';
  // Réinitialise le champ de pièce jointe image (issue #191) : fichier choisi,
  // bouton (redésactivé) et message d'état.
  const inputImage = document.getElementById('image-jointe');
  if (inputImage) inputImage.value = '';
  const msgImage = document.getElementById('image-jointe-msg');
  if (msgImage) msgImage.textContent = '';
  majEtatBoutonImage();
  // Réinitialise l'état des détections d'en-tête (issues #117/#129) : sans ça,
  // un ancien PROJET/TIMEOUT mémorisé empêcherait de redétecter la même valeur
  // au prochain collage, et le résumé afficherait des champs d'une issue passée.
  dernierProjetAutoDetecte  = null;
  dernierTimeoutAutoDetecte = null;
  champsEnteteExtraits      = {};
  // Le corps est vidé par programme (pas d'event « input ») : on masque
  // explicitement le résumé d'en-tête (issue #117).
  mettreAJourResumeEntete();
  // Désélectionne le template chargé (issue #284) : un formulaire vidé ne
  // reflète plus aucun template en particulier.
  const selectTemplate = document.getElementById('template-select');
  if (selectTemplate) selectTemplate.value = '';
  onTemplateSelectChange();
}

// ─── Mémorisation de notif_pc (issue #93) ─────────────────────────────────
// notif_pc est coché par défaut au premier usage. Si Alain le décoche, ce
// choix est mémorisé (localStorage) et respecté aux ouvertures suivantes,
// jusqu'à ce qu'il le recoche. Cohérent avec le pattern des autres clés
// « bridge_* » de l'interface. notif_gsm / notif_tous ne sont pas concernés.
//
// Depuis l'issue #652, la lecture/écriture passe par la brique persistance du
// socle (import direct), et non plus par window.Bridge.persistance : notif_pc
// n'est utilisée QUE par ce formulaire (vérifié par grep — le panneau latéral,
// lui, dérive l'état des cases 🔔 des labels GitHub de l'issue, cf.
// panneau_lateral.js#etatsCasesNotif, sans lire cette clé). Aucune
// factorisation supplémentaire nécessaire : la clé (persistance.CLES.notifPc)
// est déjà l'unique point d'accès depuis #644.

// Applique l'état mémorisé au champ notif_pc : coché par défaut si la clé
// n'existe pas encore, sinon l'état enregistré ('true' / 'false').
function appliquerNotifPc() {
  const cb = document.getElementById('notif_pc');
  if (!cb) return;
  const memo = persistance.lireTexte(persistance.CLES.notifPc);
  cb.checked = (memo === null) ? true : (memo === 'true');
}

// ─── Délégation d'événements (remplace les onclick=/onchange= inline du
//     fragment onglet_creation.html, refonte web §6.7) ─────────────────────
function installerDelegationCreation() {
  // Bibliothèque de templates (issue #284).
  dom.surAction('[data-action="creation-template-change"]',    'change', () => onTemplateSelectChange());
  dom.surAction('[data-action="creation-template-modifier"]',  'click',  () => modifierTemplateSelectionne());
  dom.surAction('[data-action="creation-template-supprimer"]', 'click',  () => supprimerTemplateSelectionne());

  // Mode (radios) : recolore le bouton d'envoi selon le mode choisi.
  dom.surAction('[data-action="creation-mode"]', 'change', () => mettreAJourBoutonEnvoi());

  // Barre d'envoi.
  dom.surAction('[data-action="creation-vider"]',          'click', () => viderFormulaire());
  dom.surAction('[data-action="creation-apercu"]',         'click', () => afficherApercu());
  dom.surAction('[data-action="creation-creer-template"]', 'click', () => creerTemplate());
  // Un seul point d'entrée pour le bouton d'envoi : mono ou lot selon le corps
  // (remplace l'ancien basculement de btn.onclick fait par mettreAJourBoutonLot).
  dom.surAction('[data-action="creation-envoyer"]', 'click',
    () => (enModeLot() ? envoyerLot() : envoyerIssue()));

  // Pièce jointe image (issue #191/#192).
  dom.surAction('[data-action="creation-image-change"]',  'change', () => majEtatBoutonImage());
  dom.surAction('[data-action="creation-joindre-image"]', 'click',  () => joindreImage());

  // Détecteurs d'en-tête à la frappe + résumé + bascule mono/lot du bouton.
  // Enregistrés dans le MÊME ORDRE que les anciens addEventListener('input')
  // d'app.js : detecterTitre → PROJET → TIMEOUT → MODE → résumé → bouton lot.
  // La brique de délégation (socle/dom.js) exécute les règles d'un même type
  // dans leur ordre d'enregistrement — l'ordre est donc préservé. insererDansCorps
  // (joindreImage) redéclenche cet enchaînement via un Event('input', bubbles:true).
  dom.surAction('#corps', 'input', () => detecterTitreDansCorps());
  dom.surAction('#corps', 'input', () => detecterProjetDansCorps());
  dom.surAction('#corps', 'input', () => detecterTimeoutDansCorps());
  dom.surAction('#corps', 'input', () => detecterModeDansCorps());
  dom.surAction('#corps', 'input', () => mettreAJourResumeEntete());
  dom.surAction('#corps', 'input', () => mettreAJourBoutonLot());
}

// ─── Point d'entrée (idempotent), appelé par onglets.js à l'activation de
//     l'onglet « Nouvelle issue » — par import direct, plus par le pont ──────
let creationInitialisee = false;
export function initCreation() {
  if (creationInitialisee) return;
  creationInitialisee = true;
  installerDelegationCreation();

  // Mémorisation de notif_pc (issue #93) : écouteur de changement + application
  // de l'état mémorisé. Remplace l'ancien window.addEventListener('DOMContentLoaded')
  // d'app.js — l'onglet n'étant interactif qu'une fois affiché, appliquer l'état
  // à sa première activation est équivalent, et window.Bridge existe forcément ici.
  const cbNotif = document.getElementById('notif_pc');
  if (cbNotif) {
    cbNotif.addEventListener('change', function() {
      persistance.ecrireTexte(persistance.CLES.notifPc, cbNotif.checked ? 'true' : 'false');
    });
  }
  appliquerNotifPc();
}

// ─── Pont ancien → creation (à retirer avec le pont, fin de refonte) ───────
// app.js (script CLASSIQUE, ne peut pas importer ce module) appelle encore ces
// fonctions par leur nom : chargerTemplates() au changement de projet global
// (onProjetChange) et afficherMessage() pour les erreurs du bouton watcher
// (lancerWatcher). On les publie en globales window.* dès l'évaluation du module
// (avant DOMContentLoaded), comme panneau_lateral.js le fait dans l'autre sens.
if (typeof window !== 'undefined') {
  window.chargerTemplates = chargerTemplates;
  window.afficherMessage  = afficherMessage;
}
