"""Tests de src/rfm.py sur un jeu minimal construit a la main (pas besoin des donnees reelles)."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import rfm as rfmlib  # noqa: E402

T = pd.Timestamp("2011-09-01")


def make_purchases() -> pd.DataFrame:
    rows = [
        # client 1 : deux factures avant T (10 + 5 GBP), une apres (1000 GBP, ne doit pas compter)
        (1, "A1", "2011-08-31 12:00", 10.0),
        (1, "A1", "2011-08-31 12:00", 5.0),     # meme facture : frequence = 1 pour A1
        (1, "A2", "2011-07-01 09:00", 20.0),
        (1, "A3", "2011-09-01 00:00", 1000.0),  # exactement a T : exclue (strictement avant)
        (1, "A4", "2011-10-01 10:00", 1000.0),
        # client 2 : un seul achat, 10 jours avant T
        (2, "B1", "2011-08-22 08:00", 7.5),
        # client 3 : n'achete qu'apres T, absent de la sortie
        (3, "C1", "2011-09-15 08:00", 50.0),
    ]
    df = pd.DataFrame(rows, columns=["customer_id", "Invoice", "InvoiceDate", "montant_brut_gbp"])
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"])
    return df


def test_definitions_rfm():
    out = rfmlib.build_rfm(make_purchases(), T)
    assert list(out.index) == [1, 2]
    assert out.loc[1, "frequency"] == 2                # A1 et A2
    assert out.loc[1, "monetary_brut_gbp"] == 35.0     # 10 + 5 + 20
    assert out.loc[1, "recency_days"] == 0             # dernier achat le 31/08 a 12h : moins d'un jour avant T
    assert out.loc[2, "recency_days"] == 9             # 22/08 08:00 -> 01/09 00:00 = 9 j 16 h
    assert out.loc[2, "monetary_brut_gbp"] == 7.5


def test_les_lignes_a_partir_de_T_sont_ignorees():
    base = make_purchases()
    expected = rfmlib.build_rfm(base, T)
    tampered = base.copy()
    future = tampered["InvoiceDate"] >= T
    tampered.loc[future, "montant_brut_gbp"] *= 1000
    tampered.loc[future, "customer_id"] += 10
    pd.testing.assert_frame_equal(rfmlib.build_rfm(tampered, T), expected)
    pd.testing.assert_frame_equal(rfmlib.build_rfm(base[~future], T), expected)


def test_erreur_si_aucun_achat_avant_T():
    with pytest.raises(ValueError):
        rfmlib.build_rfm(make_purchases(), "2000-01-01")


def test_retours_avant_T_seulement():
    returns = pd.DataFrame({
        "customer_id": [1, 1, 2],
        "InvoiceDate": pd.to_datetime(["2011-08-01 00:00", "2011-09-02 00:00", "2011-09-01 00:00"]),
        "montant_retour_gbp": [-4.0, -100.0, -9.0],
    })
    out = rfmlib.returns_summary_before(returns, T)
    assert out.loc[1, "return_lines"] == 1 and out.loc[1, "returns_gbp"] == -4.0
    assert 2 not in out.index


def test_log_features_est_non_negatif():
    out = rfmlib.log_features(rfmlib.build_rfm(make_purchases(), T))
    assert (out >= 0).all().all()
