let sourceSSE = null;

let intervalWatchers = null;

// SOURCE UNIQUE DE VÉRITÉ pour la couleur de chaque projet (issue #120).
// Utilisée à la fois pour l'accent du formulaire (couleurProjet) et pour les
// pastilles/badges/boutons de l'onglet Résultats (couleurProjetResultats).
// Les 5 couleurs sont volontairement distinctes visuellement.
const COULEURS_PROJET = {
  'bridge_agent': '#185FA5',  // bleu
  'alchess':      '#3B6D11',  // vert
  'ff_galerie':   '#BA7517',  // orange
  'scrabble':     '#0E8A82',  // turquoise
  'ecole':        '#6B3FA0',  // violet
};

// Couleur de secours STABLE dérivée du nom du projet (hash simple sur les
// charCodes → teinte HSL). Même nom ⇒ même couleur à chaque session. Sert
// uniquement aux projets pas encore présents dans COULEURS_PROJET (nouveau
// projet créé via le modal avant qu'on lui attribue une couleur dédiée).
function couleurHashProjet(nom) {
  let h = 0;
  for (let i = 0; i < nom.length; i++) {
    h = (h * 31 + nom.charCodeAt(i)) % 360;
  }
  return 'hsl(' + ((h + 360) % 360) + ', 60%, 34%)';
}

// Couleur du projet, par ordre de priorité (issue #121) :
//   1. couleur persistée dans le .conf (champ COULEUR), exposée par
//      lister_projets() et injectée dans window.COULEURS_PERSISTEES ;
//   2. sinon la map fixe COULEURS_PROJET (projets historiques sans ce champ) ;
//   3. sinon le hash HSL de secours (nouveau projet pas encore configuré),
//      plutôt qu'un gris uniforme, pour qu'il reste distinguable.
function couleurProjet(nom) {
  const persistees = window.COULEURS_PERSISTEES || {};
  return persistees[nom] || COULEURS_PROJET[nom] || couleurHashProjet(nom);
}

// Applique l'accent visuel du projet : bordure gauche du select et du bandeau,
// et libellé « Projet actif : … » en grand, tous de la même couleur.
function appliquerAccentProjet(nom) {
  const couleur = couleurProjet(nom);
  const select  = document.getElementById('projet');
  const bandeau = document.querySelector('.bandeau-projet');
  const label   = document.getElementById('projet-actif-label');
  if (select)  select.style.borderLeftColor  = couleur;
  if (bandeau) bandeau.style.borderLeftColor  = couleur;
  if (label) {
    label.textContent = 'Projet actif : ' + nom;
    label.style.color = couleur;
  }
}

function basculerOnglet(nom) {
  const noms = ['creation', 'resultats', 'journal', 'config', 'watchers'];
  document.querySelectorAll('.onglet').forEach((o, i) =>
    o.classList.toggle('actif', noms[i] === nom));
  noms.forEach(n =>
    document.getElementById('panneau-' + n).classList.toggle('actif', n === nom));
  if (nom === 'journal')  demarrerJournal();
  if (nom === 'resultats') { chargerListeIssues(); demarrerTempsRestant(); }
  else arreterTempsRestant();
  if (nom === 'watchers') {
    chargerWatchers();
    intervalWatchers = setInterval(chargerWatchers, 5000);
  } else {
    clearInterval(intervalWatchers);
  }
  if (nom === 'config') chargerConfig();
}

// reinitialiserTimeout : un changement de projet MANUEL (sélecteur, chargement
// initial, ajouterProjetAuSelecteur) doit recharger le timeout par défaut du
// projet. En revanche, la détection d'en-tête (detecterProjetDansCorps) appelle
// onProjetChange(false) pour NE PAS écraser le TIMEOUT collé, dont la pose reste
// la seule responsabilité de detecterTimeoutDansCorps (issue #143).
function onProjetChange(reinitialiserTimeout = true) {
  const nom = document.getElementById('projet').value;
  // Mémorise le projet choisi pour le restaurer à la prochaine ouverture.
  try { localStorage.setItem('bridge_projet_actif', nom); } catch(e) {}
  appliquerAccentProjet(nom);
  verifierStatut();
  mettreAJourInfoProjet(reinitialiserTimeout);
  // L'onglet Résultats est indépendant du sélecteur global (il agrège tous
  // les projets) : on ne le recharge donc PAS ici.
  // Si l'onglet Configuration est actif, recharger sa config pour le
  // nouveau projet (l'onglet lit désormais le sélecteur global #projet).
  if (document.getElementById('panneau-config').classList.contains('actif')) {
    chargerConfig();
  }
}

async function mettreAJourInfoProjet(reinitialiserTimeout = true) {
  const nom = document.getElementById('projet').value;
  try {
    const rep = await fetch('/config/' + encodeURIComponent(nom));
    const cfg = await rep.json();
    const depEl = document.getElementById('info-depot');
    const repEl = document.getElementById('info-rep-travail');
    const perEl = document.getElementById('info-perimetre');
    depEl.textContent = '📦 ' + cfg.depot;
    repEl.textContent = ' · 📁 ' + cfg.rep_travail;
    if (cfg.perimetre) {
      perEl.textContent = ' · 🔒 ' + cfg.perimetre;
    } else {
      perEl.textContent = '';
    }
    // Le timeout par défaut suit la valeur TIMEOUT_CLAUDE du projet sélectionné.
    // On ne réinitialise le champ QUE lors d'un changement de projet manuel :
    // lors d'une détection d'en-tête (reinitialiserTimeout=false), le TIMEOUT
    // collé, déjà posé par detecterTimeoutDansCorps, doit être préservé (#143).
    if (reinitialiserTimeout) {
      document.getElementById('timeout').value = cfg.timeout_claude || 300;
    }
    // Le libellé du bouton d'envoi affiche le projet cible pour éviter les
    // envois sur le mauvais projet.
    document.getElementById('btn-envoyer').textContent = 'Envoyer sur ' + cfg.nom;
  } catch(e) {}
}

async function chargerConfig() {
  const nom = document.getElementById('projet').value;
  try {
    const rep = await fetch('/config/' + encodeURIComponent(nom));
    const cfg = await rep.json();

    document.getElementById('config-readonly').innerHTML =
      `NOM = ${cfg.nom}<br>DEPOT = ${cfg.depot}<br>` +
      `REP_TRAVAIL = ${cfg.rep_travail}<br>` +
      (cfg.perimetre  ? `PERIMETRE = ${cfg.perimetre}<br>` : '') +
      (cfg.cmd_backup ? `CMD_BACKUP = ${cfg.cmd_backup}` : '');

    document.getElementById('conf-TOPIC_NTFY').value        = cfg.topic_ntfy        || '';
    document.getElementById('conf-LABEL').value             = cfg.label             || 'for-linux';
    document.getElementById('conf-INTERVALLE').value        = cfg.intervalle        || 10;
    document.getElementById('conf-MAX_ESSAIS').value        = cfg.max_essais        || 3;
    document.getElementById('conf-TIMEOUT_CLAUDE').value    = cfg.timeout_claude    || 300;
    document.getElementById('conf-SCRIPT_BIP').value        = cfg.script_bip        || '';
    document.getElementById('conf-FICHIER_CONTEXTE').value  = cfg.fichier_contexte  || '';
    document.getElementById('conf-MODELE_CCL').value        = cfg.modele_ccl        || '';
    document.getElementById('conf-LOG_TAILLE_MAX_MO').value = cfg.log_taille_max_mo || 1;
    document.getElementById('conf-LOG_ARCHIVES').value      = cfg.log_archives      || 5;
    document.getElementById('msg-config').style.display = 'none';
  } catch(e) {
    const msg = document.getElementById('msg-config');
    msg.textContent = 'Erreur de chargement : ' + e.message;
    msg.className = 'message erreur'; msg.style.display = 'block';
  }
}

async function sauvegarderConfig(relancer) {
  const nom = document.getElementById('projet').value;
  const data = {
    TOPIC_NTFY:        document.getElementById('conf-TOPIC_NTFY').value,
    LABEL:             document.getElementById('conf-LABEL').value,
    INTERVALLE:        document.getElementById('conf-INTERVALLE').value,
    MAX_ESSAIS:        document.getElementById('conf-MAX_ESSAIS').value,
    TIMEOUT_CLAUDE:    document.getElementById('conf-TIMEOUT_CLAUDE').value,
    SCRIPT_BIP:        document.getElementById('conf-SCRIPT_BIP').value,
    FICHIER_CONTEXTE:  document.getElementById('conf-FICHIER_CONTEXTE').value,
    MODELE_CCL:        document.getElementById('conf-MODELE_CCL').value,
    LOG_TAILLE_MAX_MO: document.getElementById('conf-LOG_TAILLE_MAX_MO').value,
    LOG_ARCHIVES:      document.getElementById('conf-LOG_ARCHIVES').value,
  };
  const rep  = await fetch('/config/' + encodeURIComponent(nom), {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data)
  });
  const json = await rep.json();
  const msg  = document.getElementById('msg-config');
  msg.textContent = json.message;
  msg.className   = 'message ' + (json.succes ? 'succes' : 'erreur');
  msg.style.display = 'block';
  if (json.succes && relancer) {
    await fetch('/lancer-watcher', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({projet: nom, relancer: true})
    });
    msg.textContent += ' Watcher relancé.';
  }
}

function demarrerJournal() {
  if (sourceSSE) { sourceSSE.close(); sourceSSE = null; }
  const nom = document.getElementById('projet').value;
  document.getElementById('label-journal').textContent = 'logs/watcher-' + nom + '.log';
  document.getElementById('terminal').innerHTML = '';
  sourceSSE = new EventSource('/journal/' + encodeURIComponent(nom));
  sourceSSE.onmessage = function(e) {
    const term = document.getElementById('terminal');
    const div = document.createElement('div');
    const t = e.data;
    if (t.includes('[WARNING]') || t.includes('⚠'))  div.className = 'log-warn';
    else if (t.includes('[ERROR]'))                    div.className = 'log-err';
    else if (t.includes('✓') || t.includes('succès')) div.className = 'log-ok';
    else                                               div.className = 'log-info';
    div.textContent = t;
    // Les lignes les plus récentes s'affichent en haut
    term.insertBefore(div, term.firstChild);
    term.scrollTop = 0;
  };
  sourceSSE.onerror = function() {
    const term = document.getElementById('terminal');
    const div = document.createElement('div');
    div.className = 'log-warn';
    div.textContent = '— connexion perdue, tentative de reconnexion…';
    term.insertBefore(div, term.firstChild);
    term.scrollTop = 0;
  };
}

function viderTerminal() {
  document.getElementById('terminal').innerHTML = '';
}

// ─── Onglet Résultats : visualisation des issues ──────────────────────────

// Préfixe visuel d'une issue selon ses labels.
// needs-human prime sur tout ; sinon mode_write (✏️) puis done (✅) se cumulent ;
// à défaut, ○.
function prefixeIssue(labels) {
  const noms = (labels || []).map(l => ((l && l.name) || l || '').toLowerCase());
  if (noms.includes('needs-human')) return '⚠️';
  let p = '';
  if (noms.includes('mode_write')) p += '✏️';
  if (noms.includes('done'))       p += '✅';
  return p || '○';
}

// Détecte le TYPE d'une issue dans le pattern chef/ouvriers (issue #86).
// Renvoie 'ouvrier', 'chef' ou '' (issue normale). Trois signaux, l'un suffit :
//  - un label dont le nom contient « ouvrier » ou « chef » ;
//  - le titre commençant par « Ouvrier » ou « Chef » (insensible à la casse,
//    ex. « Ouvrier 3 : ... ») ;
//  - le corps contenant | TYPE | ouvrier | ou | TYPE | chef | (le corps n'est
//    disponible qu'au détail ; en liste la détection repose sur titre/labels).
// « ouvrier » est prioritaire sur « chef ».
function typeIssue(it) {
  const noms = ((it && it.labels) || [])
    .map(l => ((l && l.name) || l || '').toLowerCase());
  if (noms.some(n => n.includes('ouvrier'))) return 'ouvrier';
  if (noms.some(n => n.includes('chef')))    return 'chef';
  const titre = ((it && it.title) || '').trim().toLowerCase();
  if (/^ouvrier\b/.test(titre)) return 'ouvrier';
  if (/^chef\b/.test(titre))    return 'chef';
  const body = ((it && it.body) || '').toLowerCase();
  if (/\|\s*type\s*\|\s*ouvrier\s*\|/.test(body)) return 'ouvrier';
  if (/\|\s*type\s*\|\s*chef\s*\|/.test(body))    return 'chef';
  return '';
}

// Préfixe emoji du TYPE d'une issue : 🎯 chef, 👷 ouvrier, rien sinon.
function prefixeTypeIssue(it) {
  const t = typeIssue(it);
  return t === 'chef' ? '🎯' : (t === 'ouvrier' ? '👷' : '');
}

// Badge coloré pour un label dans le panneau de détail.
function badgeLabel(nom) {
  const map = {
    'done':        {cls: 'succes',   txt: '✅ succès'},
    'needs-human': {cls: 'echec',    txt: '⚠️ échec'},
    'mode_write':  {cls: 'ecriture', txt: '✏️ écriture'},
    'bridge':      {cls: 'gris',     txt: 'bridge'},
    'for-linux':   {cls: 'gris',     txt: 'for-linux'},
  };
  const b = map[nom] || {cls: 'gris', txt: nom};
  return '<span class="badge-label ' + b.cls + '">' + escapeHtml(b.txt) + '</span>';
}

// ─── Onglet Résultats : vue consolidée multi-projets ──────────────────────
// L'onglet Résultats est INDÉPENDANT du sélecteur global : il agrège les
// issues de TOUS les projets, quel que soit le projet actif en haut.

// Couleur du projet pour l'onglet Résultats (pastilles, badges, boutons de
// filtre). Alias de couleurProjet : même source de vérité (COULEURS_PROJET)
// que l'accent du formulaire, donc couleur identique aux deux endroits.
function couleurProjetResultats(nom) {
  return couleurProjet(nom);
}

// Liste des noms de projets disponibles (lue depuis le sélecteur global, qui
// est peuplé côté serveur par lister_projets()).
function nomsProjetsDisponibles() {
  return [...document.getElementById('projet').options]
    .map(o => o.value).filter(Boolean);
}

// État de l'onglet Résultats : liste fusionnée des issues (chacune porte son
// projet source) + ensemble des projets actuellement affichés (filtre).
let listeIssuesResultats = [];
let projetsFiltresActifs = new Set();

// Clé localStorage du cache de la liste d'issues (issue #52). Affichage
// instantané depuis le cache, rafraîchi ensuite par un fetch d'arrière-plan.
const CLE_CACHE_ISSUES = 'bridge_cache_issues';

// Affiche/masque l'indicateur discret « Mise à jour… » sous la liste.
function majIndicateurListe(actif) {
  const el = document.getElementById('maj-indicateur');
  if (el) el.style.display = actif ? '' : 'none';
}

// Applique une liste d'issues à l'UI : filtres + boutons + rendu.
function appliquerListeIssues(liste, noms) {
  listeIssuesResultats = liste;
  projetsFiltresActifs = restaurerFiltresProjets(noms);
  filtreOuvriersActif  = restaurerFiltreOuvriers();
  construireBoutonsFiltre(noms);
  rendreListeIssues(true);
}

