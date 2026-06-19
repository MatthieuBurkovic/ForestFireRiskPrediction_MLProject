# ForestFireRiskPrediction_MLProject

where to download all the datasets:

weather dataset : https://meteo.data.gouv.fr/datasets/donnees-changement-climatique-sim-quotidienne/
(need to download 2 datasets to get the data from 2015 to 2024)

forests : https://inventaire-forestier.ign.fr/dataifn/

forest fires : https://bdiff.agriculture.gouv.fr/incendies (select the correct time period before downloading)

french towns : https://www.data.gouv.fr/datasets/communes-et-villes-de-france-en-csv-excel-json-parquet-et-feather (needed because the forest fires are linked to a town and not geographic coordinates)

Order in which to run the python files to get the final dataset: 

fork.py
clean.py
add_ign.py
enrich_fires.py
add_fires.py
fusion.py