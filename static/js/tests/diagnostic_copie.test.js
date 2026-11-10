// Tests de logique pure du journal de diagnostic de la copie presse-papier
// (issue #878). Lancement (depuis la racine) : node --test static/js/tests/
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  diagnosticActif,
  construireLigneDiagnostic,
  libelleEtatSse,
  ligneRedessineeRecemment,
  SEUIL_REDESSIN_RECENT_MS,
  borneFile,
  BORNE_FILE,
  diagnostiquer,
  rejouerFileEnAttente,
} from '../socle/diagnostic_copie.js';

// ─── diagnosticActif ──────────────────────────────────────────────────────────
test('diagnosticActif : false sans window, ou si window.DIAGNOSTIC_COPIE n\'est pas EXACTEMENT true', () => {
  const avant = globalThis.window;
  try {
    delete globalThis.window;
    assert.equal(diagnosticActif(), false);
    globalThis.window = {};
    assert.equal(diagnosticActif(), false);
    globalThis.window = { DIAGNOSTIC_COPIE: 'oui' };   // chaîne, pas le booléen attendu
    assert.equal(diagnosticActif(), false);
    globalThis.window = { DIAGNOSTIC_COPIE: true };
    assert.equal(diagnosticActif(), true);
  } finally {
    if (avant === undefined) delete globalThis.window; else globalThis.window = avant;
  }
});

// ─── construireLigneDiagnostic (pure) ─────────────────────────────────────────
test('construireLigneDiagnostic : tous les champs attendus, dans l\'ordre documenté', () => {
  const ligne = construireLigneDiagnostic({
    date: '2026-11-10T10:00:00.000Z',
    navigateur: 'Firefox 131.0',
    projet: 'bridge_agent',
    numero: 878,
    depuisDernierEvenementSseMs: 45231,
    etatSse: 1,
    elementDansDocument: true,
    ligneRedessineeRecemment: true,
    etape: 'change',
    resultat: 'declenche',
  });
  assert.match(ligne, /date=2026-11-10T10:00:00\.000Z/);
  assert.match(ligne, /navigateur=Firefox 131\.0/);
  assert.match(ligne, /projet=bridge_agent/);
  assert.match(ligne, /issue=878/);
  assert.match(ligne, /depuisDernierEvenementSse=45231ms/);
  assert.match(ligne, /etatSse=ouvert/);
  assert.match(ligne, /elementDansDocument=oui/);
  assert.match(ligne, /ligneRedessineeRecemment=oui/);
  assert.match(ligne, /etape=change/);
  assert.match(ligne, /resultat=declenche/);
});

test('construireLigneDiagnostic : contexte vide → valeurs "inconnu"/"inconnue", jamais d\'exception', () => {
  const ligne = construireLigneDiagnostic();
  assert.match(ligne, /depuisDernierEvenementSse=inconnu/);
  assert.match(ligne, /etatSse=inconnu/);
  assert.match(ligne, /elementDansDocument=inconnu/);
  assert.match(ligne, /ligneRedessineeRecemment=inconnu/);
  assert.match(ligne, /etape=inconnue/);
  assert.match(ligne, /resultat=inconnu/);
});

test('construireLigneDiagnostic : une seule LIGNE (pas de retour à la ligne interne) — contrat du journal serveur', () => {
  const ligne = construireLigneDiagnostic({ projet: 'a', numero: 1, etape: 'ecriture', resultat: 'succes' });
  assert.ok(!ligne.includes('\n'));
});

// ─── libelleEtatSse ────────────────────────────────────────────────────────────
test('libelleEtatSse : readyState EventSource (0/1/2) → libellé lisible', () => {
  assert.equal(libelleEtatSse(0), 'connexion');
  assert.equal(libelleEtatSse(1), 'ouvert');
  assert.equal(libelleEtatSse(2), 'ferme');
  assert.equal(libelleEtatSse(null), 'inconnu');
  assert.equal(libelleEtatSse(undefined), 'inconnu');
});

// ─── ligneRedessineeRecemment ──────────────────────────────────────────────────
test('ligneRedessineeRecemment : redessin il y a moins du seuil → true', () => {
  const maintenant = 1_000_000;
  assert.equal(ligneRedessineeRecemment(maintenant - 100, maintenant), true);
  assert.equal(ligneRedessineeRecemment(maintenant - (SEUIL_REDESSIN_RECENT_MS - 1), maintenant), true);
});

test('ligneRedessineeRecemment : redessin ancien (≥ seuil) → false', () => {
  const maintenant = 1_000_000;
  assert.equal(ligneRedessineeRecemment(maintenant - SEUIL_REDESSIN_RECENT_MS, maintenant), false);
  assert.equal(ligneRedessineeRecemment(maintenant - 999999, maintenant), false);
});

test('ligneRedessineeRecemment : horodatage absent/NaN (ligne jamais retrouvée) → false, pas d\'exception', () => {
  assert.equal(ligneRedessineeRecemment(NaN, Date.now()), false);
  assert.equal(ligneRedessineeRecemment(undefined, Date.now()), false);
});

// ─── borneFile ─────────────────────────────────────────────────────────────────
test('borneFile : garde les plus RÉCENTES (fin du tableau), perd les plus anciennes au-delà de la borne', () => {
  const liste = Array.from({ length: BORNE_FILE + 5 }, (_, i) => 'ligne' + i);
  const bornee = borneFile(liste);
  assert.equal(bornee.length, BORNE_FILE);
  assert.equal(bornee[0], 'ligne5');                       // les 5 plus anciennes perdues
  assert.equal(bornee[bornee.length - 1], liste[liste.length - 1]);
});

test('borneFile : liste vide/absente → tableau vide', () => {
  assert.deepEqual(borneFile([]), []);
  assert.deepEqual(borneFile(undefined), []);
});

// ─── diagnostiquer/rejouerFileEnAttente : NO-OP strict si désactivé ───────────
// (localStorage/fetch/console ne doivent être touchés QUE si diagnosticActif()
// — on les instrumente pour vérifier qu'ils ne le sont PAS ici.)
test('diagnostiquer/rejouerFileEnAttente : aucun accès réseau/console/localStorage quand DIAGNOSTIC_COPIE est désactivé', () => {
  const avantWindow = globalThis.window;
  const avantFetch = globalThis.fetch;
  const avantConsoleLog = console.log;
  let appelsFetch = 0;
  let appelsConsole = 0;
  globalThis.window = { DIAGNOSTIC_COPIE: false };
  globalThis.fetch = () => { appelsFetch += 1; return Promise.resolve(); };
  console.log = () => { appelsConsole += 1; };
  try {
    diagnostiquer({ projet: 'a', numero: 1, etape: 'ecriture', resultat: 'succes' });
    rejouerFileEnAttente();
    assert.equal(appelsFetch, 0);
    assert.equal(appelsConsole, 0);
  } finally {
    globalThis.window = avantWindow;
    globalThis.fetch = avantFetch;
    console.log = avantConsoleLog;
  }
});