async function chargerListeIssues() {
  const zone = document.getElementById('liste-issues');
  const noms = nomsProjetsDisponibles();
  if (!noms.length) {
    zone.innerHTML = '<div class="issue-vide">Aucun projet</div>';
    return;
  }

  // 1) Affichage immédiat depuis le cache localStorage, s'il existe.
  let cache = null;
  try { cache = JSON.parse(localStorage.getItem(CLE_CACHE_ISSUES) || 'null'); } catch(e) {}
  const cacheAffiche = Array.isArray(cache) && cache.length > 0;
  if (cacheAffiche) {
    appliquerListeIssues(cache, noms);
  } else {
    zone.innerHTML = '<div class="issue-vide">Chargement…</div>';
  }

  // 2) Fetch d'arrière-plan des issues de chaque projet (jusqu'à 30 côté
  //    backend). Le nombre réellement affiché par projet est ensuite plafonné
  //    par un quota adaptatif dans appliquerFiltresListe() (issue #136), selon
  //    le nombre de projets actifs dans le filtre — plus de troncature ici.
  majIndicateurListe(true);
  try {
    const listes = await Promise.all(noms.map(async nom => {
      try {
        const rep = await fetch('/issues-liste/' + encodeURIComponent(nom));
        const liste = await rep.json();
        if (!Array.isArray(liste)) return [];
        // Toute la liste reçue (déjà plafonnée à 30 côté backend), triée par
        // date de création décroissante (plus récentes en premier).
        return liste
          .slice()
          .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))
          .map(it => Object.assign({}, it, {projet: nom}));
      } catch(e) {
        return [];
      }
    }));
    // Fusion + tri global par date de création décroissante (plus récentes en premier).
    const nouvelle = listes.flat().sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));

    // Ne re-render que si la liste a réellement changé : évite de perdre la
    // sélection courante quand le cache était déjà à jour.
    const inchangee = cacheAffiche && JSON.stringify(nouvelle) === JSON.stringify(cache);
    if (!inchangee) {
      appliquerListeIssues(nouvelle, noms);
    } else {
      listeIssuesResultats = nouvelle;
    }
    try { localStorage.setItem(CLE_CACHE_ISSUES, JSON.stringify(nouvelle)); } catch(e) {}
  } catch(e) {
    if (!cacheAffiche) zone.innerHTML = '<div class="issue-vide">Erreur de chargement</div>';
  } finally {
    majIndicateurListe(false);
  }
}

// Clé localStorage mémorisant l'état des boutons de filtre projet.
const CLE_FILTRES_RESULTATS = 'bridge_filtres_resultats';

// Lit l'état des filtres depuis localStorage → Set des projets actifs.
// Clé absente/illisible → tous actifs (comportement par défaut). Un projet
// n'est inactif que s'il est explicitement marqué false ; un projet apparu
// depuis la dernière sauvegarde (absent de l'objet) est donc actif.
function restaurerFiltresProjets(noms) {
  let brut = null;
  try { brut = localStorage.getItem(CLE_FILTRES_RESULTATS); } catch(e) {}
  if (!brut) return new Set(noms);
  let etat;
  try { etat = JSON.parse(brut); } catch(e) { return new Set(noms); }
  if (!etat || typeof etat !== 'object') return new Set(noms);
  return new Set(noms.filter(nom => etat[nom] !== false));
}

// ── Filtre « 👷 Ouvriers » (issue #86) ────────────────────────────────────
// Par défaut inactif → les issues de type ouvrier sont masquées dans Résultats.
// État persisté (true/false) sous cette clé ; absent/illisible → false.
const CLE_FILTRE_OUVRIERS = 'bridge_filtre_ouvriers';
let filtreOuvriersActif = false;

// Lit l'état du filtre ouvriers depuis localStorage (false par défaut).
function restaurerFiltreOuvriers() {
  try { return localStorage.getItem(CLE_FILTRE_OUVRIERS) === 'true'; }
  catch(e) { return false; }
}

// Bascule l'affichage des issues ouvrières, persiste l'état et ré-applique le
// filtre. Si la ligne sélectionnée devient masquée, on sélectionne la première
// encore visible.
function basculerFiltreOuvriers() {
  filtreOuvriersActif = !filtreOuvriersActif;
  try { localStorage.setItem(CLE_FILTRE_OUVRIERS, filtreOuvriersActif ? 'true' : 'false'); }
  catch(e) {}
  majBoutonOuvriers();
  appliquerFiltresListe();
  const sel = document.querySelector('#liste-issues .ligne-issue.selectionnee');
  if (!sel || sel.style.display === 'none') selectionnerPremiereVisible();
}

// Reflète l'état du filtre ouvriers sur le bouton toggle (grisé = inactif).
function majBoutonOuvriers() {
  const btn = document.getElementById('filtre-ouvriers');
  if (btn) btn.classList.toggle('inactif', !filtreOuvriersActif);
}

// Écrit l'état courant des filtres dans localStorage.
function sauvegarderFiltresProjets(noms) {
  const etat = {};
  for (const nom of noms) etat[nom] = projetsFiltresActifs.has(nom);
  try {
    localStorage.setItem(CLE_FILTRES_RESULTATS, JSON.stringify(etat));
  } catch(e) {}
}

// (Re)construit la ligne de boutons toggle — un par projet + « Tous ».
function construireBoutonsFiltre(noms) {
  const zone = document.getElementById('filtres-projets');
  zone.innerHTML = '';
  for (const nom of noms) {
    const btn = document.createElement('span');
    btn.className = 'filtre-projet';
    btn.dataset.projet = nom;
    // La couleur du projet est stockée en attribut data ; appliqueCouleurBouton
    // la reporte en texte + bordure quand le bouton est actif (indicateur
    // visible de projet, cohérent avec la pastille et le badge de détail).
    btn.dataset.couleur = couleurProjetResultats(nom);
    btn.onclick = () => basculerFiltreProjet(nom);
    btn.innerHTML = '<span class="pastille" style="background:'
      + couleurProjetResultats(nom) + '"></span>' + escapeHtml(nom);
    zone.appendChild(btn);
  }
  majClassesBoutonsFiltre();
  // Toggle « 👷 Ouvriers » (issue #86), après les boutons projet. Inactif par
  // défaut : les issues de type ouvrier restent masquées jusqu'à un clic.
  const ouv = document.createElement('span');
  ouv.id = 'filtre-ouvriers';
  ouv.className = 'filtre-projet ouvriers';
  ouv.textContent = '👷 Ouvriers';
  ouv.title = 'Afficher / masquer les issues de type ouvrier';
  ouv.onclick = basculerFiltreOuvriers;
  zone.appendChild(ouv);
  majBoutonOuvriers();
  const tous = document.createElement('span');
  tous.className = 'filtre-projet tous';
  tous.textContent = 'Tous';
  tous.onclick = reactiverTousLesFiltres;
  zone.appendChild(tous);
  // Bouton rafraîchir déplacé ici, juste après « Tous » (issue #57). Recréé à
  // chaque reconstruction de la ligne car zone.innerHTML est vidé au début.
  const rafr = document.createElement('button');
  rafr.id = 'btn-rafraichir';
  rafr.className = 'btn-rafraichir';
  rafr.title = 'Rafraîchir depuis GitHub';
  rafr.textContent = '↻';
  rafr.onclick = rafraichirResultats;
  zone.appendChild(rafr);
}

// Active/désactive un projet dans le filtre puis masque/affiche les lignes
// correspondantes (display:none). Si la ligne sélectionnée devient masquée, on
// bascule sur la première ligne encore visible.
function basculerFiltreProjet(nom) {
  if (projetsFiltresActifs.has(nom)) projetsFiltresActifs.delete(nom);
  else projetsFiltresActifs.add(nom);
  sauvegarderFiltresProjets(nomsProjetsDisponibles());
  majClassesBoutonsFiltre();
  appliquerFiltresListe();
  const sel = document.querySelector('#liste-issues .ligne-issue.selectionnee');
  if (!sel || sel.style.display === 'none') selectionnerPremiereVisible();
}

// Remet tous les projets à l'état actif ET efface la mémoire localStorage
// (retour au comportement par défaut : tous actifs au prochain chargement).
function reactiverTousLesFiltres() {
  projetsFiltresActifs = new Set(nomsProjetsDisponibles());
  try { localStorage.removeItem(CLE_FILTRES_RESULTATS); } catch(e) {}
  majClassesBoutonsFiltre();
  appliquerFiltresListe();
  const sel = document.querySelector('#liste-issues .ligne-issue.selectionnee');
  if (!sel || sel.style.display === 'none') selectionnerPremiereVisible();
}

function majClassesBoutonsFiltre() {
  document.querySelectorAll('#filtres-projets .filtre-projet[data-projet]')
    .forEach(btn => {
      const actif = projetsFiltresActifs.has(btn.dataset.projet);
      btn.classList.toggle('inactif', !actif);
      // Actif : texte + bordure à la couleur du projet (bien visible).
      // Inactif : on efface le style inline pour laisser la classe .inactif
      // (grisé) reprendre la main.
      btn.style.color       = actif ? btn.dataset.couleur : '';
      btn.style.borderColor = actif ? btn.dataset.couleur : '';
    });
}

// Convertit une couleur hexadécimale #RRGGBB en rgba() avec l'alpha demandé.
// Sert aux fonds translucides (survol/sélection) propres à chaque projet.
function avecOpacite(hex, alpha) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ','
       + (n & 255) + ',' + alpha + ')';
}

// ─── Case à cocher libre par résultat (issue #154) ────────────────────────
// Repère visuel purement personnel pour Alain (« ce résultat, je l'ai déjà
// traité/lu »), SANS aucune logique métier. L'état vit UNIQUEMENT dans le
// localStorage du navigateur : aucun appel au serveur Flask, rien de stocké
// côté Python/fichier. La clé est stable, dérivée de l'identité de l'issue
// (projet + numéro), donc l'état survit aux rechargements et re-rendus.
function cleCocheResultat(projet, numero) {
  return 'resultat-coche:' + projet + ':' + numero;
}
// Vrai si l'utilisateur a coché ce résultat. Robuste si localStorage est
// indisponible (mode privé strict) : on renvoie simplement false.
function estResultatCoche(projet, numero) {
  try { return localStorage.getItem(cleCocheResultat(projet, numero)) === '1'; }
  catch (e) { return false; }
}
// Bascule appelée par onchange de la case : persiste l'état dans localStorage
// et grise/dégrise instantanément la ligne (aucun rechargement de page).
function basculerCocheResultat(event, projet, numero) {
  const cb = event.target;
  const ligne = cb.closest('.ligne-issue');
  const coche = cb.checked;
  try {
    if (coche) localStorage.setItem(cleCocheResultat(projet, numero), '1');
    else       localStorage.removeItem(cleCocheResultat(projet, numero));
  } catch (e) { /* localStorage indisponible : la case reste juste visuelle */ }
  if (ligne) ligne.classList.toggle('resultat-traite', coche);
}

// (Re)construit la liste HTML cliquable à partir de listeIssuesResultats. TOUTES
// les issues sont rendues comme lignes ; le filtre projet ne fait que masquer
// (display:none) les lignes des projets inactifs. Chaque ligne est coloriée à la
// couleur de son projet et déclenche afficherIssue() au clic. Si reset=true, on
// sélectionne et affiche la première issue visible.
function rendreListeIssues(reset) {
  const zone = document.getElementById('liste-issues');
  zone.innerHTML = '';
  if (!listeIssuesResultats.length) {
    zone.innerHTML = '<div class="issue-vide">Aucune issue à afficher</div>';
    document.getElementById('zone-issue').innerHTML =
      '<div class="issue-vide">Aucune issue à afficher</div>';
    return;
  }
  for (const it of listeIssuesResultats) {
    const etat = (it.state || '').toUpperCase() === 'CLOSED' ? 'fermé' : 'ouvert';
    const couleur = couleurProjetResultats(it.projet);
    const numero = String(it.number);
    // Horodatage en heure locale du navigateur (issue #58). Depuis l'issue #95,
    // la ligne n'affiche QUE l'heure "HH:MM:SS" (colonne plus étroite) ; la date
    // complète "DD/MM/YYYY HH:MM:SS" reste disponible au survol (attribut title).
    const dObj = it.createdAt ? new Date(it.createdAt) : null;
    const heureCreation = dObj
      ? dObj.toLocaleTimeString('fr-FR', {
          hour: '2-digit', minute: '2-digit', second: '2-digit'
        })
      : '';
    const dateCreation = dObj
      ? dObj.toLocaleString('fr-FR', {
          day: '2-digit', month: '2-digit', year: 'numeric',
          hour: '2-digit', minute: '2-digit', second: '2-digit'
        })
      : '';
    const ligne = document.createElement('div');
    ligne.className = 'ligne-issue';
    ligne.dataset.projet = it.projet;
    ligne.dataset.numero = numero;
    // Case à cocher libre (issue #154) : repère visuel personnel d'Alain, SANS
    // aucune signification métier. État persisté côté navigateur uniquement
    // (localStorage), jamais envoyé au serveur. On lit l'état mémorisé pour
    // pré-cocher la case et marquer la ligne « traitée » dès le rendu (texte
    // grisé + fond pâle, badges colorés préservés — voir .resultat-traite, #155).
    const dejaCoche = estResultatCoche(it.projet, numero);
    if (dejaCoche) ligne.classList.add('resultat-traite');
    // TYPE de l'issue (pattern chef/ouvriers, issue #86) porté en dataset :
    // exploité par appliquerFiltresListe() pour masquer les ouvriers au besoin.
    ligne.dataset.type = typeIssue(it);
    // Couleur du texte = couleur du projet ; fonds translucides propres au projet
    // portés par des variables CSS, exploitées par .ligne-issue:hover/.selectionnee.
    ligne.style.color = couleur;
    ligne.style.setProperty('--bg-hover', avecOpacite(couleur, 0.10));
    ligne.style.setProperty('--bg-sel',   avecOpacite(couleur, 0.20));
    // Clic simple : sélectionne et affiche l'issue. Ctrl+clic : idem, puis
    // défile automatiquement jusqu'au bloc résultat CCL (dans cette UI, le
    // résultat est rendu EN PREMIER via .commentaire.resultat ; on le vise
    // donc explicitement, avec repli sur .commentaire:last-child).
    ligne.onclick = async (event) => {
      event.preventDefault();
      await afficherIssue(it.projet, numero);
      if (event.ctrlKey) {
        setTimeout(() => {
          const cible = document.querySelector('#zone-issue .commentaire.resultat')
                     || document.querySelector('#zone-issue .commentaire:last-child');
          if (cible) cible.scrollIntoView({behavior: 'smooth', block: 'start'});
        }, 100);
      }
    };
    // Gauche : badges emoji (✅ ✏️ ⚠️ ○) + pastille ● colorée du projet.
    // Centre : #N — titre [état].
    // Le badge ✅ des issues FERMÉES portant le label « done » (les seules qui
    // ont une réponse CCL) devient cliquable : un clic copie directement la
    // réponse CCL sans ouvrir le détail (issue #62).
    // Préfixe visuel du TYPE (🎯 chef / 👷 ouvrier / rien) devant les badges.
    const prefType = prefixeTypeIssue(it);
    let badgesHtml = (prefType ? prefType + ' ' : '') + prefixeIssue(it.labels);
    const nomsLabelsLigne = (it.labels || [])
      .map(l => ((l && l.name) || l || '').toLowerCase());
    if (etat === 'fermé' && nomsLabelsLigne.includes('done')
        && badgesHtml.includes('✅')) {
      // Trois badges aux rôles distincts et non redondants (issue #116) :
      //   ✅ (vert) → réponse CCL COMPLÈTE seule (plus jamais le résumé),
      //   « Diff »  → diff seul du/des commit(s) associé(s),
      //   « All »   → réponse complète + diff ensemble.
      // Le badge ✅ (vert) copie la réponse CCL COMPLÈTE (résumé + détails), sans
      // le diff. Le résumé seul n'est plus copié par aucun badge (issue #116).
      badgesHtml = badgesHtml.replace('✅',
        '<span class="badge-copie-ccl" title="Copier la réponse CCL complète"'
        + ' onclick="copierReponseDepuisBadge(event, \''
        + escapeHtml(it.projet) + '\', ' + Number(numero) + ')">✅</span>');
      // Badge « Diff » (issue #116) : copie UNIQUEMENT le diff du/des commit(s)
      // associé(s) (résultat de git show), sans la réponse. Sans commit (issue en
      // lecture seule), comportement neutre — rien n'est copié, pas d'erreur.
      badgesHtml +=
        '<span class="badge-copie-diff" title="Copier le diff seul du/des commit(s)"'
        + ' onclick="copierDiffDepuisBadge(event, \''
        + escapeHtml(it.projet) + '\', ' + Number(numero) + ')">Diff</span>';
      // Badge « All » (issue #116) : copie, en un seul geste, la réponse CCL
      // COMPLÈTE suivie du diff du/des commit(s) associé(s). Sans commit (lecture
      // seule), copie la réponse seule — sans section diff vide ni erreur.
      badgesHtml +=
        '<span class="badge-copie-all" title="Copier la réponse complète + le diff"'
        + ' onclick="copierToutEtDiffDepuisBadge(event, \''
        + escapeHtml(it.projet) + '\', ' + Number(numero) + ')">All</span>';
    }
    ligne.innerHTML =
      // Case à cocher libre (issue #154), tout à gauche de la ligne. Le clic ne
      // doit PAS sélectionner/ouvrir l'issue (stopPropagation) ; onchange délègue
      // à basculerCocheResultat() qui persiste l'état dans localStorage.
      '<input type="checkbox" class="coche-resultat"'
      + (dejaCoche ? ' checked' : '')
      + ' title="Repère personnel : marquer ce résultat comme traité/lu"'
      + ' onclick="event.stopPropagation()"'
      + ' onchange="basculerCocheResultat(event, \''
      + escapeHtml(it.projet) + '\', ' + Number(numero) + ')">'
      + '<span class="ligne-date" title="' + escapeHtml(dateCreation) + '"'
      + ' style="font-size:11px;color:#999;'
      + 'min-width:66px;font-family:monospace">' + escapeHtml(heureCreation) + '</span>'
      + '<span class="ligne-gauche">'
      + '<span class="ligne-badges">' + badgesHtml + '</span>'
      + '<span class="pastille-ligne" style="background:' + couleur + '"></span>'
      + '</span>'
      // Poignée de redimensionnement de la SEULE colonne titre (issue #95) :
      // sur la bordure gauche de .ligne-texte. onclick stoppe la propagation
      // pour qu'un clic de fin de glisser ne sélectionne pas l'issue.
      + '<span class="poignee-titre" title="Glisser pour redimensionner la colonne titre"'
      + ' onmousedown="demarrerRedimTitre(event)" onclick="event.stopPropagation()"></span>'
      + '<span class="ligne-texte">#' + escapeHtml(numero) + ' — '
      + escapeHtml(it.title) + ' [' + etat + ']</span>'
      // Badge d'estimation prédictive (issue #108) PUIS badge de temps restant
      // (issues #91/#106) : l'estimation (durée médiane historique du même
      // projet+type+mode) s'affiche JUSTE AVANT le décompte, qui reste inchangé.
      // Les deux sont remplis/actualisés par majBadgesTempsRestant().
      + (etat === 'ouvert'
          ? '<span class="ligne-estimation" style="display:none"></span>'
            + '<span class="ligne-tempsrestant" style="display:none"></span>'
          : '');
    zone.appendChild(ligne);
  }
  appliquerFiltresListe();
  appliquerLargeurTitre();
  majBadgesTempsRestant();
  if (reset) selectionnerPremiereVisible();
}

