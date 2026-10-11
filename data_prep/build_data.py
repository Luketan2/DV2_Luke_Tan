"""
Builds the small, web-ready data files in ../data from the raw ABS / ASIC downloads in ../raw.

Sources (all downloaded Oct 2026):
  ABS 8165.0 Counts of Australian Businesses, incl. Entries and Exits
     - Jul 2022 - Jun 2026 release (18 Aug 2026), data cube 1        -> raw/cabee_2026_DC01.xlsx
     - Jul 2021 - Jun 2025 release (16 Dec 2025), data cube 8 (SA2)  -> raw/c2025/8165DC08.xlsx
     - Jul 2018 - Jun 2022 release, data cube 1                      -> raw/c2022/816501.xlsx
     - Jul 2020 - Jun 2024 release, quarterly time series            -> raw/c2024/8165TS13.xlsx
  ABS 3218.0 Regional population 2024-25 (SA2 ERP)                   -> raw/pop/rp_ds1.xlsx
  ABS 3101.0 National, state and territory population, Mar 2026      -> raw/pop/310104.xlsx
  ABS ASGS Edition 3 (2021) SA4 + STE boundaries, GDA2020            -> raw/geo/
  ASIC Insolvency statistics Series 1 & 2 (published 6 Oct 2026)     -> raw/asic/asic_s1s2_oct2026.xlsx
  ASIC Insolvency statistics Series 1 archive (Jan 1999 - Jul 2022)  -> raw/asic/asic_s1_2022.xlsx

Run:  python -I data_prep/build_data.py   (from the project root)
"""
import json
import re
from pathlib import Path

import geopandas as gpd
import numpy as np
import openpyxl
import pandas as pd
from shapely.geometry import mapping
from shapely.geometry.polygon import orient
from shapely.geometry import MultiPolygon, Polygon

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
OUT = ROOT / "data"
OUT.mkdir(exist_ok=True)

STATES = ["New South Wales", "Victoria", "Queensland", "South Australia", "Western Australia",
          "Tasmania", "Northern Territory", "Australian Capital Territory"]
