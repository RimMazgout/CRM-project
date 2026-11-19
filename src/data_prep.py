"""Etape 1 : chargement, nettoyage et bilan qualite d'Online Retail II.

Source : Chen, D. (2012). Online Retail II. UCI Machine Learning Repository.
https://doi.org/10.24432/C5CG6D  (licence CC BY 4.0)

Usage (depuis la racine du depot) :
    python src/data_prep.py                        # verifie la source, nettoie, ecrit le rapport
    python src/data_prep.py --force                # relit l'Excel meme si le cache parquet est valide
    python src/data_prep.py --refresh-source       # retelecharge le zip depuis UCI
    python src/data_prep.py --accept-source-change # accepte un zip dont l'empreinte differe de la valeur epinglee
    python src/data_prep.py --verify               # controle les empreintes sans rien reconstruire

Sorties (data/ est ignore par git, reports/ est versionne) :
    data/raw/online_retail_ii.zip, data/raw/online_retail_II.xlsx
    data/interim/raw.parquet + manifest.json   cache brut et ses empreintes
    data/processed/purchases.parquet           achats nettoyes (clients identifies)
    data/processed/returns.parquet             retours (clients identifies)
    reports/data_quality_report.json|md        bilan qualite chiffre

Chaine de coherence : zip (SHA-256 compare a la valeur epinglee) -> xlsx (SHA-256 egal a
celui du fichier dans le zip) -> raw.parquet (valide seulement si le manifeste porte les
memes empreintes de zip et de xlsx, le meme numero de schema et le meme SHA-256 du parquet)
-> tables nettoyees. Si un maillon ne correspond pas, le cache est reconstruit ; si le zip
lui-meme a change, le script s'arrete sauf avec --accept-source-change.

Choix de traitement (voir docs/etape1_donnees.md) :
  * Les retours (factures "C...") ne sont PAS deduits des achats. Ils sont ecrits
    dans une table separee. Le montant des achats s'appelle donc `montant_brut_gbp`
    (Quantity * Price, hors retours) et jamais "net".
  * Aucune variable n'est calculee ici : pas de RFM, pas de churn, donc aucune
    notion de date de coupure. Le filtrage temporel est fait a l'etape suivante.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
INTERIM_DIR = ROOT / "data" / "interim"
PROCESSED_DIR = ROOT / "data" / "processed"
REPORTS_DIR = ROOT / "reports"

DATA_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
ZIP_PATH = RAW_DIR / "online_retail_ii.zip"
XLSX_PATH = RAW_DIR / "online_retail_II.xlsx"
RAW_CACHE = INTERIM_DIR / "raw.parquet"
MANIFEST = INTERIM_DIR / "manifest.json"
PURCHASES_PATH = PROCESSED_DIR / "purchases.parquet"
RETURNS_PATH = PROCESSED_DIR / "returns.parquet"
REPORT_JSON = REPORTS_DIR / "data_quality_report.json"
REPORT_MD = REPORTS_DIR / "data_quality_report.md"

# Empreinte du zip observee au premier telechargement. UCI ne publie pas de checksum :
# elle sert seulement a detecter un changement du fichier source.
PINNED_ZIP_SHA256 = "572E36277C2390FBFDE10664750731E0A86F55E33470D91919085F0408E67BFB"
# A incrementer si le contenu ou le format de raw.parquet change (invalide les anciens caches).
CACHE_SCHEMA_VERSION = 2

COLUMNS = ["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Customer ID", "Country"]
KEY_COLS = COLUMNS  # une ligne est un doublon exact si les 8 colonnes sont egales

# --------------------------------------------------------------------------- #
# Regle produit / non produit
# --------------------------------------------------------------------------- #
# Regle documentee : un code est un frais ou un ajustement s'il figure dans cette liste
# ou correspond au motif ci-dessous (casse ignoree). Tout autre code est un produit.
# La liste vient de l'examen des 61 codes qui ne commencent pas par 5 chiffres et d'une
# recherche de mots-cles (carriage, postage, fee, adjust, ...) dans les codes numeriques.
NON_PRODUCT_EXACT = {
    "POST": "frais de port",
    "DOT": "frais de port (Dotcom)",
    "C2": "transport (carriage)",
    "C3": "ajustement sans description",
    "23444": "transport 'Next Day Carriage' (code numerique)",
    "M": "saisie manuelle (Manual)",
    "B": "ajustement de creance (bad debt)",
    "D": "remise (Discount)",
    "S": "echantillons (Samples)",
    "GIFT": "ligne d'ajustement, quantite negative, sans description",
    "CRUK": "frais associatifs (CRUK Commission)",
    "BANK CHARGES": "frais bancaires",
    "AMAZONFEE": "frais Amazon",
}
# ADJUST, ADJUST2 : ajustements ; TEST001, TEST002 : produits de test ;
# gift_0001_NN : bons cadeaux (instrument de paiement, pas un article).
NON_PRODUCT_PATTERN = r"^(ADJUST\d*|TEST\d+|GIFT_\d{4}_\d+)$"
# Codes non numeriques gardes comme produits : DCGS* (articles du site Dotcomgiftshop),
# SP1002 (chevalet), PADS (coussins, prix symbolique de 0,001 GBP).


def non_product_mask(codes: pd.Series, rule: str = "documented") -> pd.Series:
    """True pour les lignes qui ne sont pas des produits.

    rule="documented" : liste explicite + motifs (regle retenue).
    rule="legacy"     : regle de la premiere version, code ne commencant pas par 5 chiffres.
                        Conservee uniquement pour mesurer l'effet du changement.
    """
    if rule == "legacy":
        return ~codes.str.match(r"^\d{5}", na=False)
    up = codes.str.strip().str.upper()
    return up.isin(NON_PRODUCT_EXACT) | up.str.match(NON_PRODUCT_PATTERN, na=False)


# --------------------------------------------------------------------------- #
# Empreintes et manifeste
# --------------------------------------------------------------------------- #
def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def sha256_of_stream(stream) -> str:
    h = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1 << 20), b""):
        h.update(chunk)
    return h.hexdigest().upper()


def read_manifest() -> dict | None:
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


# --------------------------------------------------------------------------- #
# Source : zip -> xlsx
# --------------------------------------------------------------------------- #
def ensure_source(refresh: bool = False, accept_change: bool = False) -> dict:
    """Garantit un zip et un xlsx coherents. Renvoie les informations de provenance.

    - zip absent (ou --refresh-source) : telechargement vers un fichier temporaire.
    - empreinte du zip differente de la valeur epinglee : arret, sauf accept_change.
    - xlsx absent ou different du fichier contenu dans le zip : extrait a nouveau.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if refresh or not ZIP_PATH.exists():
        print(f"Telechargement : {DATA_URL}")
        tmp = ZIP_PATH.with_name(ZIP_PATH.name + ".part")
        urllib.request.urlretrieve(DATA_URL, tmp)
        os.replace(tmp, ZIP_PATH)

    zip_sha = sha256_of(ZIP_PATH)
    matches = zip_sha == PINNED_ZIP_SHA256
    if not matches and not accept_change:
        raise SystemExit(
            "ARRET : l'empreinte du zip ne correspond pas a la valeur epinglee.\n"
            f"  calculee : {zip_sha}\n  epinglee : {PINNED_ZIP_SHA256}\n"
            "Le fichier source a change ou est corrompu. Aucun cache n'est reutilise.\n"
            "Si le changement est voulu, relancer avec --accept-source-change "
            "(le rapport l'indiquera) et mettre a jour PINNED_ZIP_SHA256."
        )
    if not matches:
        print("ATTENTION : zip different de la valeur epinglee, accepte via --accept-source-change.")

    with zipfile.ZipFile(ZIP_PATH) as z:
        bad = z.testzip()
        if bad:
            raise SystemExit(f"ARRET : zip corrompu (CRC invalide pour {bad}).")
        members = [m for m in z.namelist() if m.lower().endswith(".xlsx")]
        if len(members) != 1:
            raise SystemExit(f"ARRET : le zip doit contenir un seul .xlsx, trouve : {members}")
        member = members[0]
        with z.open(member) as s:
            member_sha = sha256_of_stream(s)
        xlsx_ok = XLSX_PATH.exists() and sha256_of(XLSX_PATH) == member_sha
        if not xlsx_ok:
            print(f"Extraction de {member} (absent ou different du contenu du zip).")
            tmp = XLSX_PATH.with_name(XLSX_PATH.name + ".part")
            with z.open(member) as s, tmp.open("wb") as out:
                for chunk in iter(lambda: s.read(1 << 20), b""):
                    out.write(chunk)
            os.replace(tmp, XLSX_PATH)
        member_bytes = z.getinfo(member).file_size

    xlsx_sha = sha256_of(XLSX_PATH)
    return {
        "url": DATA_URL,
        "zip_bytes": ZIP_PATH.stat().st_size,
        "zip_sha256": zip_sha,
        "zip_sha256_epinglee": PINNED_ZIP_SHA256,
        "zip_conforme_a_la_valeur_epinglee": matches,
        "changement_de_source_accepte": bool(not matches and accept_change),
        "xlsx_dans_zip": member,
        "xlsx_bytes": member_bytes,
        "xlsx_sha256": xlsx_sha,
        "xlsx_identique_au_contenu_du_zip": xlsx_sha == member_sha,
    }


