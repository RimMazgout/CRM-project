"""Etape 3 : variables et etiquettes de churn a 90 jours, calculees a une date de reference.

Regles anti-fuite :
  * Les VARIABLES d'un instantane T n'utilisent que les lignes datees strictement avant T
    (achats et retours).
  * L'ETIQUETTE regarde la fenetre [T, T + horizon) : churn = 1 si le client n'effectue aucun
    achat dans cette fenetre. Les deux fenetres ne se chevauchent pas.
  * Un instantane n'est construit que si sa fenetre d'etiquette est entierement couverte par les
    donnees (sinon une erreur est levee), pour ne pas confondre « pas encore observe » et « parti ».

Definition du churn : inactivite d'achat. Les retours (factures C*) ne comptent pas comme une
activite. Les montants sont des ventes brutes, retours non deduits.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import rfm as rfmlib

HORIZON_DAYS = 90

BASE_FEATURES = [
    "recency_days", "frequency", "monetary_brut_gbp", "tenure_days", "avg_basket_gbp",
    "mean_gap_days", "overdue_ratio", "invoices_last_90d", "invoices_prev_90d",
    "spend_last_90d_gbp", "distinct_products",
]
BINARY_FEATURES = ["is_uk"]
RETURN_FEATURES = ["return_lines", "return_share"]   # variante de sensibilite, hors version 1


def build_features(purchases: pd.DataFrame, returns: pd.DataFrame, reference_date) -> pd.DataFrame:
    """Une ligne par client ayant au moins un achat avant T. N'utilise que les lignes < T."""
    T = pd.Timestamp(reference_date)
    p = purchases.loc[purchases["InvoiceDate"] < T]
    base = rfmlib.build_rfm(p, T)

    inv = (p.groupby(["customer_id", "Invoice"])
             .agg(date=("InvoiceDate", "min"), amount=("montant_brut_gbp", "sum")).reset_index())
    g = inv.groupby("customer_id")
    span_days = (g["date"].max() - g["date"].min()).dt.total_seconds() / 86400
    n_inv = g.size()
    mean_gap = (span_days / (n_inv - 1)).where(n_inv >= 2)          # NaN si une seule facture

    last90 = inv["date"] >= T - pd.Timedelta(days=90)
    prev90 = (inv["date"] >= T - pd.Timedelta(days=180)) & ~last90
    inv_last = inv[last90].groupby("customer_id")
    inv_prev = inv[prev90].groupby("customer_id")

    last_country = p.sort_values("InvoiceDate", kind="stable").groupby("customer_id")["Country"].last()

    f = pd.DataFrame(index=base.index)
    f["recency_days"] = base["recency_days"]
    f["frequency"] = base["frequency"]
    f["monetary_brut_gbp"] = base["monetary_brut_gbp"]
    f["tenure_days"] = (T - base["first_purchase"]).dt.days
    f["avg_basket_gbp"] = base["monetary_brut_gbp"] / base["frequency"]
    f["mean_gap_days"] = mean_gap.reindex(f.index)
    f["overdue_ratio"] = f["recency_days"] / (f["mean_gap_days"] + 1.0)
    f["invoices_last_90d"] = inv_last.size().reindex(f.index).fillna(0)
    f["invoices_prev_90d"] = inv_prev.size().reindex(f.index).fillna(0)
    f["spend_last_90d_gbp"] = inv_last["amount"].sum().reindex(f.index).fillna(0.0)
    f["distinct_products"] = p.groupby("customer_id")["StockCode"].nunique().reindex(f.index)
    f["is_uk"] = (last_country.reindex(f.index) == "United Kingdom").astype(int)

    r = returns.loc[returns["InvoiceDate"] < T].groupby("customer_id")
    f["return_lines"] = r.size().reindex(f.index).fillna(0)
    ret_gbp = (-r["montant_retour_gbp"].sum()).reindex(f.index).fillna(0.0)
    f["return_share"] = (ret_gbp / f["monetary_brut_gbp"]).clip(0, 1)

    assert (p["InvoiceDate"].max() < T) and (returns.loc[returns["InvoiceDate"] < T, "InvoiceDate"].max() < T)
    return f


def build_labels(purchases: pd.DataFrame, customer_ids: pd.Index, reference_date, horizon_days: int = HORIZON_DAYS) -> pd.Series:
    """churn = 1 si le client n'achete pas dans [T, T + horizon). Leve une erreur si la fenetre depasse les donnees."""
    T = pd.Timestamp(reference_date)
    end = T + pd.Timedelta(days=horizon_days)
    last_day = purchases["InvoiceDate"].max().normalize() + pd.Timedelta(days=1)
    if end > last_day:
        raise ValueError(f"La fenetre d'etiquette [{T:%Y-%m-%d}, {end:%Y-%m-%d}) depasse les donnees (fin : {last_day:%Y-%m-%d}).")
    window = purchases.loc[(purchases["InvoiceDate"] >= T) & (purchases["InvoiceDate"] < end), "customer_id"]
    return pd.Series((~pd.Index(customer_ids).isin(window.unique())).astype(int), index=customer_ids, name="churn")


def build_snapshot(purchases: pd.DataFrame, returns: pd.DataFrame, reference_date, horizon_days: int = HORIZON_DAYS) -> pd.DataFrame:
    """Variables (avant T) + etiquette churn (fenetre [T, T + horizon)) + date de l'instantane."""
    T = pd.Timestamp(reference_date)
    feats = build_features(purchases, returns, T)
    feats["churn"] = build_labels(purchases, feats.index, T, horizon_days)
    feats.insert(0, "snapshot_date", T)
    return feats


def check_temporal_plan(train_dates, validation_date, test_date, horizon_days: int = HORIZON_DAYS) -> pd.DataFrame:
    """Verifie que les etiquettes de chaque periode sont connues avant la date suivante.

    Renvoie un tableau (date, fin de la fenetre d'etiquette, role). Leve une erreur si une
    fenetre d'etiquette se prolonge au-dela de la date de la periode suivante.
    """
    dates = [pd.Timestamp(d) for d in train_dates] + [pd.Timestamp(validation_date), pd.Timestamp(test_date)]
    roles = ["entrainement"] * len(train_dates) + ["validation", "test"]
    if dates != sorted(dates):
        raise ValueError("Les dates doivent etre croissantes.")
    rows = []
    for i, (d, role) in enumerate(zip(dates, roles)):
        end = d + pd.Timedelta(days=horizon_days)
        if i + 1 < len(dates) and end > dates[i + 1]:
            raise ValueError(f"Les etiquettes de {d:%Y-%m-%d} ({role}) ne sont connues qu'au {end:%Y-%m-%d}, apres la date suivante {dates[i + 1]:%Y-%m-%d}.")
        rows.append({"role": role, "date_reference": d.date(), "fin_fenetre_etiquette": end.date()})
    return pd.DataFrame(rows)
