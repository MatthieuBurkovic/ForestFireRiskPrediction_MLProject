"""
Integration des donnees IGN (Inventaire Forestier National) au pipeline
de prediction du risque incendie.

Etapes :
1. Agregation de la table ARBRE au niveau de la placette (CAMPAGNE, IDP)
2. Jointure avec la table PLACETTE (coordonnees + relief + perturbations)
3. Rattachement de chaque placette a la maille SAFRAN la plus proche
4. Propagation de la derniere campagne IFN disponible sur chaque annee
   2015-2024 (la vegetation evolue lentement, donc on reutilise le dernier
   etat connu jusqu'a la campagne suivante)

A VERIFIER avant utilisation (cf. message d'explication) :
- Le seuil ESPAR >= 51 = "resineux" est une approximation construite a partir
  d'une table de correspondance partielle. Pour la precision finale, recupere
  la table complete sur https://inventaire-forestier.ign.fr/dataifn/
  (section documentation) et adapte la fonction est_resineux().
- VEGET : confirme empiriquement -> 0 = vivant, le reste (1, 5, A, C, Z) =
  non-vivant (melange mort recent/ancien/coupe, a affiner avec VEGET5 si
  besoin de distinguer "coupe" de "mort sur pied"). Les lignes sans valeur
  sont exclues du calcul plutot que comptees comme mortes.
- Coordonnees : confirme empiriquement -> le fichier SAFRAN/SIM utilise le
  Lambert II etendu en HECTOMETRES (pas le Lambert 93 en metres comme le
  laissait penser la doc Meteo-France), d'ou la reprojection via pyproj a
  l'etape 4. Necessite : pip install pyproj
- ANPYR / DPYR semblent liees aux incendies (racine "pyr") mais leur
  definition exacte n'a pas pu etre confirmee ici : verifie dans la doc
  correspondant a tes campagnes avant de t'appuyer dessus.
"""

import pandas as pd
import numpy as np
from scipy.spatial import cKDTree
from pyproj import Transformer

# ---------- 0. Parametres ----------
FICHIER_ARBRE = "arbre.csv"
FICHIER_PLACETTE = "placette.csv"
FICHIER_METEO_PARQUET = "SIM_ML.parquet"  
FICHIER_SORTIE = "vegetation_ign_par_maille_annee.parquet"

ANNEE_DEBUT, ANNEE_FIN = 2015, 2024
SEUIL_RESINEUX = 51  # ESPAR >= 51 => resineux (approximation, voir doc)

# ---------- 1. Chargement ----------
# dtype=str sur TOUT a la lecture : evite que pandas devine des types
# differents selon les blocs du fichier (cause de l'erreur Parquet/pyarrow
# "Expected bytes, got a float object"). On reconvertira en numerique
# uniquement les colonnes qui en ont vraiment besoin, juste apres.
arbre = pd.read_csv(FICHIER_ARBRE, sep=";", dtype=str, low_memory=False)
placette = pd.read_csv(FICHIER_PLACETTE, sep=";", dtype=str, low_memory=False)
meteo = pd.read_parquet(FICHIER_METEO_PARQUET)

# Cle de jointure CAMPAGNE : doit etre numerique pour le merge_asof plus loin
arbre["CAMPAGNE"] = arbre["CAMPAGNE"].astype(int)
placette["CAMPAGNE"] = placette["CAMPAGNE"].astype(int)

# Colonnes numeriques necessaires aux agregations / a la jointure spatiale
for col in ["V", "HTOT", "AGE", "C13"]:
    arbre[col] = pd.to_numeric(arbre[col], errors="coerce")
placette["XL"] = pd.to_numeric(placette["XL"], errors="coerce")
placette["YL"] = pd.to_numeric(placette["YL"], errors="coerce")

# ---------- 2. Agregation ARBRE -> niveau placette ----------
def code_espar_num(x):
    """ESPAR peut contenir des lettres ('20G', '53CA') : on garde la partie numerique."""
    chiffres = "".join(c for c in str(x) if c.isdigit())
    return int(chiffres) if chiffres else np.nan

arbre["ESPAR_NUM"] = arbre["ESPAR"].apply(code_espar_num)
arbre["EST_RESINEUX"] = arbre["ESPAR_NUM"] >= SEUIL_RESINEUX

# Mortalite : 0 = vivant (confirme empiriquement, ~8% de non-vivant parmi
# les arbres renseignes, coherent avec la statistique officielle IGN). Les
# lignes sans VEGET renseigne (NaN -> "nan" apres str(), souvent des arbres
# "simplifies" avec seulement 2 donnees collectees) sont EXCLUES du calcul
# plutot que comptees comme mortes.
arbre["VEGET"] = arbre["VEGET"].astype(str).str.strip()
print("Codes VEGET presents :", arbre["VEGET"].value_counts().to_dict())
arbre["VEGET_RENSEIGNE"] = arbre["VEGET"] != "nan"
arbre["EST_VIVANT"] = (arbre["VEGET"] == "0") & arbre["VEGET_RENSEIGNE"]

