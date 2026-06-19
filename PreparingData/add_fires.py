"""
Construction de la variable cible (occurrence d'incendie) au format
(maille SAFRAN, annee, mois, jour) a partir du fichier BDIFF enrichi en
coordonnees GPS.

Sortie : une table avec une ligne par (LAMBX, LAMBY, ANNEE, MOIS, JOUR) ou
au moins un incendie a demarre. A fusionner ensuite (left join sur ces
memes colonnes, puis fillna(0) sur INCENDIE) avec la grande table
meteo + vegetation pour obtenir le jeu de donnees d'entrainement final.

A garder en tete :
- Les lignes sans GPS (communes fusionnees/renommees) sont supprimees.
- latitude_centre/longitude_centre sont des centroides de COMMUNE, pas le
  point exact de l'incendie.
- Avec ~9000 mailles x ~3650 jours et seulement ~27 000 incendies, le taux
  de positifs dans la table finale sera tres faible (<0.1%) : a anticiper
  pour le choix du modele (poids de classe, sous-echantillonnage des
  negatifs, etc.) -- ce n'est pas traite dans ce script, qui ne fait que
  construire le label brut.
"""

import pandas as pd
from scipy.spatial import cKDTree
from pyproj import Transformer

FICHIER_INCENDIES = "Incendies_enrichie.csv"
FICHIER_METEO_PARQUET = "SIM_ML.parquet"
FICHIER_SORTIE = "label_incendies_par_maille_jour.parquet"

# ---------- 1. Chargement ----------
# encoding="utf-8-sig" retire le BOM en tete de fichier (sinon la 1ere
# colonne s'appelle litteralement "\ufeffAnnee" au lieu de "Annee")
incendies = pd.read_csv(FICHIER_INCENDIES, sep=";", encoding="utf-8-sig")

domtom = {"971", "972", "973", "974", "976"}

avant = len(incendies)
incendies = incendies[~incendies["Département"].astype(str).isin(domtom)]
print(f"{avant - len(incendies)} lignes DOM-TOM supprimées")

cols_utiles = ["LAMBX", "LAMBY", "ANNEE", "MOIS", "JOUR"]
meteo = pd.read_parquet(FICHIER_METEO_PARQUET, columns=cols_utiles)

print(f"{len(incendies)} incendies charges")

# ---------- 2. Nettoyage minimal ----------
avant = len(incendies)
incendies = incendies.dropna(subset=["latitude_centre", "longitude_centre"])
print(f"{avant - len(incendies)} lignes sans GPS supprimees "
      f"(communes fusionnees/renommees non reconnues par la table de "
      f"correspondance)")

# ---------- 3. Extraction des composantes de date ----------
incendies["DATE_ALERTE"] = pd.to_datetime(incendies["Date de première alerte"])
incendies["ANNEE"] = incendies["DATE_ALERTE"].dt.year
incendies["MOIS"] = incendies["DATE_ALERTE"].dt.month
incendies["JOUR"] = incendies["DATE_ALERTE"].dt.day

# ---------- 4. Reprojection WGS84 (lat/lon) -> Lambert 93 ----------
transformer_wgs84_l93 = Transformer.from_crs("EPSG:4326", "EPSG:2154", always_xy=True)
incendies["X_L93"], incendies["Y_L93"] = transformer_wgs84_l93.transform(
    incendies["longitude_centre"].values, incendies["latitude_centre"].values
)

# ---------- 5. Rattachement a la maille SAFRAN la plus proche ----------
# Meme logique que pour les placettes IGN : SAFRAN est en Lambert II etendu
# (EPSG:27572) en HECTOMETRES -> on reprojette les mailles en Lambert 93
# pour comparer dans le meme repere que les coordonnees des incendies.
transformer_l2e_l93 = Transformer.from_crs("EPSG:27572", "EPSG:2154", always_xy=True)

mailles = meteo[["LAMBX", "LAMBY"]].drop_duplicates().reset_index(drop=True)
mailles["X_L93"], mailles["Y_L93"] = transformer_l2e_l93.transform(
    mailles["LAMBX"].values * 100, mailles["LAMBY"].values * 100
)

kdtree = cKDTree(mailles[["X_L93", "Y_L93"]].values)
dist, idx = kdtree.query(incendies[["X_L93", "Y_L93"]].values)

incendies["LAMBX"] = mailles.loc[idx, "LAMBX"].values
incendies["LAMBY"] = mailles.loc[idx, "LAMBY"].values
incendies["DIST_MAILLE_M"] = dist

print(f"Distance moyenne commune -> maille SAFRAN : {dist.mean():.0f} m "
      f"(max : {dist.max():.0f} m)")

# ---------- 6. Construction du label (une ligne par maille x jour avec feu) ----------
label = (
    incendies
    .groupby(["LAMBX", "LAMBY", "ANNEE", "MOIS", "JOUR"])
    .agg(NB_INCENDIES=("Numéro", "count"),
         SURFACE_TOTALE_M2=("Surface parcourue (m2)", "sum"))
    .reset_index()
)
label["INCENDIE"] = 1

label.to_parquet(FICHIER_SORTIE, index=False)

nb_mailles = meteo[["LAMBX", "LAMBY"]].drop_duplicates().shape[0]
nb_jours = (incendies["ANNEE"].max() - incendies["ANNEE"].min() + 1) * 365

print(f"\n{len(label)} lignes (maille x jour avec incendie) ecrites dans {FICHIER_SORTIE}")
print(f"Pour comparaison, ta table meteo complete couvre environ "
      f"{nb_mailles} mailles x {nb_jours} jours -- le taux de positifs "
      f"attendu apres fusion est donc tres faible (<0.1%).")