STATE_ABBR = dict(zip(STATES, ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"]))

# Short, plain-English industry names for an everyday audience
IND_SHORT = {
    "Agriculture, Forestry and Fishing": "Agriculture",
    "Mining": "Mining",
    "Manufacturing": "Manufacturing",
    "Electricity, Gas, Water and Waste Services": "Utilities",
    "Construction": "Construction",
    "Wholesale Trade": "Wholesale",
    "Retail Trade": "Retail",
    "Accommodation and Food Services": "Hospitality",
    "Transport, Postal and Warehousing": "Transport & delivery",
    "Information Media and Telecommunications": "Media & telco",
    "Financial and Insurance Services": "Finance & insurance",
    "Rental, Hiring and Real Estate Services": "Real estate & rental",
    "Professional, Scientific and Technical Services": "Professional services",
    "Administrative and Support Services": "Admin & support",
    "Public Administration and Safety": "Public admin",
    "Education and Training": "Education",
    "Health Care and Social Assistance": "Health care",
    "Arts and Recreation Services": "Arts & recreation",
    "Other Services": "Other services",
}
SIZE_ORDER = ["Non-employing", "1-4", "5-19", "20-199", "200+"]


def clean(s):
    return re.sub(r"\s+", " ", str(s).replace("–", "-").replace(" ", " ")).strip() if s is not None else ""


def first_text(r):
    return next((clean(c) for c in r if isinstance(c, str) and c.strip()), "")


def rows(path, sheet, data_only=False):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=data_only)
    out = [list(r) for r in wb[sheet].iter_rows(values_only=True)]
    wb.close()
    return out


# ---------------------------------------------------------------- CABEE flow tables
FLOW_COLS = {
    "operating at start": "start", "entries - births": "births", "entries - other": "entries_other",
    "entries - total": "entries", "exits - cancellations": "cancellations", "exits - other": "exits_other",
    "exits - total": "exits", "net movement": "net_movement", "operating at end": "end",
}


def parse_flow_table(path, sheet):
    """Parse a CABEE 'Operating at start ... Operating at end' table into long records."""
    rs = rows(path, sheet)
    hdr_i = next(i for i, r in enumerate(rs) if any("Operating at start" in clean(c) for c in r if c))
    hdr = [clean(c).lower() for c in rs[hdr_i]]
    colmap = {}
    for j, h in enumerate(hdr):
        for key, name in FLOW_COLS.items():
            if h.startswith(key) and name not in colmap.values():
                colmap[j] = name
    recs, fy = [], None
    for r in rs[hdr_i + 2:]:
        lab = clean(r[0])
        if re.fullmatch(r"\d{4}-\d{2}", lab):
            fy = lab
            continue
        if not lab or fy is None or not isinstance(r[1], (int, float)):
            continue
        rec = {"fy": fy, "label": lab.replace("Non-employing", "Non-employing")}
        for j, name in colmap.items():
            rec[name] = r[j]
        recs.append(rec)
    return pd.DataFrame(recs)


def fy_end_year(fy):
    return int(fy[:4]) + 1


def build_flows():
    old, new = RAW / "c2022" / "816501.xlsx", RAW / "cabee_2026_DC01.xlsx"
    out = {}
    for key, (s_old, s_new) in {"industry": ("Table_1", "Table 1"),
                                 "state": ("Table_4", "Table 4"),
                                 "size": ("Table_13a", "Table 13")}.items():
        df = pd.concat([parse_flow_table(old, s_old), parse_flow_table(new, s_new)], ignore_index=True)
        df["label"] = df["label"].str.replace("Non employing", "Non-employing")
        df["year"] = df["fy"].map(fy_end_year)
        df["net"] = df["end"] - df["start"]
        df["growth_pct"] = (df["net"] / df["start"] * 100).round(2)
        df["entry_rate"] = (df["entries"] / df["start"] * 100).round(2)
        df["exit_rate"] = (df["exits"] / df["start"] * 100).round(2)
        out[key] = df
    return out


# ---------------------------------------------------------------- population
def state_erp_june():
    """June ERP (persons) per state per year, plus the latest quarter as a stand-in for June 2026."""
    rs = rows(RAW / "pop" / "310104.xlsx", "Data1")
    names = [clean(c) for c in rs[0]]
    cols = {}
    for j, n in enumerate(names):
        m = re.match(r"Estimated Resident Population ; Persons ; (.+?) ;", n)
        if m:
            cols[j] = m.group(1)
    recs = []
    for r in rs[10:]:
        if not hasattr(r[0], "year"):
            continue
        for j, st in cols.items():
            recs.append({"date": r[0], "state": st, "erp": r[j]})
    df = pd.DataFrame(recs)
    df["year"] = df["date"].dt.year
    june = df[df["date"].dt.month == 6].copy()
    latest = df[df["date"] == df["date"].max()].copy()
    if latest["date"].iloc[0].month != 6:  # use latest quarter for the newest (incomplete) year
        latest["year"] = latest["date"].dt.year
        june = pd.concat([june, latest[~latest["year"].isin(june["year"])]])
    return june[["year", "state", "erp"]]


def sa2_erp():
    recs = []
    for t in range(1, 10):
        rs = rows(RAW / "pop" / "rp_ds1.xlsx", f"Table {t}")
        for r in rs:
            if isinstance(r[6], (int, float)) or (isinstance(r[6], str) and r[6].isdigit() and len(r[6]) == 9):
                if isinstance(r[8], (int, float)) and isinstance(r[9], (int, float)):
                    recs.append({"sa2": str(int(r[6])), "sa4": str(int(r[2])), "sa4_name": clean(r[3]),
                                 "erp2024": r[8], "erp2025": r[9], "area_km2": r[15]})
    return pd.DataFrame(recs)


# ---------------------------------------------------------------- SA2 -> SA4 business counts
def sa2_business(sheet):
    rs = rows(RAW / "c2025" / "8165DC08.xlsx", sheet)
    recs = []
    for r in rs:
        if r[2] is None or not str(r[2]).strip().isdigit() or len(str(r[2]).strip()) != 9:
            continue
        recs.append({"ind_code": r[0], "industry": clean(r[1]), "sa2": str(r[2]).strip(),
                     "nonemp": r[4] or 0, "e1_4": r[5] or 0, "e5_19": r[6] or 0,
                     "e20_199": r[7] or 0, "e200": r[8] or 0, "total": r[9] or 0})
    df = pd.DataFrame(recs)
    df["sa4"] = df["sa2"].str[:3]
    return df


# ---------------------------------------------------------------- geography
def to_d3_winding(geom):
    """d3-geo (used by Vega) wants clockwise exterior rings - the opposite of RFC 7946."""
    if isinstance(geom, Polygon):
        return orient(geom, sign=-1.0)
    if isinstance(geom, MultiPolygon):
        return MultiPolygon([orient(p, sign=-1.0) for p in geom.geoms])
    return geom


def round_coords(obj, nd=3):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(v, nd) for v in obj]
        return [round_coords(o, nd) for o in obj]
    return obj


