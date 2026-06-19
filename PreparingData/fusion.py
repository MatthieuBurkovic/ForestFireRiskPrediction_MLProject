import duckdb
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ML_DIR = BASE_DIR.parent / "ML"    

METEO = BASE_DIR / "SIM_ML.parquet"
VEGETATION = BASE_DIR / "vegetation_ign_par_maille_annee.parquet"
INCENDIES = BASE_DIR / "label_incendies_par_maille_jour.parquet"

SORTIE = ML_DIR / "dataset_final_incendies.parquet"

con = duckdb.connect()
t0 = time.time()

print("Fusion météo + végétation + incendies...")

con.execute(f"""
COPY (

SELECT
    m.*,
    v.* EXCLUDE (LAMBX, LAMBY, ANNEE),
    COALESCE(i.INCENDIE, 0) AS INCENDIE

FROM read_parquet('{METEO.as_posix()}') AS m

LEFT JOIN read_parquet('{VEGETATION.as_posix()}') AS v
ON  m.LAMBX = v.LAMBX
AND m.LAMBY = v.LAMBY
AND m.ANNEE = v.ANNEE

LEFT JOIN read_parquet('{INCENDIES.as_posix()}') AS i
ON  m.LAMBX = i.LAMBX
AND m.LAMBY = i.LAMBY
AND m.ANNEE = i.ANNEE
AND m.MOIS = i.MOIS
AND m.JOUR = i.JOUR

) TO '{SORTIE.as_posix()}'
(FORMAT PARQUET);
""")

print(f"Terminé en {time.time()-t0:.1f} s")

nb = con.execute(f"SELECT COUNT(*) FROM read_parquet('{SORTIE.as_posix()}')").fetchone()[0]
nb_feux = con.execute(f"SELECT COUNT(*) FROM read_parquet('{SORTIE.as_posix()}') WHERE INCENDIE=1").fetchone()[0]

print(f"Lignes : {nb:,}")
print(f"Incendies : {nb_feux:,}")
print(f"Taux positif : {100*nb_feux/nb:.4f} %")