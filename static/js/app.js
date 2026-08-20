let sourceSSE = null;

let intervalWatchers = null;

// ─── Panneau latéral droit de l'onglet Résultats (issue #375) ─────────────
// Rafraîchi toutes les 30s (intervalPanneauLateral) + sur chaque événement SSE
// fin_issue (#350) + sur chaque changement de sélection de ligne. Dernière
// liste connue des services CCW (projet/service/etat), alimentée par
// ccwChargerProjets() — jamais interrogée directement depuis ce panneau, pour
// ne pas ajouter un second polling des appels SSH coûteux de l'onglet
// CCW (voir ccwOuvrirOnglet) : seul un clic sur le lien « Vérifier les
// services CCW » du panneau (sidebarChargerCcw) ou une action déjà existante
// de l'onglet CCW la met à jour.
let ccwProjetsConnus = [];
let intervalPanneauLateral = null;

// Connexion SSE dédiée au rafraîchissement instantané des résultats (issue
// #350) — ouverte à l'entrée dans l'onglet Résultats, fermée en le quittant.
let sourceFinIssue = null;

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
  const noms = ['creation', 'resultats', 'journal', 'config', 'watchers', 'ccw'];
  document.querySelectorAll('.onglet').forEach((o, i) =>
    o.classList.toggle('actif', noms[i] === nom));
  noms.forEach(n =>
    document.getElementById('panneau-' + n).classList.toggle('actif', n === nom));
  if (nom === 'journal')  demarrerJournal();
  if (nom === 'resultats') {
    chargerListeIssues(); demarrerTempsRestant(); demarrerStreamFinIssue();
    demarrerPanneauLateral();
  } else {
    arreterTempsRestant(); arreterStreamFinIssue(); arreterPanneauLateral();
  }
  if (nom === 'watchers') {
    chargerWatchers();
    intervalWatchers = setInterval(chargerWatchers, 5000);
  } else {
    clearInterval(intervalWatchers);
  }
  if (nom === 'config') chargerConfig();
  // Onglet CCW (issue #174) : chargé à l'ouverture, PAS de polling automatique
  // (chaque requête déclenche des appels SSH coûteux — l'utilisateur
  // rafraîchit à la demande via les boutons dédiés).
  if (nom === 'ccw') ccwOuvrirOnglet();
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
  // Bibliothèque de templates (issue #284) : filtrée par projet, rechargée à
  // chaque changement de projet (manuel ou détection d'en-tête).
  chargerTemplates();
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
    // ?? et non || : 0 est une valeur valide (auto-extinction désactivée).
    document.getElementById('conf-DELAI_INACTIVITE_MIN').value = cfg.delai_inactivite_min ?? 20;
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
    DELAI_INACTIVITE_MIN: document.getElementById('conf-DELAI_INACTIVITE_MIN').value,
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

// ─── Onglet CCW (issue #174, SSH depuis #447) ──────────────────────────────
// Pilotage du PC fixe Windows CCW et de ses projets depuis Linux, via les
// routes /ccw/* (qui exécutent des commandes SSH/SCP côté serveur). Aucune
// valeur de token n'est jamais journalisée ni passée en argument : la sortie
// affichée provient des scripts distants, qui ne les affichent pas.

// Affiche un message (succès/erreur/avertissement) dans un élément .message.
function ccwMessage(idEl, texte, type) {
  const el = document.getElementById(idEl);
  if (!el) return;
  el.textContent = texte || '';
  el.className = 'message' + (type ? ' ' + type : '');
  el.style.display = texte ? 'block' : 'none';
}

// Affiche la sortie brute d'un script distant dans le terminal CCW commun.
function ccwAfficherSortie(sortie) {
  const term = document.getElementById('ccw-sortie');
  if (!term) return;
  if (sortie && sortie.trim()) {
    term.textContent = sortie;
    term.style.display = 'block';
  } else {
    term.textContent = '';
    term.style.display = 'none';
  }
}

// Active/désactive un bouton pendant une opération longue (SSH).
function ccwOccupe(idBtn, occupe, labelOccupe) {
  const b = document.getElementById(idBtn);
  if (!b) return;
  if (occupe) {
    b.dataset.label = b.dataset.label || b.textContent;
    b.textContent = labelOccupe || 'Patientez…';
    b.disabled = true;
  } else {
    if (b.dataset.label) b.textContent = b.dataset.label;
    b.disabled = false;
  }
}

// Ouverture de l'onglet : liste des projets (le PC fixe est toujours allumé,
// plus d'état de VM à vérifier — issue #447).
function ccwOuvrirOnglet() {
  ccwChargerProjets();
}

async function ccwChargerProjets() {
  const corps = document.getElementById('ccw-corps-projets');
  const selectFin = document.getElementById('ccw-fin-nom');
  ccwMessage('ccw-msg-projets', 'Interrogation du PC fixe…', '');
  corps.innerHTML = '';
  try {
    const rep = await fetch('/ccw/projets');
    const j   = await rep.json();
    if (!j.succes) {
      ccwMessage('ccw-msg-projets', j.erreur || 'Erreur inconnue.', 'erreur');
      return;
    }
    const projets = j.projets || [];
    // Seul point d'écriture de ccwProjetsConnus (issue #375) : le panneau
    // latéral de l'onglet Résultats lit cette variable sans jamais fetcher
    // /ccw/projets lui-même (pas de second polling des appels SSH).
    ccwProjetsConnus = projets;
    rafraichirPanneauLateralResultats();
    // Mémorise la sélection courante pour la restaurer si le projet existe encore.
    const selectionCourante = selectFin ? selectFin.value : '';
    if (projets.length === 0) {
      ccwMessage('ccw-msg-projets', 'Aucun service CCW-Watcher* enregistré sur le PC fixe.', '');
      if (selectFin)
        selectFin.innerHTML = '<option value="" disabled selected>-- Choisir un projet --</option>';
      return;
    }
    ccwMessage('ccw-msg-projets', '', '');
    corps.innerHTML = projets.map(function(p) {
      const etatCouleur = (p.etat === 'running') ? '#2e8b57'
                        : (p.etat === 'stopped') ? '#c0392b' : '#888';
      let topicHtml;
      if (p.topicStatut === 'placeholder')
        topicHtml = '<span style="color:#e0a800">⚠ à définir</span>';
      else if (p.topicStatut === 'ok')
        topicHtml = '<span style="color:#2e8b57">✓ renseigné</span>';
      else
        topicHtml = '<span style="color:#888">? inconnu</span>';
      return '<tr style="border-bottom:1px solid #f2f2f0;cursor:pointer"'
        + ' title="Cliquer pour pré-sélectionner ce projet dans « Finaliser »"'
        + ' onclick="ccwPreselectionnerProjet(\'' + escapeHtml(p.projet) + '\')">'
        + '<td style="padding:8px 12px;font-size:13px">' + escapeHtml(p.projet)
          + (p.base ? ' <span style="color:#aaa;font-size:11px">(base)</span>' : '') + '</td>'
        + '<td style="padding:8px 12px;font-size:12px;color:#777;font-family:monospace">'
          + escapeHtml(p.service) + '</td>'
        + '<td style="padding:8px 12px;font-size:13px;color:' + etatCouleur + '">'
          + escapeHtml(p.etat || '—') + '</td>'
        + '<td style="padding:8px 12px;font-size:13px">' + topicHtml + '</td>'
        // Actions par ligne : « Redémarrer » (issue #180) toujours dispo, plus
        // « Démarrer » / « Arrêter » indépendants (issue #203) affichés selon
        // l'état — Démarrer seulement si stopped, Arrêter seulement si running,
        // comme pour les watchers Linux. stopPropagation pour ne PAS déclencher
        // aussi la pré-sélection portée par le onclick de la ligne.
        + '<td style="padding:8px 12px;white-space:nowrap">'
          + '<button onclick="event.stopPropagation(); ccwRedemarrerProjet(\''
            + escapeHtml(p.projet) + '\', this)"'
          + ' style="font-size:12px;padding:4px 10px">Redémarrer</button>'
          + (p.etat !== 'running'
              ? ' <button onclick="event.stopPropagation(); ccwDemarrerProjet(\''
                  + escapeHtml(p.projet) + '\', this)"'
                + ' style="font-size:12px;padding:4px 10px">Démarrer</button>'
              : '')
          + (p.etat !== 'stopped'
              ? ' <button onclick="event.stopPropagation(); ccwArreterProjet(\''
                  + escapeHtml(p.projet) + '\', this)"'
                + ' style="font-size:12px;padding:4px 10px">Arrêter</button>'
              : '')
          + '</td>'
        + '</tr>';
    }).join('');
    // Alimente le <select> du formulaire « Finaliser » : seuls les projets
    // réellement listés ci-dessus sont sélectionnables (plus de saisie libre).
    if (selectFin) {
      const noms = projets.map(function(p) { return p.projet; });
      selectFin.innerHTML = '<option value="" disabled>-- Choisir un projet --</option>'
        + projets.map(function(p) {
            return '<option value="' + escapeHtml(p.projet) + '">'
                 + escapeHtml(p.projet) + '</option>';
          }).join('');
      // Restaure la sélection précédente si le projet existe toujours,
      // sinon repositionne le placeholder.
      selectFin.value = (noms.indexOf(selectionCourante) !== -1) ? selectionCourante : '';
    }
  } catch (e) {
    ccwMessage('ccw-msg-projets', 'Erreur réseau : ' + e.message, 'erreur');
  }
}

// Confort : un clic sur une ligne du tableau « Projets CCW existants »
// pré-sélectionne ce projet dans le <select> de la section « Finaliser ».
function ccwPreselectionnerProjet(nom) {
  const selectFin = document.getElementById('ccw-fin-nom');
  if (!selectFin) return;
  // Ne sélectionne que si l'option existe réellement dans le <select>.
  const options = selectFin.options;
  for (let i = 0; i < options.length; i++) {
    if (options[i].value === nom) { selectFin.value = nom; break; }
  }
}

// Redémarre le service d'un projet CCW (issue #180) : simple « nssm restart »
// côté VM, sans reposer topic ni tokens. Le bouton passé (btn) est désactivé le
// temps de l'opération. Résultat affiché dans le bandeau + le terminal communs.
async function ccwRedemarrerProjet(nom, btn) {
  if (!nom) return;
  if (!confirm('Redémarrer le service du projet « ' + nom + ' » ?\n\n'
             + '(Redémarrage simple : ni le TOPIC_NTFY ni les tokens ne sont modifiés.)')) return;
  const labelInitial = btn ? btn.textContent : null;
  if (btn) { btn.disabled = true; btn.textContent = 'Redémarrage…'; }
  ccwMessage('ccw-message', 'Redémarrage du service de « ' + nom + ' » sur le PC fixe…', '');
  ccwAfficherSortie('');
  try {
    const rep = await fetch('/ccw/redemarrer-projet', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({nom: nom})
    });
    const j = await rep.json();
    ccwAfficherSortie(j.sortie);
    if (j.succes) {
      ccwMessage('ccw-message',
        'Service « ' + (j.service || nom) + ' » redémarré.', 'succes');
    } else {
      ccwMessage('ccw-message', j.erreur || 'Échec du redémarrage.', 'erreur');
    }
    ccwChargerProjets();
  } catch (e) {
    ccwMessage('ccw-message', 'Erreur réseau : ' + e.message, 'erreur');
  } finally {
    if (btn) { btn.disabled = false; if (labelInitial !== null) btn.textContent = labelInitial; }
  }
}

// Démarre le service d'un projet CCW (issue #203) : « nssm start » côté VM,
// contrôle indépendant du redémarrage. Même pattern que ccwRedemarrerProjet.
async function ccwDemarrerProjet(nom, btn) {
  if (!nom) return;
  const labelInitial = btn ? btn.textContent : null;
  if (btn) { btn.disabled = true; btn.textContent = 'Démarrage…'; }
  ccwMessage('ccw-message', 'Démarrage du service de « ' + nom + ' » sur le PC fixe…', '');
  ccwAfficherSortie('');
  try {
    const rep = await fetch('/ccw/demarrer-projet', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({nom: nom})
    });
    const j = await rep.json();
    ccwAfficherSortie(j.sortie);
    if (j.succes) {
      ccwMessage('ccw-message',
        'Service « ' + (j.service || nom) + ' » démarré.', 'succes');
    } else {
      ccwMessage('ccw-message', j.erreur || 'Échec du démarrage.', 'erreur');
    }
    ccwChargerProjets();
  } catch (e) {
    ccwMessage('ccw-message', 'Erreur réseau : ' + e.message, 'erreur');
  } finally {
    if (btn) { btn.disabled = false; if (labelInitial !== null) btn.textContent = labelInitial; }
  }
}

// Arrête le service d'un projet CCW (issue #203) : « nssm stop » côté VM, pour
// libérer des ressources sans le relancer aussitôt. Confirmation demandée.
async function ccwArreterProjet(nom, btn) {
  if (!nom) return;
  if (!confirm('Arrêter le service du projet « ' + nom + ' » ?\n\n'
             + '(Le service restera arrêté jusqu\'à un « Démarrer » ou « Redémarrer ».)')) return;
  const labelInitial = btn ? btn.textContent : null;
  if (btn) { btn.disabled = true; btn.textContent = 'Arrêt…'; }
  ccwMessage('ccw-message', 'Arrêt du service de « ' + nom + ' » sur le PC fixe…', '');
  ccwAfficherSortie('');
  try {
    const rep = await fetch('/ccw/arreter-projet', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({nom: nom})
    });
    const j = await rep.json();
    ccwAfficherSortie(j.sortie);
    if (j.succes) {
      ccwMessage('ccw-message',
        'Service « ' + (j.service || nom) + ' » arrêté.', 'succes');
    } else {
      ccwMessage('ccw-message', j.erreur || 'Échec de l\'arrêt.', 'erreur');
    }
    ccwChargerProjets();
  } catch (e) {
    ccwMessage('ccw-message', 'Erreur réseau : ' + e.message, 'erreur');
  } finally {
    if (btn) { btn.disabled = false; if (labelInitial !== null) btn.textContent = labelInitial; }
  }
}