def write_geojson(gdf, path, props, tol, min_area=0.0):
    feats = []
    for _, row in gdf.iterrows():
        g = row.geometry
        if g is None or g.is_empty:
            continue
        if min_area and isinstance(g, MultiPolygon):  # drop tiny islands to save bytes
            parts = [p for p in g.geoms if p.area >= min_area]
            g = MultiPolygon(parts) if parts else g
        g = to_d3_winding(g.simplify(tol, preserve_topology=True))
        gm = mapping(g)
        feats.append({"type": "Feature", "properties": {k: row[k] for k in props},
                      "geometry": {"type": gm["type"], "coordinates": round_coords(gm["coordinates"])}})
    with open(path, "w") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f, separators=(",", ":"))


def random_points_in(geom, n, rng):
    from shapely.geometry import Point
    from shapely.prepared import prep
    pg = prep(geom)
    minx, miny, maxx, maxy = geom.bounds
    pts = []
    while len(pts) < n:
        xs = rng.uniform(minx, maxx, n * 4)
        ys = rng.uniform(miny, maxy, n * 4)
        for x, y in zip(xs, ys):
            if pg.contains(Point(x, y)):
                pts.append((x, y))
                if len(pts) == n:
                    break
    return pts


# ---------------------------------------------------------------- ASIC
def asic_new_fy_totals(sheet, first_col_name):
    """FY totals per column from the 2026 ASIC pivot sheets (1.2 = industry, 1.3 = state)."""
    rs = rows(RAW / "asic" / "asic_s1s2_oct2026.xlsx", sheet, data_only=True)
    hdr_i = max(i for i, r in enumerate(rs) if any(clean(c) == first_col_name for c in r))
    hdr = [clean(c) for c in rs[hdr_i]]
    recs = []
    for r in rs[hdr_i + 1:]:
        lab = first_text(r)
        m = re.fullmatch(r"(\d{4})-(\d{4}) Total", lab)
        if not m:
            continue
        for j, h in enumerate(hdr):
            if h and j > 0 and isinstance(r[j], (int, float)):
                recs.append({"year": int(m.group(2)), "col": h, "n": r[j]})
    return pd.DataFrame(recs)