# --------------------------------------------------------------------------- #
# Cache brut
# --------------------------------------------------------------------------- #
def cache_problem(prov: dict) -> str | None:
    """Renvoie la raison pour laquelle le cache brut n'est pas utilisable, ou None s'il l'est."""
    m = read_manifest()
    if not RAW_CACHE.exists():
        return "pas de cache parquet"
    if m is None:
        return "manifeste absent ou illisible"
    if m.get("schema_version") != CACHE_SCHEMA_VERSION:
        return f"version de schema differente ({m.get('schema_version')} != {CACHE_SCHEMA_VERSION})"
    if m.get("zip_sha256") != prov["zip_sha256"]:
        return "le zip source a change depuis la creation du cache"
    if m.get("xlsx_sha256") != prov["xlsx_sha256"]:
        return "le fichier Excel a change depuis la creation du cache"
    if m.get("raw_parquet_sha256") != sha256_of(RAW_CACHE):
        return "le fichier parquet ne correspond plus a son empreinte (modifie ou incomplet)"
    return None


def build_raw_cache(prov: dict) -> pd.DataFrame:
    """Lit les deux feuilles Excel, ajoute `source_sheet`, ecrit le parquet puis le manifeste."""
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.unlink(missing_ok=True)  # un cache en cours de reconstruction n'est jamais declare valide
    print("Lecture du fichier Excel (1 a 3 minutes)...")
    sheets = pd.read_excel(XLSX_PATH, sheet_name=None, engine="openpyxl")
    frames = []
    for name, df in sheets.items():
        missing = set(COLUMNS) - set(df.columns)
        if missing:
            raise ValueError(f"Feuille {name!r} : colonnes absentes {missing}")
        df = df[COLUMNS].copy()
        df["source_sheet"] = name
        frames.append(df)
    raw = pd.concat(frames, ignore_index=True)
    raw["Invoice"] = raw["Invoice"].astype(str)
    raw["StockCode"] = raw["StockCode"].astype(str)
    # Description contient quelques valeurs numeriques : on force le texte (NaN conserves).
    raw["Description"] = raw["Description"].astype("string")

    tmp = RAW_CACHE.with_name(RAW_CACHE.name + ".tmp")
    raw.to_parquet(tmp, index=False)
    os.replace(tmp, RAW_CACHE)
    write_json_atomic(MANIFEST, {  # ecrit en dernier : sa presence valide le cache
        "schema_version": CACHE_SCHEMA_VERSION,
        "zip_sha256": prov["zip_sha256"],
        "xlsx_sha256": prov["xlsx_sha256"],
        "raw_parquet_sha256": sha256_of(RAW_CACHE),
        "raw_rows": int(len(raw)),
    })
    return raw