// ─── Colonne titre redimensionnable (issue #95) ───────────────────────────
// SEULE la colonne titre (.ligne-texte) est redimensionnable : par défaut elle
// est en flex:1 (occupe l'espace restant, tronquée par ellipsis). Dès qu'une
// largeur est mémorisée, on bascule .liste-issues en mode « titre fixe » : la
// colonne prend cette largeur explicite (var CSS --largeur-titre) et l'onglet
// défile horizontalement si la ligne dépasse. Les autres colonnes (heure,
// badges, pastille) gardent leur largeur fixe. La largeur choisie est persistée
// (même convention que bridge_notif_pc, issue #93).
const CLE_LARGEUR_TITRE = 'bridge_largeur_titre';

// Lit la largeur mémorisée (px) ou null si absente/illisible/invalide.
function largeurTitreStockee() {
  try {
    const v = parseInt(localStorage.getItem(CLE_LARGEUR_TITRE), 10);
    return Number.isFinite(v) && v > 0 ? v : null;
  } catch(e) { return null; }
}

// Applique (ou retire) la largeur de titre mémorisée sur le conteneur de liste.
// Sans largeur stockée : mode par défaut (flex:1, ellipsis, pas de scroll).
function appliquerLargeurTitre() {
  const liste = document.getElementById('liste-issues');
  if (!liste) return;
  const w = largeurTitreStockee();
  if (w) {
    liste.style.setProperty('--largeur-titre', w + 'px');
    liste.classList.add('titre-redimensionne');
  } else {
    liste.classList.remove('titre-redimensionne');
    liste.style.removeProperty('--largeur-titre');
  }
}

// État du glisser-déposer en cours (null hors redimensionnement).
let redimTitreEtat = null;

// Début du glisser sur la poignée gauche de la colonne titre. On mémorise la
// largeur de départ de CETTE ligne comme référence ; le mouvement met à jour la
// var CSS partagée par toutes les lignes (colonne cohérente).
function demarrerRedimTitre(event) {
  event.preventDefault();
  event.stopPropagation();
  const ligne = event.currentTarget.closest('.ligne-issue');
  const texte = ligne ? ligne.querySelector('.ligne-texte') : null;
  if (!texte) return;
  redimTitreEtat = {
    xDepart: event.clientX,
    largeurDepart: texte.getBoundingClientRect().width,
  };
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';
  document.addEventListener('mousemove', surRedimTitre);
  document.addEventListener('mouseup', finRedimTitre);
}

// Pendant le glisser : la poignée est sur la bordure GAUCHE du titre → tirer
// vers la gauche élargit la colonne, vers la droite la rétrécit. Bornée à
// [80, 1200] px pour rester utilisable.
function surRedimTitre(event) {
  if (!redimTitreEtat) return;
  const delta = redimTitreEtat.xDepart - event.clientX;
  let w = Math.round(redimTitreEtat.largeurDepart + delta);
  w = Math.max(80, Math.min(w, 1200));
  const liste = document.getElementById('liste-issues');
  if (!liste) return;
  liste.style.setProperty('--largeur-titre', w + 'px');
  liste.classList.add('titre-redimensionne');
}

// Fin du glisser : on persiste la largeur courante dans localStorage.
function finRedimTitre() {
  document.removeEventListener('mousemove', surRedimTitre);
  document.removeEventListener('mouseup', finRedimTitre);
  document.body.style.cursor = '';
  document.body.style.userSelect = '';
  if (!redimTitreEtat) return;
  redimTitreEtat = null;
  const liste = document.getElementById('liste-issues');
  if (!liste) return;
  const w = parseInt(liste.style.getPropertyValue('--largeur-titre'), 10);
  if (Number.isFinite(w) && w > 0) {
    try { localStorage.setItem(CLE_LARGEUR_TITRE, String(w)); } catch(e) {}
  }
}

// Masque/affiche les lignes selon les projets actifs ET le filtre ouvriers
// (filtre = display:none). Une ligne ouvrière reste masquée tant que le toggle
// « 👷 Ouvriers » est inactif (issue #86).
function appliquerFiltresListe() {
  // Quota adaptatif par projet (issue #136) : au lieu d'un plafond fixe, le
  // nombre d'issues affichées par projet dépend du nombre de projets actifs
  // dans le filtre. 1 projet → 30 ; 2 → 15 ; 3 → 10 ; 4 → 7 ; etc.
  const nActifs = projetsFiltresActifs.size;
  const quota   = nActifs > 0 ? Math.max(1, Math.floor(30 / nActifs)) : 0;

  // Compteur par projet, incrémenté dans l'ordre du DOM (déjà trié par date
  // décroissante globale) uniquement pour les lignes réellement affichables
  // (projet actif ET non masquée par le filtre ouvriers).
  const comptes = {};
  document.querySelectorAll('#liste-issues .ligne-issue').forEach(ligne => {
    const projet         = ligne.dataset.projet;
    const projetVisible  = projetsFiltresActifs.has(projet);
    const ouvrierMasque  = ligne.dataset.type === 'ouvrier' && !filtreOuvriersActif;
    let visible = projetVisible && !ouvrierMasque;
    if (visible) {
      const n = comptes[projet] || 0;
      if (n < quota) comptes[projet] = n + 1;   // dans le quota → on la garde
      else visible = false;                     // quota atteint → masquée
    }
    ligne.style.display = visible ? '' : 'none';
  });
}

// ─── Temps restant estimé des issues ouvertes (issue #91) ─────────────────
// L'heure de début de traitement n'est persistée nulle part par le watcher :
// la route /issues-en-attente la retrouve via l'horodatage du commentaire ACK
// (champ `debut`). Le compte à rebours est ensuite PUREMENT client : une fois
// debut+timeout connus, un intervalle JS recalcule le restant chaque seconde
// sans re-solliciter le serveur. Un re-fetch plus espacé (fetchTiming) capte
// les issues nouvellement démarrées ou terminées.
let timingIssues = {};              // clé "projet#numero" → {timeout, max_essais, backoff, debut, sans_limite}
let intervalTempsRestant = null;    // recalcul 1 s du compte à rebours (client seul)
let intervalFetchTiming  = null;    // re-fetch périodique des débuts/timeouts

function cleTiming(projet, numero) { return projet + '#' + numero; }

// Formate une durée en secondes → "45s" / "3min 20s" (compact, lisible).
function formaterDuree(s) {
  s = Math.max(0, Math.floor(s));
  if (s < 60) return s + 's';
  const m = Math.floor(s / 60), r = s % 60;
  return m + 'min' + (r ? ' ' + r + 's' : '');
}

// Récupère, pour tous les projets, les débuts de traitement + timeouts des
// issues ouvertes, puis rafraîchit immédiatement les badges.
async function chargerTimingIssues() {
  const noms = nomsProjetsDisponibles();
  const map = {};
  await Promise.all(noms.map(async nom => {
    try {
      const rep = await fetch('/issues-en-attente/' + encodeURIComponent(nom));
      const liste = await rep.json();
      if (!Array.isArray(liste)) return;
      for (const it of liste) {
        map[cleTiming(nom, it.number)] = {
          timeout:     it.timeout,
          max_essais:  it.max_essais,
          backoff:     it.backoff,
          debut:       it.debut,
          sans_limite: it.sans_limite,
          estimation:  it.estimation,   // estimation prédictive de durée (issue #108)
        };
      }
    } catch(e) {}
  }));
  timingIssues = map;
  majBadgesTempsRestant();
}

// Applique l'estimation prédictive de durée à un badge (issue #108), affiché
// JUSTE AVANT le décompte. La donnée `estimation` vient de la route
// /issues-en-attente : médiane des durées historiques du même projet+type+mode
// + niveau de fiabilité (nombre d'échantillons). Code couleur : rouge = peu sûr
// (< 5 échantillons), noir = correct (5-15), vert = sûr (> 15). Sans historique
// pour la catégorie : « pas encore de données ». N'affecte JAMAIS le décompte.
//
// Décompte live (issue #112) : une fois l'issue prise en charge (ACK connu),
// le badge devient un compte à rebours recalculé chaque seconde par
// majBadgesTempsRestant() : restant_estime = médiane − (maintenant − heure ACK).
// Contrairement au décompte réel (temps restant sur le TIMEOUT), le dépassement
// de la médiane n'est PAS une alerte de blocage : l'estimation reste indicative,
// affichée « estimation dépassée » en ton neutre (jamais l'alerte rouge ⌛).
function formaterBadgeEstimation(badge, t) {
  badge.className = 'ligne-estimation';
  const est = t && t.estimation;
  if (!est) { badge.style.display = 'none'; badge.textContent = ''; return; }
  badge.style.display = '';
  // Catégorie inédite (projet+type+mode jamais fermé) : on le dit clairement,
  // sans masquer le décompte qui suit (issue #108, cas 4). Rien à décompter
  // sans médiane.
  if (est.fiabilite === 'aucune' || est.mediane == null) {
    badge.textContent = '◦ pas encore de données';
    badge.classList.add('est-aucune');
    badge.title = 'Aucune issue fermée pour cette catégorie (projet + type + mode). '
                + "L'estimation apparaîtra dès qu'au moins une issue similaire aura "
                + 'été traitée. Le décompte à droite reste affiché normalement.';
    return;
  }
  // Classe de fiabilité (code couleur rouge/noir/vert selon le nombre
  // d'échantillons), commune à l'estimation figée et au décompte live.
  const cls = est.fiabilite === 'sur'     ? 'est-sur'       // vert  (> 15 échant.)
            : est.fiabilite === 'correct' ? 'est-correct'   // noir  (5-15 échant.)
            :                               'est-incertain';// rouge (< 5 échant.)
  const libFiab = est.fiabilite === 'sur'     ? 'fiable'
                : est.fiabilite === 'correct' ? 'correcte'
                :                               'incertaine (peu de données)';
  // Rappel commun : ne jamais confondre avec le décompte réel à droite, seule
  // vraie alerte de blocage (basée sur le TIMEOUT configuré).
  const rappel = ' À ne pas confondre avec le décompte à droite, qui est le temps '
               + 'restant réel sur le TIMEOUT configuré (seule vraie alerte de blocage).';

  // Pas encore prise en charge (aucun ACK) : impossible de décompter, on
  // affiche l'estimation figée (médiane) comme repère de départ.
  if (!t.debut) {
    badge.textContent = '≈ ' + formaterDuree(est.mediane);
    badge.classList.add(cls);
    badge.title = 'Durée médiane observée sur ' + est.n + ' issue(s) fermée(s) du même '
                + 'projet + type + mode — estimation ' + libFiab + '. Le décompte '
                + 'estimé démarrera dès la prise en charge par le watcher.' + rappel;
    return;
  }

  // Décompte live (issue #112) : restant estimé = médiane − temps écoulé depuis
  // l'ACK. Recalculé chaque seconde comme le badge de décompte réel (issue #91).
  const ecoule  = (Date.now() - new Date(t.debut).getTime()) / 1000;
  const restant = Math.round(est.mediane - ecoule);

  if (restant > 0) {                     // encore sous la médiane : compte à rebours
    badge.textContent = '≈ ' + formaterDuree(restant);
    badge.classList.add(cls);
    badge.title = 'Temps restant ESTIMÉ avant la durée médiane ('
                + formaterDuree(est.mediane) + ' sur ' + est.n + ' issue(s) similaires, '
                + 'estimation ' + libFiab + '). Simple repère prédictif, '
                + 'pas une limite dure.' + rappel;
  } else {                               // médiane franchie mais issue non fermée
    // Estimation dépassée (issue #112, cas 3) : ce n'est qu'une estimation, PAS
    // un blocage. Ton neutre, visuellement distinct de l'alerte rouge « ⌛
    // dépassement » du décompte réel (qui, elle, signale un vrai budget épuisé).
    badge.textContent = '≈ estimation dépassée';
    badge.classList.add('est-depasse');
    badge.title = 'La durée médiane estimée (' + formaterDuree(est.mediane)
                + ') est dépassée de ' + formaterDuree(-restant) + ", mais ce n'est "
                + "qu'une estimation indicative, pas une limite dure : l'issue peut "
                + 'légitimement durer plus longtemps.' + rappel;
  }
}