// Nettoie les verrous CCW orphelins d'un projet (issue #431, prévu par #378) :
// arrête le service, supprime tous les .lock de son dossier de verrous, puis
// relance — en un seul appel serveur (/ccw/nettoyer-verrous). Cas d'usage :
// un verrou orphelin bloque le watcher CCW sans issue précise à interrompre
// (à la différence du bouton « Interrompre l'issue », qui exige une issue
// ouverte). Même pattern que ccwRedemarrerProjet/ccwArreterProjet, utilisé
// depuis le panneau latéral (#pl-zone-actions) : la zone #ccw-message de
// l'onglet CCW n'y existe pas, ccwMessage()/ccwAfficherSortie() y sont donc
// des no-op silencieux — le retour visuel se fait via le libellé du bouton.
async function ccwNettoyerVerrous(nom, btn) {
  if (!nom) return;
  if (!confirm('Nettoyer les verrous CCW du projet « ' + nom + ' » ?\n\n'
             + 'Le service sera ARRÊTÉ, tous les fichiers .lock de son dossier de '
             + 'verrous seront supprimés, puis le service sera relancé.')) return;
  const labelInitial = btn ? btn.textContent : null;
  if (btn) { btn.disabled = true; btn.textContent = 'Nettoyage…'; }
  ccwMessage('ccw-message', 'Nettoyage des verrous de « ' + nom + ' » sur le PC fixe…', '');
  ccwAfficherSortie('');
  try {
    const rep = await fetch('/ccw/nettoyer-verrous', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({nom: nom})
    });
    const j = await rep.json();
    ccwAfficherSortie(j.sortie);
    if (j.statut === 'succes') {
      ccwMessage('ccw-message', j.message || 'Verrous nettoyés, service relancé.', 'succes');
      alert('✅ ' + (j.message || 'Verrous nettoyés, service relancé.'));
    } else {
      ccwMessage('ccw-message', j.message || 'Échec du nettoyage des verrous.', 'erreur');
      alert('❌ ' + (j.message || 'Échec du nettoyage des verrous CCW.'));
    }
    ccwChargerProjets();
  } catch (e) {
    ccwMessage('ccw-message', 'Erreur réseau : ' + e.message, 'erreur');
    alert('Erreur réseau : ' + e.message);
  } finally {
    if (btn) { btn.disabled = false; if (labelInitial !== null) btn.textContent = labelInitial; }
  }
}

async function ccwAjouterProjet() {
  const nom   = document.getElementById('ccw-add-nom').value.trim();
  const depot = document.getElementById('ccw-add-depot').value.trim();
  if (!nom || !depot) {
    ccwMessage('ccw-message', 'Nom du projet et dépôt requis.', 'erreur');
    return;
  }
  ccwOccupe('ccw-btn-ajouter', true, 'Création…');
  ccwMessage('ccw-message', 'Création du projet sur le PC fixe (clone + config + service)…', '');
  ccwAfficherSortie('');
  try {
    const rep = await fetch('/ccw/ajouter-projet', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({nom: nom, depot: depot})
    });
    const j = await rep.json();
    ccwAfficherSortie(j.sortie);
    if (j.succes) {
      ccwMessage('ccw-message', 'Projet « ' + nom + ' » ajouté. Finalisez-le ci-dessous (TOPIC_NTFY + tokens).', 'succes');
      ccwChargerProjets();
    } else {
      ccwMessage('ccw-message', j.erreur || 'Échec de la création.', 'erreur');
    }
  } catch (e) {
    ccwMessage('ccw-message', 'Erreur réseau : ' + e.message, 'erreur');
  } finally {
    ccwOccupe('ccw-btn-ajouter', false);
  }
}

async function ccwFinaliserProjet() {
  const nom   = document.getElementById('ccw-fin-nom').value.trim();
  const topic = document.getElementById('ccw-fin-topic').value.trim();
  const gh    = document.getElementById('ccw-fin-gh').value;
  const oauth = document.getElementById('ccw-fin-oauth').value;
  if (!nom) {
    ccwMessage('ccw-message', 'Choisissez un projet dans la liste déroulante.', 'erreur');
    return;
  }
  if (!gh || !oauth) {
    ccwMessage('ccw-message', 'Les deux tokens (GH_TOKEN et CLAUDE_CODE_OAUTH_TOKEN) sont requis.', 'erreur');
    return;
  }
  if (!confirm('Finaliser « ' + nom + ' » : écrire TOPIC_NTFY et poser les deux tokens '
             + 'sur le service, puis le redémarrer ?')) return;
  ccwOccupe('ccw-btn-finaliser', true, 'Finalisation…');
  ccwMessage('ccw-message', 'Finalisation en cours (topic + tokens + redémarrage du service)…', '');
  ccwAfficherSortie('');
  try {
    const rep = await fetch('/ccw/finaliser-projet', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({nom: nom, topic: topic, gh_token: gh, oauth_token: oauth})
    });
    const j = await rep.json();
    ccwAfficherSortie(j.sortie);
    if (j.succes && !j.avertissement) {
      ccwMessage('ccw-message', 'Projet « ' + nom + ' » finalisé : tokens posés, service redémarré.', 'succes');
    } else if (j.avertissement) {
      ccwMessage('ccw-message', j.erreur || 'Appliqué, mais à vérifier.', 'avertissement');
    } else {
      ccwMessage('ccw-message', j.erreur || 'Échec de la finalisation.', 'erreur');
    }
    // Effacer les champs de tokens dès la réponse reçue (ne pas les laisser en clair).
    document.getElementById('ccw-fin-gh').value    = '';
    document.getElementById('ccw-fin-oauth').value = '';
    ccwChargerProjets();
  } catch (e) {
    ccwMessage('ccw-message', 'Erreur réseau : ' + e.message, 'erreur');
    document.getElementById('ccw-fin-gh').value    = '';
    document.getElementById('ccw-fin-oauth').value = '';
  } finally {
    ccwOccupe('ccw-btn-finaliser', false);
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

// Préfixe emoji de l'OS CIBLE d'une issue : 🪟 for-windows (CCW), rien sinon.
// Dimension DISTINCTE du type (chef/ouvrier) : les deux se cumulent (ex. un
// ouvrier for-windows affiche 👷🪟). On ne pose pas d'icône pour for-linux :
// c'est le cas par défaut (CCL), déjà signalé par le badge « for-linux » du
// détail — n'ajouter une icône que pour ce qui sort de l'ordinaire (issue #165).
function prefixeOSCible(it) {
  const noms = ((it && it.labels) || [])
    .map(l => ((l && l.name) || l || '').toLowerCase());
  return noms.includes('for-windows') ? '🪟' : '';
}

// Badge coloré pour un label dans le panneau de détail.
function badgeLabel(nom) {
  const map = {
    'done':        {cls: 'succes',   txt: '✅ succès'},
    'needs-human': {cls: 'echec',    txt: '⚠️ échec'},
    'mode_write':  {cls: 'ecriture', txt: '✏️ écriture'},
    'bridge':      {cls: 'gris',     txt: 'bridge'},
    'for-linux':   {cls: 'gris',     txt: 'for-linux'},
    'for-windows': {cls: 'bleu',     txt: '🪟 for-windows'},
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

// ── Limite d'issues chargées PAR PROJET (issue #271) ──────────────────────
// Transmise en paramètre de requête à /issues-liste/<projet> : c'est ce qui
// est TÉLÉCHARGÉ depuis GitHub, pas ce qui est affiché — le quota adaptatif
// d'appliquerFiltresListe() (issue #136) reste seul responsable de ce qui est
// MONTRÉ une fois la liste en mémoire. Un total serait ambigu (il faudrait le
// diviser par le nombre de projets actifs, qui change à chaque clic sur un
// filtre) ; exprimer un nombre par projet garde le même sens en toute
// circonstance. Défaut 5 (besoin courant réel dans 70% des cas d'après
// l'issue) et non 30 : l'ancienne valeur reste atteignable en remontant le
// champ. Changer la valeur ne déclenche PAS de rechargement automatique
// (cohérent avec #270) : seul le bouton rafraîchir applique la nouvelle
// limite. Le cache liste est néanmoins invalidé tout de suite (point 6),
// sinon un cache constitué à une profondeur différente resterait affiché
// avec une profondeur d'historique qui ne correspond plus au réglage visible.
const CLE_LIMITE_ISSUES = 'bridge_limite_issues_projet';
const LIMITE_ISSUES_DEFAUT = 5;
const LIMITE_ISSUES_MIN = 1;
const LIMITE_ISSUES_MAX = 50;

function limiteIssuesProjet() {
  let brut = null;
  try { brut = localStorage.getItem(CLE_LIMITE_ISSUES); } catch(e) {}
  const n = parseInt(brut, 10);
  return Number.isFinite(n) && n >= LIMITE_ISSUES_MIN && n <= LIMITE_ISSUES_MAX
    ? n : LIMITE_ISSUES_DEFAUT;
}

// Applique une nouvelle valeur saisie : bornée, persistée, cache liste
// invalidé — mais AUCUN rechargement déclenché ici (voir commentaire ci-dessus).
function changerLimiteIssuesProjet(valeur) {
  const n = parseInt(valeur, 10);
  const bornee = Number.isFinite(n)
    ? Math.min(LIMITE_ISSUES_MAX, Math.max(LIMITE_ISSUES_MIN, n))
    : LIMITE_ISSUES_DEFAUT;
  try { localStorage.setItem(CLE_LIMITE_ISSUES, String(bornee)); } catch(e) {}
  try { localStorage.removeItem(CLE_CACHE_ISSUES); } catch(e) {}
  return bornee;
}

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

async function chargerListeIssues(nomsAFetcher) {
  const zone = document.getElementById('liste-issues');
  const noms = nomsProjetsDisponibles();
  if (!noms.length) {
    zone.innerHTML = '<div class="issue-vide">Aucun projet</div>';
    return;
  }

  // Restriction optionnelle des projets réellement fetchés (issue #428) :
  // seul rafraichirResultats() passe ce paramètre (liste des projets actifs
  // dans le filtre), pour éviter un fetch par projet disponible quand
  // l'utilisateur n'en regarde qu'un seul. Tous les autres appelants
  // (chargement initial, SSE fin d'issue…) laissent nomsAFetcher indéfini →
  // comportement inchangé (tous les projets disponibles).
  const nomsFetch = Array.isArray(nomsAFetcher)
    ? nomsAFetcher.filter(nom => noms.includes(nom))
    : noms;
  const nomsFetchSet = new Set(nomsFetch);

  // 1) Affichage immédiat depuis le cache localStorage, s'il existe.
  let cache = null;
  try { cache = JSON.parse(localStorage.getItem(CLE_CACHE_ISSUES) || 'null'); } catch(e) {}
  const cacheAffiche = Array.isArray(cache) && cache.length > 0;
  if (cacheAffiche) {
    appliquerListeIssues(cache, noms);
  } else {
    zone.innerHTML = '<div class="issue-vide">Chargement…</div>';
  }

  // 2) Fetch d'arrière-plan des issues de chaque projet à recharger (jusqu'à
  //    la limite par projet réglée par l'utilisateur côté backend, issue #271
  //    — 5 par défaut). Le nombre réellement affiché par projet est ensuite
  //    plafonné par un quota adaptatif dans appliquerFiltresListe() (issue
  //    #136), selon le nombre de projets actifs dans le filtre — plus de
  //    troncature ici.
  const limite = limiteIssuesProjet();
  majIndicateurListe(true);
  try {
    const listes = await Promise.all(nomsFetch.map(async nom => {
      try {
        const rep = await fetch('/issues-liste/' + encodeURIComponent(nom)
          + '?limite=' + encodeURIComponent(limite));
        const liste = await rep.json();
        if (!Array.isArray(liste)) return [];
        // Toute la liste reçue (déjà plafonnée côté backend à la limite par
        // projet), triée par date de création décroissante (plus récentes en
        // premier).
        return liste
          .slice()
          .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))
          .map(it => Object.assign({}, it, {projet: nom}));
      } catch(e) {
        return [];
      }
    }));
    // Fusion avec les issues des projets NON refetchés cette fois (fetch
    // restreint, issue #428) : conservées telles quelles depuis l'état le
    // plus à jour déjà connu (cache tout juste lu, sinon liste en mémoire),
    // pour ne pas les faire disparaître de l'onglet Résultats. Puis tri
    // global par date de création décroissante (plus récentes en premier).
    const anterieures = (cacheAffiche ? cache : listeIssuesResultats)
      .filter(it => !nomsFetchSet.has(it.projet));
    const nouvelle = anterieures.concat(listes.flat())
      .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));

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
  tous.onclick = basculerTousLesFiltres;
  zone.appendChild(tous);
  // Appelé ici, une fois TOUS les boutons créés (dont « Tous ») : sinon la
  // mise à jour de son état visuel (issue #262) n'aurait rien à trouver dans
  // le DOM, ce bouton étant créé après les boutons projet.
  majClassesBoutonsFiltre();
  // Champ « limite par projet » (issue #271), juste avant le bouton
  // rafraîchir. Recréé à chaque reconstruction de la ligne comme les autres
  // contrôles ci-dessus ; sa valeur est restaurée depuis localStorage à
  // chaque fois. Le libellé et le title précisent explicitement qu'il s'agit
  // d'un nombre PAR PROJET (pas un total) et que la saisie seule ne recharge
  // rien — cohérent avec la décision de #270 : seul le bouton ↻ recharge.
  const limiteLabel = document.createElement('label');
  limiteLabel.className = 'limite-issues-label';
  limiteLabel.title = 'Nombre d\'issues chargées par projet (pas un total). '
    + 'Ex. 5 → 5 issues par projet affiché. La saisie seule ne recharge '
    + 'rien : cliquez sur ↻ pour appliquer.';
  limiteLabel.textContent = 'par projet :';
  const limiteInput = document.createElement('input');
  limiteInput.type = 'number';
  limiteInput.id = 'limite-issues-projet';
  limiteInput.className = 'limite-issues-projet';
  limiteInput.min = String(LIMITE_ISSUES_MIN);
  limiteInput.max = String(LIMITE_ISSUES_MAX);
  limiteInput.step = '1';
  limiteInput.value = String(limiteIssuesProjet());
  limiteInput.title = limiteLabel.title;
  limiteInput.onchange = () => {
    limiteInput.value = String(changerLimiteIssuesProjet(limiteInput.value));
  };
  limiteLabel.appendChild(limiteInput);
  zone.appendChild(limiteLabel);
  // Bouton « Cocher tout » (issue #381), juste avant le bouton rafraîchir :
  // coche toutes les issues actuellement VISIBLES (respecte le filtre projet
  // courant, ou toutes si aucun filtre spécifique n'est actif), en réutilisant
  // le même mécanisme de case à cocher que la case individuelle (issue #154).
  const coutTout = document.createElement('button');
  coutTout.id = 'btn-cocher-tout';
  coutTout.className = 'btn-cocher-tout';
  coutTout.title = 'Cocher toutes les issues actuellement visibles (projet filtré, ou tous si aucun filtre)';
  coutTout.textContent = '✓ Cocher tout';
  coutTout.onclick = cocherToutesVisibles;
  zone.appendChild(coutTout);
  // Bouton rafraîchir déplacé ici, juste après « Tous » (issue #57). Recréé à
  // chaque reconstruction de la ligne car zone.innerHTML est vidé au début.
  const rafr = document.createElement('button');
  rafr.id = 'btn-rafraichir';
  rafr.className = 'btn-rafraichir';
  rafr.title = 'Rafraîchir depuis GitHub';
  rafr.textContent = '↻';
  rafr.onclick = rafraichirResultats;
  zone.appendChild(rafr);
  // Pastilles de notification sur les boutons de filtre projet (issue #381),
  // calculées depuis les données déjà en mémoire — voir majPastillesFiltres().
  majPastillesFiltres();
}