def load_raw(prov: dict, force: bool = False) -> tuple[pd.DataFrame, str]:
    """Renvoie (donnees brutes, origine). Le cache n'est reutilise que s'il est coherent."""
    problem = "option --force" if force else cache_problem(prov)
    if problem is None:
        raw = pd.read_parquet(RAW_CACHE)
        expected = read_manifest()["raw_rows"]
        if len(raw) == expected:
            return raw, "cache parquet valide reutilise"
        problem = f"nombre de lignes du cache ({len(raw)}) different du manifeste ({expected})"
    print(f"Cache brut non reutilise : {problem}.")
    return build_raw_cache(prov), f"cache reconstruit depuis l'Excel ({problem})"


# --------------------------------------------------------------------------- #
# Nettoyage
# --------------------------------------------------------------------------- #
def clean(raw: pd.DataFrame, drop_within_sheet_duplicates: bool = False, rule: str = "documented"):
    """Renvoie (purchases, returns, steps, meta).

    `steps` liste les etapes sequentielles avec le nombre de lignes retirees.
    Les etapes sont exclusives : une ligne est comptee a la premiere regle qui la retire.
    """
    steps: list[dict] = []
    meta: dict = {}
    df = raw.copy()
    df["montant_brut_gbp"] = df["Quantity"] * df["Price"]

    def log(name: str, removed: int, note: str = "") -> None:
        steps.append({"etape": name, "lignes_retirees": int(removed), "lignes_restantes": int(len(df)), "note": note})

    steps.append({"etape": "lignes brutes", "lignes_retirees": 0, "lignes_restantes": int(len(df)), "note": ""})

    # 1. Chevauchement des deux feuilles (1er au 9 decembre 2010 present dans les deux).
    #    On verifie que les deux copies sont identiques (memes lignes, memes multiplicites),
    #    puis on retire la copie de la feuille la plus recente. Les lignes repetees a
    #    l'interieur d'une feuille ne sont pas touchees ici.
    a = df[df["source_sheet"] == "Year 2009-2010"]
    b = df[df["source_sheet"] == "Year 2010-2011"]
    lo, hi = b["InvoiceDate"].min(), a["InvoiceDate"].max()
    a_ov, b_ov = a[a["InvoiceDate"] >= lo], b[b["InvoiceDate"] <= hi]
    same = a_ov.value_counts(KEY_COLS, dropna=False).sort_index().equals(
        b_ov.value_counts(KEY_COLS, dropna=False).sort_index())
    if not same:
        raise ValueError("Le chevauchement entre feuilles n'est pas une copie identique : verifier le fichier source.")
    n_before = len(df)
    df = df.drop(index=b_ov.index)
    log("chevauchement entre feuilles (copie identique retiree)", n_before - len(df),
        f"{lo:%Y-%m-%d} au {hi:%Y-%m-%d}, copie verifiee identique")

    within = df.duplicated(KEY_COLS, keep="first")
    if drop_within_sheet_duplicates:
        n_before = len(df)
        df = df[~within]
        log("doublons exacts dans une meme feuille", n_before - len(df), "option activee")
    else:
        steps.append({"etape": "doublons exacts dans une meme feuille (CONSERVES)",
                      "lignes_retirees": 0, "lignes_restantes": int(len(df)),
                      "note": f"{int(within.sum())} lignes concernees, a valider"})

    # 2. Retours : factures dont le numero commence par C. Table separee, non deduite.
    is_cancel = df["Invoice"].str.upper().str.startswith("C")
    cancel_all = df[is_cancel]
    df = df[~is_cancel]
    log("annulations / retours (factures C*) mis de cote", len(cancel_all), "ecrits dans returns.parquet, non deduits")

    # 3. Frais et ajustements (voir NON_PRODUCT_EXACT / NON_PRODUCT_PATTERN).
    npm = non_product_mask(df["StockCode"], rule)
    removed = df[npm]
    kept_alpha = df[~npm & ~df["StockCode"].str.match(r"^\d{5}", na=False)]
    meta["codes_exclus"] = _code_table(removed)
    meta["codes_non_numeriques_conserves"] = _code_table(kept_alpha)
    n_before = len(df)
    df = df[~npm]
    note = "frais, ajustements, tests, bons cadeaux" if rule == "documented" else "regle initiale : code sans 5 chiffres en tete"
    log("lignes non produit (regle " + rule + ")", n_before - len(df), note)

    # 4. Quantite ou prix non positifs dans les factures de vente.
    bad = (df["Quantity"] <= 0) | (df["Price"] <= 0)
    n_before = len(df)
    df = df[~bad]
    log("quantite <= 0 ou prix <= 0", n_before - len(df), "ajustements de stock, dettes, prix a 0")

    # 5. Identifiant client absent : conserve pour les statistiques globales,
    #    retire des tables clients.
    meta["lignes_avant_filtre_customer_id"] = int(len(df))
    meta["montant_brut_avant_filtre_customer_id_gbp"] = round(float(df["montant_brut_gbp"].sum()), 2)
    no_id = df["Customer ID"].isna()
    n_before = len(df)
    n_missing_revenue = float(df.loc[no_id, "montant_brut_gbp"].sum())
    df = df[~no_id].copy()
    log("Customer ID manquant", n_before - len(df), f"{n_missing_revenue:,.0f} GBP de montant brut hors analyse client")

    df["Customer ID"] = df["Customer ID"].astype("int64")
    purchases = df.rename(columns={"Customer ID": "customer_id"}).reset_index(drop=True)

    # Table des retours : meme regle produit et meme exigence d'identifiant client.
    ret = cancel_all[~non_product_mask(cancel_all["StockCode"], rule) & cancel_all["Customer ID"].notna()].copy()
    ret["Customer ID"] = ret["Customer ID"].astype("int64")
    ret = ret.rename(columns={"Customer ID": "customer_id"}).reset_index(drop=True)
    ret["montant_retour_gbp"] = ret["montant_brut_gbp"]  # negatif (Quantity < 0)
    ret = ret.drop(columns=["montant_brut_gbp"])

    return purchases, ret, steps, meta


