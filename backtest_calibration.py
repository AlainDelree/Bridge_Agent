import json
import math
import sys
from collections import defaultdict

# ── Chargement ────────────────────────────────────────────────────────────────
with open("logs/historique_durees.json") as f:
    data = json.load(f)

# Filtrer les durées aberrantes (timeouts censurés, valeurs nulles)
# et trier chronologiquement
data = [e for e in data if e.get("duree", 0) > 0]
data.sort(key=lambda e: e.get("date", ""))

# ── Paramètres à tester ───────────────────────────────────────────────────────
K_VALUES        = [2, 3, 4, 5, 6]
DEMI_VIES       = [5, 10, 15, 20, 30]
PLANCHER        = 30   # secondes

def cle(e):
    return f"{e['projet']}|{e['type']}|{e['mode']}"

# ── Replay EWMA ───────────────────────────────────────────────────────────────
def alpha(n):
    """Poids EWMA pour une demi-vie de n issues."""
    return 1 - math.exp(-math.log(2) / n)

def backtest(k, demi_vie):
    """
    Rejoue l'historique et retourne pour chaque clé :
    - nb observations
    - taux de couverture (timeout_suggéré >= durée réelle)
    - ratio moyen timeout_suggéré / durée réelle (gaspillage)
    """
    # état EWMA par clé : (mu, sigma2)  — mu=moyenne, sigma2=variance
    etats = {}
    resultats_par_cle = defaultdict(lambda: {"n": 0, "couverts": 0, "ratios": []})

    a = alpha(demi_vie)

    for e in data:
        k_cle = cle(e)
        duree = e["duree"]

        if k_cle not in etats:
            # Initialisation sur la première observation
            etats[k_cle] = (duree, 0.0)
            # Pas de prédiction possible sur le 1er point
            continue

        mu, var = etats[k_cle]

        # Prédiction AVANT mise à jour
        sigma = math.sqrt(var) if var > 0 else mu * 0.5
        timeout_suggere = max(mu + k * sigma, PLANCHER)

        # Enregistrement
        r = resultats_par_cle[k_cle]
        r["n"] += 1
        if timeout_suggere >= duree:
            r["couverts"] += 1
        r["ratios"].append(timeout_suggere / duree if duree > 0 else 1.0)

        # Mise à jour EWMA
        new_mu  = a * duree + (1 - a) * mu
        new_var = (1 - a) * (var + a * (duree - mu) ** 2)
        etats[k_cle] = (new_mu, new_var)

    return resultats_par_cle

# ── Rapport ───────────────────────────────────────────────────────────────────
print("=" * 70)
print(f"BACKTEST CALIBRATION — {len(data)} observations")
print("=" * 70)

# Clés avec assez d'observations
MIN_OBS = 20
toutes_cles = set(cle(e) for e in data)

# 1. Comparaison des K (demi-vie fixée à 15)
print("\n── 1. Impact de K (demi-vie = 15) ──────────────────────────────────")
print(f"{'Clé':<40} {'N':>5}", end="")
for k in K_VALUES:
    print(f"  K={k}", end="")
print()

resultats_K = {k: backtest(k, 15) for k in K_VALUES}
totaux_K = {k: {"n": 0, "couverts": 0, "ratios": []} for k in K_VALUES}

for cle_str in sorted(toutes_cles):
    n_ref = resultats_K[K_VALUES[0]][cle_str]["n"]
    if n_ref < MIN_OBS:
        continue
    print(f"{cle_str:<40} {n_ref:>5}", end="")
    for k in K_VALUES:
        r = resultats_K[k][cle_str]
        taux = r["couverts"] / r["n"] * 100 if r["n"] else 0
        print(f"  {taux:>4.0f}%", end="")
        totaux_K[k]["n"] += r["n"]
        totaux_K[k]["couverts"] += r["couverts"]
        totaux_K[k]["ratios"].extend(r["ratios"])
    print()

print(f"\n{'GLOBAL (toutes clés ≥20 obs)':<46}", end="")
for k in K_VALUES:
    t = totaux_K[k]
    taux = t["couverts"] / t["n"] * 100 if t["n"] else 0
    print(f"  {taux:>4.0f}%", end="")
print()

print(f"\n{'Ratio médian timeout/durée réelle (gaspillage)':<46}", end="")
for k in K_VALUES:
    ratios = sorted(totaux_K[k]["ratios"])
    med = ratios[len(ratios)//2] if ratios else 0
    print(f"  {med:>4.2f}x", end="")
print()

# 2. Comparaison des demi-vies (K fixé à 4)
print("\n── 2. Impact de la demi-vie (K = 4) ────────────────────────────────")
print(f"{'Clé':<40} {'N':>5}", end="")
for dv in DEMI_VIES:
    print(f"  dv={dv:>2}", end="")
print()

resultats_DV = {dv: backtest(4, dv) for dv in DEMI_VIES}
totaux_DV = {dv: {"n": 0, "couverts": 0, "ratios": []} for dv in DEMI_VIES}

for cle_str in sorted(toutes_cles):
    n_ref = resultats_DV[DEMI_VIES[0]][cle_str]["n"]
    if n_ref < MIN_OBS:
        continue
    print(f"{cle_str:<40} {n_ref:>5}", end="")
    for dv in DEMI_VIES:
        r = resultats_DV[dv][cle_str]
        taux = r["couverts"] / r["n"] * 100 if r["n"] else 0
        print(f"   {taux:>4.0f}%", end="")
        totaux_DV[dv]["n"] += r["n"]
        totaux_DV[dv]["couverts"] += r["couverts"]
        totaux_DV[dv]["ratios"].extend(r["ratios"])
    print()

print(f"\n{'GLOBAL':<46}", end="")
for dv in DEMI_VIES:
    t = totaux_DV[dv]
    taux = t["couverts"] / t["n"] * 100 if t["n"] else 0
    print(f"   {taux:>4.0f}%", end="")
print()

print(f"\n{'Ratio médian timeout/durée réelle':<46}", end="")
for dv in DEMI_VIES:
    ratios = sorted(totaux_DV[dv]["ratios"])
    med = ratios[len(ratios)//2] if ratios else 0
    print(f"   {med:>4.2f}x", end="")
print()

# 3. Résumé des durées réelles par clé
print("\n── 3. Statistiques descriptives par clé ────────────────────────────")
print(f"{'Clé':<40} {'N':>5} {'min':>6} {'med':>6} {'p90':>6} {'max':>6} {'moy':>6}")
par_cle = defaultdict(list)
for e in data:
    par_cle[cle(e)].append(e["duree"])

for cle_str in sorted(par_cle.keys()):
    durees = sorted(par_cle[cle_str])
    n = len(durees)
    if n < MIN_OBS:
        continue
    med = durees[n//2]
    p90 = durees[int(n*0.9)]
    moy = sum(durees)/n
    print(f"{cle_str:<40} {n:>5} {min(durees):>6} {med:>6} {p90:>6} {max(durees):>6} {moy:>6.0f}")

print("\n" + "=" * 70)