// Applique l'état de temps restant à un badge, selon les données de timing.
function formaterBadgeTempsRestant(badge, t) {
  badge.className = 'ligne-tempsrestant';
  if (!t) { badge.style.display = 'none'; badge.textContent = ''; return; }
  badge.style.display = '';
  if (!t.debut) {                       // ouverte mais pas encore prise en charge
    badge.textContent = '⏳ en file';
    badge.classList.add('tr-attente');
    badge.title = 'En attente de prise en charge par le watcher';
    return;
  }
  if (t.sans_limite) {                   // priorité haute/critique → retry infini
    badge.textContent = '⏳ en cours (pas de limite)';
    badge.classList.add('tr-illimite');
    badge.title = 'Priorité haute/critique : réessais illimités, pas de deadline';
    return;
  }
  // Budget de retry conscient (issue #106) : le watcher dispose de max_essais
  // tentatives de `timeout` secondes, séparées par un backoff. On raisonne donc
  // sur le budget TOTAL (timeout × essais + backoffs), et non sur un seul cycle.
  const essais   = Math.max(1, t.max_essais || 1);
  const backoff  = t.backoff || 0;
  const cycle    = t.timeout + backoff;                 // durée d'un cycle (tentative + backoff)
  const budget   = t.timeout * essais + backoff * (essais - 1);
  const ecoule   = (Date.now() - new Date(t.debut).getTime()) / 1000;
  const restant  = Math.round(budget - ecoule);
  // Tentative estimée en cours (1-based), plafonnée au nombre max.
  const tentative = Math.min(essais, Math.floor(ecoule / cycle) + 1);

  if (restant > 0 && tentative <= 1) {   // 1er cycle : compte à rebours classique
    badge.textContent = '⏳ ' + formaterDuree(restant);
    badge.classList.add(restant <= 30 ? 'tr-bientot' : 'tr-ok');
    badge.title = 'Temps restant estimé sur le budget total ('
                + essais + ' tentative(s) × ' + t.timeout + 's'
                + (backoff ? ' + backoffs' : '') + ') avant dépassement réel.';
  } else if (restant > 0) {              // au-delà du 1er cycle : retry en cours, PAS un échec
    badge.textContent = '🔄 tentative ' + tentative + '/' + essais
                      + ' — ' + formaterDuree(restant);
    badge.classList.add('tr-retry');
    badge.title = 'Le 1er cycle TIMEOUT (' + t.timeout + 's) a été dépassé, mais '
                + 'le watcher dispose de ' + essais + ' tentatives. Reste ~'
                + formaterDuree(restant) + ' sur le budget total ; pas encore un échec.';
  } else {                               // budget total (toutes tentatives) épuisé
    badge.textContent = '⌛ dépassement +' + formaterDuree(-restant);
    badge.classList.add('tr-depasse');
    badge.title = 'Budget total épuisé (' + essais + ' tentatives × ' + t.timeout
                + 's' + (backoff ? ' + backoffs' : '') + ') ; intervention '
                + 'humaine probable (label needs-human).';
  }
}

// Actualise tous les badges de temps restant des lignes ouvertes (recalcul pur,
// aucun appel réseau). Appelée chaque seconde et après chaque rendu de liste.
function majBadgesTempsRestant() {
  document.querySelectorAll('#liste-issues .ligne-issue').forEach(ligne => {
    const t = timingIssues[cleTiming(ligne.dataset.projet, ligne.dataset.numero)];
    // Estimation prédictive (issue #108) : affichée JUSTE AVANT le décompte.
    const badgeEst = ligne.querySelector('.ligne-estimation');
    if (badgeEst) formaterBadgeEstimation(badgeEst, t);
    const badge = ligne.querySelector('.ligne-tempsrestant');
    if (!badge) return;
    formaterBadgeTempsRestant(badge, t);
  });
}

// Démarre le suivi du temps restant (à l'ouverture de l'onglet Résultats) :
// fetch initial des débuts/timeouts, recalcul chaque seconde, re-fetch espacé.
function demarrerTempsRestant() {
  chargerTimingIssues();
  arreterTempsRestant();
  intervalTempsRestant = setInterval(majBadgesTempsRestant, 1000);
  intervalFetchTiming  = setInterval(chargerTimingIssues, 15000);
}

// Stoppe les intervalles de temps restant (en quittant l'onglet Résultats).
function arreterTempsRestant() {
  if (intervalTempsRestant) { clearInterval(intervalTempsRestant); intervalTempsRestant = null; }
  if (intervalFetchTiming)  { clearInterval(intervalFetchTiming);  intervalFetchTiming  = null; }
}

// Sélectionne et affiche la première ligne encore visible (ou vide le détail).
function selectionnerPremiereVisible() {
  const premiere = [...document.querySelectorAll('#liste-issues .ligne-issue')]
    .find(ligne => ligne.style.display !== 'none');
  if (premiere) {
    afficherIssue(premiere.dataset.projet, premiere.dataset.numero);
  } else {
    document.getElementById('zone-issue').innerHTML =
      '<div class="issue-vide">Aucune issue à afficher</div>';
  }
}

function escapeHtml(t) {
  const d = document.createElement('div');
  d.textContent = t == null ? '' : t;
  return d.innerHTML;
}

// Rendu HTML restreint pour la réponse CCL (issue #61). On échappe TOUT le
// corps (aucune balise brute ne survit), puis on ré-autorise uniquement une
// liste blanche de balises sûres SANS attribut. Toute autre balise — ou une
// balise autorisée mais porteuse d'attributs, ex. <details open> ou
// <a href> — ne matche pas et reste échappée : elle s'affiche telle quelle
// plutôt que d'être interprétée. Pas d'injection possible via attributs.
function rendreHtmlRestreint(t) {
  // Échappement déterministe (& d'abord) — ne dépend pas de la sérialisation
  // du navigateur, contrairement à escapeHtml().
  let s = (t == null ? '' : String(t))
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const balises = ['details','summary','p','br','strong','em','code','pre',
                   'ul','ol','li','h1','h2','h3','h4','h5','h6'];
  balises.forEach(function(b) {
    s = s.split('&lt;' + b + '&gt;').join('<' + b + '>');   // ouvrante <tag>
    s = s.split('&lt;/' + b + '&gt;').join('</' + b + '>'); // fermante </tag>
  });
  // <br> auto-fermant toléré sous ses deux formes courantes.
  s = s.split('&lt;br/&gt;').join('<br/>').split('&lt;br /&gt;').join('<br/>');
  return s;
}

// Cache localStorage du détail d'une issue (issue #52). Clé par projet+numéro,
// avec un TTL court : le détail (commentaires, état) évolue vite, on n'affiche
// donc le cache que s'il a moins de TTL_DETAIL_MS.
const CLE_CACHE_DETAIL = 'bridge_cache_detail_';

// Issue actuellement affichée dans #zone-issue (null si aucune). Permet au
// bouton rafraîchir (issue #56) de la recharger depuis GitHub.
let projetCourant = null;
let numeroCourant = null;
const TTL_DETAIL_MS = 60000;
// Jeton anti-course : chaque appel à afficherIssue l'incrémente ; un fetch qui
// revient alors qu'une autre issue a été demandée entre-temps est ignoré.
let afficherIssueSeq = 0;

// Construit le HTML de détail d'une issue à partir de sa donnée brute (`it`).
// Fonction pure : même sortie depuis le cache et depuis le fetch frais.
function construireHtmlIssue(it, nom) {
  const ferme = (it.state || '').toUpperCase() === 'CLOSED';
  let html = '';
  html += '<div class="issue-titre">#' + escapeHtml(it.number) + ' — ' + escapeHtml(it.title) + '</div>';

  // Badge coloré du projet source (couleur cohérente avec les filtres).
  html += '<div><span class="badge-projet" style="background:'
        + couleurProjetResultats(nom) + '">'
        + '<span class="pastille"></span>' + escapeHtml(nom) + '</span></div>';

  html += '<div class="issue-badges">';
  html += '<span class="badge-etat ' + (ferme ? 'ferme' : 'ouvert') + '">'
        + (ferme ? 'fermé' : 'ouvert') + '</span>';
  for (const lab of (it.labels || [])) {
    html += badgeLabel(lab.name || lab);
  }
  html += '</div>';

  // Bouton « Annuler cette issue » : uniquement si l'issue est ouverte, porte
  // le label for-linux (donc destinée au watcher), n'est pas déjà en échec
  // (needs-human) et n'a encore aucun commentaire. Un commentaire signifie que
  // le watcher a capté l'issue et posté son ACK : CCL tourne déjà, l'annulation
  // serait sans effet — on masque le bouton pour ne pas induire en erreur.
  const nomsLabels = (it.labels || []).map(l => ((l.name || l) || '').toLowerCase());
  const comments = it.comments || [];
  const annulable = !ferme
    && nomsLabels.includes('for-linux')
    && !nomsLabels.includes('needs-human')
    && comments.length === 0;
  if (annulable) {
    html += '<div class="bloc-annuler">'
          + '<button class="danger" onclick="annulerIssue(\'' + nom + '\', '
          + Number(it.number) + ')">'
          + 'Annuler cette issue</button></div>';
  } else if (!ferme
    && nomsLabels.includes('for-linux')
    && !nomsLabels.includes('needs-human')
    && comments.length > 0) {
    // Issue en cours de traitement (ACK posté, pas encore needs-human). Le CCL
    // tourne : la seule façon de l'interrompre est de couper le watcher du
    // projet (killpg via #145). On combine cette coupure et la fermeture de
    // l'issue dans un seul bouton, car elles n'ont de sens qu'ensemble ici
    // (issue #144). Le watcher reste éteint : Alain le relance manuellement.
    html += '<div class="bloc-annuler">'
          + '<button class="danger" onclick="fermerEtInterrompre(\'' + nom + '\', '
          + Number(it.number) + ')">'
          + 'Interrompre et fermer cette issue</button></div>';
  }

  // Issue en échec définitif (label needs-human) et toujours ouverte :
  // l'intervention humaine ayant été effectuée, on propose de la clore
  // directement, sans passer par GitHub (issue #80). Bouton rouge plein à côté
  // du rappel « intervention humaine requise ».
  if (!ferme && nomsLabels.includes('needs-human')) {
    html += '<div class="bloc-annuler">'
          + '<span class="traitement-encours">'
          + '⚠️ Échec — intervention humaine requise</span> '
          + '<button class="danger-plein" onclick="fermerIssue(\'' + nom + '\', '
          + Number(it.number) + ')">'
          + 'Fermer définitivement</button></div>';
  }

  html += '<div class="issue-body">' + escapeHtml(it.body || '(pas de description)') + '</div>';

  const comms = it.comments || [];
  html += '<div class="issue-sep">Commentaires (' + comms.length + ')</div>';
  if (!comms.length) {
    html += '<div class="issue-vide">Aucun commentaire</div>';
  } else {
    // La réponse de CCL (dernier commentaire) est affichée en premier ;
    // les autres commentaires suivent dans l'ordre chronologique.
    const dernier = comms.length - 1;
    const ordre = [dernier, ...comms.map((_, i) => i).filter(i => i !== dernier)];
    ordre.forEach(i => {
      const c = comms[i];
      const auteur = (c.author && c.author.login) ? c.author.login : (c.author || 'inconnu');
      if (i === dernier) {
        // Réponse de CCL : on sépare le résumé court (texte AVANT <details>)
        // du bloc détails verbeux. Le bouton « Copier » est ancré au bloc
        // résumé et ne copie que ce résumé — pas les détails (issue #59).
        const corpsBrut = c.body || '';
        const idxDetails = corpsBrut.indexOf('<details>');
        const resume = (idxDetails >= 0 ? corpsBrut.slice(0, idxDetails) : corpsBrut)
                       .replace(/\s+$/, '');
        const details = idxDetails >= 0 ? corpsBrut.slice(idxDetails) : '';
        // Hash(s) de commit détecté(s) dans la réponse CCL : alimentent l'onglet
        // « Diff » (issue #114). Liste vide pour une issue en lecture seule.
        const hashes = hashesDeCommit(it);
        // Onglet « Réponse » : le contenu actuel (résumé + détails dépliables).
        // Onglet « Diff » : chargé paresseusement au clic (git show du/des
        // commit(s)), ou message clair si aucun commit associé (issue #114).
        html += '<div class="commentaire resultat">'
              + '<div class="commentaire-auteur">' + escapeHtml(auteur) + ' — résultat CCL</div>'
              + '<div class="reponse-onglets">'
              + '<div class="reponse-tabs">'
              + '<button class="reponse-tab actif" onclick="basculerOngletReponse(this,\'reponse\')">Réponse</button>'
              + '<button class="reponse-tab" onclick="basculerOngletReponse(this,\'diff\')">Diff</button>'
              + '</div>'
              + '<div class="reponse-pane reponse-pane-reponse actif">'
              + '<div class="commentaire-resume">'
              // « Copier résumé » : le texte avant <details> uniquement (issue #59).
              // « Copier tout » : résumé + détails en markdown brut (issue #77).
              // Les deux boutons sont côte à côte dans un conteneur flex ancré en
              // haut à droite, au lieu de deux absolute superposés (issue #81).
              + '<div class="copier-actions">'
              + '<button class="btn-copier" onclick="copierReponse(this)">Copier résumé</button>'
              + '<button class="btn-copier" onclick="copierTout(this)">Copier tout</button>'
              + '</div>'
              // Le bloc <details> brut (markdown non rendu) est conservé caché ici
              // pour que « Copier tout » puisse reconstruire le texte exact à coller
              // dans Claude Chat, indépendamment du rendu HTML de l'accordéon.
              + (details
                  ? '<div class="commentaire-details-brut" style="display:none">'
                    + escapeHtml(details) + '</div>'
                  : '')
              + '<div class="commentaire-corps">' + escapeHtml(resume) + '</div>'
              + '</div>';
        if (details) {
          // Le corps contient un bloc <details> : on le rend en HTML restreint
          // (liste blanche de balises sûres) pour un accordéon dépliable et
          // interactif au lieu de markdown brut échappé (issue #61).
          html += '<div class="commentaire-details commentaire-html">'
                + rendreHtmlRestreint(details) + '</div>';
        }
        html += '</div>'   // fin .reponse-pane-reponse
              // Onglet Diff : les hash sont portés en dataset ; le contenu est
              // chargé au premier clic sur l'onglet (chargerDiffOnglet).
              + '<div class="reponse-pane reponse-pane-diff" data-charge="0"'
              + ' data-projet="' + escapeHtml(nom) + '"'
              + ' data-hashes="' + escapeHtml(hashes.join(',')) + '">'
              + (hashes.length
                  ? '<div class="diff-vide">Cliquez sur l\'onglet « Diff » pour charger le diff.</div>'
                  : '<div class="diff-vide">Aucun commit associé à cette issue.</div>')
              + '</div>'   // fin .reponse-pane-diff
              + '</div>';  // fin .reponse-onglets
        html += '</div>';  // fin .commentaire.resultat
      } else {
        // Autres commentaires (ACK, etc.) : rendu texte échappé (sécurité) +
        // bouton « Copier » discret en haut à droite, ancré au bloc (issue #61).
        html += '<div class="commentaire commentaire-copiable">'
              + '<button class="btn-copier" onclick="copierReponse(this)">Copier</button>'
              + '<div class="commentaire-auteur">' + escapeHtml(auteur) + '</div>'
              + '<div class="commentaire-corps">' + escapeHtml(c.body || '') + '</div>'
              + '</div>';
      }
    });
  }
  return html;
}

