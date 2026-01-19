import pandas as pd
from pathlib import Path

src = Path("data/cities15000.txt")
out = Path("data/geo_index.csv")

cols = [
    "geonameid","name","asciiname","alternatenames","lat","lon",
    "feature_class","feature_code","country_code","cc2",
    "admin1","admin2","admin3","admin4","population",
    "elevation","dem","timezone","moddate"
]

df = pd.read_csv(src, sep="\t", names=cols, dtype=str)

df["lat"] = df["lat"].astype(float)
df["lon"] = df["lon"].astype(float)
df["population"] = df["population"].fillna("0").astype(int)

# expand alternates
alt = df[["name","alternatenames","lat","lon","country_code","population"]].copy()
alt["alternatenames"] = alt["alternatenames"].fillna("")
alt = alt.assign(alias=alt["alternatenames"].str.split(",")).explode("alias")

base = df[["name","lat","lon","country_code","population"]].rename(columns={"name":"alias"})
geo = pd.concat([base, alt[["alias","lat","lon","country_code","population"]]])

geo = geo.drop_duplicates(subset=["alias"])
geo = geo.sort_values("population", ascending=False)

geo.to_csv(out, index=False)

print(f"Geo index saved → {out} ({len(geo)} rows)")