def _code_table(rows: pd.DataFrame, top: int = 30) -> list[dict]:
    """Resume par StockCode : lignes, lignes avec identifiant client, description la plus frequente."""
    if rows.empty:
        return []
    g = rows.assign(_code=rows["StockCode"].str.strip().str.upper(), _id=rows["Customer ID"].notna())
    out = g.groupby("_code").agg(
        lignes=("Invoice", "size"),
        lignes_avec_customer_id=("_id", "sum"),
        description=("Description", lambda s: (s.dropna().mode().iloc[0] if s.notna().any() else "")),
    ).sort_values("lignes", ascending=False).head(top)
    return [{"code": k, "lignes": int(r.lignes), "lignes_avec_customer_id": int(r.lignes_avec_customer_id),
             "description": str(r.description)[:40]} for k, r in out.iterrows()]


def summarize(purchases: pd.DataFrame, returns: pd.DataFrame, meta: dict) -> dict:
    return {
        "lignes_vente_avant_filtre_customer_id": meta["lignes_avant_filtre_customer_id"],
        "montant_brut_avant_filtre_customer_id_gbp": meta["montant_brut_avant_filtre_customer_id_gbp"],
        "lignes_achat": int(len(purchases)),
        "clients": int(purchases["customer_id"].nunique()),
        "factures": int(purchases["Invoice"].nunique()),
        "montant_brut_gbp": round(float(purchases["montant_brut_gbp"].sum()), 2),
        "lignes_retour": int(len(returns)),
        "clients_avec_retour": int(returns["customer_id"].nunique()),
        "montant_retours_gbp": round(float(returns["montant_retour_gbp"].sum()), 2),
    }


