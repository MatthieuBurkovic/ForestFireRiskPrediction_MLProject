"""
Filtre et fusionne les fichiers SIM quotidien (Meteo-France SAFRAN-ISBA)
pour ne garder que la periode du 1er janvier 2015 au 31 decembre 2024.

Pre-requis :
    pip install duckdb --break-system-packages
    (ou simplement : pip install duckdb, selon ton environnement)

Usage :
    Place ce script dans le meme dossier que tes deux fichiers CSV,
    puis lance :  python filtrer_sim_dates.py
"""

import duckdb
import os

DATE_DEBUT = "20150101"
DATE_FIN = "20241231"

FICHIER_1 = "QUOT_SIM2_2010-2019.csv"
FICHIER_2 = "QUOT_SIM2_previous-2020-202605.csv"
FICHIER_SORTIE = "QUOT_SIM2_2015_2024.csv"

for f in (FICHIER_1, FICHIER_2):
    if not os.path.exists(f):
        raise FileNotFoundError(
            f"Fichier introuvable : {f}\n"
            "Verifie que le script est bien dans le meme dossier que les CSV, "
            "ou modifie les chemins FICHIER_1 / FICHIER_2 ci-dessus."
        )

con = duckdb.connect()

requete = f"""
COPY (
    SELECT *
    FROM read_csv_auto('{FICHIER_1}', delim=';')
    WHERE DATE BETWEEN {DATE_DEBUT} AND {DATE_FIN}

    UNION ALL

    SELECT *
    FROM read_csv_auto('{FICHIER_2}', delim=';')
    WHERE DATE BETWEEN {DATE_DEBUT} AND {DATE_FIN}
) TO '{FICHIER_SORTIE}' (HEADER, DELIMITER ';')
"""

print("Filtrage en cours (peut prendre une a deux minutes)...")
con.execute(requete)



# Petit recap du resultat
nb_lignes = con.execute(
    f"SELECT COUNT(*) FROM read_csv_auto('{FICHIER_SORTIE}')"
).fetchone()[0]

print(f"Termine : {nb_lignes:,} lignes ecrites dans {FICHIER_SORTIE}")


resultats = con.execute(f"""
    SELECT
        CAST(DATE / 10000 AS INTEGER) AS annee,
        COUNT(*) AS nb_lignes
    FROM read_csv_auto('{FICHIER_SORTIE}', delim=';')
    GROUP BY annee
    ORDER BY annee
""").fetchall()

for annee, nb in resultats:
    print(f"{annee} : {nb:,} lignes")