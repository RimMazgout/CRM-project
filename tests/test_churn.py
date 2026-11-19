"""Tests de src/churn.py et du Segmenter sur des jeux construits a la main."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import churn as ch  # noqa: E402
import rfm as rfmlib  # noqa: E402

T = pd.Timestamp("2011-03-01")


def make_data():
    rows = [
        # client 1 : achete avant T et dans la fenetre -> churn 0
        (1, "A1", "2011-02-20 10:00", 10.0, "United Kingdom", "10001"),
        (1, "A2", "2011-01-10 10:00", 20.0, "United Kingdom", "10002"),
        (1, "A3", "2011-03-01 00:00", 5.0, "United Kingdom", "10001"),   # exactement T : dans la fenetre
        # client 2 : achete avant T, rien dans la fenetre -> churn 1
        (2, "B1", "2011-02-01 09:00", 50.0, "France", "10003"),
        # client 3 : achete avant T, puis exactement a T + 90 j (hors fenetre) -> churn 1
        (3, "C1", "2011-02-25 09:00", 8.0, "United Kingdom", "10001"),
        (3, "C2", "2011-05-30 00:00", 8.0, "United Kingdom", "10001"),
        # client 4 : premier achat dans la fenetre, absent de la population de T
        (4, "D1", "2011-04-01 09:00", 30.0, "United Kingdom", "10001"),
        # ligne tardive qui fixe la fin des donnees
        (5, "E1", "2011-09-30 09:00", 1.0, "United Kingdom", "10001"),
    ]
    p = pd.DataFrame(rows, columns=["customer_id", "Invoice", "InvoiceDate", "montant_brut_gbp", "Country", "StockCode"])
    p["InvoiceDate"] = pd.to_datetime(p["InvoiceDate"])
    r = pd.DataFrame({"customer_id": [1, 2], "Invoice": ["C1", "C2"],
                      "InvoiceDate": pd.to_datetime(["2011-02-10 00:00", "2011-03-10 00:00"]),
                      "montant_retour_gbp": [-4.0, -9.0]})
    return p, r


def test_etiquettes_definition_et_bornes():
    p, r = make_data()
    snap = ch.build_snapshot(p, r, T, 90)
    assert list(snap.index) == [1, 2, 3]                  # 4 et 5 absents : pas d'achat avant T
    assert snap.loc[1, "churn"] == 0                      # achat exactement a T : compte
    assert snap.loc[2, "churn"] == 1
    assert snap.loc[3, "churn"] == 1                      # achat a T + 90 j : hors fenetre [T, T + 90 j)


def test_variables_ignorent_tout_ce_qui_est_a_partir_de_T():
    p, r = make_data()
    ref = ch.build_features(p, r, T)
    p2, r2 = p.copy(), r.copy()
    fp, fr = p2.InvoiceDate >= T, r2.InvoiceDate >= T
    p2.loc[fp, "montant_brut_gbp"] *= 1000
    p2.loc[fp, "customer_id"] += 10
    r2.loc[fr, "montant_retour_gbp"] *= 1000
    pd.testing.assert_frame_equal(ch.build_features(p2, r2, T), ref)


def test_etiquettes_ignorent_tout_ce_qui_est_a_partir_de_T_plus_horizon():
    p, r = make_data()
    ref = ch.build_snapshot(p, r, T, 90)["churn"]
    p2 = p.copy()
    p2.loc[p2.InvoiceDate >= T + pd.Timedelta(days=90), "customer_id"] += 10
    pd.testing.assert_series_equal(ch.build_labels(p2, ref.index, T, 90), ref)


def test_fenetre_hors_donnees_refusee():
    p, _ = make_data()
    with pytest.raises(ValueError):
        ch.build_labels(p, pd.Index([1]), "2011-09-15", 90)


def test_definitions_des_variables():
    p, r = make_data()
    f = ch.build_features(p, r, T)
    assert f.loc[1, "frequency"] == 2 and f.loc[1, "monetary_brut_gbp"] == 30.0
    assert f.loc[1, "recency_days"] == 8                  # 20/02 10:00 -> 01/03 00:00
    assert np.isnan(f.loc[2, "mean_gap_days"])            # une seule facture
    assert f.loc[1, "is_uk"] == 1 and f.loc[2, "is_uk"] == 0
    assert f.loc[1, "return_lines"] == 1 and f.loc[2, "return_lines"] == 0   # le retour du client 2 est apres T
    assert 0 <= f["return_share"].max() <= 1


def test_plan_temporel_valide_et_refuse():
    plan = ch.check_temporal_plan(["2010-06-01", "2010-09-01"], "2010-12-01", "2011-03-01", 90)
    assert list(plan.role) == ["entrainement", "entrainement", "validation", "test"]
    with pytest.raises(ValueError):      # etiquette de 2010-09-01 connue le 2010-11-30 : apres la date suivante
        ch.check_temporal_plan(["2010-09-01"], "2010-10-15", "2011-03-01", 90)
    with pytest.raises(ValueError):
        ch.check_temporal_plan(["2010-09-01"], "2010-06-01", "2011-03-01", 90)


def test_segmenter_ajuste_sur_entrainement_seulement():
    rng = np.random.default_rng(0)
    def fake(n, shift):
        return pd.DataFrame({"recency_days": rng.integers(0, 600, n) + shift, "frequency": rng.integers(1, 30, n),
                             "monetary_brut_gbp": rng.uniform(5, 5000, n)}, index=range(n))
    train, test = fake(400, 0), fake(100, 5000)        # le test est tres different de l'entrainement
    seg = rfmlib.Segmenter(seed=42).fit(train)
    centers_before = seg.kmeans_.cluster_centers_.copy()
    mean_before = seg.scaler_.mean_.copy()
    out = seg.predict(test)
    assert set(out.unique()) <= set(rfmlib.SEGMENT_ORDER)
    np.testing.assert_array_equal(seg.kmeans_.cluster_centers_, centers_before)   # predict ne reajuste rien
    np.testing.assert_array_equal(seg.scaler_.mean_, mean_before)
    assert len(seg.names_) == 4 and len(set(seg.names_.values())) == 4
