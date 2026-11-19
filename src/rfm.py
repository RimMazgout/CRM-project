"""Etape 2 : indicateurs RFM calcules a une date de reference explicite.

Regle anti-fuite : build_rfm() ne lit que les lignes dont InvoiceDate < reference_date.
Une ligne datee de la date de reference ou apres est ignoree, meme si elle est presente
dans le tableau passe en argument.

Montants : `monetary_brut_gbp` = somme de Quantity * Price des factures de vente.
Les retours (factures C*) ne sont PAS deduits ; ce n'est pas un montant net.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

RFM_COLUMNS = ["recency_days", "frequency", "monetary_brut_gbp"]


def build_rfm(purchases: pd.DataFrame, reference_date: str | pd.Timestamp) -> pd.DataFrame:
    """Une ligne par client ayant au moins un achat avant `reference_date`.

    recency_days      : jours entiers ecoules entre le dernier achat et la date de reference (0 = veille).
    frequency         : nombre de factures de vente distinctes avant la date de reference.
    monetary_brut_gbp : ventes brutes cumulees en GBP avant la date de reference, retours non deduits.
    """
    ref = pd.Timestamp(reference_date)
    past = purchases.loc[purchases["InvoiceDate"] < ref]
    if past.empty:
        raise ValueError("Aucun achat avant la date de reference.")
    g = past.groupby("customer_id")
    rfm = pd.DataFrame({
        "first_purchase": g["InvoiceDate"].min(),
        "last_purchase": g["InvoiceDate"].max(),
        "frequency": g["Invoice"].nunique(),
        "monetary_brut_gbp": g["montant_brut_gbp"].sum(),
    })
    rfm["recency_days"] = (ref - rfm["last_purchase"]).dt.days
    # Garde-fou : aucune information posterieure a la date de reference.
    assert rfm["last_purchase"].max() < ref
    return rfm[["recency_days", "frequency", "monetary_brut_gbp", "first_purchase", "last_purchase"]]


def returns_summary_before(returns: pd.DataFrame, reference_date: str | pd.Timestamp) -> pd.DataFrame:
    """Nombre de lignes de retour et montant des retours par client, avant la date de reference.

    Sert a decrire les segments. N'entre pas dans le calcul des segments.
    """
    ref = pd.Timestamp(reference_date)
    past = returns.loc[returns["InvoiceDate"] < ref]
    g = past.groupby("customer_id")
    return pd.DataFrame({"return_lines": g.size(), "returns_gbp": g["montant_retour_gbp"].sum()})


def log_features(rfm: pd.DataFrame) -> pd.DataFrame:
    """log(1 + x) sur R, F et M : reduit l'asymetrie avant la standardisation."""
    return np.log1p(rfm[RFM_COLUMNS].astype(float))

SEGMENT_ORDER = ["Champions", "Réguliers à risque", "Récents à développer", "Endormis"]


def name_segments(rfm: pd.DataFrame, cluster_col: str = "cluster") -> dict:
    """Nomme les 4 clusters d'apres les medianes de R et M (independant de la numerotation).

    Champions = mediane de montant la plus haute ; Recents a developper = recence mediane la plus
    basse parmi les trois autres ; Endormis = recence mediane la plus haute parmi les deux restants ;
    le dernier est Reguliers a risque. Regle calibree sur Online Retail II : relire le profil avant
    de la reutiliser sur d'autres donnees ou d'autres dates.
    """
    med = rfm.groupby(cluster_col)[["recency_days", "monetary_brut_gbp"]].median()
    if len(med) != 4:
        raise ValueError("name_segments attend exactement 4 clusters.")
    left, names = {int(i) for i in med.index}, {}
    champ = int(med.loc[list(left), "monetary_brut_gbp"].idxmax()); names[champ] = "Champions"; left.remove(champ)
    recent = int(med.loc[list(left), "recency_days"].idxmin()); names[recent] = "Récents à développer"; left.remove(recent)
    sleep = int(med.loc[list(left), "recency_days"].idxmax()); names[sleep] = "Endormis"; left.remove(sleep)
    names[left.pop()] = "Réguliers à risque"
    return names


class Segmenter:
    """Standardisation + K-means a 4 clusters sur log(1+R, F, M), ajustes sur des donnees d'entrainement.

    fit() n'utilise que le tableau fourni ; predict() applique ensuite les memes parametres
    (moyennes, ecarts types, centres) a de nouveaux clients, sans les reajuster.
    """

    def __init__(self, k: int = 4, seed: int = 42, n_init: int = 20):
        self.k, self.seed, self.n_init = k, seed, n_init

    def fit(self, rfm: pd.DataFrame) -> "Segmenter":
        logged = log_features(rfm)
        self.scaler_ = StandardScaler().fit(logged)
        self.kmeans_ = KMeans(n_clusters=self.k, n_init=self.n_init, random_state=self.seed).fit(self.scaler_.transform(logged))
        train = rfm.assign(cluster=self.kmeans_.labels_)
        self.names_ = name_segments(train)
        return self

    def predict(self, rfm: pd.DataFrame) -> pd.Series:
        clusters = self.kmeans_.predict(self.scaler_.transform(log_features(rfm)))
        return pd.Series(clusters, index=rfm.index).map(self.names_).rename("segment")
