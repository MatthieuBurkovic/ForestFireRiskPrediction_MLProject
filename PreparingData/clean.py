import duckdb

FICHIER = "QUOT_SIM2_2015_2024.csv"
SORTIE = "SIM_ML.parquet"

con = duckdb.connect()

con.execute(f"""
COPY (

WITH base AS (
    SELECT
        LAMBX,
        LAMBY,
        DATE,

        CAST(DATE/10000 AS INTEGER) AS ANNEE,
        CAST((DATE%10000)/100 AS INTEGER) AS MOIS,
        CAST(DATE%100 AS INTEGER) AS JOUR,

        -- saisonnalité
        CAST(((DATE%10000)/100) AS INTEGER) AS MOIS_NUM,

        T,
        FF,
        HU,
        Q,

        PRELIQ,
        PRENEI,

        ETP,
        EVAP,
        PE,

        SWI,
        SSWI_10J,
        WG_RACINE,

        SSI,

        TINF_H,
        TSUP_H,

        -- jour de l'année approx
        (CAST(DATE/10000 AS INTEGER) * 1000) AS YEAR_KEY

    FROM read_csv_auto('{FICHIER}', delim=';')
),

ordered AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY LAMBX, LAMBY
            ORDER BY DATE
        ) AS rn
    FROM base
),

features AS (
    SELECT
        a.*,

        /* =========================
           PLUIE cumulée
        ========================= */
        SUM(COALESCE(PRELIQ,0)) OVER (
            PARTITION BY LAMBX, LAMBY
            ORDER BY DATE
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS PLUIE_7J,

        SUM(COALESCE(PRELIQ,0)) OVER (
            PARTITION BY LAMBX, LAMBY
            ORDER BY DATE
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ) AS PLUIE_30J,

        /* =========================
           Température
        ========================= */
        AVG(T) OVER (
            PARTITION BY LAMBX, LAMBY
            ORDER BY DATE
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS T_MOY_7J,

        MAX(T) OVER (
            PARTITION BY LAMBX, LAMBY
            ORDER BY DATE
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS T_MAX_7J,

        /* =========================
           Humidité / vent
        ========================= */
        AVG(HU) OVER (
            PARTITION BY LAMBX, LAMBY
            ORDER BY DATE
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS HU_MOY_7J,

        MAX(FF) OVER (
            PARTITION BY LAMBX, LAMBY
            ORDER BY DATE
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS FF_MAX_7J,

        /* =========================
           ETP cumulée
        ========================= */
        SUM(COALESCE(ETP,0)) OVER (
            PARTITION BY LAMBX, LAMBY
            ORDER BY DATE
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS ETP_7J,

        /* =========================
           déficit hydrique
        ========================= */
        SUM(COALESCE(PE,0)) OVER (
            PARTITION BY LAMBX, LAMBY
            ORDER BY DATE
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS BILAN_HYDRO_7J,

        /* =========================
           SWI variation
        ========================= */
        SWI - LAG(SWI, 7) OVER (
            PARTITION BY LAMBX, LAMBY
            ORDER BY DATE
        ) AS SWI_DIFF_7J,

        /* =========================
           jours sans pluie
        ========================= */
        SUM(CASE WHEN COALESCE(PRELIQ,0) = 0 THEN 1 ELSE 0 END) OVER (
            PARTITION BY LAMBX, LAMBY
            ORDER BY DATE
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ) AS JOURS_SANS_PLUIE_30J,

        /* =========================
           saisonnalité
        ========================= */
        SIN(2 * PI() * (CAST(DATE % 10000 AS INTEGER) / 100) / 12) AS SIN_SAISON,
        COS(2 * PI() * (CAST(DATE % 10000 AS INTEGER) / 100) / 12) AS COS_SAISON

    FROM base a
)

SELECT *
FROM features

) TO '{SORTIE}' (FORMAT PARQUET);
""")

print("OK - dataset ML prêt :", SORTIE)