def asic_monthly():
    rs = rows(RAW / "asic" / "asic_s1s2_oct2026.xlsx", "1", data_only=True)
    hdr_i = next(i for i, r in enumerate(rs) if first_text(r) == "Month")
    hdr = [clean(c) for c in rs[hdr_i]]
    fy_cols = {j: int("20" + h[2:]) for j, h in enumerate(hdr) if re.fullmatch(r"FY\d\d", h)}
    months = ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun"]
    recs = []
    for r in rs[hdr_i + 2: hdr_i + 14]:
        mon = first_text(r)
        if mon not in months:
            continue
        i = months.index(mon)
        cal_month = i + 7 if i < 6 else i - 5
        for j, fy in fy_cols.items():
            if isinstance(r[j], (int, float)):
                cal_year = fy - 1 if i < 6 else fy
                recs.append({"fy": f"{fy-1}-{str(fy)[2:]}", "fy_end": fy, "month": mon, "month_idx": i,
                             "date": f"{cal_year}-{cal_month:02d}-01", "n": r[j]})
    return pd.DataFrame(recs)


def asic_old_state_annual():
    rs = rows(RAW / "asic" / "asic_s1_2022.xlsx", "1.1", data_only=True)
    hdr_i = next(i for i, r in enumerate(rs) if first_text(r) == "Period")
    hdr = [clean(c) for c in rs[hdr_i]]
    recs = []
    for r in rs[hdr_i + 1:]:
        lab = first_text(r)
        if lab.startswith("QUARTERLY"):
            break
        m = re.fullmatch(r"(\d{4})-(\d{4})", lab)
        if m:
            for j, h in enumerate(hdr):
                if j > 0 and h:
                    recs.append({"year": int(m.group(2)), "col": h, "n": r[j]})
    return pd.DataFrame(recs)