// Coche toutes les issues actuellement visibles dans la liste (issue #381) —
// « visible » au sens d'appliquerFiltresListe (projet filtré + quota + filtre
// ouvriers), donc « tous projets » quand le filtre « Tous » est actif. Même
// mécanisme que la case individuelle (basculerCocheResultat, issue #154) :
// persistance localStorage + classe .resultat-traite, sans logique métier.
function cocherToutesVisibles() {
  document.querySelectorAll('#liste-issues .ligne-issue').forEach(ligne => {
    if (ligne.style.display === 'none') return;
    const cb = ligne.querySelector('.coche-resultat');
    if (!cb || cb.checked) return;
    cb.checked = true;
    try { localStorage.setItem(cleCocheResultat(ligne.dataset.projet, ligne.dataset.numero), '1'); }
    catch(e) { /* localStorage indisponible : la case reste juste visuelle */ }
    ligne.classList.add('resultat-traite');
  });
  // Pastilles filtre projet (issue #383) : comptent les issues décochées,
  // donc cocher tout le visible doit rafraîchir immédiatement leur compte.
  majPastillesFiltres();
}

// Pastille de notification sur chaque bouton de filtre projet (issue #381) :
// petit badge rouge affichant le nombre d'issues OUVERTES ni done ni
// needs-human de ce projet, visible même quand le projet n'est PAS
// sélectionné dans le filtre. Calcul purement local depuis
// listeIssuesResultats (déjà en mémoire) — aucun fetch réseau. Appelée à
// chaque (re)construction des boutons et à chaque mise à jour de la liste
// (rendreListeIssues, remplacerLigneIssue).
// Portée respectée (issue #382) : ne compte que dans les N premières issues
// de CHAQUE projet (N = limiteIssuesProjet(), le champ « par projet : N »),
// même lecture de la limite que celle qui borne le téléchargement — sinon un
// cache plus profond que la limite couramment affichée (N abaissé sans clic
// sur ↻, cf. commentaire de limiteIssuesProjet) gonflerait la pastille
// au-delà de ce que l'utilisateur voit réellement dans la liste.
// Compte les issues DÉCOCHÉES (issue #383) : la case à cocher libre
// (localStorage, voir estResultatCoche/cleCocheResultat) reflète si Alain a
// déjà traité/lu ce résultat — indépendamment de son état GitHub (open/closed,
// labels done/needs-human). Une issue décochée reste à traiter quel que soit
// son état GitHub, donc plus aucun filtre sur state/labels ici.
function majPastillesFiltres() {
  const limite = limiteIssuesProjet();
  const vus = {};
  const comptes = {};
  listeIssuesResultats.forEach(it => {
    const v = vus[it.projet] || 0;
    if (v >= limite) return;
    vus[it.projet] = v + 1;
    if (estResultatCoche(it.projet, String(it.number))) return;
    comptes[it.projet] = (comptes[it.projet] || 0) + 1;
  });
  document.querySelectorAll('#filtres-projets .filtre-projet[data-projet]').forEach(btn => {
    const n = comptes[btn.dataset.projet] || 0;
    let pastilleNotif = btn.querySelector('.pastille-notif');
    if (!n) {
      if (pastilleNotif) pastilleNotif.remove();
      return;
    }
    if (!pastilleNotif) {
      pastilleNotif = document.createElement('span');
      pastilleNotif.className = 'pastille-notif';
      btn.appendChild(pastilleNotif);
    }
    pastilleNotif.textContent = String(n);
  });
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

// Bascule « Tous » entre deux états (issue #262) : un vrai toggle, pas une
// simple remise à zéro. Si au moins un projet est masqué → tout afficher ;
// si tout est déjà affiché → tout masquer. Seul l'état « tout affiché »
// bascule vers « tout masqué » ; tout état partiel revient à « tout affiché ».
// L'ensemble vide (tout masqué) est un état légitime et volontaire — l'ancien
// garde-fou de l'issue #259, qui l'interdisait, a été retiré : il contredisait
// désormais l'intention même de la fonction.
// Persistance localStorage asymétrique, à dessein : « tout affiché » efface
// la mémoire (retour au défaut au prochain chargement, comme avant #262) ;
// « tout masqué » est au contraire persisté via sauvegarderFiltresProjets
// (comme basculerFiltreProjet), sans quoi un rechargement de page annulerait
// silencieusement le masquage volontaire de l'utilisateur.
function basculerTousLesFiltres() {
  const noms = nomsProjetsDisponibles();
  const tousAffiches = noms.every(nom => projetsFiltresActifs.has(nom));
  if (tousAffiches) {
    projetsFiltresActifs = new Set();
    sauvegarderFiltresProjets(noms);
  } else {
    projetsFiltresActifs = new Set(noms);
    try { localStorage.removeItem(CLE_FILTRES_RESULTATS); } catch(e) {}
  }
  majClassesBoutonsFiltre();
  appliquerFiltresListe();
  const sel = document.querySelector('#liste-issues .ligne-issue.selectionnee');
  if (!sel || sel.style.display === 'none') selectionnerPremiereVisible();
}

// Projets actifs dans le filtre de l'onglet Résultats (issue #428) : le
// sous-ensemble réellement affiché — égal à nomsProjetsDisponibles() quand
// « Tous » est actif (rien à restreindre), un sous-ensemble strict sinon (y
// compris vide si tous les projets sont masqués). Utilisé par
// rafraichirResultats() pour ne fetcher/invalider que ce qui est visible,
// au lieu de systématiquement tous les projets disponibles.
function projetsActifsDansFiltreResultats() {
  return nomsProjetsDisponibles().filter(nom => projetsFiltresActifs.has(nom));
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
  // Bouton « Tous » (issue #262) : reflète l'action du PROCHAIN clic, pas
  // l'état courant — grisé (.inactif) tant qu'au moins un projet est masqué,
  // ce qui correspond à « le prochain clic affichera tout ».
  const boutonTous = document.querySelector('#filtres-projets .filtre-projet.tous');
  if (boutonTous) {
    const tousAffiches = nomsProjetsDisponibles().every(nom => projetsFiltresActifs.has(nom));
    boutonTous.classList.toggle('inactif', !tousAffiches);
    boutonTous.title = tousAffiches ? 'Tout masquer' : 'Tout afficher';
  }
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
  // Pastilles filtre projet (issue #383) : comptent les issues décochées,
  // donc chaque bascule de case doit rafraîchir immédiatement leur compte.
  majPastillesFiltres();
  // Cocher la case déclenche, pour cette SEULE issue, la même copie
  // réponse+diff que le badge « All » (issue #444). Décocher ne fait rien
  // (pas de « décopie »). copierToutEtDiffDepuisBadge gère déjà sans erreur
  // le cas d'une issue sans réponse/commit (garde « copie vide », feedback
  // ⚠/∅) : appel sans condition sur l'état de l'issue.
  if (coche) copierToutEtDiffDepuisBadge(event, projet, numero);
}

// Relit le LocalStorage et resynchronise l'état de TOUTES les cases à cocher
// « résultat » actuellement dans le DOM (issue #462). construireLigneIssueDOM
// lit déjà le LocalStorage à la CONSTRUCTION d'une ligne, mais rien ne
// garantissait qu'un futur redessin partiel (heartbeat, SSE) passe par cette
// construction — ce filet de sécurité resynchronise explicitement après
// coup, pour que l'état coché/décoché survive à toute mise à jour dynamique
// du DOM exactement comme il survit à un F5.
function restaurerCasesCocheesResultats() {
  document.querySelectorAll('.ligne-issue').forEach(ligne => {
    const cb = ligne.querySelector('.coche-resultat');
    if (!cb) return;
    // Garde #463 : ne jamais écraser la case sur laquelle l'utilisateur est
    // EN TRAIN d'agir (focus actif au moment de l'appel). basculerCocheResultat
    // gère déjà cette case précise ; la resynchroniser ici en pleine bascule
    // recréerait la course qui, sur Edge/Firefox Windows, pouvait annuler le
    // clic avant même que le onchange ne déclenche la copie (régression #462).
    if (document.activeElement === cb) return;
    const coche = estResultatCoche(ligne.dataset.projet, ligne.dataset.numero);
    cb.checked = coche;
    ligne.classList.toggle('resultat-traite', coche);
  });
}

// Construit l'élément DOM d'UNE ligne d'issue (case à cocher, pastille,
// badges ✅/Diff/All, titre) — markup PARTAGÉ entre la liste principale de
// l'onglet Résultats (rendreListeIssues) et la fenêtre de recherche par titre
// (issue #321), pour que chaque résultat de recherche soit une réplique EXACTE
// d'une ligne de l'onglet. Les badges ✅/Diff/All sont câblés ICI (leur action
// copierReponseDepuisBadge & consorts ne dépend d'aucun contexte, juste de
// projet+numéro) ; en revanche onclick/ondblclick de la ligne elle-même ne
// sont PAS posés ici — chaque appelant les branche selon son propre contexte
// (sélection + zone de détail cible).
function construireLigneIssueDOM(it) {
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
  ligne.title = 'Double-cliquez pour afficher le détail de cette issue';
  // Gauche : badges emoji (✅ ✏️ ⚠️ ○) + pastille ● colorée du projet.
  // Centre : #N — titre [état].
  // Le badge ✅ des issues FERMÉES portant le label « done » (les seules qui
  // ont une réponse CCL) devient cliquable : un clic copie directement la
  // réponse CCL sans ouvrir le détail (issue #62).
  // Préfixe visuel du TYPE (🎯 chef / 👷 ouvrier / rien) et de l'OS CIBLE
  // (🪟 for-windows / rien) devant les badges. Deux dimensions distinctes et
  // cumulables : un ouvrier for-windows affiche « 👷🪟 » (issue #165).
  const prefType = prefixeTypeIssue(it) + prefixeOSCible(it);
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
  return ligne;
}

// (Re)construit la liste HTML cliquable à partir de listeIssuesResultats. TOUTES
// les issues sont rendues comme lignes ; le filtre projet ne fait que masquer
// (display:none) les lignes des projets inactifs. Chaque ligne est coloriée à la
// couleur de son projet ; le clic simple sélectionne (selectionnerLigne), le
// double-clic charge et affiche le détail (afficherIssue, issue #261). Si
// reset=true, on sélectionne (sans charger) la première issue visible.
// Câble le clic simple (sélection seule, issue #261), le ctrl+clic (détail +
// défilement jusqu'au résultat CCL) et le double-clic (détail) d'une ligne.
// Extrait de rendreListeIssues pour être réutilisé par remplacerLigneIssue
// (issue #334), qui reconstruit une ligne isolée après vérification du
// dépassement TIMEOUT — même rendu, mêmes gestes qu'un rendu de liste complet.
function brancherEvenementsLigneIssue(ligne, it) {
  const numero = String(it.number);
  ligne.onclick = async (event) => {
    event.preventDefault();
    if (event.ctrlKey) {
      await afficherIssue(it.projet, numero);
      setTimeout(() => {
        const cible = document.querySelector('#zone-issue .commentaire.resultat')
                   || document.querySelector('#zone-issue .commentaire:last-child');
        if (cible) cible.scrollIntoView({behavior: 'smooth', block: 'start'});
      }, 100);
    } else {
      selectionnerLigne(it.projet, numero);
    }
  };
  ligne.ondblclick = async (event) => {
    event.preventDefault();
    await afficherIssue(it.projet, numero);
  };
}

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
    const ligne = construireLigneIssueDOM(it);
    brancherEvenementsLigneIssue(ligne, it);
    zone.appendChild(ligne);
  }
  appliquerFiltresListe();
  appliquerLargeurTitre();
  restaurerCasesCocheesResultats();
  majBadgesTempsRestant();
  majPastillesFiltres();
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
// largeur de départ de CETTE ligne comme référence, ainsi que la liste (.liste-
// issues) qui la contient : depuis l'issue #321, ce n'est plus forcément
// #liste-issues (l'onglet Résultats) — la fenêtre de recherche par titre
// affiche ses propres lignes dans #liste-resultats-recherche, qui porte aussi
// la classe .liste-issues et doit se redimensionner indépendamment, sans
// affecter la colonne de l'onglet.
function demarrerRedimTitre(event) {
  event.preventDefault();
  event.stopPropagation();
  const ligne = event.currentTarget.closest('.ligne-issue');
  const texte = ligne ? ligne.querySelector('.ligne-texte') : null;
  const liste = ligne ? ligne.closest('.liste-issues') : null;
  if (!texte || !liste) return;
  redimTitreEtat = {
    xDepart: event.clientX,
    largeurDepart: texte.getBoundingClientRect().width,
    liste: liste,
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
  redimTitreEtat.liste.style.setProperty('--largeur-titre', w + 'px');
  redimTitreEtat.liste.classList.add('titre-redimensionne');
}

// Fin du glisser : on persiste la largeur courante dans localStorage — mais
// UNIQUEMENT pour la liste de l'onglet Résultats (#liste-issues) ; un
// redimensionnement dans la fenêtre de recherche reste local à cette session,
// la fenêtre étant reconstruite à chaque nouvelle recherche.
function finRedimTitre() {
  document.removeEventListener('mousemove', surRedimTitre);
  document.removeEventListener('mouseup', finRedimTitre);
  document.body.style.cursor = '';
  document.body.style.userSelect = '';
  if (!redimTitreEtat) return;
  const liste = redimTitreEtat.liste;
  redimTitreEtat = null;
  if (liste.id !== 'liste-issues') return;
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
  // dans le filtre. 1 projet → 30 ; 2 → 15 ; 3 → 10 ; 4 → 7 ; etc. Ce calcul
  // reste basé sur 30 (délibérément non touché par #271) : il plafonne ce qui
  // est MONTRÉ, indépendamment de limiteIssuesProjet() qui plafonne ce qui est
  // TÉLÉCHARGÉ. Si la limite de téléchargement est plus basse que ce quota
  // d'affichage, ce dernier n'a simplement rien de plus à masquer — sans
  // conséquence, les deux mécanismes ne se contredisent pas.
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
// sans re-solliciter le serveur.
// Mise à jour des données elles-mêmes (issue #270, suite #269) : PLUS de
// re-fetch périodique — l'interface web laissée ouverte avec plusieurs
// projets configurés interrogeait GitHub en continu (~3840 pts/h mesurés,
// premier poste de consommation du quota GraphQL, cf. issue #263) pour un
// gain (voir apparaître un badge 15s plus tôt) jugé insuffisant par Alain.
// chargerTimingIssues() n'est donc plus appelée qu'à la demande : au
// chargement initial de l'onglet Résultats (demarrerTempsRestant) et par le
// bouton rafraîchir (rafraichirResultats), qui met à jour liste ET badges
// d'un même geste. Conséquence assumée : une issue qui se termine pendant
// que l'onglet reste ouvert garde son décompte affiché jusqu'au prochain
// rafraîchissement manuel. Décompte figé à zéro une fois le budget épuisé
// (cf. formaterBadgeTempsRestant) : jamais de valeur négative, jamais de
// message spéculatif du type « terminé ? » — sans re-fetch, cette
// information n'est pas connue côté client. Cohérent avec le fait que la
// LISTE elle-même (chargerListeIssues) suit déjà ce même modèle « à la
// demande » et ne se rafraîchit pas non plus toute seule.
let timingIssues = {};              // clé "projet#numero" → {timeout, max_essais, backoff, debut, sans_limite}
let intervalTempsRestant = null;    // recalcul 1 s du compte à rebours (client seul, aucun appel réseau)

// ─── Fetch unique au dépassement du TIMEOUT (issue #334) ──────────────────
// Clés (cleTiming) des issues pour lesquelles le fetch unique de vérification
// a déjà été programmé — évite qu'un re-rendu (rendreListeIssues) ou le tick
// de majBadgesTempsRestant (chaque seconde) ne reprogramme un second setTimeout
// pour la même issue tant que la page reste ouverte.
let issuesFetchDepassementProgrammees = new Set();
// Clés des issues dont le fetch unique a confirmé qu'elles sont toujours
// ouvertes (cas marginal de timing) : affiche « rafraîchir ↻ » à la place du
// message générique « budget épuisé » et empêche formaterBadgeTempsRestant de
// reprogrammer un nouveau fetch automatique (un seul essai, jamais de polling).
let issuesDepassementVerifie = new Set();

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
  // On repart de l'état COURANT, pas d'un map vide (issue #190). Avant, chaque
  // appel reconstruisait le map à partir de zéro : dès qu'un fetch
  // /issues-en-attente échouait ou expirait — typiquement pendant une contention
  // réseau provoquée par un cycle du poller de notifications (12 appels gh
  // groupés, cf. notifications_poller.py) — le projet concerné disparaissait du
  // map et TOUS ses badges (décompte + estimation) s'effaçaient jusqu'au prochain
  // fetch réussi. C'est la « perte intermittente des badges » constatée par
  // Alain. Désormais, seul un fetch RÉUSSI remplace les entrées de son projet ;
  // un échec laisse les badges existants intacts.
  const map = Object.assign({}, timingIssues);
  await Promise.all(noms.map(async nom => {
    try {
      const rep = await fetch('/issues-en-attente/' + encodeURIComponent(nom));
      const liste = await rep.json();
      // Erreur/timeout (réponse non-tableau : {erreur:…} en 5xx) → on NE touche
      // pas aux entrées du projet, on garde les badges actuels.
      if (!Array.isArray(liste)) return;
      // Succès : on purge d'abord les anciennes entrées de CE projet (pour retirer
      // les issues désormais fermées) puis on réinjecte la liste fraîche. Le
      // séparateur '#' évite qu'un nom soit préfixe d'un autre (ex. « ecole »).
      for (const cle of Object.keys(map)) {
        if (cle.startsWith(nom + '#')) delete map[cle];
      }
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
// projet/numero (issue #334) : nécessaires pour programmer, au moment où le
// budget tombe à zéro, le fetch unique de vérification 15s plus tard.
function formaterBadgeTempsRestant(badge, t, projet, numero) {
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
  } else if (issuesDepassementVerifie.has(cleTiming(projet, numero))) {
    // Fetch unique déjà effectué (issue #334) et l'issue était encore ouverte
    // à ce moment (cas marginal de timing) : on le dit clairement plutôt que
    // de réafficher indéfiniment le message générique « budget épuisé », et on
    // NE reprogramme AUCUN autre fetch automatique — seul un ↻ (ligne ou
    // global) ira revérifier.
    badge.textContent = '⌛ dépassement — rafraîchir ↻';
    badge.classList.add('tr-depasse');
    badge.title = 'Budget total épuisé (' + essais + ' tentatives × ' + t.timeout
                + 's' + (backoff ? ' + backoffs' : '') + ') ; la vérification '
                + 'automatique 15s après le dépassement montre l\'issue toujours '
                + 'ouverte. Cliquez sur ↻ pour revérifier — aucune autre '
                + 'vérification automatique ne sera programmée.';
  } else {
    // Budget total (toutes tentatives) épuisé : décompte figé à zéro (issue
    // #270), jamais de valeur négative ni de compteur de dépassement qui
    // grossirait indéfiniment. Le watcher a encore besoin de quelques
    // secondes pour poster son diagnostic et fermer l'issue une fois son
    // TIMEOUT écoulé : un unique fetch de vérification est donc programmé
    // 15s après ce dépassement (issue #334, voir programmerFetchDepassement),
    // sans aucun polling — un seul appel réseau, une seule fois par issue.
    badge.textContent = '⌛ 0s — budget épuisé';
    badge.classList.add('tr-depasse');
    badge.title = 'Budget total épuisé (' + essais + ' tentatives × ' + t.timeout
                + 's' + (backoff ? ' + backoffs' : '') + ') ; intervention '
                + 'humaine probable (label needs-human). Vérification automatique '
                + 'programmée dans 15s ; en cas de doute, ↻ revérifie immédiatement.';
    programmerFetchDepassement(projet, numero);
  }
}

// Actualise tous les badges de temps restant des lignes ouvertes (recalcul pur,
// aucun appel réseau). Appelée chaque seconde et après chaque rendu de liste.
// Ne resynchronise PAS les cases cochées (issue #463) : cette fonction ne
// reconstruit jamais les nœuds DOM des cases, donc rien à restaurer ici — cet
// appel superflu, exécuté chaque seconde via setInterval, créait une fenêtre
// de course avec le clic utilisateur (annulait parfois la coche AVANT que le
// onchange ne déclenche la copie résultat+diff, régression Windows-only
// introduite par #462). La restauration reste faite là où le DOM est
// effectivement reconstruit : rendreListeIssues, remplacerLigneIssue,
// rendreResultatsRecherche.
function majBadgesTempsRestant() {
  document.querySelectorAll('#liste-issues .ligne-issue').forEach(ligne => {
    const t = timingIssues[cleTiming(ligne.dataset.projet, ligne.dataset.numero)];
    // Estimation prédictive (issue #108) : affichée JUSTE AVANT le décompte.
    const badgeEst = ligne.querySelector('.ligne-estimation');
    if (badgeEst) formaterBadgeEstimation(badgeEst, t);
    const badge = ligne.querySelector('.ligne-tempsrestant');
    if (!badge) return;
    formaterBadgeTempsRestant(badge, t, ligne.dataset.projet, ligne.dataset.numero);
  });
}

const DELAI_FETCH_DEPASSEMENT_MS = 15000;   // marge laissée au watcher (issue #334)

// Programme le fetch unique de vérification (issue #334), 15s après que le
// décompte TIMEOUT d'une issue soit tombé à zéro — le Set garde-fou garantit
// qu'un seul setTimeout est posé par issue, même si formaterBadgeTempsRestant
// repasse par cette branche à chaque tick (1/s) tant que la page reste ouverte.
function programmerFetchDepassement(projet, numero) {
  const cle = cleTiming(projet, numero);
  if (issuesFetchDepassementProgrammees.has(cle)) return;
  issuesFetchDepassementProgrammees.add(cle);
  setTimeout(() => verifierIssueApresDepassement(projet, numero), DELAI_FETCH_DEPASSEMENT_MS);
}

// Retrouve la ligne DOM d'une issue par projet+numéro (pas de sélecteur CSS
// construit à partir de valeurs externes, pour rester robuste à un nom de
// projet contenant des caractères spéciaux).
function trouverLigneIssue(projet, numero) {
  numero = String(numero);
  return [...document.querySelectorAll('#liste-issues .ligne-issue')]
    .find(l => l.dataset.projet === projet && l.dataset.numero === numero);
}

// Remplace intégralement la ligne DOM d'une issue par une version reconstruite
// à partir des données fraîches `it` — même rendu et mêmes gestes (clic/double-
// clic) qu'un ↻ manuel global, mais restreint à cette seule ligne (issue #334).
function remplacerLigneIssue(ligneAncienne, it) {
  const nouvelle = construireLigneIssueDOM(it);
  brancherEvenementsLigneIssue(nouvelle, it);
  if (ligneAncienne.classList.contains('selectionnee')) nouvelle.classList.add('selectionnee');
  ligneAncienne.replaceWith(nouvelle);
  appliquerFiltresListe();
  restaurerCasesCocheesResultats();
  majBadgesTempsRestant();
  majPastillesFiltres();
}

// Exécute le fetch unique programmé par programmerFetchDepassement, 15s après
// le dépassement du TIMEOUT. Issue fermée (done/needs-human) → met à jour la
// ligne normalement (badge terminal, retrait du décompte), comme un ↻ manuel
// restreint à cette seule issue. Issue encore ouverte (cas marginal de
// timing) → le badge devient « rafraîchir ↻ » (géré par formaterBadgeTempsRestant
// via issuesDepassementVerifie) et AUCUN autre fetch automatique n'est
// programmé — zéro polling, un seul appel réseau par issue.
async function verifierIssueApresDepassement(projet, numero) {
  const cle = cleTiming(projet, numero);
  let it;
  try {
    const rep = await fetch('/issue/' + encodeURIComponent(projet) + '/' + encodeURIComponent(numero));
    it = await rep.json();
  } catch(e) {
    return;   // échec réseau : pas de nouvelle tentative auto (cohérent avec #270)
  }
  if (!it || it.erreur) return;
  if ((it.state || '').toUpperCase() === 'CLOSED') {
    const itListe = {
      number: it.number, title: it.title, state: it.state,
      labels: it.labels, createdAt: it.createdAt, projet: projet,
    };
    const idx = listeIssuesResultats.findIndex(
      x => x.projet === projet && String(x.number) === String(numero));
    if (idx !== -1) listeIssuesResultats[idx] = Object.assign({}, listeIssuesResultats[idx], itListe);
    delete timingIssues[cle];
    const ligne = trouverLigneIssue(projet, numero);
    if (ligne) remplacerLigneIssue(ligne, itListe);
  } else {
    issuesDepassementVerifie.add(cle);
    majBadgesTempsRestant();
  }
}

// Démarre le suivi du temps restant (à l'ouverture de l'onglet Résultats) :
// fetch initial des débuts/timeouts puis recalcul chaque seconde (client
// seul). Plus de re-fetch périodique (issue #270) : les données ne sont
// ensuite rafraîchies qu'explicitement, via rafraichirResultats().
function demarrerTempsRestant() {
  chargerTimingIssues();
  arreterTempsRestant();
  intervalTempsRestant = setInterval(majBadgesTempsRestant, 1000);
}

// Stoppe l'intervalle de temps restant (en quittant l'onglet Résultats).
function arreterTempsRestant() {
  if (intervalTempsRestant) { clearInterval(intervalTempsRestant); intervalTempsRestant = null; }
}

// Ouvre le canal SSE de fin d'issue (issue #350), à l'ouverture de l'onglet
// Résultats. Sur réception d'un événement fin_issue pour une issue affichée
// dans listeIssuesResultats, réutilise EXACTEMENT le traitement du fetch de
// vérification de #334 (verifierIssueApresDepassement) — même fetch, même
// remplacement de ligne — plutôt que de dupliquer cette logique. La
// reconnexion en cas de coupure est gérée nativement par EventSource, aucun
// code supplémentaire n'est nécessaire ici.
function demarrerStreamFinIssue() {
  if (sourceFinIssue) return;   // déjà ouverte
  sourceFinIssue = new EventSource('/stream');
  sourceFinIssue.addEventListener('fin_issue', function(e) {
    let donnees;
    try { donnees = JSON.parse(e.data); } catch (err) { return; }
    const { projet, numero } = donnees;
    const dansLaListe = listeIssuesResultats.some(
      it => it.projet === projet && String(it.number) === String(numero));
    if (dansLaListe) verifierIssueApresDepassement(projet, numero);
    // Panneau latéral (issue #375) : une fin d'issue change potentiellement
    // l'état « ouvert/fermé » de l'issue sélectionnée (bouton Interrompre) et
    // peut coïncider avec un arrêt de watcher — rafraîchi à chaque événement,
    // sans coût supplémentaire (le fetch /watchers est local, pas d'appel
    // GitHub, cf. issue #375).
    rafraichirPanneauLateralResultats();
  });
}

// Ferme le canal SSE de fin d'issue (en quittant l'onglet Résultats) : pas de
// connexion inutile maintenue quand l'onglet n'est pas affiché.
function arreterStreamFinIssue() {
  if (sourceFinIssue) { sourceFinIssue.close(); sourceFinIssue = null; }
}

// ─── Panneau latéral droit de l'onglet Résultats (issue #375, #377, #380) ──
// Panneau FLOTTANT (position:fixed, voir .panneau-lateral dans style.css),
// basculé par #pl-toggle, trois zones EMPILÉES, non exclusives, pilotées par
// projetCourant/numeroCourant (mêmes variables que la sélection de ligne,
// voir selectionnerLigne) :
//  - zone haute (#pl-zone-monitoring) : monitoring passif des watchers CCL+CCW
//    de tous les projets actifs (rendrePanneauLateralMonitoring), TOUJOURS
//    rendue, sélection ou non — pour garder l'infra sous les yeux en
//    travaillant sur une issue (issue #377), une ligne par watcher, noir et
//    blanc, bouton individuel Lancer/Relancer (issue #380) ;
//  - zone médiane (#pl-zone-extras) : réservée aux futurs boutons, vide,
//    voir templates/index.html (issue #380) ;
//  - zone basse (#pl-zone-actions) : actions contextuelles pour le projet/
//    l'issue sélectionnés (rendrePanneauLateralActions), sans fetch réseau
//    (données déjà en mémoire : listeIssuesResultats + ccwProjetsConnus) —
//    vidée (donc invisible) quand aucune ligne n'est sélectionnée.

// Ouvre le panneau flottant par défaut à chaque entrée dans l'onglet
// Résultats (issue #380) — sauf sur écran étroit, où il reste fermé par
// défaut pour ne pas masquer la liste (même seuil que le media query CSS
// associé, 900px). Un panneau déjà ouvert/fermé manuellement par l'utilisateur
// est donc réinitialisé à chaque changement d'onglet, comportement voulu.
function ouvrirPanneauLateralParDefaut() {
  const panneau = document.getElementById('panneau-lateral-resultats');
  if (!panneau) return;
  panneau.classList.toggle('ferme', window.innerWidth < 900);
  mettreAJourToggleLateral();
}

// Bascule manuel du panneau flottant (clic sur #pl-toggle).
function basculerPanneauLateral() {
  const panneau = document.getElementById('panneau-lateral-resultats');
  if (!panneau) return;
  panneau.classList.toggle('ferme');
  mettreAJourToggleLateral();
}

// Reflète l'état ouvert/fermé du panneau sur le bouton toggle (accent visuel
// seulement — le bouton reste cliquable et visible dans les deux états).
function mettreAJourToggleLateral() {
  const panneau = document.getElementById('panneau-lateral-resultats');
  const toggle  = document.getElementById('pl-toggle');
  if (!panneau || !toggle) return;
  toggle.classList.toggle('actif', !panneau.classList.contains('ferme'));
}

function demarrerPanneauLateral() {
  ouvrirPanneauLateralParDefaut();
  rafraichirPanneauLateralResultats();
  arreterPanneauLateral();
  intervalPanneauLateral = setInterval(rafraichirPanneauLateralResultats, 30000);
}

function arreterPanneauLateral() {
  if (intervalPanneauLateral) { clearInterval(intervalPanneauLateral); intervalPanneauLateral = null; }
}

async function rafraichirPanneauLateralResultats() {
  const panneau = document.getElementById('panneau-resultats');
  if (!panneau || !panneau.classList.contains('actif')) return;
  // Les deux zones sont indépendantes (issue #377) : le monitoring se
  // rafraîchit toujours, les actions contextuelles se (re)rendent — ou se
  // vident — selon la sélection courante, sans attendre le fetch du monitoring.
  await rendrePanneauLateralMonitoring();
  rendrePanneauLateralActions();
}

// Service CCW connu pour ce projet (ou null), depuis la dernière liste chargée
// (ccwProjetsConnus) — jamais un fetch direct, voir le commentaire sur cette
// variable en tête de fichier.
function serviceCcwProjet(nom) {
  return ccwProjetsConnus.find(p => (p.projet || '').toLowerCase() === nom.toLowerCase()) || null;
}

// Déclenche (à la demande, sur clic) le seul fetch de l'état des services CCW
// utilisé par ce panneau : ccwChargerProjets(), qui alimente ccwProjetsConnus
// et re-rend elle-même ce panneau une fois la réponse reçue.
async function sidebarChargerCcw() {
  await ccwChargerProjets();
}

// Résumé « X en cours, Y en file » d'un projet (issue #381), calculé
// UNIQUEMENT à partir de données déjà en mémoire — jamais de fetch réseau
// supplémentaire ici : le monitoring se rafraîchit déjà tout seul toutes les
// 30s (rendrePanneauLateralMonitoring), un appel gh par projet à ce rythme
// reproduirait la surconsommation de quota GraphQL déjà corrigée par
// l'issue #270 (cf. commentaire de chargerTimingIssues). « en cours » = issue
// ouverte for-linux/for-windows (ni done ni needs-human) dont l'ACK watcher
// est déjà connu (timingIssues[...].debut renseigné, alimenté à la demande
// par chargerTimingIssues/rafraichirResultats) ; « en file » = même filtre
// mais sans ACK connu — soit réellement en attente, soit parce que
// timingIssues n'a simplement pas encore été chargé pour ce projet.
function resumeProjetMonitoring(nom) {
  let enCours = 0, enFile = 0;
  listeIssuesResultats.forEach(it => {
    if (it.projet !== nom) return;
    if ((it.state || '').toUpperCase() !== 'OPEN') return;
    const noms = (it.labels || []).map(l => ((l && l.name) || l || '').toLowerCase());
    if (!noms.includes('for-linux') && !noms.includes('for-windows')) return;
    if (noms.includes('done') || noms.includes('needs-human')) return;
    const t = timingIssues[cleTiming(nom, it.number)];
    if (t && t.debut) enCours++; else enFile++;
  });
  return {enCours: enCours, enFile: enFile};
}

// Monitoring de l'infrastructure, TOUJOURS visible en zone haute du panneau
// (issue #375/#376/#377, refonte lisibilité #380), qu'une issue soit
// sélectionnée ou non : état de la VM CCW + bouton de démarrage si éteinte,
// UNE LIGNE PAR WATCHER CCL (point vert/gris foncé, sans couleur projet —
// lisible en noir et blanc, issue #380) avec bouton individuel Lancer/
// Relancer, son résumé « en cours/en file » (issue #381) + boutons de
// relance groupée (éteints seuls, ou tous les CCL), une ligne par service CCW
// (ou lien de vérification si aucun service encore connu), puis l'horodatage
// du dernier rafraîchissement. Cible #pl-zone-monitoring, indépendante de la
// zone d'actions contextuelles (#pl-zone-actions) — voir le commentaire
// d'en-tête.
async function rendrePanneauLateralMonitoring() {
  const zone = document.getElementById('pl-zone-monitoring');
  if (!zone) return;
  const noms = nomsProjetsDisponibles();
  // Deux fetchs locaux en parallèle : /watchers (état CCL) et /ccw/vm-statut
  // (état de la VM, VBoxManage local — pas de guestcontrol, rapide). Aucun
  // appel GitHub, aucun polling des services CCW (guestcontrol) ici.
  let watchersMap = null, vmStatut = null;
  try {
    const [repW, repVm] = await Promise.all([
      fetch('/watchers'),
      fetch('/ccw/vm-statut').catch(() => null),
    ]);
    const liste = await repW.json();
    watchersMap = {};
    liste.forEach(w => { watchersMap[w.nom] = w; });
    if (repVm) { try { vmStatut = await repVm.json(); } catch(e) { vmStatut = null; } }
  } catch(e) { watchersMap = null; }

  let html = '<div class="titre-section" style="margin-top:0">Monitoring infrastructure</div>'
           + '<div class="pl-sous">Tous projets actifs — actualisé toutes les 30 s</div>';
  if (!watchersMap) {
    html += '<div class="issue-vide" style="padding:10px 0">Erreur de chargement</div>';
    zone.innerHTML = html;
    return;
  }

  // 1. VM CCW : ligne unique, allumée/éteinte/inconnue.
  let vmTexte = '⚪ VM : état inconnu', vmEteinte = false;
  if (vmStatut && vmStatut.succes) {
    if (!vmStatut.existe) {
      vmTexte = '🔴 VM introuvable (non créée)';
    } else if (vmStatut.etat === 'running') {
      vmTexte = '🟢 VM allumée';
    } else {
      vmTexte = '🔴 VM éteinte (' + escapeHtml(vmStatut.etat || '?') + ')';
      vmEteinte = true;
    }
  } else if (vmStatut && vmStatut.erreur) {
    vmTexte = '⚪ VM : ' + escapeHtml(vmStatut.erreur);
  }
  html += '<div class="pl-ligne"><span class="pl-ligne-libelle">' + vmTexte + '</span>';
  if (vmEteinte) {
    html += '<button class="pl-btn-mini" onclick="sidebarDemarrerVm(this)">▶ Démarrer</button>';
  }
  html += '</div>';

  // 2. Watchers CCL : une ligne PAR watcher (issue #380) — point vert = actif,
  // gris foncé = éteint, sans couleur projet (monitoring noir et blanc, à
  // distinguer des pastilles colorées de la liste des issues). Bouton
  // individuel à droite (Lancer si éteint, Relancer si actif) + sous-ligne
  // résumé « en cours/en file » (issue #381) + boutons de relance groupée :
  // « ▶ Lancer les éteints » (seulement les watchers éteints, si au moins un)
  // et « ↺ Relancer tous les CCL » (TOUS les watchers CCL, actifs ou non).
  html += '<div class="pl-resume-titre">Watchers CCL</div>';
  const cclEteints = [];
  noms.forEach(function(nom) {
    const actif = !!(watchersMap[nom] && watchersMap[nom].actif);
    if (!actif) cclEteints.push(nom);
    const resume = resumeProjetMonitoring(nom);
    html += '<div class="pl-ligne">'
          + '<span class="pl-ligne-libelle">' + (actif ? '🟢' : '⚫') + ' ' + escapeHtml(nom) + '</span>'
          + '<button class="pl-btn-mini" onclick="sidebarRelancerWatcherCCL(\'' + escapeHtml(nom) + '\', this)">'
          + (actif ? '↺ Relancer' : '▶ Lancer') + '</button>'
          + '</div>'
          + '<div class="pl-sous-projet">' + resume.enCours + ' en cours, ' + resume.enFile + ' en file</div>';
  });
  if (noms.length) {
    html += '<div class="pl-boutons-ccl">';
    if (cclEteints.length) {
      html += '<button class="pl-btn-vm" onclick="sidebarRelancerTousEteints(this)">'
            + '▶ Lancer les éteints</button>';
    }
    html += '<button class="pl-btn-vm" onclick="sidebarRelancerTousCCL(this)">'
          + '↺ Relancer tous les CCL</button>';
    html += '</div>';
  }

  // 3. Services CCW : même format ligne par ligne, seulement si des services
  // sont déjà connus (aucun polling automatique — voir ccwProjetsConnus en
  // tête de fichier). Pas de bouton individuel ici : la relance CCW d'un
  // service reste une action contextuelle liée à une issue sélectionnée
  // (#pl-zone-actions, ccwRedemarrerProjet), inchangé depuis #375.
  html += '<div class="pl-resume-titre">Services CCW</div>';
  if (ccwProjetsConnus.length) {
    ccwProjetsConnus.forEach(function(p) {
      const actif = p.etat === 'running';
      html += '<div class="pl-ligne"><span class="pl-ligne-libelle">'
            + (actif ? '🟢' : '⚫') + ' ' + escapeHtml(p.projet)
            + (actif ? '' : ' (' + escapeHtml(p.etat || '?') + ')') + '</span></div>';
    });
  } else {
    html += '<div class="pl-lien" onclick="sidebarChargerCcw()">🔄 Vérifier les services CCW</div>';
  }

  // 4. Horodatage du dernier rafraîchissement (issue #381), une seule ligne en
  // bas du monitoring — heure locale du navigateur, comme le reste de
  // l'interface (issue #58).
  html += '<div class="pl-sous" style="margin-top:10px">Mis à jour à '
        + new Date().toLocaleTimeString('fr-FR', {hour: '2-digit', minute: '2-digit', second: '2-digit'})
        + '</div>';
  zone.innerHTML = html;
}

// Actions contextuelles (issue #375, zone basse fixe depuis #377) : projet/
// issue actuellement sélectionnés (projetCourant/numeroCourant). Aucun fetch
// réseau — les données viennent de listeIssuesResultats (déjà en mémoire) et
// ccwProjetsConnus. Cible #pl-zone-actions, sous #pl-zone-monitoring et la
// zone réservée #pl-zone-extras (toujours visible, voir
// rendrePanneauLateralMonitoring) ; se vide (donc disparaît, séparateur
// compris) quand aucune ligne n'est sélectionnée.
// Libellé du mode d'une issue (issue #381), affiché en haut de la zone
// actions — mêmes labels que modeEcritureDepuisLabels (mode_write/
// mode_scratch), reformulés pour l'affichage : « écriture » → ⚠️ Écriture
// (working tree modifié), « lecture_active » → ✏️ Lecture active (mode_scratch,
// travail hors working tree définitif), aucun des deux → 📖 Lecture seule.
function libelleModeIssue(nomsLabels) {
  const modeEcr = modeEcritureDepuisLabels(nomsLabels);
  if (modeEcr === 'ecriture')       return '⚠️ Écriture';
  if (modeEcr === 'lecture_active') return '✏️ Lecture active';
  return '📖 Lecture seule';
}

function rendrePanneauLateralActions() {
  const zone = document.getElementById('pl-zone-actions');
  if (!zone) return;
  const nom = projetCourant, numero = numeroCourant;
  if (!nom || !numero) { zone.innerHTML = ''; return; }
  const it = listeIssuesResultats.find(
    x => x.projet === nom && String(x.number) === String(numero));
  const nomsLabels = it ? (it.labels || []).map(l => ((l && l.name) || l || '').toLowerCase()) : [];
  const ferme = !!(it && (it.state || '').toUpperCase() === 'CLOSED');
  // Même condition que le bouton « Interrompre » du détail d'issue
  // (construireHtmlIssue, issue #323) : issue ouverte, ni done ni needs-human.
  const interromptible = !!it && !ferme
    && !nomsLabels.includes('done') && !nomsLabels.includes('needs-human');
  const service = serviceCcwProjet(nom);
  // Adaptation CCL/CCW (issue #381) : le libellé du watcher ciblé par
  // « Interrompre et relancer » suit le label de l'issue, pas la simple
  // présence d'un service CCW connu pour le projet (utilisée plus bas pour le
  // bouton « Relancer watcher CCW », inchangé).
  const windows = nomsLabels.includes('for-windows');
  const libelleWatcherCible = windows ? 'watcher CCW' : 'watcher CCL';

  let html = '<hr class="pl-sep">'
           + '<div class="titre-section" style="margin-top:0">Actions — '
           + escapeHtml(nom) + ' #' + escapeHtml(numero) + '</div>';
  if (it) {
    html += '<div class="pl-mode-issue">' + libelleModeIssue(nomsLabels) + '</div>';
  }
  // Toggles des labels de notification (issue #384) : mêmes conditions que les
  // boutons d'interruption (issue ouverte, ni done ni needs-human) — pas de
  // notification à reconfigurer sur une issue déjà terminée. État initial
  // coché/décoché reflète les labels actuels de l'issue (listeIssuesResultats).
  if (interromptible) {
    html += '<div class="pl-notifs">'
          + '<div class="pl-notifs-titre">🔔 Notifications</div>'
          + rendreCheckboxNotif(nom, numero, 'notif_pc',   'Bureau', nomsLabels)
          + rendreCheckboxNotif(nom, numero, 'notif_gsm',  'GSM',    nomsLabels)
          + rendreCheckboxNotif(nom, numero, 'notif_tous', 'Tous',   nomsLabels)
          + '<div id="pl-notif-erreur" class="pl-notif-erreur"></div>'
          + '</div>';
  }
  html += '<div class="pl-actions">'
        + '<button onclick="sidebarRelancerWatcherCCL(\'' + escapeHtml(nom) + '\', this)">'
        + '↺ Relancer watcher CCL</button>';
  if (interromptible) {
    html += '<button class="danger" onclick="interrompreEtRelancer(\'' + escapeHtml(nom) + '\', '
          + Number(numero) + ')">⛔ Interrompre et relancer (' + libelleWatcherCible + ')</button>';
    html += '<button class="danger" onclick="interrompreIssue(\'' + escapeHtml(nom) + '\', '
          + Number(numero) + ')">⛔ Interrompre l\'issue</button>';
  }
  // « Fermer l'issue » (issue #381) : même route que le bouton existant du
  // détail (construireHtmlIssue, issue #80) — /fermer-issue via fermerIssue(),
  // réutilisée à l'identique, aucune nouvelle route.
  if (!ferme && nomsLabels.includes('needs-human')) {
    html += '<button onclick="relancerIssue(\'' + escapeHtml(nom) + '\', '
          + Number(numero) + ')">🔄 Relancer</button>';
    html += '<button class="danger-plein" onclick="fermerIssue(\'' + escapeHtml(nom) + '\', '
          + Number(numero) + ')">✖ Fermer l\'issue</button>';
  }
  if (service) {
    html += '<button onclick="ccwRedemarrerProjet(\'' + escapeHtml(nom) + '\', this)">'
          + '↺ Relancer watcher CCW</button>'
          + '<button class="danger" onclick="ccwNettoyerVerrous(\'' + escapeHtml(nom) + '\', this)">'
          + '🔒 Nettoyer verrous CCW + redémarrer</button>';
  }
  html += '</div>';
  if (!ccwProjetsConnus.length) {
    html += '<div class="pl-lien" onclick="sidebarChargerCcw()">🔄 Vérifier le service CCW de ce projet</div>';
  }
  zone.innerHTML = html;
}

// Une ligne « ☐ Libellé » du bloc Notifications (issue #384). Coché si `label`
// (ex. notif_pc) figure parmi les labels actuels de l'issue (nomsLabels, déjà
// en minuscules — voir rendrePanneauLateralActions).
function rendreCheckboxNotif(nom, numero, label, libelle, nomsLabels) {
  const coche = nomsLabels.includes(label) ? ' checked' : '';
  return '<label class="pl-notif-ligne">'
       + '<input type="checkbox"' + coche + ' onchange="toggleLabelNotif(\''
       + escapeHtml(nom) + '\', ' + Number(numero) + ', \'' + label + '\', this)"> '
       + escapeHtml(libelle) + '</label>';
}

// Bascule un label de notification (notif_pc/notif_gsm/notif_tous) sur l'issue
// sélectionnée via /modifier-label-notif (issue #384), sans passer par GitHub.
// En cas d'échec (réseau ou refus serveur) : la checkbox revient à son état
// précédent et un message d'erreur discret s'affiche brièvement sous les
// toggles, sans bloquer l'interface (pas d'alert()).
async function toggleLabelNotif(nom, numero, label, cb) {
  const actif = cb.checked;
  cb.disabled = true;
  let ok = false, erreur = '';
  try {
    const rep = await fetch('/modifier-label-notif', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({projet: nom, numero: numero, label: label, actif: actif})
    });
    const json = await rep.json();
    ok = !!json.succes;
    if (!ok) erreur = json.erreur || 'échec de la mise à jour du label.';
  } catch(e) {
    erreur = 'Erreur réseau : ' + e.message;
  }
  cb.disabled = false;
  if (!ok) {
    cb.checked = !actif;
    afficherErreurNotifDiscrete(erreur);
    return;
  }
  // Mise à jour locale de listeIssuesResultats (sans refetch réseau), puis
  // re-rendu du panneau d'actions pour rester cohérent avec l'état affiché
  // ailleurs (ex. si un autre widget lit aussi les labels de cette issue).
  const it = listeIssuesResultats.find(
    x => x.projet === nom && String(x.number) === String(numero));
  if (it) {
    const dejaPresent = (it.labels || []).some(
      l => ((l && l.name) || l || '').toLowerCase() === label);
    if (actif && !dejaPresent) {
      it.labels = (it.labels || []).concat([{name: label}]);
    } else if (!actif && dejaPresent) {
      it.labels = (it.labels || []).filter(
        l => ((l && l.name) || l || '').toLowerCase() !== label);
    }
  }
  rendrePanneauLateralActions();
}

// Message d'erreur discret (pas d'alert()) sous les toggles de notification —
// s'efface tout seul après quelques secondes.
function afficherErreurNotifDiscrete(message) {
  const zone = document.getElementById('pl-notif-erreur');
  if (!zone) return;
  zone.textContent = '⚠ ' + message;
  setTimeout(function() {
    if (zone.textContent === '⚠ ' + message) zone.textContent = '';
  }, 4000);
}

// Relance (ou lance) le watcher CCL du projet donné — même endpoint que
// l'onglet Watchers (actionWatchers → /lancer-watcher), appelé ici pour un
// seul projet directement depuis le panneau latéral.
async function sidebarRelancerWatcherCCL(nom, btn) {
  const label = btn ? btn.textContent : null;
  if (btn) { btn.disabled = true; btn.textContent = 'Relance…'; }
  try {
    await fetch('/lancer-watcher', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({projet: nom, relancer: true})
    });
  } catch(e) {
    alert('Erreur réseau : ' + e.message);
  }
  const panneauWatchers = document.getElementById('panneau-watchers');
  if (panneauWatchers && panneauWatchers.classList.contains('actif')) await chargerWatchers();
  if (btn) { btn.disabled = false; if (label !== null) btn.textContent = label; }
  await rafraichirPanneauLateralResultats();
}

// Relance séquentiellement TOUS les watchers CCL actuellement éteints (issue
// #377), un par un via le même endpoint que sidebarRelancerWatcherCCL. Relit
// /watchers juste avant de lancer les relances plutôt que de réutiliser la
// liste déjà affichée dans le panneau, potentiellement périmée entre le rendu
// et le clic.
async function sidebarRelancerTousEteints(btn) {
  if (btn) { btn.disabled = true; btn.textContent = 'Relance…'; }
  try {
    const repW = await fetch('/watchers');
    const liste = await repW.json();
    const watchersMap = {};
    liste.forEach(w => { watchersMap[w.nom] = w; });
    const eteints = nomsProjetsDisponibles()
      .filter(n => !(watchersMap[n] && watchersMap[n].actif));
    for (const nom of eteints) {
      try {
        await fetch('/lancer-watcher', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({projet: nom, relancer: true})
        });
      } catch(e) { /* une relance en échec ne doit pas bloquer les suivantes */ }
    }
  } catch(e) {
    alert('Erreur réseau : ' + e.message);
  }
  const panneauWatchers = document.getElementById('panneau-watchers');
  if (panneauWatchers && panneauWatchers.classList.contains('actif')) await chargerWatchers();
  if (btn) { btn.disabled = false; btn.textContent = '▶ Lancer les éteints'; }
  await rafraichirPanneauLateralResultats();
}

// Relance séquentiellement TOUS les watchers CCL, actifs OU éteints (issue
// #381) — même mécanique que sidebarRelancerTousEteints, mais SANS filtrer
// sur l'état : chaque projet est relancé via /lancer-watcher (relancer=true),
// qui redémarre un watcher déjà actif comme il lance un watcher éteint.
async function sidebarRelancerTousCCL(btn) {
  if (btn) { btn.disabled = true; btn.textContent = 'Relance…'; }
  try {
    for (const nom of nomsProjetsDisponibles()) {
      try {
        await fetch('/lancer-watcher', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({projet: nom, relancer: true})
        });
      } catch(e) { /* une relance en échec ne doit pas bloquer les suivantes */ }
    }
  } catch(e) {
    alert('Erreur réseau : ' + e.message);
  }
  const panneauWatchers = document.getElementById('panneau-watchers');
  if (panneauWatchers && panneauWatchers.classList.contains('actif')) await chargerWatchers();
  if (btn) { btn.disabled = false; btn.textContent = '↺ Relancer tous les CCL'; }
  await rafraichirPanneauLateralResultats();
}

// Sélectionne la première ligne encore visible SANS charger son détail (voir
// selectionnerLigne, issue #261) ; vide le détail s'il n'y a plus rien à
// afficher. Appelée à l'ouverture de l'onglet, à chaque changement de filtre
// projet et après chaque rafraîchissement de liste — aucun de ces gestes ne
// doit déclencher de fetch réseau.
function selectionnerPremiereVisible() {
  const premiere = [...document.querySelectorAll('#liste-issues .ligne-issue')]
    .find(ligne => ligne.style.display !== 'none');
  if (premiere) {
    selectionnerLigne(premiere.dataset.projet, premiere.dataset.numero);
  } else {
    // Aucune ligne visible (ex. issue #262 : toggle « Tous » à l'état tout
    // masqué) : on retire aussi la classe .selectionnee de la ligne masquée,
    // sinon elle reste marquée sélectionnée en coulisse — un futur retour à
    // l'affichage la retrouverait "déjà sélectionnée" et sauterait la
    // resynchronisation (zone de détail restée sur ce message).
    document.querySelectorAll('#liste-issues .ligne-issue.selectionnee')
      .forEach(ligne => ligne.classList.remove('selectionnee'));
    projetCourant = null;
    numeroCourant = null;
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

// Projet/numéro actuellement SÉLECTIONNÉ dans la liste (ligne en surbrillance),
// que son détail ait été chargé ou non. Permet au bouton rafraîchir (issue #56)
// de recharger l'issue affichée.
let projetCourant = null;
let numeroCourant = null;
// true seulement si le détail de projetCourant/numeroCourant a réellement été
// chargé (double-clic ou Ctrl+clic — voir afficherIssue), PAS pour une simple
// sélection (clic simple, sélection automatique — voir selectionnerLigne).
// Distingue « ligne mise en évidence » de « détail effectivement demandé »,
// pour que le rafraîchissement (issue #56) ne force pas un fetch que
// l'utilisateur n'a jamais explicitement demandé (issue #261).
let detailCourantCharge = false;
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

  // Bouton « Interrompre » (issue #323, suite #320) : sur TOUTE issue ouverte
  // ni done ni needs-human — remplace au niveau de l'issue elle-même l'action
  // corrective qui se faisait jusqu'ici hors interface (kill manuel, verrou à
  // la main). Contrairement à « Interrompre et fermer » (#144, ci-dessus) :
  // ne FERME PAS l'issue (needs-human seulement, trace via commentaire), et
  // fonctionne aussi côté for-windows (CCW), pas seulement for-linux.
  if (!ferme && !nomsLabels.includes('done') && !nomsLabels.includes('needs-human')) {
    html += '<div class="bloc-annuler">'
          + '<button class="danger" onclick="interrompreIssue(\'' + nom + '\', '
          + Number(it.number) + ')">'
          + '⛔ Interrompre cette issue</button></div>';
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
        const corpsBrut = retirerMarqueurResultat(c.body || '');
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

// Sélectionne visuellement une ligne (fond coloré persistant, classe
// .selectionnee) et mémorise projetCourant/numeroCourant, SANS charger son
// détail. Utilisée par le clic simple et la sélection automatique (issue
// #261) : contrairement à afficherIssue(), aucun fetch n'est déclenché — la
// zone de détail affiche un état neutre invitant au double-clic. Invalide au
// passage tout fetch de détail encore en vol (afficherIssueSeq) pour qu'il ne
// vienne pas écraser cet état neutre après coup.
function selectionnerLigne(nom, numero) {
  numero = numero == null ? '' : String(numero);
  ++afficherIssueSeq;
  detailCourantCharge = false;
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
    rafraichirPanneauLateralResultats();
    return;
  }
  projetCourant = nom;
  numeroCourant = numero;
  zone.innerHTML = '<div class="issue-vide">Double-cliquez une issue pour afficher son détail.</div>';
  rafraichirPanneauLateralResultats();
}

async function afficherIssue(nom, numero) {
  numero = numero == null ? '' : String(numero);
  selectionnerLigne(nom, numero);
  if (!numero || !nom) return;
  const seq = ++afficherIssueSeq;
  detailCourantCharge = true;
  const zone = document.getElementById('zone-issue');

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

// ─── Fenêtre de recherche par titre (issue #321) ──────────────────────────
// Contexte : le 02/08/2026 une issue a été envoyée en double (#315/#316)
// faute de moyen rapide de vérifier si un sujet avait déjà été traité. La
// PORTÉE de recherche (nombre d'issues ratissées PAR PROJET sélectionné dans
// les filtres) est INDÉPENDANTE de la limite d'affichage de l'onglet
// (limiteIssuesProjet) : la recherche re-interroge toujours GitHub avec sa
// propre portée — elle ne filtre jamais listeIssuesResultats déjà en mémoire,
// sans quoi une issue au-delà de la limite d'affichage resterait introuvable.

// Jeton anti-course dédié à la zone de détail de la fenêtre de recherche —
// INDÉPENDANT de afficherIssueSeq (zone-issue de l'onglet Résultats) : les
// deux zones chargent des détails en parallèle sans interférer, et un
// double-clic dans la fenêtre n'affecte jamais projetCourant/numeroCourant ni
// la sélection de l'onglet (contrairement à afficherIssue, qui reste dédiée à
// #zone-issue et inchangée).
let seqDetailRecherche = 0;

// Charge et affiche le détail d'un résultat de recherche dans la zone de
// détail PROPRE à la fenêtre (#zone-issue-recherche, autonome — jamais
// #zone-issue de l'onglet). Reprend la même mécanique cache TTL + fetch +
// rendu que afficherIssue, en réutilisant construireHtmlIssue (même badges,
// mêmes onglets Réponse/Diff) sans la dupliquer.
async function afficherIssueRecherche(nom, numero) {
  numero = numero == null ? '' : String(numero);
  const zone = document.getElementById('zone-issue-recherche');
  if (!zone || !nom || !numero) return;
  const seq = ++seqDetailRecherche;

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

  try {
    const rep = await fetch('/issue/' + encodeURIComponent(nom) + '/' + encodeURIComponent(numero));
    const it = await rep.json();
    if (seq !== seqDetailRecherche) return;
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
    if (seq === seqDetailRecherche && htmlAffiche === null) {
      zone.innerHTML = '<div class="issue-vide">Erreur réseau : ' + escapeHtml(e.message) + '</div>';
    }
  }
}

// Lit le champ « portée » de la recherche, bornée par les mêmes constantes
// que la limite d'affichage (LIMITE_ISSUES_MIN..MAX) — deux réglages distincts
// partageant les mêmes bornes serveur (_limite_issues_requete).
function porteeRechercheTitre() {
  const input = document.getElementById('recherche-titre-portee');
  const n = parseInt(input ? input.value : '', 10);
  const bornee = Number.isFinite(n)
    ? Math.min(LIMITE_ISSUES_MAX, Math.max(LIMITE_ISSUES_MIN, n))
    : 15;
  if (input) input.value = String(bornee);
  return bornee;
}

// (Re)construit la liste des résultats de recherche : réplique EXACTE d'une
// ligne de l'onglet Résultats (construireLigneIssueDOM, mêmes badges), dont le
// double-clic cible la zone de détail PROPRE à la fenêtre (afficherIssueRecherche),
// jamais celle de l'onglet.
function rendreResultatsRecherche(resultats) {
  const zone = document.getElementById('liste-resultats-recherche');
  zone.innerHTML = '';
  if (!resultats.length) {
    zone.innerHTML = '<div class="issue-vide">Aucun résultat</div>';
    return;
  }
  for (const it of resultats) {
    const numero = String(it.number);
    const ligne = construireLigneIssueDOM(it);
    ligne.ondblclick = async (event) => {
      event.preventDefault();
      await afficherIssueRecherche(it.projet, numero);
    };
    zone.appendChild(ligne);
  }
  restaurerCasesCocheesResultats();
}

function ouvrirModalRechercheTitre() {
  const modal = document.getElementById('modal-recherche-titre');
  if (modal) modal.classList.add('actif');
}

function fermerModalRechercheTitre() {
  const modal = document.getElementById('modal-recherche-titre');
  if (modal) modal.classList.remove('actif');
}

// Lance la recherche par titre : un appel gh --state all --limit <portée> PAR
// PROJET sélectionné dans les filtres (issue #321), state=all car on cherche
// justement à retrouver un sujet DÉJÀ traité (doublon #315/#316). Déclenchée
// UNIQUEMENT au clic sur le bouton (ou Entrée dans le champ texte) — jamais à
// la frappe, cohérent avec la décision de #270 pour le bouton ↻. L'échec d'un
// projet n'annule pas la recherche sur les autres : ce qui a réussi est
// agrégé, les projets en échec sont listés dans un message discret.
async function lancerRechercheTitre() {
  const champTexte = document.getElementById('recherche-titre-texte');
  const titre = (champTexte ? champTexte.value : '').trim();
  const zoneErreurs = document.getElementById('recherche-titre-erreurs');
  if (zoneErreurs) { zoneErreurs.style.display = 'none'; zoneErreurs.innerHTML = ''; }

  if (!titre) {
    if (zoneErreurs) {
      zoneErreurs.textContent = 'Saisissez un titre à rechercher.';
      zoneErreurs.style.display = '';
    }
    return;
  }
  // Portée = projets ACTUELLEMENT sélectionnés dans les filtres de l'onglet
  // (projetsFiltresActifs) — pas tous les projets configurés.
  const projets = nomsProjetsDisponibles().filter(nom => projetsFiltresActifs.has(nom));
  if (!projets.length) {
    if (zoneErreurs) {
      zoneErreurs.textContent = 'Aucun projet sélectionné — activez au moins un filtre projet ci-dessus.';
      zoneErreurs.style.display = '';
    }
    return;
  }

  const portee = porteeRechercheTitre();
  const btn = document.getElementById('btn-recherche-titre');
  const indicateur = document.getElementById('recherche-titre-indicateur');
  if (btn) btn.disabled = true;
  if (indicateur) indicateur.style.display = '';

  const echecs = [];
  let resultats = [];
  try {
    // Un appel gh PAR PROJET sélectionné, chacun avec sa propre portée — la
    // recherche ne s'arrête pas au premier match, elle ratisse toute la
    // portée de tous les projets sélectionnés (issue #321).
    const listes = await Promise.all(projets.map(async nom => {
      try {
        const rep = await fetch('/recherche-issues/' + encodeURIComponent(nom)
          + '?titre=' + encodeURIComponent(titre)
          + '&limite=' + encodeURIComponent(portee));
        const json = await rep.json();
        if (!Array.isArray(json)) {
          echecs.push(nom + ' : ' + (json && json.erreur ? json.erreur : 'erreur inconnue'));
          return [];
        }
        return json.map(it => Object.assign({}, it, {projet: nom}));
      } catch(e) {
        echecs.push(nom + ' : erreur réseau (' + e.message + ')');
        return [];
      }
    }));
    resultats = listes.flat();
  } finally {
    if (btn) btn.disabled = false;
    if (indicateur) indicateur.style.display = 'none';
  }

  // Filtre « 👷 Ouvriers » (issue #86), même détection que l'onglet — appliqué
  // uniquement sur les projets ratissés (les autres n'ont de toute façon pas
  // été interrogés).
  if (!filtreOuvriersActif) {
    resultats = resultats.filter(it => typeIssue(it) !== 'ouvrier');
  }
  resultats.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));

  if (zoneErreurs && echecs.length) {
    zoneErreurs.innerHTML = '⚠️ Échec sur ' + echecs.length + ' projet(s) : '
      + echecs.map(escapeHtml).join(' — ');
    zoneErreurs.style.display = '';
  }

  rendreResultatsRecherche(resultats);
  const zoneDetail = document.getElementById('zone-issue-recherche');
  if (zoneDetail) {
    zoneDetail.innerHTML = '<div class="issue-vide">Double-cliquez un résultat pour afficher son détail.</div>';
  }
  ouvrirModalRechercheTitre();
}

// Bouton rafraîchir (issue #56) : vide le cache localStorage (liste + tous les
// détails) puis recharge tout depuis GitHub. Contourne le TTL du cache détail,
// qui peut montrer une issue « ouverte » alors que le watcher l'a fermée.
async function rafraichirResultats() {
  // Mémorise l'issue affichée AVANT le rechargement : chargerListeIssues()
  // réécrit projetCourant/numeroCourant en auto-sélectionnant la première ligne
  // (sans charger son détail, voir selectionnerLigne). On mémorise aussi si ce
  // détail avait été explicitement chargé (double-clic/Ctrl+clic) — sélection
  // automatique et clic simple ne comptent pas (issue #261) : sans ça, on
  // rechargerait de force un détail que personne n'a demandé.
  const projet = projetCourant;
  const numero = numeroCourant;
  const etaitCharge = detailCourantCharge;

  // Restreint le rechargement aux seuls projets actifs dans le filtre de
  // l'onglet Résultats (issue #428) : évite un fetch « gh issue list » par
  // projet DISPONIBLE quand l'utilisateur n'en regarde qu'un sous-ensemble.
  // « Tous » actif (ou aucun filtre spécifique) → comportement inchangé.
  const nomsDisponibles = nomsProjetsDisponibles();
  const nomsActifs = projetsActifsDansFiltreResultats();
  const rechargeTout = nomsActifs.length === nomsDisponibles.length;

  // 1) Cache de la liste : purge globale seulement si on recharge tout —
  //    sinon la fusion de chargerListeIssues() préserve les projets non
  //    refetchés depuis ce même cache, donc pas besoin (ni souhaitable) de
  //    le vider ici.
  if (rechargeTout) {
    try { localStorage.removeItem(CLE_CACHE_ISSUES); } catch(e) {}
  }
  // 2) Clés de cache détail « bridge_cache_detail_<projet>_* » — toutes si on
  //    recharge tout, sinon seulement celles des projets actifs du filtre.
  try {
    const aSupprimer = [];
    for (let i = 0; i < localStorage.length; i++) {
      const cle = localStorage.key(i);
      if (!cle || cle.indexOf(CLE_CACHE_DETAIL) !== 0) continue;
      if (rechargeTout || nomsActifs.some(nom => cle.indexOf(CLE_CACHE_DETAIL + nom + '_') === 0)) {
        aSupprimer.push(cle);
      }
    }
    aSupprimer.forEach(cle => localStorage.removeItem(cle));
  } catch(e) {}
  // 3) Recharge la liste depuis GitHub — restreinte aux projets filtrés,
  //    sauf si « Tous » est actif (undefined → comportement par défaut).
  await chargerListeIssues(rechargeTout ? undefined : nomsActifs);
  // 3bis) Recharge aussi les badges de temps restant (issue #270) : depuis la
  // suppression du re-fetch périodique, c'est le SEUL geste qui les remet à
  // jour — sans cet appel, le bouton actualiserait les états d'issues en
  // laissant les badges figés, une incohérence pire que l'ancien comportement.
  await chargerTimingIssues();
  // 4) Ne recharge l'issue affichée que si son détail avait été explicitement
  //    chargé — pas seulement sélectionnée (issue #261).
  if (etaitCharge && projet && numero) {
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

// Copie texte dans le presse-papier : navigator.clipboard.writeText() si
// disponible et la promesse aboutit ; sinon fallback document.execCommand
// ('copy') via un <textarea> temporaire hors écran (issue #464). Nécessaire en
// HTTP non-localhost (mode --lan) : navigator.clipboard est restreint aux
// contextes sécurisés (HTTPS/localhost) et y est silencieusement indisponible.
// Retourne true si la copie a réussi (par l'une ou l'autre voie).
async function copierPressePapier(texte) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(texte);
      return true;
    } catch(e) {
      console.warn('copierPressePapier : échec navigator.clipboard, fallback execCommand.', e);
    }
  }
  try {
    const ta = document.createElement('textarea');
    ta.value = texte;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    ta.style.top = '0';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    if (!ok) console.warn('copierPressePapier : échec document.execCommand(copy).');
    return ok;
  } catch(e) {
    console.warn('copierPressePapier : échec fallback execCommand.', e);
    return false;
  }
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
  if (await copierPressePapier(texte)) {
    btn.disabled = true;
    btn.textContent = '✓ Copié !';
    setTimeout(function() {
      btn.textContent = libelle;
      btn.disabled = false;
    }, 2000);
    return;
  }
  // Fallback ultime (échec clipboard ET execCommand) : on sélectionne le texte
  // du bloc pour permettre un Ctrl+C manuel.
  const sel = window.getSelection();
  if (sel) {
    const range = document.createRange();
    range.selectNodeContents(corps);
    sel.removeAllRanges();
    sel.addRange(range);
  }
}

// Retire la ligne marqueur `<!-- bridge:resultat -->` (posée en tête du
// commentaire CCL par watcher.py, MARQUEUR_RESULTAT) du texte brut avant
// affichage/copie (issue #426) : ce marqueur HTML est avalé par le parseur
// de Claude.ai au collage, rendant le contenu illisible. Il reste dans le
// corps GitHub brut (utile à watcher.py pour repérer le commentaire) — on ne
// le filtre qu'à la lecture côté interface, jamais côté GitHub.
function retirerMarqueurResultat(texte) {
  return (texte || '').replace(/^<!--\s*bridge:resultat\s*-->\n?/, '');
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
  if (await copierPressePapier(texte)) {
    btn.disabled = true;
    btn.textContent = '✓ Copié !';
    setTimeout(function() {
      btn.textContent = libelle;
      btn.disabled = false;
    }, 1500);
    return;
  }
  // Fallback ultime (échec clipboard ET execCommand) : à défaut de
  // presse-papier, on sélectionne au moins le résumé
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

  // Copie dans le presse-papier (fallback execCommand si l'API clipboard est
  // indisponible ou échoue — issue #464).
  await copierPressePapier(texte);

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
  const corpsBrut = retirerMarqueurResultat(comms[comms.length - 1].body || '');
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

  // Avertissement diff volumineux (issue #441) : Claude.ai tronque silencieusement
  // les collages trop longs. La copie a quand même lieu — le toast est purement
  // informatif, sans bouton de confirmation.
  const nbLignes = texte.split('\n').length;
  if (nbLignes > 1000) {
    afficherToast('⚠ Diff volumineux (' + nbLignes + ' lignes) — Claude.ai pourrait ne pas le lire');
  }

  // Copie dans le presse-papier (fallback execCommand si l'API clipboard est
  // indisponible ou échoue — issue #464).
  await copierPressePapier(texte);

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

  // Copie dans le presse-papier (fallback execCommand si l'API clipboard est
  // indisponible ou échoue — issue #464).
  await copierPressePapier(texte);

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

// ─── Interruption ciblée d'une issue en cours (issue #323, suite #320) ──────
// Contrairement à fermerEtInterrompre() (#144, ci-dessus) : ne ferme PAS
// l'issue (needs-human + commentaire seulement, trace conservée), et gère
// aussi bien for-linux (CCL) que for-windows (CCW via SSH/nssm).
// Le dépôt GitHub est lu depuis le <select id="projet"> peuplé côté serveur
// (« nom — depot », cf. templates/index.html et ajouterProjetAuSelecteur) —
// JAMAIS déduit du nom du projet (les deux peuvent diverger, voir la route
// Flask /interrompre, app/interruption.py). Les labels viennent du cache
// localStorage du détail déjà affiché (CLE_CACHE_DETAIL), forcément à jour
// puisque c'est ce détail qui vient de faire apparaître le bouton.
function depotDuProjet(nom) {
  const select = document.getElementById('projet');
  if (!select) return null;
  const opt = [...select.options].find(o => o.value === nom);
  if (!opt) return null;
  const idx = (opt.textContent || '').indexOf(' — ');
  return idx >= 0 ? opt.textContent.slice(idx + 3).trim() : null;
}

function labelsIssueDepuisCache(nom, numero) {
  try {
    const obj = JSON.parse(localStorage.getItem(CLE_CACHE_DETAIL + nom + '_' + numero) || 'null');
    if (obj && obj.it && Array.isArray(obj.it.labels)) {
      return obj.it.labels.map(l => (l && l.name) || l || '').filter(Boolean);
    }
  } catch(e) {}
  return [];
}

// Détecte si l'issue interrompue ÉCRIVAIT dans le working tree du projet, à
// partir des mêmes labels que prefixeIssue() (mode_write, ligne ~606) —
// étendu à mode_scratch (lecture active, #327). Renvoie 'ecriture',
// 'lecture_active' ou null (lecture seule : pas de working tree modifié,
// donc aucun avertissement à afficher — issue #332).
function modeEcritureDepuisLabels(labels) {
  const noms = (labels || []).map(l => (l || '').toLowerCase());
  if (noms.includes('mode_write'))   return 'ecriture';
  if (noms.includes('mode_scratch')) return 'lecture_active';
  return null;
}

// Message d'avertissement working tree, ajouté à la confirmation AVANT le
// kill et/ou au rappel de la modal de résultat APRÈS (issue #332) — mêmes
// faits, formulé une seule fois pour ne pas diverger entre les deux emplois.
function avertissementWorkingTree(modeEcr, nom) {
  if (modeEcr === 'ecriture') {
    return "le kill peut tomber en pleine écriture : le working tree de « " + nom + " » "
         + 'peut rester PARTIEL (fichier à moitié écrit, backup sans le fix). '
         + 'Vérifiez `git status` dans ~/' + nom + ' avant de relancer une issue sur ce projet '
         + '(annulez si besoin, ou repartez du commit avant-XXX).';
  }
  if (modeEcr === 'lecture_active') {
    return 'le garde-fou de restauration (#327) tourne APRÈS claude — un kill peut tomber avant, '
         + 'donc le working tree de « ' + nom + ' » a pu ne PAS être restauré. '
         + 'Un `git status` de vérification dans ~/' + nom + ' est recommandé avant de relancer.';
  }
  return '';
}

// Retourne true si l'interruption a réellement été effectuée (utilisé par
// interrompreEtRelancer, issue #381, pour savoir s'il doit enchaîner sur la
// relance — false si annulée par l'utilisateur ou en échec).
async function interrompreIssue(nom, numero) {
  const depot = depotDuProjet(nom);
  if (!depot) {
    alert('Dépôt GitHub introuvable pour le projet « ' + nom + ' » — impossible d\'interrompre.');
    return false;
  }
  const labels  = labelsIssueDepuisCache(nom, numero);
  const windows = labels.map(l => l.toLowerCase()).includes('for-windows');
  const modeEcr = modeEcritureDepuisLabels(labels);
  const avertTree = avertissementWorkingTree(modeEcr, nom);
  if (!confirm("Interrompre le traitement de l'issue #" + numero
             + (windows ? ' (CCW / Windows)' : ' (CCL / Linux)') + " ?\n\n"
             + 'Le watcher ' + (windows ? 'CCW-Watcher' : 'du projet')
             + ' sera ARRÊTÉ (les autres issues en file restent ouvertes sur GitHub, '
             + 'mais en attente tant que le watcher n\'est pas relancé MANUELLEMENT). '
             + "L'issue sera marquée needs-human — elle ne sera PAS fermée."
             + (avertTree ? '\n\n⚠️ Cette issue écrit dans le projet : ' + avertTree : '')
             + ' Continuer ?')) return false;

  let resultat;
  try {
    const rep = await fetch('/interrompre', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({depot: depot, numero: Number(numero), labels: labels})
    });
    resultat = await rep.json();
  } catch(e) {
    alert('Erreur réseau : ' + e.message);
    return false;
  }
  if (!resultat.succes) {
    alert('Erreur : ' + (resultat.erreur || "échec de l'interruption."));
    return false;
  }
  ouvrirModalInterrompre(resultat, avertTree);

  // Recharge la liste (l'issue porte désormais needs-human) puis réaffiche.
  const numStr = String(numero);
  await chargerListeIssues();
  const ligne = [...document.querySelectorAll('#liste-issues .ligne-issue')]
    .find(l => l.dataset.projet === nom && l.dataset.numero === numStr);
  if (ligne && ligne.style.display !== 'none') {
    await afficherIssue(nom, numStr);
  }
  const panneauWatchers = document.getElementById('panneau-watchers');
  if (panneauWatchers && panneauWatchers.classList.contains('actif')) {
    await chargerWatchers();
  }
  return true;
}

// Interrompt l'issue PUIS relance immédiatement le watcher de son projet, en
// un seul geste (issue #381) — CCL (sidebarRelancerWatcherCCL) ou CCW
// (ccwRedemarrerProjet) selon le label for-windows de l'issue. Réutilise
// interrompreIssue() tel quel (même confirmation, même route /interrompre,
// même modal de résultat) ; la relance n'a lieu que si l'interruption a
// réellement été effectuée (pas annulée, pas en échec).
async function interrompreEtRelancer(nom, numero) {
  const labels  = labelsIssueDepuisCache(nom, numero);
  const windows = labels.map(l => l.toLowerCase()).includes('for-windows');
  const ok = await interrompreIssue(nom, numero);
  if (!ok) return;
  if (windows) {
    await ccwRedemarrerProjet(nom);
  } else {
    await sidebarRelancerWatcherCCL(nom);
  }
}

// Relance une issue bloquée en needs-human (issue #460) : retire simplement
// ce label côté GitHub (route Flask /relancer-issue, app/interruption.py) —
// il n'existe PAS de label « pending » dans ce projet, une issue ouverte
// sans needs-human ni done est déjà éligible au prochain cycle du watcher
// (voir watcher.py). Ne relance PAS le watcher lui-même : si celui-ci est
// éteint, une relance manuelle depuis l'onglet Watchers reste nécessaire.
async function relancerIssue(nom, numero) {
  const depot = depotDuProjet(nom);
  if (!depot) {
    alert('Dépôt GitHub introuvable pour le projet « ' + nom + ' » — impossible de relancer.');
    return;
  }
  if (!confirm("Relancer l'issue #" + numero + " ?\n\n"
             + "Le label needs-human sera retiré : l'issue sera reprise par le watcher "
             + "à son prochain cycle (s'il tourne).")) return;

  let resultat;
  try {
    const rep = await fetch('/relancer-issue', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({depot: depot, numero: Number(numero)})
    });
    resultat = await rep.json();
  } catch(e) {
    alert('Erreur réseau : ' + e.message);
    return;
  }
  if (!resultat.succes || resultat.statut_global === 'echec') {
    const detail = (resultat.etapes || []).map(e => e.message).filter(Boolean).join(' / ');
    alert('Erreur : ' + (resultat.erreur || detail || 'échec de la relance.'));
    return;
  }

  // Recharge la liste (l'issue a perdu needs-human) puis réaffiche si visible.
  await chargerListeIssues();
  const numStr = String(numero);
  const ligne = [...document.querySelectorAll('#liste-issues .ligne-issue')]
    .find(l => l.dataset.projet === nom && l.dataset.numero === numStr);
  if (ligne && ligne.style.display !== 'none') {
    await afficherIssue(nom, numStr);
  }
}

