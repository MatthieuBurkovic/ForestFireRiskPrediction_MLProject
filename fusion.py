import duckdb
import time

METEO = "SIM_ML.parquet"
VEGETATION = "vegetation_ign_par_maille_annee.parquet"
INCENDIES = "label_incendies_par_maille_jour.parquet"

SORTIE = "dataset_final_incendies.parquet"

con = duckdb.connect()

t0 = time.time()

print("Fusion météo + végétation + incendies...")

con.execute(f"""
COPY (

SELECT

    /* ===========================
       Toutes les variables météo
       =========================== */

    m.*,

    /* ===========================
       Variables végétation
       =========================== */

    v.* EXCLUDE (LAMBX, LAMBY, ANNEE),

    /* ===========================
       Label incendie
       =========================== */

    COALESCE(i.INCENDIE, 0) AS INCENDIE

FROM read_parquet('{METEO}') AS m

LEFT JOIN read_parquet('{VEGETATION}') AS v

ON
    m.LAMBX = v.LAMBX
AND m.LAMBY = v.LAMBY
AND m.ANNEE = v.ANNEE

LEFT JOIN read_parquet('{INCENDIES}') AS i

ON
    m.LAMBX = i.LAMBX
AND m.LAMBY = i.LAMBY
AND m.ANNEE = i.ANNEE
AND m.MOIS = i.MOIS
AND m.JOUR = i.JOUR

) TO '{SORTIE}'
(FORMAT PARQUET);
""")

print(f"Terminé en {time.time()-t0:.1f} s")

nb = con.execute(f"""
SELECT COUNT(*)
FROM read_parquet('{SORTIE}')
""").fetchone()[0]

nb_feux = con.execute(f"""
SELECT COUNT(*)
FROM read_parquet('{SORTIE}')
WHERE INCENDIE=1
""").fetchone()[0]

print(f"Lignes : {nb:,}")
print(f"Incendies : {nb_feux:,}")
print(f"Taux positif : {100*nb_feux/nb:.4f} %")