async function afficherIssue(nom, numero) {
  numero = numero == null ? '' : String(numero);
  const seq = ++afficherIssueSeq;
  // Met en évidence la ligne sélectionnée (fond coloré persistant) et retire la
  // sélection des autres lignes.
  document.querySelectorAll('#liste-issues .ligne-issue.selectionnee')
    .forEach(ligne => ligne.classList.remove('selectionnee'));
  const ligneSel = [...document.querySelectorAll('#liste-issues .ligne-issue')]
    .find(ligne => ligne.dataset.projet === nom && ligne.dataset.numero === numero);
  if (ligneSel) ligneSel.classList.add('selectionnee');
  const zone = document.getElementById('zone-issue');
  if (!numero || !nom) {
    projetCourant = null;
    numeroCourant = null;
    zone.innerHTML = '<div class="issue-vide">Aucune issue à afficher</div>';
    return;
  }
  // Mémorise l'issue affichée pour le bouton rafraîchir (issue #56).
  projetCourant = nom;
  numeroCourant = numero;

  // 1) Cache frais (< TTL) : affichage immédiat. Passé le TTL, on force le fetch
  //    pour ne montrer que du frais (état/commentaires évoluent vite).
  const cleCache = CLE_CACHE_DETAIL + nom + '_' + numero;
  let htmlAffiche = null;
  try {
    const obj = JSON.parse(localStorage.getItem(cleCache) || 'null');
    if (obj && obj.it && (Date.now() - obj.ts) < TTL_DETAIL_MS) {
      htmlAffiche = construireHtmlIssue(obj.it, nom);
      zone.innerHTML = htmlAffiche;
    }
  } catch(e) {}
  if (htmlAffiche === null) {
    zone.innerHTML = '<div class="issue-vide">Chargement de l\'issue #' + escapeHtml(numero) + '…</div>';
  }

  // 2) Fetch d'arrière-plan ; met à jour l'affichage et le cache si différent.
  try {
    const rep = await fetch('/issue/' + encodeURIComponent(nom) + '/' + encodeURIComponent(numero));
    const it = await rep.json();
    // Une autre issue a été demandée entre-temps : on n'écrase pas son affichage.
    if (seq !== afficherIssueSeq) return;
    if (it.erreur) {
      if (htmlAffiche === null) {
        zone.innerHTML = '<div class="issue-vide">Erreur : ' + escapeHtml(it.erreur) + '</div>';
      }
      return;
    }
    try { localStorage.setItem(cleCache, JSON.stringify({ts: Date.now(), it: it})); } catch(e) {}
    const htmlFrais = construireHtmlIssue(it, nom);
    if (htmlFrais !== htmlAffiche) {
      zone.innerHTML = htmlFrais;
    }
  } catch(e) {
    if (seq === afficherIssueSeq && htmlAffiche === null) {
      zone.innerHTML = '<div class="issue-vide">Erreur réseau : ' + escapeHtml(e.message) + '</div>';
    }
  }
}

// Bouton rafraîchir (issue #56) : vide le cache localStorage (liste + tous les
// détails) puis recharge tout depuis GitHub. Contourne le TTL du cache détail,
// qui peut montrer une issue « ouverte » alors que le watcher l'a fermée.
async function rafraichirResultats() {
  // Mémorise l'issue affichée AVANT le rechargement : chargerListeIssues()
  // réécrit projetCourant/numeroCourant en auto-sélectionnant la première ligne.
  const projet = projetCourant;
  const numero = numeroCourant;
  // 1) Cache de la liste.
  try { localStorage.removeItem(CLE_CACHE_ISSUES); } catch(e) {}
  // 2) Toutes les clés de cache détail « bridge_cache_detail_* ».
  try {
    const aSupprimer = [];
    for (let i = 0; i < localStorage.length; i++) {
      const cle = localStorage.key(i);
      if (cle && cle.indexOf(CLE_CACHE_DETAIL) === 0) aSupprimer.push(cle);
    }
    aSupprimer.forEach(cle => localStorage.removeItem(cle));
  } catch(e) {}
  // 3) Recharge la liste depuis GitHub.
  await chargerListeIssues();
  // 4) Recharge l'issue qui était affichée, si elle l'était.
  if (projet && numero) {
    await afficherIssue(projet, numero);
  }
}

// Copie le texte de la réponse CCL (dernier commentaire) dans le presse-papier.
// Feedback visuel « ✓ Copié ! » pendant 2 s. Fallback silencieux (sélection du
// texte + warning console) si navigator.clipboard est indisponible (non-HTTPS).
// ─── Garde « copie vide » (issue #122) ───────────────────────────────────────
// Plusieurs fonctions de copie peuvent aboutir à un texte vide sans jamais le
// signaler : fetch du détail en échec, réponse CCL pas encore propagée côté
// GitHub au moment du clic, etc. Elles affichaient alors ✓ (identique au succès)
// et écrasaient le presse-papier avec du vide — Alain collait du vide sans le
// savoir. Ces helpers factorisent la garde : détecter le texte vide, NE PAS
// copier (préserver un presse-papier peut-être utile) et afficher un feedback ⚠
// distinct du ✓ pendant ~2 s, avec un tooltip explicite.
const TITRE_COPIE_VIDE =
  'Réponse pas encore disponible — réessaie dans quelques secondes';

// texte est-il vide (chaîne vide ou uniquement des espaces / retours ligne) ?
function texteCopieVide(texte) {
  return !texte || !texte.trim();
}

// Feedback ⚠ sur un badge de liste (span) : ⚠ + tooltip explicite pendant ~2 s,
// puis restauration du libellé et du titre d'origine. Ne touche pas au
// presse-papier.
function feedbackBadgeVide(badge, original, titreOriginal) {
  if (!badge) return;
  badge.textContent = '⚠';
  badge.title = TITRE_COPIE_VIDE;
  setTimeout(function() {
    badge.textContent = original;
    badge.title = titreOriginal;
  }, 2000);
}

// Feedback ⚠ sur un bouton « Copier … » : ⚠ + tooltip explicite pendant ~2 s,
// puis restauration du libellé et du titre d'origine. Ne touche pas au
// presse-papier.
function feedbackBoutonVide(btn, libelle) {
  if (!btn) return;
  const titreOriginal = btn.title;
  btn.disabled = true;
  btn.textContent = '⚠';
  btn.title = TITRE_COPIE_VIDE;
  setTimeout(function() {
    btn.textContent = libelle;
    btn.title = titreOriginal;
    btn.disabled = false;
  }, 2000);
}

async function copierReponse(btn) {
  // Le bouton vit dans le bloc résumé : on copie le texte de CE bloc
  // uniquement (résumé court), jamais le bloc détails verbeux (issue #59).
  const bloc = btn.closest('.commentaire-resume') || btn.closest('.commentaire');
  const corps = bloc ? bloc.querySelector('.commentaire-corps') : null;
  if (!corps) return;
  // Libellé d'origine : « Copier résumé » (CCL, issue #77) ou « Copier » (autres
  // commentaires, issue #61) — on le restaure après le retour visuel.
  const libelle = btn.textContent;
  const texte = corps.textContent || '';
  // Garde « copie vide » (issue #122) : rien à copier → feedback ⚠, pas de ✓.
  if (texteCopieVide(texte)) { feedbackBoutonVide(btn, libelle); return; }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(texte);
      btn.disabled = true;
      btn.textContent = '✓ Copié !';
      setTimeout(function() {
        btn.textContent = libelle;
        btn.disabled = false;
      }, 2000);
      return;
    } catch(e) {
      console.warn('copierReponse : échec navigator.clipboard, fallback sélection.', e);
    }
  } else {
    console.warn('copierReponse : navigator.clipboard indisponible (contexte non-HTTPS), fallback sélection.');
  }
  // Fallback : on sélectionne le texte du bloc pour permettre un Ctrl+C manuel.
  const sel = window.getSelection();
  if (sel) {
    const range = document.createRange();
    range.selectNodeContents(corps);
    sel.removeAllRanges();
    sel.addRange(range);
  }
}

// Reconstruit la réponse CCL COMPLÈTE en markdown brut (issue #77) : le résumé,
// une ligne vide, puis le contenu du bloc <details> débarrassé de ses seules
// balises structurantes (<details>, <summary>, </summary>, </details>). Le texte
// interne (dont le libellé du <summary>) est conservé tel quel — résultat lisible
// et collable directement dans Claude Chat. Si les détails sont vides, on ne
// renvoie que le résumé (pas de ligne vide superflue).
function texteReponseComplete(resume, detailsBrut) {
  const contenu = (detailsBrut || '')
    .split('<details>').join('')
    .split('</details>').join('')
    .split('<summary>').join('')
    .split('</summary>').join('')
    .replace(/^\s+|\s+$/g, '');
  const r = (resume || '').replace(/\s+$/, '');
  return contenu ? (r + '\n\n' + contenu) : r;
}

// « Copier tout » (issue #77) : copie la réponse CCL complète (résumé + détails)
// en markdown brut, via texteReponseComplete(). Même feedback visuel que
// « Copier résumé » — « ✓ Copié ! » pendant 1,5 s puis retour au libellé. Le
// résumé est lu dans .commentaire-corps, les détails bruts dans le bloc caché
// .commentaire-details-brut. Fallback silencieux (sélection du résumé) si
// navigator.clipboard est indisponible (contexte non-HTTPS).
async function copierTout(btn) {
  const bloc = btn.closest('.commentaire-resume') || btn.closest('.commentaire');
  if (!bloc) return;
  const corps  = bloc.querySelector('.commentaire-corps');
  const brutEl = bloc.querySelector('.commentaire-details-brut');
  const resume = corps  ? (corps.textContent  || '') : '';
  const details = brutEl ? (brutEl.textContent || '') : '';
  const texte  = texteReponseComplete(resume, details);
  const libelle = btn.textContent;
  // Garde « copie vide » (issue #122) : rien à copier → feedback ⚠, pas de ✓.
  if (texteCopieVide(texte)) { feedbackBoutonVide(btn, libelle); return; }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(texte);
      btn.disabled = true;
      btn.textContent = '✓ Copié !';
      setTimeout(function() {
        btn.textContent = libelle;
        btn.disabled = false;
      }, 1500);
      return;
    } catch(e) {
      console.warn('copierTout : échec navigator.clipboard, fallback sélection.', e);
    }
  } else {
    console.warn('copierTout : navigator.clipboard indisponible (contexte non-HTTPS), fallback sélection.');
  }
  // Fallback : à défaut de presse-papier, on sélectionne au moins le résumé
  // affiché (le texte complet reconstruit ne peut pas être injecté dans le DOM).
  const sel = window.getSelection();
  if (sel && corps) {
    const range = document.createRange();
    range.selectNodeContents(corps);
    sel.removeAllRanges();
    sel.addRange(range);
  }
}

// Clic sur le badge ✅ (vert) d'une issue fermée+done (issue #62, comportement
// revu #116) : copie la réponse CCL COMPLÈTE (résumé + détails) directement
// depuis la liste, sans ouvrir le détail — plus jamais le résumé seul. Réutilise
// reponseCompleteCcl(), comme le badge « All ». Utilise le cache
// bridge_cache_detail_<projet>_<numero> s'il est frais (< TTL), sinon fetch le
// détail (et met le cache à jour). Feedback visuel bref sur le badge lui-même,
// sans modifier la ligne. stopPropagation() empêche la sélection de la ligne.
async function copierReponseDepuisBadge(event, nom, numero) {
  event.stopPropagation();
  const badge = event.currentTarget;   // capturé avant tout await (nullé ensuite)
  const original = badge ? badge.textContent : '';
  const titreOriginal = badge ? badge.title : '';
  numero = String(numero);
  const cleCache = CLE_CACHE_DETAIL + nom + '_' + numero;
  let texte = null;

  // 1) Cache frais (< TTL) : on évite le fetch.
  try {
    const obj = JSON.parse(localStorage.getItem(cleCache) || 'null');
    if (obj && obj.it && (Date.now() - obj.ts) < TTL_DETAIL_MS) {
      texte = reponseCompleteCcl(obj.it);
    }
  } catch(e) {}

  // 2) Pas de cache exploitable : fetch le détail et rafraîchit le cache.
  if (texte === null) {
    try {
      const rep = await fetch('/issue/' + encodeURIComponent(nom)
                              + '/' + encodeURIComponent(numero));
      const it = await rep.json();
      if (!it.erreur) {
        try { localStorage.setItem(cleCache, JSON.stringify({ts: Date.now(), it: it})); } catch(e) {}
        texte = reponseCompleteCcl(it);
      }
    } catch(e) {
      console.warn('copierReponseDepuisBadge : échec fetch du détail.', e);
    }
  }
  if (texte === null) texte = '';

  // Garde « copie vide » (issue #122) : réponse pas encore disponible (fetch en
  // échec ou dernier commentaire vide) → feedback ⚠, aucune copie, pas de ✓.
  if (texteCopieVide(texte)) { feedbackBadgeVide(badge, original, titreOriginal); return; }

  // Copie dans le presse-papier (fallback silencieux si indisponible / non-HTTPS).
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(texte);
    } catch(e) {
      console.warn('copierReponseDepuisBadge : échec navigator.clipboard.', e);
    }
  } else {
    console.warn('copierReponseDepuisBadge : navigator.clipboard indisponible (non-HTTPS).');
  }

  // Feedback visuel : ✅ → ✓ pendant 1,5 s, puis retour au libellé (ligne inchangée).
  if (badge) {
    badge.textContent = '✓';
    setTimeout(function() { badge.textContent = original; }, 1500);
  }
}

// Reconstruit la réponse CCL COMPLÈTE (résumé + détails) en markdown brut à
// partir d'une donnée issue brute — équivalent de « Copier tout » du détail
// (issue #77), mais pour l'icône « All » de la liste (issue #95). Réutilise
// texteReponseComplete() pour retirer les seules balises structurantes du bloc
// <details>.
function reponseCompleteCcl(it) {
  const comms = (it && it.comments) || [];
  if (!comms.length) return '';
  const corpsBrut = comms[comms.length - 1].body || '';
  const idxDetails = corpsBrut.indexOf('<details>');
  const resume  = (idxDetails >= 0 ? corpsBrut.slice(0, idxDetails) : corpsBrut)
                  .replace(/\s+$/, '');
  const details = idxDetails >= 0 ? corpsBrut.slice(idxDetails) : '';
  return texteReponseComplete(resume, details);
}

// ─── Onglets Réponse / Diff du détail d'une issue (issue #114) ────────────────

// Extrait la liste des hash de commit mentionnés dans la réponse CCL (dernier
// commentaire). Le template de réponse porte une ligne « Commits : <hash>
// (backup) + <hash> (fix) — … » (ou « Commits : aucun » en lecture seule) : on
// cible cette ligne et on en tire les jetons hexadécimaux 7-40 caractères,
// dédupliqués dans l'ordre. Liste vide si aucun commit (issue en lecture seule).
function hashesDeCommit(it) {
  const comms = (it && it.comments) || [];
  if (!comms.length) return [];
  const corps = comms[comms.length - 1].body || '';
  const ligneCommits = corps.split('\n').find(l => /^\s*commits?\s*:/i.test(l));
  if (!ligneCommits) return [];
  const trouves = ligneCommits.match(/\b[0-9a-f]{7,40}\b/gi) || [];
  const vus = [];
  trouves.forEach(h => { h = h.toLowerCase(); if (!vus.includes(h)) vus.push(h); });
  return vus;
}

// Colore un texte de diff (sortie de `git show`) ligne par ligne : ajouts en
// vert, retraits en rouge, en-têtes de section (@@) et métadonnées (diff/index/
// commit/…) distincts. Chaque ligne est échappée AVANT insertion (sécurité).
function colorierDiff(texte) {
  return (texte || '').split('\n').map(function(l) {
    const e = escapeHtml(l);
    if (l.startsWith('@@')) return '<span class="diff-hunk">' + e + '</span>';
    if (l.startsWith('+') && !l.startsWith('+++')) return '<span class="diff-add">' + e + '</span>';
    if (l.startsWith('-') && !l.startsWith('---')) return '<span class="diff-del">' + e + '</span>';
    if (/^(diff |index |\+\+\+|---|commit |Author:|Date:|Merge:)/.test(l))
      return '<span class="diff-meta">' + e + '</span>';
    return e;
  }).join('\n');
}

// Bascule entre les onglets « Réponse » et « Diff » du bloc résultat CCL. Le
// diff est chargé paresseusement au premier affichage de son onglet
// (chargerDiffOnglet), pour ne pas appeler `git show` tant qu'Alain ne consulte
// pas le diff.
function basculerOngletReponse(btn, onglet) {
  const onglets = btn.closest('.reponse-onglets');
  if (!onglets) return;
  onglets.querySelectorAll('.reponse-tab').forEach(t => t.classList.remove('actif'));
  btn.classList.add('actif');
  onglets.querySelectorAll('.reponse-pane').forEach(p => p.classList.remove('actif'));
  const pane = onglets.querySelector('.reponse-pane-' + onglet);
  if (!pane) return;
  pane.classList.add('actif');
  if (onglet === 'diff') chargerDiffOnglet(pane);
}