# --------------------------------------------------------------------------- #
# Bilan qualite
# --------------------------------------------------------------------------- #
def quality_report(raw, purchases, returns, steps, meta, provenance, sensitivity) -> dict:
    r: dict = {"provenance": provenance, "nettoyage": steps, **meta, "sensibilite_regle_stockcode": sensitivity}

    r["brut"] = {
        "lignes": int(len(raw)),
        "lignes_par_feuille": raw["source_sheet"].value_counts().to_dict(),
        "periode_par_feuille": {
            s: [str(g["InvoiceDate"].min()), str(g["InvoiceDate"].max())] for s, g in raw.groupby("source_sheet")
        },
        "valeurs_manquantes": raw[COLUMNS].isna().sum().astype(int).to_dict(),
        "part_customer_id_manquant_pct": round(100 * raw["Customer ID"].isna().mean(), 2),
        "annulations_pct_des_lignes": round(100 * raw["Invoice"].str.upper().str.startswith("C").mean(), 2),
        "quantite_negative_hors_annulation": int(
            ((raw["Quantity"] < 0) & ~raw["Invoice"].str.upper().str.startswith("C")).sum()
        ),
        "prix_nul_ou_negatif": int((raw["Price"] <= 0).sum()),
    }

    p = purchases
    inv_per_cust = p.groupby("customer_id")["Invoice"].nunique()
    r["achats_nettoyes"] = {
        "lignes": int(len(p)),
        "clients": int(p["customer_id"].nunique()),
        "factures": int(p["Invoice"].nunique()),
        "periode": [str(p["InvoiceDate"].min()), str(p["InvoiceDate"].max())],
        "montant_brut_total_gbp": round(float(p["montant_brut_gbp"].sum()), 2),
        "montant_brut_note": "Quantity*Price des factures de vente, retours NON deduits",
        "clients_une_seule_facture_pct": round(100 * float((inv_per_cust == 1).mean()), 2),
        "mediane_factures_par_client": float(inv_per_cust.median()),
        "pays_top5_part_lignes_pct": (100 * p["Country"].value_counts(normalize=True).head(5)).round(2).to_dict(),
        "quantite_p99": float(p["Quantity"].quantile(0.99)),
        "quantite_max": float(p["Quantity"].max()),
        "prix_p99": float(p["Price"].quantile(0.99)),
        "prix_max": float(p["Price"].max()),
        "montant_ligne_max_gbp": round(float(p["montant_brut_gbp"].max()), 2),
        "lignes_par_mois": {str(k): int(v) for k, v in p.groupby(p["InvoiceDate"].dt.to_period("M")).size().items()},
    }

    ret_amount = float(returns["montant_retour_gbp"].sum())
    gross = float(p["montant_brut_gbp"].sum())
    r["retours"] = {
        "lignes": int(len(returns)),
        "clients_concernes": int(returns["customer_id"].nunique()),
        "montant_retours_gbp": round(ret_amount, 2),
        "retours_en_pct_du_montant_brut": round(100 * abs(ret_amount) / gross, 2),
        "clients_avec_retour_pct": round(100 * returns["customer_id"].nunique() / p["customer_id"].nunique(), 2),
        "traitement": "table separee, non deduite du montant des achats",
    }

    prov = provenance
    r["controles"] = {
        "zip_conforme_a_la_valeur_epinglee_ou_changement_accepte":
            bool(prov["zip_conforme_a_la_valeur_epinglee"] or prov["changement_de_source_accepte"]),
        "xlsx_identique_au_contenu_du_zip": bool(prov["xlsx_identique_au_contenu_du_zip"]),
        "aucune_annulation_dans_achats": bool(~purchases["Invoice"].str.upper().str.startswith("C").any()),
        "aucun_code_non_produit_dans_achats_ni_retours": bool(
            not non_product_mask(purchases["StockCode"]).any() and not non_product_mask(returns["StockCode"]).any()),
        "quantite_et_prix_positifs": bool(((purchases["Quantity"] > 0) & (purchases["Price"] > 0)).all()),
        "customer_id_sans_nan": bool(purchases["customer_id"].notna().all()),
        "aucun_doublon_inter_feuilles": bool(
            (purchases.groupby(pd.util.hash_pandas_object(
                purchases[["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Country"]],
                index=False))["source_sheet"].nunique() == 1).all()
        ),
        "retours_quantite_negative": bool((returns["Quantity"] < 0).all()),
    }
    return r


