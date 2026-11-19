"""Tests de src/campaigns.py : ciblage par rang et formule de gain, verifies a la main."""

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import campaigns as cp  # noqa: E402


def sample_df():
    return pd.DataFrame({
        "customer_id": [1, 2, 3, 4, 5, 6, 7, 8],
        "segment": ["A", "A", "A", "A", "B", "B", "B", "B"],
        "proba_logistique": [0.9, 0.7, 0.7, 0.1, 0.2, 0.8, 0.5, 0.5],
        "churn_reel": [1, 0, 1, 0, 0, 1, 1, 0],
    }).set_index("customer_id", drop=False)


def test_formule_hand_computed():
    out = cp.simulate(n_targeted=100, base_churn=0.5, basket_gbp=200, reactivation=0.1, margin=0.3,
                      discount=0.1, redemption=0.2, contact_cost=1.0, fixed_cost=50)
    assert out["clients_qui_partiraient"] == 50 and out["clients_reactives"] == 5
    assert out["ventes_brutes_additionnelles_gbp"] == pytest.approx(1000)
    assert out["marge_gagnee_gbp"] == pytest.approx(200)            # 1000 * (0,30 - 0,10)
    assert out["cout_cannibalisation_gbp"] == pytest.approx(200)    # 100 * 0,5 * 0,2 * 200 * 0,10
    assert out["cout_contacts_gbp"] == pytest.approx(100)
    assert out["gain_net_gbp"] == pytest.approx(-150)
    assert out["seuil_rentabilite_reactivation"] == pytest.approx(0.175)


def test_seuil_de_rentabilite_annule_le_gain():
    kw = dict(n_targeted=300, base_churn=0.4, basket_gbp=120, margin=0.3, discount=0.05, redemption=0.1,
              contact_cost=0.5, fixed_cost=100)
    r_star = cp.simulate(reactivation=0.1, **kw)["seuil_rentabilite_reactivation"]
    assert cp.simulate(reactivation=r_star, **kw)["gain_net_gbp"] == pytest.approx(0, abs=1e-9)


def test_sans_remise_pas_de_cannibalisation_et_gain_croit_avec_la_reactivation():
    kw = dict(n_targeted=200, base_churn=0.4, basket_gbp=300, margin=0.3, discount=0.0, redemption=0.5,
              contact_cost=2.0, fixed_cost=0)
    assert cp.simulate(reactivation=0.1, **kw)["cout_cannibalisation_gbp"] == 0
    gains = [cp.simulate(reactivation=r, **kw)["gain_net_gbp"] for r in (0.0, 0.05, 0.1, 0.2)]
    assert gains == sorted(gains) and gains[0] == pytest.approx(-400)     # sans reactivation : seulement les couts


def test_marge_inferieure_a_la_remise_rend_la_rentabilite_impossible():
    out = cp.simulate(100, 0.5, 100, 0.1, margin=0.1, discount=0.2, redemption=0.1, contact_cost=0, fixed_cost=0)
    assert math.isinf(out["seuil_rentabilite_reactivation"]) and out["gain_net_gbp"] < 0


def test_parametres_invalides_refuses():
    with pytest.raises(ValueError):
        cp.simulate(10, 1.2, 100, 0.1, 0.3, 0, 0, 0, 0)
    with pytest.raises(ValueError):
        cp.select_targets(sample_df(), "A", 0)


def test_ciblage_prend_les_plus_a_risque_du_segment_avec_egalites_departagees():
    df = sample_df()
    assert list(cp.select_targets(df, "A", 0.5)) == [1, 2]       # 0,9 puis l'egalite 0,7 : identifiant 2 avant 3
    assert list(cp.select_targets(df, "B", 0.25)) == [6]
    assert list(cp.select_targets(df, "A", 0.3)) == [1, 2]       # ceil(0,3 * 4) = 2
    assert len(cp.select_targets(df, "B", 1.0)) == 4


def test_ciblage_independant_du_resultat_observe():
    df = sample_df()
    shuffled = df.copy()
    shuffled["churn_reel"] = np.random.default_rng(0).permutation(df["churn_reel"].values)
    for seg in ("A", "B"):
        assert list(cp.select_targets(df, seg, 0.5)) == list(cp.select_targets(shuffled, seg, 0.5))


def test_rang_de_risque():
    r = cp.risk_rank_in_segment(sample_df())
    assert r.loc[1] == 0.25 and r.loc[4] == 1.0 and r.loc[6] == 0.25 and r.loc[5] == 1.0
    assert r.between(0, 1).all()


def test_ecart_minimal_detectable():
    # 2 groupes de 458 clients, taux de base 0,5 : environ 9 points
    assert cp.minimum_detectable_effect(0.5, 458) == pytest.approx(0.0925, abs=0.002)
    assert cp.minimum_detectable_effect(0.5, 4000) < cp.minimum_detectable_effect(0.5, 400)

def test_taille_necessaire_coherente_avec_l_ecart_minimal_detectable():
    mde = cp.minimum_detectable_effect(0.5, 458)
    assert abs(cp.required_n_per_group(0.5, mde) - 458) <= 1
    assert cp.required_n_per_group(0.5, 0.02) > cp.required_n_per_group(0.5, 0.05)
    with pytest.raises(ValueError):
        cp.required_n_per_group(0.5, 0)