const LIBELLES_STATUT_INTERROMPRE = {
  ok:              {icone: '✅', texte: 'Interruption effectuée'},
  succes_partiel:  {icone: '⚠️', texte: 'Interruption partielle — certaines étapes ont échoué'},
  echec_critique:  {icone: '⛔', texte: "Interruption incomplète — action manuelle requise"},
};
const BADGES_ETAPE_INTERROMPRE = {succes: '✅', rien_a_faire: '➖', echec: '❌'};

function ouvrirModalInterrompre(resultat, avertTree) {
  const overlay = document.getElementById('modal-interrompre');
  const titre   = document.getElementById('modal-interrompre-titre');
  const liste   = document.getElementById('modal-interrompre-liste');
  const rappel  = document.getElementById('modal-interrompre-rappel');

  const lib = LIBELLES_STATUT_INTERROMPRE[resultat.statut_global]
           || {icone: '', texte: resultat.statut_global || '?'};
  titre.textContent = lib.icone + ' ' + lib.texte;

  liste.innerHTML = (resultat.etapes || []).map(e =>
    '<div class="etape-interrompre etape-' + escapeHtml(e.statut) + '">'
    + '<span class="etape-badge">' + (BADGES_ETAPE_INTERROMPRE[e.statut] || '?') + '</span> '
    + '<b>' + escapeHtml(e.etape) + '</b> — ' + escapeHtml(e.message || '')
    + '</div>'
  ).join('') || '<div class="issue-vide">Aucune étape.</div>';

  let rappelTexte = resultat.agent === 'windows'
    ? 'Service CCW-Watcher arrêté — relance via l\'onglet CCW (pas de rallumage automatique).'
    : 'Relance manuelle du watcher obligatoire (onglet Watchers) — pas de rallumage automatique.';
  if (resultat.agent === 'windows' && resultat.vm_running === false) {
    rappelTexte += ' ⚠ La VM CCW-Build ne semble pas démarrée actuellement.';
  }
  if (resultat.statut_global === 'echec_critique') {
    rappelTexte += " ⛔ Un process n'a pas pu être confirmé mort — vérifiez avec ps / le "
                 + 'Gestionnaire des tâches AVANT de relancer le watcher (le verrou a été '
                 + 'volontairement laissé en place pour éviter un double traitement).';
  } else if (resultat.statut_global === 'succes_partiel') {
    rappelTexte += ' ⚠ Certaines étapes ont échoué (détail ci-dessus) — vérifiez avant de relancer.';
  }
  if (avertTree) {
    rappelTexte += ' ⚠️ Cette issue écrivait dans le projet : ' + avertTree
                 + ' Ne relancez aucune issue sur ce projet avant working tree propre.';
  }
  rappel.textContent = rappelTexte;

  overlay.classList.add('actif');
}