// Charge (une seule fois) le contenu de l'onglet « Diff » : pour chaque hash
// porté par le dataset, appelle /diff/<projet>/<hash> et rend la sortie colorée.
// Aucun hash (lecture seule) : le message « aucun commit associé » posé à la
// construction reste affiché, rien à charger. En cas d'erreur réseau, l'onglet
// est remis en état « à recharger » pour permettre une nouvelle tentative.
async function chargerDiffOnglet(pane) {
  if (!pane || pane.dataset.charge === '1') return;
  const hashes = (pane.dataset.hashes || '').split(',').filter(Boolean);
  if (!hashes.length) return;   // message « aucun commit » déjà en place
  pane.dataset.charge = '1';
  const nom = pane.dataset.projet || '';
  pane.innerHTML = '<div class="diff-vide">Chargement du diff…</div>';
  const morceaux = [];
  let echecReseau = false;
  for (const h of hashes) {
    try {
      const rep = await fetch('/diff/' + encodeURIComponent(nom)
                              + '/' + encodeURIComponent(h));
      const json = await rep.json();
      if (json.erreur) {
        morceaux.push('<div class="diff-erreur">Commit ' + escapeHtml(h)
                      + ' : ' + escapeHtml(json.erreur) + '</div>');
      } else {
        morceaux.push('<pre class="diff-bloc">' + colorierDiff(json.diff || '') + '</pre>');
      }
    } catch(e) {
      echecReseau = true;
      morceaux.push('<div class="diff-erreur">Commit ' + escapeHtml(h)
                    + ' : erreur réseau.</div>');
    }
  }
  if (echecReseau) pane.dataset.charge = '0';   // autorise une nouvelle tentative
  pane.innerHTML = morceaux.join('');
}

// Clic sur le badge « All » d'une issue fermée+done (issue #114, rôle confirmé
// #116) : copie, en un seul geste, la réponse CCL COMPLÈTE (réutilise
// reponseCompleteCcl) suivie du diff du/des commit(s) associé(s) (fetch /diff
// pour chaque hash). Sans commit (lecture seule), copie la réponse seule — sans
// section diff vide ni erreur. Même mécanique cache/fetch et feedback que les
// autres badges de la liste.
async function copierToutEtDiffDepuisBadge(event, nom, numero) {
  event.stopPropagation();
  const badge = event.currentTarget;   // capturé avant tout await (nullé ensuite)
  const original = badge ? badge.textContent : '';
  const titreOriginal = badge ? badge.title : '';
  numero = String(numero);
  const cleCache = CLE_CACHE_DETAIL + nom + '_' + numero;
  let it = null;

  // 1) Cache frais (< TTL) : on évite le fetch du détail.
  try {
    const obj = JSON.parse(localStorage.getItem(cleCache) || 'null');
    if (obj && obj.it && (Date.now() - obj.ts) < TTL_DETAIL_MS) it = obj.it;
  } catch(e) {}

  // 2) Pas de cache exploitable : fetch le détail et rafraîchit le cache.
  if (it === null) {
    try {
      const rep = await fetch('/issue/' + encodeURIComponent(nom)
                              + '/' + encodeURIComponent(numero));
      const j = await rep.json();
      if (!j.erreur) {
        it = j;
        try { localStorage.setItem(cleCache, JSON.stringify({ts: Date.now(), it: it})); } catch(e) {}
      }
    } catch(e) {
      console.warn('copierToutEtDiffDepuisBadge : échec fetch du détail.', e);
    }
  }

  let texte = it ? reponseCompleteCcl(it) : '';
  const hashes = it ? hashesDeCommit(it) : [];
  // Concatène le diff de chaque commit sous la réponse complète. Lecture seule
  // (aucun hash) : la boucle ne s'exécute pas, on copie la réponse seule.
  for (const h of hashes) {
    try {
      const rep = await fetch('/diff/' + encodeURIComponent(nom)
                              + '/' + encodeURIComponent(h));
      const j = await rep.json();
      if (j.diff) texte += '\n\n===== Diff ' + h + ' =====\n\n' + j.diff;
    } catch(e) {
      console.warn('copierToutEtDiffDepuisBadge : échec fetch diff ' + h + '.', e);
    }
  }

  // Garde « copie vide » (issue #122) : fetch du détail en échec ou réponse CCL
  // pas encore propagée côté GitHub → texte vide. Feedback ⚠, aucune copie
  // silencieuse, pas de ✓ trompeur.
  if (texteCopieVide(texte)) { feedbackBadgeVide(badge, original, titreOriginal); return; }

  // Copie dans le presse-papier (fallback silencieux si indisponible / non-HTTPS).
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(texte);
    } catch(e) {
      console.warn('copierToutEtDiffDepuisBadge : échec navigator.clipboard.', e);
    }
  } else {
    console.warn('copierToutEtDiffDepuisBadge : navigator.clipboard indisponible (non-HTTPS).');
  }

  // Feedback visuel : « All » → ✓ pendant 1,5 s, puis retour au libellé.
  if (badge) {
    badge.textContent = '✓';
    setTimeout(function() { badge.textContent = original; }, 1500);
  }
}

// Clic sur le badge « Diff » d'une issue fermée+done (issue #116) : copie
// UNIQUEMENT le diff du/des commit(s) associé(s) (fetch /diff pour chaque hash),
// sans la réponse — pendant du bloc résultat filtré sur son seul onglet « Diff ».
// Sans commit (lecture seule), comportement NEUTRE : rien n'est copié, feedback
// « ∅ » bref, pas d'erreur. Même mécanique cache/fetch du détail et feedback que
// les autres badges de la liste.
async function copierDiffDepuisBadge(event, nom, numero) {
  event.stopPropagation();
  const badge = event.currentTarget;   // capturé avant tout await (nullé ensuite)
  const original = badge ? badge.textContent : '';
  const titreOriginal = badge ? badge.title : '';
  numero = String(numero);
  const cleCache = CLE_CACHE_DETAIL + nom + '_' + numero;
  let it = null;

  // 1) Cache frais (< TTL) : on évite le fetch du détail.
  try {
    const obj = JSON.parse(localStorage.getItem(cleCache) || 'null');
    if (obj && obj.it && (Date.now() - obj.ts) < TTL_DETAIL_MS) it = obj.it;
  } catch(e) {}

  // 2) Pas de cache exploitable : fetch le détail et rafraîchit le cache.
  if (it === null) {
    try {
      const rep = await fetch('/issue/' + encodeURIComponent(nom)
                              + '/' + encodeURIComponent(numero));
      const j = await rep.json();
      if (!j.erreur) {
        it = j;
        try { localStorage.setItem(cleCache, JSON.stringify({ts: Date.now(), it: it})); } catch(e) {}
      }
    } catch(e) {
      console.warn('copierDiffDepuisBadge : échec fetch du détail.', e);
    }
  }

  const hashes = it ? hashesDeCommit(it) : [];
  // Aucun commit (lecture seule) : rien à copier, comportement neutre. Feedback
  // « ∅ » bref pour signaler l'absence de diff, sans toucher au presse-papier.
  if (!hashes.length) {
    if (badge) {
      badge.textContent = '∅';
      setTimeout(function() { badge.textContent = original; }, 1500);
    }
    return;
  }

  // Concatène le diff de chaque commit — sans la réponse (contraste avec « All »).
  const morceaux = [];
  for (const h of hashes) {
    try {
      const rep = await fetch('/diff/' + encodeURIComponent(nom)
                              + '/' + encodeURIComponent(h));
      const j = await rep.json();
      if (j.diff) morceaux.push('===== Diff ' + h + ' =====\n\n' + j.diff);
    } catch(e) {
      console.warn('copierDiffDepuisBadge : échec fetch diff ' + h + '.', e);
    }
  }
  const texte = morceaux.join('\n\n');

  // Garde « copie vide » (issue #122) : des commits existent mais tous les fetch
  // de diff ont échoué / renvoyé vide → texte vide. Feedback ⚠, aucune copie
  // silencieuse, pas de ✓ trompeur. (Le cas « aucun commit » reste géré par ∅
  // plus haut, feedback neutre déjà distinct du ✓.)
  if (texteCopieVide(texte)) { feedbackBadgeVide(badge, original, titreOriginal); return; }

  // Copie dans le presse-papier (fallback silencieux si indisponible / non-HTTPS).
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(texte);
    } catch(e) {
      console.warn('copierDiffDepuisBadge : échec navigator.clipboard.', e);
    }
  } else {
    console.warn('copierDiffDepuisBadge : navigator.clipboard indisponible (non-HTTPS).');
  }

  // Feedback visuel : « Diff » → ✓ pendant 1,5 s, puis retour au libellé.
  if (badge) {
    badge.textContent = '✓';
    setTimeout(function() { badge.textContent = original; }, 1500);
  }
}

// Ferme une issue en attente sur GitHub (pas encore traitée par le watcher),
// puis rafraîchit l'affichage et la combobox.
async function annulerIssue(nom, numero) {
  if (!confirm("Annuler (fermer) l'issue #" + numero + " sur GitHub ?")) return;
  try {
    const rep = await fetch('/annuler-issue/' + encodeURIComponent(nom)
                            + '/' + encodeURIComponent(numero), {method: 'POST'});
    const json = await rep.json();
    if (!json.succes) {
      alert('Erreur : ' + (json.message || 'échec de l\'annulation.'));
      return;
    }
  } catch(e) {
    alert('Erreur réseau : ' + e.message);
    return;
  }
  // Recharge la liste (l'issue devient fermée) puis réaffiche la même issue si
  // sa ligne existe encore et reste visible (projet non filtré).
  const numStr = String(numero);
  await chargerListeIssues();
  const ligne = [...document.querySelectorAll('#liste-issues .ligne-issue')]
    .find(l => l.dataset.projet === nom && l.dataset.numero === numStr);
  if (ligne && ligne.style.display !== 'none') {
    await afficherIssue(nom, numStr);
  }
}

// Ferme définitivement une issue en échec (label needs-human) après
// intervention humaine, puis rafraîchit l'affichage et la combobox (issue #80).
// L'action est irréversible → double confirmation via confirm().
async function fermerIssue(nom, numero) {
  if (!confirm("Fermer définitivement l'issue #" + numero
               + " ? Cette action est irréversible.")) return;
  try {
    const rep = await fetch('/fermer-issue/' + encodeURIComponent(nom)
                            + '/' + encodeURIComponent(numero), {method: 'POST'});
    const json = await rep.json();
    if (!json.succes) {
      alert('Erreur : ' + (json.message || 'échec de la fermeture.'));
      return;
    }
  } catch(e) {
    alert('Erreur réseau : ' + e.message);
    return;
  }
  // Recharge la liste (l'issue devient fermée) puis réaffiche la même issue si
  // sa ligne existe encore et reste visible (projet non filtré).
  const numStr = String(numero);
  await chargerListeIssues();
  const ligne = [...document.querySelectorAll('#liste-issues .ligne-issue')]
    .find(l => l.dataset.projet === nom && l.dataset.numero === numStr);
  if (ligne && ligne.style.display !== 'none') {
    await afficherIssue(nom, numStr);
  }
}

// Interrompt le CCL en cours ET ferme l'issue en un seul geste (issue #144).
// Cas visé : une issue « en cours de traitement » (for-linux, pas needs-human,
// au moins un commentaire = ACK posté). Le CCL tourne déjà : la seule façon de
// l'interrompre est de couper le watcher du projet — après #145, /arreter-watcher
// fait un killpg qui tue réellement le `claude` en cours (pas seulement la boucle
// du watcher). Ordre imposé des deux appels réseau : (1) arrêt du watcher, puis
// (2) fermeture de l'issue — on ne ferme que si la coupure a réussi ou que le
// watcher était déjà inactif. Le watcher reste ÉTEINT : Alain le relance lui-même
// depuis l'onglet Watchers quand il est prêt (pas de relance automatique).
async function fermerEtInterrompre(nom, numero) {
  if (!confirm("Ceci va arrêter le watcher du projet " + nom
             + " (donc interrompre le CCL en cours pour CETTE issue comme pour"
             + " toute autre en attente sur ce projet) puis fermer l'issue #"
             + numero + ". Le watcher restera éteint : tu devras le relancer"
             + " toi-même depuis l'onglet Watchers. Continuer ?")) return;

  // (1) Arrêt du watcher (killpg via #145). On tolère « watcher déjà inactif » :
  // dans ce cas succes=false mais l'objectif (plus de CCL en cours) est atteint,
  // et on enchaîne quand même sur la fermeture.
  let arretOk = false;
  try {
    const rep = await fetch('/arreter-watcher', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({projet: nom})
    });
    const json = await rep.json();
    arretOk = json.succes || /déjà inactif/i.test(json.message || '');
    if (!arretOk) {
      alert('Erreur : arrêt du watcher impossible — '
            + (json.message || json.erreur || 'cause inconnue')
            + '. Issue NON fermée.');
      return;
    }
  } catch(e) {
    alert('Erreur réseau lors de l\'arrêt du watcher : ' + e.message
          + '. Issue NON fermée.');
    return;
  }

  // (2) Fermeture de l'issue, seulement après un arrêt réussi (ou déjà inactif).
  // fermerIssue() (inchangée) recharge déjà la liste des issues en fin de course.
  await fermerIssue(nom, numero);

  // Reflète l'état « watcher éteint » si l'onglet Watchers est actuellement affiché.
  const panneauWatchers = document.getElementById('panneau-watchers');
  if (panneauWatchers && panneauWatchers.classList.contains('actif')) {
    await chargerWatchers();
  }
}

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