def _fmt_summary_row(label: str, key: str, s_old: dict, s_new: dict, money: bool = False) -> str:
    f = (lambda v: f"{v:,.2f}") if money else (lambda v: f"{v:,}")
    return f"| {label} | {f(s_old[key])} | {f(s_new[key])} | {f(round(s_new[key] - s_old[key], 2) if money else s_new[key] - s_old[key])} |"


def render_markdown(r: dict) -> str:
    b, a, ret, pv = r["brut"], r["achats_nettoyes"], r["retours"], r["provenance"]
    sens = r["sensibilite_regle_stockcode"]
    old, new = sens["regle_initiale_5_chiffres"], sens["regle_documentee"]
    L = ["# Bilan qualite des donnees - Online Retail II", "",
         "Genere par `python src/data_prep.py`. Ne pas editer a la main.", "",
         "## Provenance",
         f"- URL : {pv['url']}",
         f"- Zip : {pv['zip_bytes']:,} octets, SHA-256 `{pv['zip_sha256']}`",
         f"- Valeur epinglee dans le script : `{pv['zip_sha256_epinglee']}` ; conforme : {pv['zip_conforme_a_la_valeur_epinglee']} ; changement accepte : {pv['changement_de_source_accepte']}",
         f"- Excel extrait (`{pv['xlsx_dans_zip']}`) : {pv['xlsx_bytes']:,} octets, SHA-256 `{pv['xlsx_sha256']}` ; identique au contenu du zip : {pv['xlsx_identique_au_contenu_du_zip']}",
         "- Le cache parquet n'est reutilise que si le manifeste porte ces deux empreintes (voir `--verify`).",
         "", "## Donnees brutes",
         f"- Lignes : {b['lignes']:,}  ({b['lignes_par_feuille']})",
         f"- Periode par feuille : {b['periode_par_feuille']}",
         f"- Customer ID manquant : {b['part_customer_id_manquant_pct']} % des lignes",
         f"- Annulations (factures C*) : {b['annulations_pct_des_lignes']} % des lignes",
         f"- Quantites negatives hors annulation : {b['quantite_negative_hors_annulation']:,}",
         f"- Prix <= 0 : {b['prix_nul_ou_negatif']:,}",
         f"- Valeurs manquantes par colonne : {b['valeurs_manquantes']}",
         "", "## Etapes de nettoyage", "",
         "| Etape | Lignes retirees | Lignes restantes | Note |", "|---|---:|---:|---|"]
    for s in r["nettoyage"]:
        L.append(f"| {s['etape']} | {s['lignes_retirees']:,} | {s['lignes_restantes']:,} | {s['note']} |")
    L += ["", "## Achats nettoyes",
          f"- Lignes : {a['lignes']:,} ; clients : {a['clients']:,} ; factures : {a['factures']:,}",
          f"- Periode : {a['periode'][0]} -> {a['periode'][1]}",
          f"- Montant brut total : {a['montant_brut_total_gbp']:,.2f} GBP ({a['montant_brut_note']})",
          f"- Clients avec une seule facture : {a['clients_une_seule_facture_pct']} % ; mediane de factures par client : {a['mediane_factures_par_client']}",
          f"- Top 5 pays (part des lignes, %) : {a['pays_top5_part_lignes_pct']}",
          f"- Quantite : p99 = {a['quantite_p99']}, max = {a['quantite_max']}",
          f"- Prix : p99 = {a['prix_p99']}, max = {a['prix_max']} ; montant de ligne max = {a['montant_ligne_max_gbp']:,}",
          "", "## Retours (non deduits)",
          f"- Lignes : {ret['lignes']:,} ; clients concernes : {ret['clients_concernes']:,} ({ret['clients_avec_retour_pct']} % des clients)",
          f"- Montant des retours : {ret['montant_retours_gbp']:,.2f} GBP, soit {ret['retours_en_pct_du_montant_brut']} % du montant brut",
          "", "## Regle produit / non produit",
          "", "Un code est un frais ou un ajustement s'il figure dans la liste explicite (POST, DOT, C2, C3, 23444, M, B, D, S, GIFT, CRUK, BANK CHARGES, AMAZONFEE) "
          "ou correspond aux motifs `ADJUST*`, `TEST<n>`, `gift_0001_<n>` (casse ignoree). Tout autre code est un produit.",
          "", "### Codes retires (factures de vente, avant filtres quantite/prix/client)", "",
          "| Code | Lignes | dont avec Customer ID | Description |", "|---|---:|---:|---|"]
    L += [f"| {c['code']} | {c['lignes']:,} | {c['lignes_avec_customer_id']:,} | {c['description']} |" for c in r["codes_exclus"]]
    L += ["", "### Codes non numeriques conserves comme produits", "",
          "| Code | Lignes | dont avec Customer ID | Description |", "|---|---:|---:|---|"]
    L += [f"| {c['code']} | {c['lignes']:,} | {c['lignes_avec_customer_id']:,} | {c['description']} |"
          for c in r["codes_non_numeriques_conserves"]]
    L += ["", "### Effet du changement de regle", "",
          "Regle initiale = code ne commencant pas par 5 chiffres. Regle documentee = liste ci-dessus.", "",
          "| Mesure | Regle initiale | Regle documentee | Ecart |", "|---|---:|---:|---:|",
          _fmt_summary_row("Lignes de vente avant filtre Customer ID", "lignes_vente_avant_filtre_customer_id", old, new),
          _fmt_summary_row("Montant brut avant filtre Customer ID (GBP)", "montant_brut_avant_filtre_customer_id_gbp", old, new, True),
          _fmt_summary_row("Lignes d'achat (clients identifies)", "lignes_achat", old, new),
          _fmt_summary_row("Clients", "clients", old, new),
          _fmt_summary_row("Factures", "factures", old, new),
          _fmt_summary_row("Montant brut (GBP)", "montant_brut_gbp", old, new, True),
          _fmt_summary_row("Lignes de retour", "lignes_retour", old, new),
          _fmt_summary_row("Montant des retours (GBP)", "montant_retours_gbp", old, new, True),
          "", "## Controles d'integrite", ""]
    L += [f"- {'OK' if v else 'ECHEC'} : {k}" for k, v in r["controles"].items()]
    L += ["", "## Lignes d'achat par mois", "", "| Mois | Lignes |", "|---|---:|"]
    L += [f"| {k} | {v:,} |" for k, v in a["lignes_par_mois"].items()]
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- #
# Verification sans reconstruction
# --------------------------------------------------------------------------- #
def _rows(path: Path) -> int:
    """Nombre de lignes d'un parquet, ou -1 s'il est illisible (fichier altere)."""
    try:
        return len(pd.read_parquet(path, columns=["Invoice"]))
    except Exception:
        return -1