function fermerModalInterrompre() {
  document.getElementById('modal-interrompre').classList.remove('actif');
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

function normaliserTexteMode(texte) {
  return texte.trim().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
}

// Traduit le texte brut de la cellule « | MODE | … | » en valeur de radio.
// Absent (chaîne vide/null) ou non reconnu → 'lecture' (défaut sûr).
function reconnaitreModeTexte(brut) {
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
  // Mode LOT : le MODE reste COMMUN à tout le lot, choisi via le radio du
  // formulaire — pas détecté par bloc (DOC §3, hors périmètre de #326).
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
document.getElementById('corps').addEventListener('input', detecterModeDansCorps);

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
          if (json.watcher_demarre === true) watcherDemarre = true;
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
  document.getElementById('np-rappel-projet').style.display = 'none';
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
  document.getElementById('np-rappel-projet').style.display = 'none';
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
    // Rappels propres au PROJET créé (dépôt distinct de Bridge_Agent) : issue
    // #257 — sans eux l'encart ci-dessus, seul affiché jusque-là, laissait
    // croire à tort que rien d'autre n'était à faire.
    afficherRappelProjet(res);
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
  const cmds = 'cd ~/Bridge_Agent\n'
             + 'git add BRIDGE_AGENT_DOC.md\n'
             + 'git commit -m "Ajout du projet ' + nom + ' (§2)"\n'
             + 'git push';
  const box = document.getElementById('np-rappel-git');
  box.innerHTML =
    '<div class="titre">⚠ Action requise — dépôt Bridge_Agent : pousser la doc</div>'
    + 'Le projet est créé, mais la mise à jour de <b>BRIDGE_AGENT_DOC.md</b> (§2) '
    + "n'est que locale. Tant qu'elle n'est pas poussée, le projet reste invisible "
    + 'pour Claude Chat. Exécute (clic pour sélectionner) :'
    + '<pre onclick="npSelectionnerTexte(this)">' + escapeHtml(cmds) + '</pre>';
  box.style.display = 'block';
}

// Rappels propres au PROJET créé (dépôt distinct de Bridge_Agent, cf.
// afficherRappelGit ci-dessus) — issue #257, complété #258. Deux points,
// jamais mentionnés nulle part avant l'issue #257 :
//  1. CONTEXTE.md est créé VIDE (injecté dans chaque prompt CCL, plafonné à
//     4000 caractères) — toujours à rappeler, quel que soit le cas git.
//  2. Si l'initialisation git du répertoire de travail n'a pas pu se
//     terminer (push initial échoué), OU si le push a été VOLONTAIREMENT
//     retenu parce que le répertoire contenait déjà du contenu non relu
//     (issue #258 — le dépôt est public), les commandes manuelles
//     nécessaires. Les deux cas partagent commande_manuelle mais doivent
//     rester des messages distincts : le premier est un échec, le second une
//     retenue délibérée — les confondre laisserait croire à une erreur là où
//     rien n'a raté.
// Encart visuellement distinct (bordure bleue) de celui de afficherRappelGit
// (bordure orange) : c'est précisément la confusion entre « dépôt
// Bridge_Agent » et « dépôt du projet créé » qui a fait passer inaperçu le
// bug d'origine de l'issue #257.
function afficherRappelProjet(res) {
  const box = document.getElementById('np-rappel-projet');
  let html = '<div class="titre">ℹ Côté projet « ' + escapeHtml(res.nom) + ' » créé</div>';
  html += '<div>CONTEXTE.md est créé <b>VIDE</b> — à rédiger avant de compter sur '
        + 'le projet : c\'est ce fichier qui est injecté dans chaque prompt CCL '
        + '(plafonné à 4000 caractères).</div>';
  if (res.git_deja_git) {
    html += '<div>Dépôt git local : déjà un dépôt git existant, inchangé.</div>';
  } else if (res.git_push_ok) {
    html += '<div>Dépôt git local : initialisé (branche master, remote HTTPS) '
          + 'et poussé sur origin/master.</div>';
  } else if (res.git_contenu_preexistant && res.git_contenu_preexistant.length) {
    const noms = res.git_contenu_preexistant.slice(0, 10);
    const reste = res.git_contenu_preexistant.length - noms.length;
    html += '<div>⚠ Push <b>volontairement non déclenché</b> : le dépôt est '
          + '<b>public</b> et le répertoire contenait déjà '
          + res.git_contenu_preexistant.length + ' fichier(s) non relu(s) — '
          + "ce n'est pas un échec, rien n'a été publié :</div>"
          + '<pre>' + escapeHtml(noms.join('\n'))
          + (reste > 0 ? '\n… et ' + reste + ' autre(s).' : '') + '</pre>'
          + '<div>Après vérification de ce contenu, lance (clic pour '
          + 'sélectionner) :</div>'
          + '<pre onclick="npSelectionnerTexte(this)">'
          + escapeHtml(res.git_commande_manuelle) + '</pre>';
  } else if (res.git_commande_manuelle) {
    html += '<div>⚠ Initialisation git incomplète — à terminer à la main '
          + '(clic pour sélectionner) :</div>'
          + '<pre onclick="npSelectionnerTexte(this)">'
          + escapeHtml(res.git_commande_manuelle) + '</pre>';
  }
  box.innerHTML = html;
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