# ================================================================= main
def main():
    flows = build_flows()

    # ---- 1. national quarterly (2013-2025)
    rs = rows(RAW / "c2024" / "8165TS13.xlsx", "Data1")
    q = []
    for r in rs[10:]:
        if hasattr(r[0], "year"):
            # ABS labels the quarter by its middle month; shift to quarter end
            d = (pd.Timestamp(r[0]) + pd.offsets.MonthEnd(2)).strftime("%Y-%m-%d")
            q.append({"date": d, "exits": r[1], "entries": r[2], "total": r[3],
                      "exits_sa": r[4], "entries_sa": r[5], "total_sa": r[6]})
    pd.DataFrame(q).to_csv(OUT / "national_quarterly.csv", index=False)

    # ---- 2. industry annual flows
    ind = flows["industry"]
    ind = ind[ind["label"].isin(IND_SHORT)].copy()
    ind["industry"] = ind["label"].map(IND_SHORT)
    keep = ["fy", "year", "industry", "start", "entries", "exits", "end", "net", "growth_pct",
            "entry_rate", "exit_rate", "births", "cancellations"]
    ind[keep].to_csv(OUT / "industry_annual.csv", index=False)

    # national totals by year (for the waterfall + hero numbers)
    nat = flows["industry"][flows["industry"]["label"] == "All Industries"].copy()
    nat[["fy", "year", "start", "births", "entries_other", "entries", "cancellations", "exits_other", "exits",
         "end", "net", "growth_pct", "entry_rate", "exit_rate"]].to_csv(OUT / "national_annual.csv", index=False)

    # ---- 3. state annual flows + per-capita
    st = flows["state"]
    st = st[st["label"].isin(STATES)].copy()
    st["state"] = st["label"]
    st["abbr"] = st["state"].map(STATE_ABBR)
    erp = state_erp_june()
    st = st.merge(erp, on=["year", "state"], how="left")
    st["per_1000"] = (st["end"] / st["erp"] * 1000).round(1)
    st[["fy", "year", "state", "abbr", "start", "entries", "exits", "end", "net", "growth_pct",
        "entry_rate", "exit_rate", "erp", "per_1000"]].to_csv(OUT / "state_annual.csv", index=False)

    # ---- 4. business size annual flows
    sz = flows["size"]
    sz["size"] = sz["label"].replace({"Non-employing": "Non-employing"})
    sz = sz[sz["size"].isin(SIZE_ORDER)]
    sz[["fy", "year", "size", "start", "entries", "exits", "end", "net", "growth_pct", "entry_rate",
        "exit_rate"]].to_csv(OUT / "size_annual.csv", index=False)

    # ---- 5. size transitions (June 2025 -> June 2026), latest block of Table 14
    rs = rows(RAW / "cabee_2026_DC01.xlsx", "Table 14")
    starts = [i for i, r in enumerate(rs) if "CHANGED BUSINESS SIZE CATEGORY AT JUNE" in clean(r[0]).upper()]
    blk = rs[starts[-1]:]
    to_sizes = SIZE_ORDER
    recs = []
    for r in blk:
        lab = clean(r[0]).replace("Non- employing", "Non-employing")
        if lab in SIZE_ORDER:
            for k, ts in enumerate(to_sizes):
                recs.append({"from": lab, "to": ts, "n": r[1 + k]})
    pd.DataFrame(recs).to_csv(OUT / "size_transitions.csv", index=False)

    # ---- 6. survival: businesses operating June 2022, and new entries in 2022-23
    def survival(sheet, base_label):
        rs = rows(RAW / "cabee_2026_DC01.xlsx", sheet)
        hdr_i = next(i for i, r in enumerate(rs) if any(base_label in clean(c) for c in r if c))
        hdr = [clean(c) for c in rs[hdr_i]]
        years = [(j, int(re.search(r"(\d{4})", h).group(1))) for j, h in enumerate(hdr) if h.startswith("Survived to June")]
        base_year = int(re.search(r"(\d{4})", hdr[1]).group(1))
        if hdr[1].startswith("Entries in"):  # a 2022-23 entry is counted from June 2023
            base_year += 1
        out = []
        for r in rs[hdr_i + 2:]:
            lab = clean(r[0])
            if lab in IND_SHORT or lab == "All Industries":
                name = IND_SHORT.get(lab, "All industries")
                out.append({"industry": name, "years": 0, "pct": 100.0, "n": r[1]})
                for j, y in years:
                    out.append({"industry": name, "years": y - base_year, "pct": round(r[j] / r[1] * 100, 1), "n": r[j]})
        return pd.DataFrame(out)

    survival("Table 3", "Entries in").to_csv(OUT / "survival_entries.csv", index=False)
    survival("Table 2", "Operating in June").to_csv(OUT / "survival_all.csv", index=False)

    # ---- 7. SA4 business counts + population
    b25, b23 = sa2_business("Table 1"), sa2_business("Table 3 ")
    pop = sa2_erp()
    pop4 = pop.groupby(["sa4", "sa4_name"], as_index=False)[["erp2025", "area_km2"]].sum()
    s25 = b25.groupby("sa4")[["total", "nonemp", "e1_4", "e5_19", "e20_199", "e200"]].sum()
    s23 = b23.groupby("sa4")[["total"]].sum().rename(columns={"total": "total2023"})
    top = (b25.groupby(["sa4", "industry"])["total"].sum().reset_index()
           .sort_values("total", ascending=False).drop_duplicates("sa4").set_index("sa4"))
    sa4 = pop4.set_index("sa4").join(s25).join(s23)
    sa4["top_industry"] = top["industry"].map(IND_SHORT)
    sa4["top_share"] = (top["total"] / sa4["total"] * 100).round(1)
    sa4["employing"] = sa4[["e1_4", "e5_19", "e20_199", "e200"]].sum(axis=1)
    sa4["per_1000"] = (sa4["total"] / sa4["erp2025"] * 1000).round(1)
    sa4["growth_2y_pct"] = ((sa4["total"] - sa4["total2023"]) / sa4["total2023"] * 100).round(2)
    sa4["growth_2y"] = sa4["total"] - sa4["total2023"]
    sa4["state_code"] = sa4.index.str[0]
    sa4 = sa4[sa4["erp2025"] > 1000].reset_index()

    # SA4 x industry (long) for the interactive map filter
    si = b25.groupby(["sa4", "industry"], as_index=False)["total"].sum()
    si["industry"] = si["industry"].map(IND_SHORT)
    si = si.dropna().merge(sa4[["sa4", "erp2025"]], on="sa4")
    si["per_1000"] = (si["total"] / si["erp2025"] * 1000).round(2)

    # national industry x employment size, June 2025 (summed from SA2) for the Marimekko chart
    isz = b25.groupby("industry")[["nonemp", "e1_4", "e5_19", "e20_199", "e200"]].sum()
    isz.index = isz.index.map(IND_SHORT)
    isz = isz[isz.index.notna()].reset_index().melt(id_vars="industry", var_name="size", value_name="n")
    isz["size"] = isz["size"].map(dict(zip(["nonemp", "e1_4", "e5_19", "e20_199", "e200"], SIZE_ORDER)))
    isz.to_csv(OUT / "industry_size_2025.csv", index=False)

    # ---- 8. geography
    g4 = gpd.read_file(RAW / "geo" / "sa4" / "SA4_2021_AUST_GDA2020.shp")
    g4 = g4[g4.geometry.notna() & g4["SA4_CODE21"].isin(sa4["sa4"])].copy()
    centroids = g4.set_index("SA4_CODE21").geometry.representative_point()
    sa4["lon"] = sa4["sa4"].map(centroids.x).round(3)
    sa4["lat"] = sa4["sa4"].map(centroids.y).round(3)
    gcc = g4.set_index("SA4_CODE21")["GCC_NAME21"]
    sa4["region_type"] = np.where(sa4["sa4"].map(gcc).str.startswith("Greater") | (sa4["state_code"] == "8"),
                                  "Capital city", "Regional")
    sa4["state"] = sa4["sa4"].map(g4.set_index("SA4_CODE21")["STE_NAME21"])
    sa4["gcc"] = sa4["sa4"].map(gcc)
    sa4 = sa4[sa4["sa4"] != "901"]
    sa4.to_csv(OUT / "sa4.csv", index=False)

    # SA4 x industry incl. an "All industries" row per SA4, for the choropleth's industry filter
    allr = sa4[["sa4", "total", "per_1000"]].assign(industry="All industries")
    si2 = pd.concat([allr, si[si["sa4"].isin(sa4["sa4"])][["sa4", "industry", "total", "per_1000"]]])
    si2 = si2.merge(sa4[["sa4", "sa4_name", "state", "gcc"]], on="sa4")
    si2.to_csv(OUT / "sa4_industry.csv", index=False)

    g4 = g4[g4["SA4_CODE21"].isin(sa4["sa4"])].copy()
    g4["sa4"] = g4["SA4_CODE21"].astype(int)
    g4["name"] = g4["SA4_NAME21"]
    g4["gcc"] = g4["GCC_NAME21"]
    write_geojson(g4, OUT / "sa4.geojson", ["sa4", "name", "gcc"], tol=0.012, min_area=0.002)

    ge = gpd.read_file(RAW / "geo" / "ste" / "STE_2021_AUST_GDA2020.shp")
    ge = ge[ge.geometry.notna() & ge["STE_NAME21"].isin(STATES)].copy()
    ge["state"] = ge["STE_NAME21"]
    ge["abbr"] = ge["state"].map(STATE_ABBR)
    write_geojson(ge, OUT / "states.geojson", ["state", "abbr"], tol=0.03, min_area=0.01)

    # ---- 9. dot-density: one dot = 1,000 businesses, coloured by employing / non-employing
    rng = np.random.default_rng(3179)
    geo_idx = g4.set_index("SA4_CODE21").geometry
    dots = []
    for _, r in sa4.iterrows():
        for kind, col in (("Non-employing", "nonemp"), ("Employing", "employing")):
            n = int(round(r[col] / 1000))
            for x, y in random_points_in(geo_idx[r["sa4"]], n, rng) if n else []:
                dots.append({"lon": round(x, 3), "lat": round(y, 3), "type": kind})
    pd.DataFrame(dots).to_csv(OUT / "dots.csv", index=False)

    # ---- 10. ASIC insolvencies
    old = asic_old_state_annual()
    old["col"] = old["col"].str.replace("South Australia", "South Australia")
    new_state = asic_new_fy_totals("1.3", "New South Wales")
    new_state = new_state[new_state["col"].isin(STATES + ["Total"])]
    new_state["col"] = new_state["col"].replace({"Total": "Australia"})
    old = old[old["year"] < 2022]
    ins_state = pd.concat([old, new_state], ignore_index=True)
    ins_state = ins_state[ins_state["col"].isin(STATES + ["Australia"])]
    ins_state = ins_state.rename(columns={"col": "state"})
    ins_state["fy"] = (ins_state["year"] - 1).astype(str) + "-" + ins_state["year"].astype(str).str[2:]
    ins_state["partial"] = ins_state["year"] > 2026
    ins_state["abbr"] = ins_state["state"].map(STATE_ABBR).fillna("AUS")
    ins_state = ins_state[~ins_state["partial"]]
    # insolvency rate per 10,000 businesses (CABEE end-of-year count)
    st_end = st[["year", "state", "end"]]
    nat_end = nat[["year", "end"]].assign(state="Australia")
    ins_state = ins_state.merge(pd.concat([st_end, nat_end]), on=["year", "state"], how="left")
    ins_state["per_10k"] = (ins_state["n"] / ins_state["end"] * 10000).round(2)
    ins_state[["fy", "year", "state", "abbr", "n", "end", "per_10k"]].to_csv(OUT / "insolvency_state_annual.csv", index=False)

    new_ind = asic_new_fy_totals("1.2", "Accommodation and Food Services")
    new_ind = new_ind[new_ind["col"].isin(IND_SHORT) & (new_ind["year"] <= 2026)]
    new_ind["industry"] = new_ind["col"].map(IND_SHORT)
    new_ind = new_ind.merge(ind[["year", "industry", "end"]], on=["year", "industry"], how="left")
    new_ind["per_10k"] = (new_ind["n"] / new_ind["end"] * 10000).round(2)
    new_ind[["year", "industry", "n", "end", "per_10k"]].to_csv(OUT / "insolvency_industry_annual.csv", index=False)

    asic_monthly().to_csv(OUT / "insolvency_monthly.csv", index=False)

    # ---- 11. waffle: 1,000 squares for June 2026 by employment size (largest-remainder rounding)
    w = sz[sz["year"] == 2026].set_index("size").loc[SIZE_ORDER, "end"]
    exact = w / w.sum() * 1000
    cnt = np.floor(exact).astype(int)
    for k in (exact - cnt).sort_values(ascending=False).index[: 1000 - cnt.sum()]:
        cnt[k] += 1
    cells, i = [], 0
    for size, n in cnt.items():
        for _ in range(n):
            cells.append({"i": i, "col": i % 40, "row": i // 40, "size": size,
                          "size_n": int(w[size]), "size_pct": round(w[size] / w.sum() * 100, 2)})
            i += 1
    pd.DataFrame(cells).to_csv(OUT / "waffle.csv", index=False)

    # ---- 12. share of businesses vs share of insolvencies, FY2025-26
    sh = new_ind[new_ind["year"] == 2026].copy()
    sh["share_insolv"] = (sh["n"] / sh["n"].sum() * 100).round(2)
    sh["share_bus"] = (sh["end"] / sh["end"].sum() * 100).round(2)
    sh[["industry", "n", "end", "share_insolv", "share_bus", "per_10k"]].to_csv(OUT / "insolvency_share_2026.csv", index=False)

    # ---- size summary
    for p in sorted(OUT.iterdir()):
        print(f"{p.name:34s} {p.stat().st_size/1024:8.1f} KB")


if __name__ == "__main__":
    main()
