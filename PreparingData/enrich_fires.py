import pandas as pd
from pathlib import Path


def main() -> None:
    base_dir = Path.cwd()
    communes_path = base_dir / "communes-france-2026.parquet"
    incendies_path = base_dir / "Incendies.csv"

    communes_df = pd.read_parquet(communes_path)
    incendies_df = pd.read_csv(incendies_path, sep=";", encoding="utf-8", skiprows=3)

    print("communes_df:", communes_df.shape)
    print("incendies_df:", incendies_df.shape)
    print("\ncommunes_df head:")
    print(communes_df.head())
    print("\nincendies_df head:")
    print(incendies_df.head())

    communes_coords = communes_df[["code_insee", "latitude_centre", "longitude_centre"]].copy()
    communes_coords["code_insee"] = communes_coords["code_insee"].astype(str).str.strip()
    incendies_df["Code INSEE"] = incendies_df["Code INSEE"].astype(str).str.strip()

    incendies_df = incendies_df.merge(
        communes_coords,
        left_on="Code INSEE",
        right_on="code_insee",
        how="left",
    ).drop(columns=["code_insee"])

    print("\nincendies_df enrichie:", incendies_df.shape)
    missing_coords = incendies_df[["latitude_centre", "longitude_centre"]].isna().any(axis=1).sum()
    print("lignes avec coordonnées manquantes:", missing_coords)
    print("\nApercu des coordonnées enrichies:")
    print(incendies_df[["Code INSEE", "latitude_centre", "longitude_centre"]].head())

    export_path = base_dir / "Incendies_enrichie.csv"
    incendies_df.to_csv(export_path, index=False, sep=";", encoding="utf-8-sig")
    print(f"\nTable incendie exportee vers: {export_path}")


if __name__ == "__main__":
    main()