function afficherMessage(texte, type) {
  const el = document.getElementById('message');
  el.textContent = texte;
  el.className = 'message ' + type;
  el.style.display = 'block';
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

// Lecture d'un champ d'en-tête « | CHAMP | valeur | » dans le corps collé.
// Source unique de vérité pour tout le parsing d'en-tête côté formulaire :
// détection PROJET (#44/#109), TIMEOUT (#111) et résumé d'en-tête (#117)
// s'appuient tous dessus, pour éviter des regex divergentes.
//   • mot-clé insensible à la casse, espaces tolérés autour des séparateurs ;
//   • la valeur est la cellule entre le 2e et le 3e « | », nettoyée ;
//   • retourne la valeur (chaîne non vide) ou null (champ absent ou vide).
function lireChampEntete(corps, champ) {
  const re = new RegExp('^\\s*\\|\\s*' + champ + '\\s*\\|([^|]*)\\|', 'im');
  const m = (corps || '').match(re);
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
function retirerLigneEntete(corps, champ) {
  const re = new RegExp('^\\s*\\|\\s*' + champ + '\\s*\\|[^|]*\\|', 'im');
  const m = (corps || '').match(re);
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
function detecterIncoherenceProjet(data) {
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

async function envoyerIssue() {
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

  const btn = document.getElementById('btn-envoyer');
  btn.disabled = true; btn.textContent = 'Envoi…';
  try {
    const rep = await fetch('/envoyer', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
    const json = await rep.json();
    if (json.succes) {
      afficherMessage('✓ Issue créée : ' + json.url, 'succes');
      viderFormulaire(false);
    } else {
      afficherMessage('Erreur : ' + json.erreur, 'erreur');
    }
  } catch(e) {
    afficherMessage('Erreur réseau : ' + e.message, 'erreur');
  }
  // Restaure le libellé avec le projet cible plutôt qu'un texte générique.
  btn.disabled = false;
  btn.textContent = 'Envoyer sur ' + document.getElementById('projet').value;
}

async function chargerWatchers() {
  const rep  = await fetch('/watchers');
  const liste = await rep.json();
  const tbody = document.getElementById('corps-watchers');
  // Mémoriser la sélection en cours avant de reconstruire les lignes,
  // pour ne pas la perdre lors d'un rafraîchissement automatique (issue #123).
  const coches = new Set(
    [...tbody.querySelectorAll('.cb-watcher:checked')].map(c => c.value)
  );
  tbody.innerHTML = '';
  for (const w of liste) {
    const tr = document.createElement('tr');
    tr.style.borderBottom = '1px solid #f0efe9';
    tr.innerHTML = `
      <td style="padding:10px 0;text-align:center">
        <input type="checkbox" class="cb-watcher" value="${w.nom}"
               ${coches.has(w.nom) ? 'checked' : ''}
               onchange="mettreAJourCompte()">
      </td>
      <td style="padding:10px 4px">
        <span style="width:8px;height:8px;border-radius:50%;
              background:${w.actif ? '#5cb85c' : '#d9534f'};
              display:inline-block"></span>
      </td>
      <td style="padding:10px 12px;font-size:13px">${w.nom}</td>
      <td style="padding:10px 12px;font-size:13px;color:#888">${w.depot}</td>
      <td style="padding:10px 0;font-size:12px;color:#aaa">
        ${w.actif ? 'pid ' + w.pid : '—'}
      </td>`;
    tbody.appendChild(tr);
  }
  // Recalculer "cb-tous" en fonction de l'état restauré : coché seulement
  // si toutes les lignes reconstruites sont cochées (et qu'il y en a au moins une).
  const toutes = tbody.querySelectorAll('.cb-watcher');
  document.getElementById('cb-tous').checked =
    toutes.length > 0 &&
    tbody.querySelectorAll('.cb-watcher:checked').length === toutes.length;
  mettreAJourCompte();
}

function selectionnerTous(cb) {
  document.querySelectorAll('.cb-watcher').forEach(c => c.checked = cb.checked);
  mettreAJourCompte();
}

function mettreAJourCompte() {
  const n = document.querySelectorAll('.cb-watcher:checked').length;
  document.getElementById('compte-selection').textContent =
    n === 0 ? 'Aucun sélectionné' : `${n} sélectionné(s)`;
}

async function actionWatchers(action) {
  const selectionnes = [...document.querySelectorAll('.cb-watcher:checked')].map(c => c.value);
  if (!selectionnes.length) {
    const msg = document.getElementById('msg-watchers');
    msg.textContent = 'Sélectionne au moins un projet.';
    msg.className = 'message erreur'; msg.style.display = 'block';
    setTimeout(() => msg.style.display = 'none', 3000);
    return;
  }
  document.getElementById('msg-watchers').style.display = 'none';

  const route   = action === 'arreter' ? '/arreter-watcher' : '/lancer-watcher';
  const payload = action === 'lancer'
    ? (nom) => ({projet: nom, relancer: false})
    : (nom) => ({projet: nom, relancer: action === 'relancer'});

  for (const nom of selectionnes) {
    await fetch(route, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload(nom))
    });
  }

  // Issue #141 : décocher explicitement les cases traitées AVANT que
  // chargerWatchers() ne restaure la sélection (mécanisme #123 prévu pour le
  // rafraîchissement automatique). Ordre : décochage → message → chargerWatchers().
  const traites = new Set(selectionnes);
  document.querySelectorAll('.cb-watcher').forEach(c => {
    if (traites.has(c.value)) c.checked = false;
  });
  const cbTous = document.getElementById('cb-tous');
  if (cbTous) cbTous.checked = false;
  mettreAJourCompte();

  const verbe = action === 'arreter' ? 'arrêté(s)'
              : action === 'relancer' ? 'relancé(s)'
              : 'lancé(s)';
  const msg = document.getElementById('msg-watchers');
  msg.textContent = `${selectionnes.length} watcher(s) ${verbe}.`;
  msg.className = 'message succes'; msg.style.display = 'block';
  setTimeout(() => msg.style.display = 'none', 3000);

  await chargerWatchers();
  await verifierStatut();
}

function mettreAJourBoutonEnvoi() {
  const ecriture = document.querySelector('input[name=mode]:checked').value === 'ecriture';
  const btn = document.getElementById('btn-envoyer');
  btn.style.background    = ecriture ? '#a32d2d' : '#1a1a18';
  btn.style.borderColor   = ecriture ? '#a32d2d' : '#1a1a18';
}

// Détection de « #Titre: … » en première ligne du corps.
// Permet de coller titre + corps en un seul copier-coller dans le champ #corps :
// si la première ligne commence par « #Titre: » (insensible à la casse, espaces
// tolérés après « : »), on déplace ce qui suit dans #titre et on retire cette
// ligne du corps. Le champ #titre reste éditable normalement ; taper directement
// dedans ne déclenche aucun comportement automatique (l'écouteur est sur #corps).
function detecterTitreDansCorps() {
  const corpsEl = document.getElementById('corps');
  // En mode lot (2+ blocs « #Titre: »), cette détection mono-titre n'a plus de
  // sens : c'est envoyerLot qui traite chaque bloc avec son propre titre. On la
  // neutralise tant que le lot est détecté (issue #135).
  if (enModeLot()) return;
  const valeur  = corpsEl.value;
  const finLigne      = valeur.indexOf('\n');
  const premiereLigne = finLigne === -1 ? valeur : valeur.slice(0, finLigne);
  const m = premiereLigne.match(/^#titre:\s*(.*)$/i);
  if (!m) return;

  // Mémorise le mode courant : la détection ne touche pas au mode, mais on
  // n'appelle mettreAJourBoutonEnvoi() que s'il a effectivement changé.
  const modeAvant = document.querySelector('input[name=mode]:checked').value;

  document.getElementById('titre').value = m[1].trim();
  // Supprime la première ligne (et son saut de ligne) du corps.
  corpsEl.value = finLigne === -1 ? '' : valeur.slice(finLigne + 1);

  const modeApres = document.querySelector('input[name=mode]:checked').value;
  if (modeApres !== modeAvant) mettreAJourBoutonEnvoi();
}
document.getElementById('corps').addEventListener('input', detecterTitreDansCorps);

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
    onProjetChange(false);             // applique accent, statut, infos — SANS
                                       // réinitialiser le timeout (#143) : le
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
document.getElementById('corps').addEventListener('input', detecterProjetDansCorps);

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
document.getElementById('corps').addEventListener('input', detecterTimeoutDansCorps);

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
  'TYPE', 'SPECS', 'SUITE_DE', 'FICHIER_CONTEXTE',
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
document.getElementById('corps').addEventListener('input', mettreAJourResumeEntete);

// ─── Envoi en lot de plusieurs issues (issue #135) ────────────────────────
// Un seul copier-coller peut contenir PLUSIEURS blocs « #Titre: … » à la
// suite : chacun devient une issue indépendante, envoyée en séquence sans
// validation intermédiaire. On généralise detecterTitreDansCorps, qui ne
// traite QUE la première ligne, en appliquant la même règle à CHAQUE ligne
// « #Titre: » (insensible à la casse, en début de ligne).

// Découpe le corps en blocs, un par ligne « #Titre: ». Chaque bloc va de son
// « #Titre: » jusqu'au « #Titre: » suivant (exclu) ou la fin du corps ; on en
// extrait le titre (texte après « #Titre: », trim) et le reste du bloc (la
// ligne « #Titre: » retirée), exactement comme le flux mono-issue mais appliqué
// à un fragment. Retourne un tableau de {titre, corps} — vide si aucune ligne
// « #Titre: » n'est trouvée (→ pas de mode lot, comportement inchangé).
function decouperCorpsEnBlocs(corps) {
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
function projetEffectifBloc(bloc, projetForm) {
  return lireChampEntete(bloc.corps, 'PROJET') || projetForm;
}

// Bascule le bouton d'envoi entre mode mono-issue et mode lot selon le contenu
// du corps. En lot : « Envoyer le lot (N issues) sur <projet(s)> » → envoyerLot ;
// sinon on restaure le bouton normal « Envoyer sur <projet> » → envoyerIssue.
// Les projets ciblés sont calculés bloc par bloc (même repli que envoyerLot) pour
// donner à Alain la même confirmation visuelle qu'en mono-issue (issue #142).
function mettreAJourBoutonLot() {
  const blocs = decouperCorpsEnBlocs(document.getElementById('corps').value);
  const btn   = document.getElementById('btn-envoyer');
  if (blocs.length >= 2) {
    const projetForm = document.getElementById('projet').value;
    // Ensemble ordonné des projets distincts effectivement ciblés par le lot.
    const projets = [];
    for (const bloc of blocs) {
      const p = projetEffectifBloc(bloc, projetForm);
      if (p && !projets.includes(p)) projets.push(p);
    }
    let suffixe = '';
    if (projets.length === 1) {
      suffixe = ' sur ' + projets[0];
    } else if (projets.length > 1) {
      suffixe = ' sur plusieurs projets (' + projets.join(', ') + ')';
    }
    btn.textContent = 'Envoyer le lot (' + blocs.length + ' issues)' + suffixe;
    btn.onclick = envoyerLot;
  } else {
    btn.textContent = 'Envoyer sur ' + document.getElementById('projet').value;
    btn.onclick = envoyerIssue;
  }
}
document.getElementById('corps').addEventListener('input', mettreAJourBoutonLot);

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
// MODELE lus dans le bloc (repli sur le formulaire), MODE/notifs communs. Envoi
// UN PAR UN (await entre chaque, jamais en parallèle → pas de conflit gh). AUCUNE
// modale (issues en attente / incohérence projet) : le but du lot est d'enchaîner
// sans validation. Un bloc en échec n'interrompt pas le lot ; tout est reporté
// dans le résumé final. (issue #135)
async function envoyerLot() {
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

  const btn = document.getElementById('btn-envoyer');
  btn.disabled = true;

  const resultats = [];
  for (let i = 0; i < blocs.length; i++) {
    const bloc = blocs[i];
    btn.textContent = 'Envoi ' + (i + 1) + '/' + blocs.length + '…';

    // Champs d'en-tête lus dans le bloc ; repli sur les valeurs du formulaire.
    const projetBloc   = lireChampEntete(bloc.corps, 'PROJET');
    const timeoutBloc  = lireChampEntete(bloc.corps, 'TIMEOUT');
    const modeleBloc   = lireChampEntete(bloc.corps, 'MODELE');
    const prioriteBloc = lireChampEntete(bloc.corps, 'PRIORITE');

    const projet = projetEffectifBloc(bloc, projetForm);

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

    const data = {
      projet:          projet,
      titre:           bloc.titre,
      priorite:        prioriteBloc || base.priorite,
      timeout:         timeout,
      mode:            base.mode,
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
        resultats.push({succes: true, titre: bloc.titre, projet: projet,
                        url: json.url, incoherence: incoherence});
      } else {
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
  // Vide le corps une fois le lot terminé (comme envoyerIssue après un succès),
  // sans masquer le récapitulatif qu'on vient d'afficher.
  viderFormulaire(false);
  btn.disabled = false;
  // Le corps a été vidé par programme (pas d'event « input ») : on rebascule
  // explicitement le bouton en mode mono.
  mettreAJourBoutonLot();
}

async function verifierStatut() {
  const nom = document.getElementById('projet').value;
  try {
    const rep  = await fetch('/statut/' + encodeURIComponent(nom));
    const json = await rep.json();
    const dot  = document.getElementById('dot-statut');
    const txt  = document.getElementById('texte-statut');
    const btn  = document.getElementById('btn-watcher');
    if (json.actif) {
      dot.style.background = '#5cb85c';
      txt.style.color      = '#155724';
      txt.textContent      = 'Watcher actif (pid ' + json.pid + ')';
      btn.textContent      = 'Relancer le watcher';
    } else {
      dot.style.background = '#d9534f';
      txt.style.color      = '#888';
      txt.textContent      = 'Watcher inactif';
      btn.textContent      = 'Lancer le watcher';
    }
  } catch(e) { /* réseau indisponible — on ignore */ }
}

async function lancerWatcher() {
  const btn = document.getElementById('btn-watcher');
  btn.disabled = true; btn.textContent = 'Démarrage…';
  try {
    const rep  = await fetch('/lancer-watcher', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({projet: document.getElementById('projet').value})
    });
    const json = await rep.json();
    if (!json.succes) afficherMessage('Erreur watcher : ' + json.erreur, 'erreur');
  } catch(e) {
    afficherMessage('Erreur réseau : ' + e.message, 'erreur');
  }
  btn.disabled = false;
  await verifierStatut();
}

// Au chargement : restaure le dernier projet mémorisé (localStorage) s'il
// correspond encore à une option existante, puis initialise l'accent visuel, le
// statut et les infos via onProjetChange(). Sonde ensuite toutes les 5 s.
(function restaurerProjet() {
  const select = document.getElementById('projet');
  let dernier = null;
  try { dernier = localStorage.getItem('bridge_projet_actif'); } catch(e) {}
  if (dernier && [...select.options].some(o => o.value === dernier)) {
    select.value = dernier;
  }
  onProjetChange();
})();
setInterval(verifierStatut, 5000);

// ─── Cycle de vie : onglet ↔ serveur ──────────────────────────────────────
// Deux liens : (1) heartbeat navigateur → serveur, qui laisse le serveur se
// couper tout seul quand l'onglet est fermé ; (2) canal SSE serveur → onglet,
// qui affiche un overlay quand le serveur s'arrête (Ctrl+C ou coupure brutale).
let sourceEvents     = null;
let timerErreurArret = null;

function afficherOverlayArret() {
  const ov = document.getElementById('overlay-arret');
  if (ov) ov.classList.add('actif');
}

// Heartbeat périodique : signale au serveur que l'onglet est toujours ouvert.
function envoyerHeartbeat() {
  fetch('/heartbeat', {method: 'POST'}).catch(() => {});
}

// Avant tout déchargement (F5, Ctrl+R, navigation, fermeture), on pose un
// drapeau : au chargement suivant, sa présence révèle un simple rechargement.
window.addEventListener('beforeunload', function() {
  try { sessionStorage.setItem('_refresh', '1'); } catch(e) {}
});

function demarrerCycleVie() {
  // Distinction refresh / fermeture : si le drapeau est présent, c'était un
  // rechargement — on le retire et on reprend normalement. S'il est absent,
  // c'était une vraie fermeture (mais alors le serveur est déjà coupé : la
  // connexion SSE tombée — et le heartbeat interrompu — l'ont fait s'arrêter,
  // donc ce code ne s'exécute pas).
  try {
    if (sessionStorage.getItem('_refresh')) sessionStorage.removeItem('_refresh');
  } catch(e) {}

  envoyerHeartbeat();
  setInterval(envoyerHeartbeat, 5000);

  // Résistance au throttling (issue #157) : les navigateurs ralentissent
  // fortement le setInterval des onglets en arrière-plan, ce qui pouvait faire
  // croire au serveur que l'onglet était fermé. Au retour au premier plan, on
  // force un heartbeat immédiat. La détection de vraie fermeture repose surtout
  // sur la connexion SSE /events (non throttlée), ceci n'est qu'un renfort.
  document.addEventListener('visibilitychange', function() {
    if (!document.hidden) envoyerHeartbeat();
    // DIAGNOSTIC TEMPORAIRE — issue #157, à retirer : trace chaque passage
    // avant-plan / arrière-plan (console + POST serveur) pour corréler après
    // coup « onglet caché » avec « serveur coupé ». Retirer ce bloc (garder le
    // envoyerHeartbeat() ci-dessus, qui fait partie du correctif).
    var etat = document.hidden ? 'caché (arrière-plan)' : 'visible (premier plan)';
    console.log('[DIAG #157] visibilitychange → ' + etat + ' @ ' + new Date().toISOString());
    fetch('/diag-visibilite', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({etat: etat, horodatage: new Date().toISOString()})
    }).catch(function() {});
  });

  // Canal serveur → onglet.
  sourceEvents = new EventSource('/events');

  // Arrêt propre du serveur (Ctrl+C) : event « shutdown » explicite.
  sourceEvents.addEventListener('shutdown', function() {
    if (timerErreurArret) { clearTimeout(timerErreurArret); timerErreurArret = null; }
    sourceEvents.close();
    afficherOverlayArret();
  });

  // Connexion (r)établie : annule une éventuelle alerte en attente.
  sourceEvents.onopen = function() {
    if (timerErreurArret) { clearTimeout(timerErreurArret); timerErreurArret = null; }
  };

  // Coupure brutale (serveur tué sans signal) : la connexion SSE tombe en
  // erreur. Délai de 3 s avant l'overlay pour ne pas réagir à un micro-freeze ;
  // si la connexion se rétablit entre-temps, onopen annule le timer.
  sourceEvents.onerror = function() {
    if (timerErreurArret) return;
    timerErreurArret = setTimeout(function() {
      timerErreurArret = null;
      afficherOverlayArret();
    }, 3000);
  };
}
demarrerCycleVie();

// Arrêt volontaire depuis l'onglet : window.close() est autorisé par le
// navigateur car déclenché par une action utilisateur (contrairement à Ctrl+C
// côté serveur, qui ne peut que déclencher l'overlay via /events). On prévient
// le serveur (/quitter pose arret_demande puis os._exit après 2 s) et on ferme.
async function quitter() {
  if (!confirm('Arrêter new_issue.py et fermer l\'onglet ?')) return;
  await fetch('/quitter', {method: 'POST'});
  window.close();
}

// ─── Mémorisation de notif_pc (issue #93) ─────────────────────────────────
// notif_pc est coché par défaut au premier usage. Si Alain le décoche, ce
// choix est mémorisé (localStorage) et respecté aux ouvertures suivantes,
// jusqu'à ce qu'il le recoche. Cohérent avec le pattern des autres clés
// « bridge_* » de l'interface. notif_gsm / notif_tous ne sont pas concernés.
const CLE_NOTIF_PC = 'bridge_notif_pc';

// Applique l'état mémorisé au champ notif_pc : coché par défaut si la clé
// n'existe pas encore, sinon l'état enregistré ('true' / 'false').
function appliquerNotifPc() {
  const cb = document.getElementById('notif_pc');
  if (!cb) return;
  let memo = null;
  try { memo = localStorage.getItem(CLE_NOTIF_PC); } catch(e) {}
  cb.checked = (memo === null) ? true : (memo === 'true');
}

// À chaque changement manuel, on écrit l'état courant dans localStorage.
(function initNotifPc() {
  const cb = document.getElementById('notif_pc');
  if (cb) {
    cb.addEventListener('change', function() {
      try { localStorage.setItem(CLE_NOTIF_PC, cb.checked ? 'true' : 'false'); } catch(e) {}
    });
  }
  appliquerNotifPc();
})();

function viderFormulaire(cacherMsg=true) {
  if (cacherMsg) cacherRetours();
  document.getElementById('titre').value = '';
  document.getElementById('corps').value = '';
  document.getElementById('priorite').value = 'normale';
  // Réinitialise le timeout sur la valeur TIMEOUT_CLAUDE du projet courant.
  mettreAJourInfoProjet();
  document.querySelector('input[name=mode][value=lecture]').checked = true;
  mettreAJourBoutonEnvoi();
  document.querySelectorAll('input[name=notifs]').forEach(c => c.checked = false);
  // notif_pc revient à l'état mémorisé (coché par défaut), pas à décoché.
  appliquerNotifPc();
  document.getElementById('modele-ponctuel').value = '';
  // Réinitialise l'état des détections d'en-tête (issues #117/#129) : sans ça,
  // un ancien PROJET/TIMEOUT mémorisé empêcherait de redétecter la même valeur
  // au prochain collage, et le résumé afficherait des champs d'une issue passée.
  dernierProjetAutoDetecte  = null;
  dernierTimeoutAutoDetecte = null;
  champsEnteteExtraits      = {};
  // Le corps est vidé par programme (pas d'event « input ») : on masque
  // explicitement le résumé d'en-tête (issue #117).
  mettreAJourResumeEntete();
}

// ─── Nouveau projet (issue #99) ───────────────────────────────────────────
// Modal reproduisant fidèlement les étapes de nouveau_projet.py, exécutées
// côté serveur par app/nouveau_projet.py (qui réutilise le script CLI sans le
// dupliquer). Les défauts (dépôt, répertoire) sont pré-remplis mais restent
// modifiables ; un champ touché à la main n'est plus écrasé par l'auto-remplissage.

let npDepotEdite = false, npRepEdite = false, npPerimetreEdite = false;
let npTimerVerif = null;
// Couleur d'accent choisie dans le modal (hex #RRGGBB). '' tant qu'aucune
// pastille n'est rendue ou si la palette est épuisée (issue #121).
let npCouleurChoisie = '';

function ouvrirNouveauProjet() {
  ['np-nom', 'np-depot', 'np-rep', 'np-perimetre', 'np-topic'].forEach(id =>
    document.getElementById(id).value = '');
  document.getElementById('np-specs').checked = false;
  document.getElementById('np-creer-depot').checked = true;
  document.getElementById('np-creer-depot-ligne').style.display = 'none';
  document.getElementById('np-nom-msg').textContent = '';
  document.getElementById('np-depot-msg').textContent = '';
  document.getElementById('np-compte-rendu').style.display = 'none';
  document.getElementById('np-message').style.display = 'none';
  document.getElementById('np-rappel-git').style.display = 'none';
  const btn = document.getElementById('np-creer');
  btn.disabled = false; btn.textContent = 'Créer le projet';
  document.getElementById('np-fermer').textContent = 'Fermer';
  npDepotEdite = npRepEdite = npPerimetreEdite = false;
  npChargerCouleurs();
  document.getElementById('modal-nouveau-projet').classList.add('actif');
  document.getElementById('np-nom').focus();
}

function fermerNouveauProjet() {
  document.getElementById('modal-nouveau-projet').classList.remove('actif');
}

// Charge les couleurs de la palette encore libres (couleurs déjà attribuées à
// un projet existant exclues côté serveur) et rend une pastille par couleur.
// Appelée à l'ouverture du modal ; le nom n'a pas d'incidence sur la liste, on
// interroge donc /verifier avec un nom vide (qui renvoie couleurs_disponibles
// dans tous les cas).
async function npChargerCouleurs() {
  const cont = document.getElementById('np-couleurs');
  cont.innerHTML = 'Chargement…';
  npCouleurChoisie = '';
  let r;
  try {
    r = await (await fetch('/nouveau-projet/verifier?nom=')).json();
  } catch (e) {
    cont.textContent = 'Couleurs indisponibles (erreur réseau) — attribution automatique.';
    return;
  }
  npRendreCouleurs(r.couleurs_disponibles || []);
}

// Rend les pastilles cliquables et pré-sélectionne la première disponible.
function npRendreCouleurs(couleurs) {
  const cont = document.getElementById('np-couleurs');
  cont.innerHTML = '';
  if (!couleurs.length) {
    cont.textContent = 'Palette épuisée — couleur attribuée automatiquement.';
    npCouleurChoisie = '';
    return;
  }
  couleurs.forEach((c, i) => {
    const p = document.createElement('button');
    p.type = 'button';
    p.className = 'np-pastille' + (i === 0 ? ' choisie' : '');
    p.style.background = c;
    p.title = c;
    p.dataset.couleur = c;
    p.onclick = () => npChoisirCouleur(c);
    cont.appendChild(p);
  });
  npCouleurChoisie = couleurs[0];
}

// Sélectionne une pastille (couleur choisie pour le nouveau projet).
function npChoisirCouleur(c) {
  npCouleurChoisie = c;
  document.querySelectorAll('#np-couleurs .np-pastille').forEach(p =>
    p.classList.toggle('choisie', p.dataset.couleur === c));
}

// Saisie du nom : débounce puis vérification serveur (validité, .conf déjà pris,
// existence du dépôt) et pré-remplissage des champs par défaut non encore édités.
function npNomChange() {
  clearTimeout(npTimerVerif);
  npTimerVerif = setTimeout(npVerifier, 350);
}

// Changement manuel du dépôt : vérifie immédiatement son existence sur GitHub.
async function npVerifierDepot() {
  clearTimeout(npTimerVerif);
  await npVerifier();
}

async function npVerifier() {
  const nom       = document.getElementById('np-nom').value.trim().toLowerCase();
  const depotSaisi = document.getElementById('np-depot').value.trim();
  const nomMsg    = document.getElementById('np-nom-msg');
  const ligneCreer = document.getElementById('np-creer-depot-ligne');
  if (!nom) {
    nomMsg.textContent = '';
    document.getElementById('np-depot-msg').textContent = '';
    ligneCreer.style.display = 'none';
    return;
  }
  let r;
  try {
    const url = '/nouveau-projet/verifier?nom=' + encodeURIComponent(nom)
              + (depotSaisi ? '&depot=' + encodeURIComponent(depotSaisi) : '');
    r = await (await fetch(url)).json();
  } catch (e) {
    nomMsg.textContent = 'Erreur réseau : ' + e.message;
    nomMsg.style.color = '#a32d2d';
    return;
  }

  if (!r.nom_valide) {
    nomMsg.textContent = '⚠ Format invalide (minuscules, chiffres, underscore ; commence par une lettre).';
    nomMsg.style.color = '#a32d2d';
  } else if (r.conf_existe) {
    nomMsg.textContent = '⚠ configs/' + nom + '.conf existe déjà — choisir un autre nom.';
    nomMsg.style.color = '#a32d2d';
  } else {
    nomMsg.textContent = '✓ Nom disponible.';
    nomMsg.style.color = '#2e7d32';
  }

  // Pré-remplissage : uniquement les champs que l'utilisateur n'a pas touchés.
  if (r.nom_valide) {
    if (!npDepotEdite && r.depot_defaut) document.getElementById('np-depot').value = r.depot_defaut;
    if (!npRepEdite   && r.rep_defaut)   document.getElementById('np-rep').value   = r.rep_defaut;
  }

  npAfficherEtatDepot(r);
}

// Affiche l'état du dépôt vérifié : existant → installation (pas de recréation),
// absent → propose la case « créer le dépôt ».
function npAfficherEtatDepot(r) {
  const depotMsg   = document.getElementById('np-depot-msg');
  const ligneCreer = document.getElementById('np-creer-depot-ligne');
  if (!r.nom_valide || !r.depot) {
    depotMsg.textContent = '';
    ligneCreer.style.display = 'none';
    return;
  }
  if (r.depot_existe) {
    depotMsg.textContent = '✓ ' + r.depot + ' existe déjà → installation dessus (pas de recréation).';
    depotMsg.style.color = '#2e7d32';
    ligneCreer.style.display = 'none';
  } else {
    depotMsg.textContent = 'ℹ ' + r.depot + " n'existe pas encore.";
    depotMsg.style.color = '#8a6d00';
    ligneCreer.style.display = 'block';
  }
}

function npMsg(texte, type) {
  const el = document.getElementById('np-message');
  el.textContent = texte;
  el.className = 'message ' + type;
  el.style.display = 'block';
}

async function soumettreNouveauProjet() {
  const nom = document.getElementById('np-nom').value.trim().toLowerCase();
  const cr  = document.getElementById('np-compte-rendu');
  document.getElementById('np-message').style.display = 'none';
  cr.style.display = 'none';
  document.getElementById('np-rappel-git').style.display = 'none';
  if (!nom) { npMsg('Un nom de projet est requis.', 'erreur'); return; }

  const btn = document.getElementById('np-creer');
  const avant = btn.textContent;
  btn.disabled = true; btn.textContent = 'Création…';

  const data = {
    nom,
    depot:     document.getElementById('np-depot').value.trim(),
    rep:       document.getElementById('np-rep').value.trim(),
    perimetre: document.getElementById('np-perimetre').value.trim(),
    topic:     document.getElementById('np-topic').value.trim(),
    couleur:   npCouleurChoisie,
    avec_specs: document.getElementById('np-specs').checked,
    creer_depot_si_absent: document.getElementById('np-creer-depot').checked,
  };

  let res;
  try {
    const rep = await fetch('/nouveau-projet', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data),
    });
    res = await rep.json();
  } catch (e) {
    btn.disabled = false; btn.textContent = avant;
    npMsg('Erreur réseau : ' + e.message, 'erreur');
    return;
  }
  btn.textContent = avant;

  // Compte-rendu par étape (succès/échec), cohérent avec le script CLI.
  if (res.etapes && res.etapes.length) {
    cr.innerHTML = res.etapes.map(e =>
      (e.ok ? '✓ ' : '❌ ') + '<b>' + escapeHtml(e.etape) + '</b> — ' + escapeHtml(e.detail || '')
    ).join('<br>');
    cr.style.display = 'block';
  }

  if (res.succes) {
    npMsg('✅ Projet « ' + res.nom + ' » créé'
          + (res.depot_existait ? ' (installé sur dépôt existant)' : '') + '.', 'succes');
    // Enregistre la couleur persistée pour ce projet afin que les onglets déjà
    // chargés (Résultats, accent du bandeau) l'utilisent sans recharger la page.
    if (res.couleur) {
      window.COULEURS_PERSISTEES = window.COULEURS_PERSISTEES || {};
      window.COULEURS_PERSISTEES[res.nom] = res.couleur;
    }
    ajouterProjetAuSelecteur(res.nom, res.depot);
    // Rappel des 3 commandes git à lancer soi-même : le modal a modifié
    // BRIDGE_AGENT_DOC.md (§2) localement mais ne pousse pas (cohérent avec le
    // CLI — Alain vérifie puis pousse). Sans push, la doc reste invisible pour
    // Claude Chat. Encart distinct du compte-rendu, sélectionnable en un clic.
    afficherRappelGit(res.nom);
    // Création réussie : on verrouille « Créer » (évite un double envoi) et on
    // renomme « Fermer » en « Terminé ».
    btn.disabled = true;
    document.getElementById('np-fermer').textContent = 'Terminé';
  } else {
    btn.disabled = false;
    npMsg('❌ ' + (res.erreur || 'Échec de la création.'), 'erreur');
  }
}

// Affiche l'encart de rappel git après une création réussie : les 3 commandes
// (add/commit/push) avec le nom du projet inséré dans le message de commit.
// Un clic sur le <pre> sélectionne tout le bloc pour un copier-coller immédiat.
// Pas de persistance : l'encart n'a de sens que pour la création qui vient
// d'avoir lieu et disparaît à la prochaine ouverture du modal (issue #118).
function afficherRappelGit(nom) {
  const cmds = 'git add BRIDGE_AGENT_DOC.md\n'
             + 'git commit -m "Ajout du projet ' + nom + ' (§2)"\n'
             + 'git push';
  const box = document.getElementById('np-rappel-git');
  box.innerHTML =
    '<div class="titre">⚠ Action requise — pousser la doc sur GitHub</div>'
    + 'Le projet est créé, mais la mise à jour de <b>BRIDGE_AGENT_DOC.md</b> (§2) '
    + "n'est que locale. Tant qu'elle n'est pas poussée, le projet reste invisible "
    + 'pour Claude Chat. Exécute (clic pour sélectionner) :'
    + '<pre onclick="npSelectionnerTexte(this)">' + escapeHtml(cmds) + '</pre>';
  box.style.display = 'block';
}

// Sélectionne tout le texte d'un élément (le <pre> des commandes git) pour que
// l'utilisateur puisse copier en un clic puis Ctrl+C.
function npSelectionnerTexte(el) {
  const sel = window.getSelection();
  const range = document.createRange();
  range.selectNodeContents(el);
  sel.removeAllRanges();
  sel.addRange(range);
}

// Rafraîchit le sélecteur global SANS redémarrer new_issue.py (contrainte
// issue #99 : le <select> est peuplé côté serveur au chargement). Ajoute (ou
// met à jour) l'option, la sélectionne, met à jour le compteur d'en-tête, puis
// onProjetChange() applique accent/statut/infos — le projet est aussitôt utilisable.
function ajouterProjetAuSelecteur(nom, depot) {
  const select = document.getElementById('projet');
  let opt = [...select.options].find(o => o.value === nom);
  if (!opt) {
    opt = document.createElement('option');
    opt.value = nom;
    select.appendChild(opt);
  }
  opt.textContent = nom + ' — ' + depot;
  select.value = nom;
  const statut = document.querySelector('.entete .statut');
  if (statut) statut.textContent = select.options.length + ' projet(s) disponible(s)';
  onProjetChange();
}