def verify() -> int:
    """Recalcule les empreintes et les compare au manifeste et au rapport. Renvoie 0 si tout est coherent."""
    checks: list[tuple[str, bool, str]] = []
    m, rep = read_manifest(), None
    try:
        rep = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    paths = [ZIP_PATH, XLSX_PATH, RAW_CACHE, PURCHASES_PATH, RETURNS_PATH]
    missing = [p.name for p in paths if not p.exists()]
    if missing or m is None or rep is None:
        print(f"ECHEC : fichiers ou manifeste/rapport manquants : {missing}, manifeste={m is not None}, rapport={rep is not None}")
        return 1
    zip_sha, xlsx_sha, raw_sha = sha256_of(ZIP_PATH), sha256_of(XLSX_PATH), sha256_of(RAW_CACHE)
    with zipfile.ZipFile(ZIP_PATH) as z:
        member = [n for n in z.namelist() if n.lower().endswith(".xlsx")][0]
        with z.open(member) as s:
            member_sha = sha256_of_stream(s)
    pv = rep["provenance"]
    checks += [
        ("zip = valeur epinglee", zip_sha == PINNED_ZIP_SHA256 or pv["changement_de_source_accepte"], zip_sha),
        ("zip = rapport", zip_sha == pv["zip_sha256"], pv["zip_sha256"]),
        ("zip = manifeste", zip_sha == m["zip_sha256"], m["zip_sha256"]),
        ("xlsx = contenu du zip", xlsx_sha == member_sha, member_sha),
        ("xlsx = rapport", xlsx_sha == pv["xlsx_sha256"], pv["xlsx_sha256"]),
        ("xlsx = manifeste", xlsx_sha == m["xlsx_sha256"], m["xlsx_sha256"]),
        ("raw.parquet = manifeste", raw_sha == m["raw_parquet_sha256"], m["raw_parquet_sha256"]),
        ("schema du cache a jour", m.get("schema_version") == CACHE_SCHEMA_VERSION, str(m.get("schema_version"))),
        ("raw.parquet : lignes = rapport", _rows(RAW_CACHE) == rep["brut"]["lignes"], str(rep["brut"]["lignes"])),
        ("purchases.parquet : lignes = rapport",
         _rows(PURCHASES_PATH) == rep["achats_nettoyes"]["lignes"], str(rep["achats_nettoyes"]["lignes"])),
        ("returns.parquet : lignes = rapport",
         _rows(RETURNS_PATH) == rep["retours"]["lignes"], str(rep["retours"]["lignes"])),
    ]
    caches = rep.get("caches", {})
    for label, path, key in [("raw.parquet", RAW_CACHE, "raw_parquet_sha256"),
                             ("purchases.parquet", PURCHASES_PATH, "purchases_parquet_sha256"),
                             ("returns.parquet", RETURNS_PATH, "returns_parquet_sha256")]:
        actual = raw_sha if path == RAW_CACHE else sha256_of(path)
        checks.append((f"{label} : SHA-256 = rapport (caches)", actual == caches.get(key), str(caches.get(key))))
    for name, ok, ref in checks:
        print(f"{'OK   ' if ok else 'ECHEC'} {name}  (reference : {ref})")
    return 0 if all(ok for _, ok, _ in checks) else 1


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="relit l'Excel meme si le cache parquet est valide")
    ap.add_argument("--refresh-source", action="store_true", help="retelecharge le zip depuis UCI")
    ap.add_argument("--accept-source-change", action="store_true",
                    help="accepte un zip dont l'empreinte differe de la valeur epinglee")
    ap.add_argument("--verify", action="store_true", help="controle les empreintes existantes sans rien reconstruire")
    ap.add_argument("--drop-within-sheet-duplicates", action="store_true",
                    help="retire aussi les doublons exacts presents dans une meme feuille")
    args = ap.parse_args()

    if args.verify:
        raise SystemExit(verify())

    provenance = ensure_source(args.refresh_source, args.accept_source_change)
    raw, origin = load_raw(provenance, force=args.force)
    print(f"Donnees brutes : {origin}.")

    purchases, returns, steps, meta = clean(raw, args.drop_within_sheet_duplicates, "documented")
    p_old, r_old, _, meta_old = clean(raw, args.drop_within_sheet_duplicates, "legacy")
    sensitivity = {
        "regle_initiale_5_chiffres": summarize(p_old, r_old, meta_old),
        "regle_documentee": summarize(purchases, returns, meta),
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    purchases.to_parquet(PURCHASES_PATH, index=False)
    returns.to_parquet(RETURNS_PATH, index=False)

    report = quality_report(raw, purchases, returns, steps, meta, provenance, sensitivity)
    # Empreintes des caches : dans le JSON seulement (elles peuvent varier selon la version de pyarrow).
    report["caches"] = {
        "origine_des_donnees_brutes_a_cette_execution": origin,
        "raw_parquet_sha256": sha256_of(RAW_CACHE),
        "purchases_parquet_sha256": sha256_of(PURCHASES_PATH),
        "returns_parquet_sha256": sha256_of(RETURNS_PATH),
    }
    write_json_atomic(REPORT_JSON, report)
    REPORT_MD.write_text(render_markdown(report), encoding="utf-8")
    print(render_markdown(report))
    if not all(report["controles"].values()):
        raise SystemExit("Un controle d'integrite a echoue.")


if __name__ == "__main__":
    main()