# Indicateur sanitaire global : au moins un signe (gelivure, gui, pourriture...)
colonnes_sanitaires = [c for c in
                       ["SFCOEUR", "SFDORGE", "SFGELIV", "SFGUI", "SFPIED"]
                       if c in arbre.columns]
arbre["A_PROBLEME_SANITAIRE"] = arbre[colonnes_sanitaires].notna().any(axis=1)

agg_placette = arbre.groupby(["CAMPAGNE", "IDP"]).agg(
    nb_arbres=("A", "count"),
    nb_arbres_renseignes=("VEGET_RENSEIGNE", "sum"),
    nb_vivants=("EST_VIVANT", "sum"),
    pct_resineux=("EST_RESINEUX", "mean"),
    volume_total=("V", "sum"),
    hauteur_moyenne=("HTOT", "mean"),
    age_moyen=("AGE", "mean"),
    pct_probleme_sanitaire=("A_PROBLEME_SANITAIRE", "mean"),
).reset_index()

agg_placette["pct_mortalite"] = 1 - (
    agg_placette["nb_vivants"] / agg_placette["nb_arbres_renseignes"].replace(0, np.nan)
)

# ---------- 3. Jointure avec PLACETTE ----------
colonnes_placette_souhaitees = [
    "CAMPAGNE", "IDP", "XL", "YL", "DATEPOINT",
    "GRECO", "SER", "PENTEXP", "ASPERITE", "ACCES",
    "INCID", "NINCID", "ANPYR", "DPYR",
]
colonnes_dispo = [c for c in colonnes_placette_souhaitees if c in placette.columns]
placette_sel = placette[colonnes_dispo]

plots = agg_placette.merge(placette_sel, on=["CAMPAGNE", "IDP"], how="left")

# ---------- 4. Rattachement a la maille SAFRAN la plus proche ----------
# IMPORTANT : malgre ce qu'indique la doc Meteo-France, les valeurs reelles
# de LAMBX/LAMBY (ex. LAMBY entre ~16170 et ~26810) correspondent a du
# Lambert II etendu (EPSG:27572) exprime en HECTOMETRES, pas a du Lambert 93
# en metres. Les placettes IGN (XL/YL), elles, sont bien en Lambert 93
# (EPSG:2154). On reprojette donc les mailles SAFRAN avant de chercher le
# plus proche voisin (transformation geodesique complete via pyproj, pas un
# simple decalage, car les deux systemes n'ont pas le meme datum).
transformer = Transformer.from_crs("EPSG:27572", "EPSG:2154", always_xy=True)

mailles = meteo[["LAMBX", "LAMBY"]].drop_duplicates().reset_index(drop=True)
x_metres = mailles["LAMBX"].values * 100  # hectometres -> metres
y_metres = mailles["LAMBY"].values * 100
mailles["X_L93"], mailles["Y_L93"] = transformer.transform(x_metres, y_metres)

arbre_kdtree = cKDTree(mailles[["X_L93", "Y_L93"]].values)
dist, idx = arbre_kdtree.query(plots[["XL", "YL"]].values)

# On garde LAMBX/LAMBY d'ORIGINE (hectometres) : c'est la cle qui permettra
# de rejoindre le fichier meteo plus loin.
plots["LAMBX"] = mailles.loc[idx, "LAMBX"].values
plots["LAMBY"] = mailles.loc[idx, "LAMBY"].values
plots["DIST_MAILLE_M"] = dist  # devrait maintenant etre de l'ordre de quelques km max

# ---------- 5. Propagation par annee (derniere campagne connue <= annee) ----------
cible = (
    plots[["LAMBX", "LAMBY"]].drop_duplicates()
    .merge(pd.DataFrame({"ANNEE": range(ANNEE_DEBUT, ANNEE_FIN + 1)}), how="cross")
    .sort_values("ANNEE")
)

source = plots.sort_values("CAMPAGNE").rename(columns={"CAMPAGNE": "ANNEE"})

vegetation_par_maille_annee = pd.merge_asof(
    cible, source,
    on="ANNEE", by=["LAMBX", "LAMBY"], direction="backward"
)

vegetation_par_maille_annee.to_parquet(FICHIER_SORTIE, index=False)

print(f"\n{len(vegetation_par_maille_annee)} lignes ecrites dans {FICHIER_SORTIE}")
print(f"Mailles sans aucune donnee vegetation : "
      f"{vegetation_par_maille_annee['IDP'].isna().sum()} lignes")
print(f"Distance moyenne placette -> maille SAFRAN : {plots['DIST_MAILLE_M'].mean():.0f} m")