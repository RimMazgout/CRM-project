"""Etape 4 : ciblage par rang de risque et simulation du gain de campagnes.

TOUT CE QUI EST CALCULE ICI EST UNE SIMULATION. Les donnees ne contiennent ni adresse e-mail, ni
resultat de campagne, ni marge, ni cout : le taux de reactivation, la marge, les couts et les taux
d'usage des offres sont des hypotheses explicites. Aucun effet reel n'est mesure.

Ciblage : les clients d'un segment sont classes par risque de depart (score du modele). On cible
les `fraction` clients les plus a risque du segment. Seul le RANG compte : les probabilites ne
sont pas calibrees (elles surestiment le churn de 5 a 14 points sur le test). Le ciblage n'utilise
jamais le resultat observe (churn reel).
"""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import pandas as pd


def _risk_order(g: pd.DataFrame, score_col: str, id_col: str) -> pd.Index:
    """Index de `g` du client le plus a risque au moins a risque ; egalites departagees par identifiant croissant."""
    positions = np.lexsort((g[id_col].to_numpy(), -g[score_col].to_numpy()))
    return g.index[positions]


def risk_rank_in_segment(df: pd.DataFrame, segment_col: str = "segment", score_col: str = "proba_logistique",
                         id_col: str = "customer_id") -> pd.Series:
    """Rang de risque dans le segment, de 1/n (client le plus a risque) a 1. Egalites departagees par identifiant."""
    out = pd.Series(np.nan, index=df.index, name="rang_risque_segment")
    for _, g in df.groupby(segment_col, sort=True):
        order = _risk_order(g, score_col, id_col)
        out.loc[order] = np.arange(1, len(order) + 1) / len(order)
    return out


def select_targets(df: pd.DataFrame, segment: str, fraction: float, segment_col: str = "segment",
                   score_col: str = "proba_logistique", id_col: str = "customer_id") -> pd.Index:
    """Index des `ceil(fraction * n)` clients les plus a risque du segment. N'utilise que le segment et le score."""
    if not 0 < fraction <= 1:
        raise ValueError("fraction doit etre dans ]0, 1].")
    g = df[df[segment_col] == segment]
    k = math.ceil(fraction * len(g) - 1e-9)
    return _risk_order(g, score_col, id_col)[:k]


def simulate(n_targeted: int, base_churn: float, basket_gbp: float, reactivation: float, margin: float,
             discount: float, redemption: float, contact_cost: float, fixed_cost: float,
             orders: float = 1.0, basket_factor: float = 1.0) -> dict:
    """Gain net simule d'une campagne (GBP).

    n_targeted    N : clients contactes.
    base_churn    p0 : part des clients cibles qui n'achetent pas dans les 90 jours SANS campagne.
    basket_gbp    panier moyen historique (ventes brutes) des clients cibles.
    reactivation  r : part des clients qui seraient partis et que la campagne fait racheter (hypothese).
    margin        m : taux de marge sur le prix catalogue (hypothese).
    discount      d : remise accordee, en part du prix (0 si aucune).
    redemption    s : part des clients qui auraient acheté de toute facon et utilisent l'offre (cannibalisation).
    contact_cost  c : cout par client contacte.   fixed_cost : cout fixe de la campagne.
    orders        commandes passees par client reactive sur la fenetre.   basket_factor : reduction du panier des clients reactives.

    pool           = N * p0                             clients qui partiraient sans campagne
    reactivated    = pool * r                           reactivation additionnelle supposee
    marge_gagnee   = reactivated * orders * basket * basket_factor * (m - d)
    cannibalisation= N * (1 - p0) * s * basket * d      remises donnees a des clients qui auraient achete
    cout_contact   = N * c ;   cout_fixe = F
    gain_net       = marge_gagnee - cannibalisation - cout_contact - cout_fixe
    """
    for name, v in [("base_churn", base_churn), ("reactivation", reactivation), ("margin", margin),
                    ("discount", discount), ("redemption", redemption)]:
        if not 0 <= v <= 1:
            raise ValueError(f"{name} doit etre dans [0, 1].")
    if n_targeted < 0 or basket_gbp < 0 or contact_cost < 0 or fixed_cost < 0:
        raise ValueError("effectif, panier et couts doivent etre positifs.")
    pool = n_targeted * base_churn
    reactivated = pool * reactivation
    unit_margin = margin - discount
    revenue = reactivated * orders * basket_gbp * basket_factor
    gained = revenue * unit_margin
    cannibal = n_targeted * (1 - base_churn) * redemption * basket_gbp * discount
    contact = n_targeted * contact_cost
    net = gained - cannibal - contact - fixed_cost
    cost_to_cover = cannibal + contact + fixed_cost
    denom = pool * orders * basket_gbp * basket_factor * unit_margin
    return {
        "clients_cibles": n_targeted, "clients_qui_partiraient": pool, "clients_reactives": reactivated,
        "ventes_brutes_additionnelles_gbp": revenue, "marge_gagnee_gbp": gained,
        "cout_cannibalisation_gbp": cannibal, "cout_contacts_gbp": contact, "cout_fixe_gbp": fixed_cost,
        "gain_net_gbp": net,
        "seuil_rentabilite_reactivation": (cost_to_cover / denom) if denom > 0 else math.inf,
    }


def minimum_detectable_effect(p0: float, n_per_group: int, alpha: float = 0.05, power: float = 0.8) -> float:
    """Plus petit ecart absolu de taux detectable entre deux groupes de meme taille (approximation normale)."""
    z = NormalDist().inv_cdf(1 - alpha / 2) + NormalDist().inv_cdf(power)
    return z * math.sqrt(2 * p0 * (1 - p0) / n_per_group)

def required_n_per_group(p0: float, effect: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """Clients necessaires dans CHAQUE groupe pour detecter un ecart absolu `effect` de taux de depart."""
    if effect <= 0:
        raise ValueError("effect doit etre positif.")
    z = NormalDist().inv_cdf(1 - alpha / 2) + NormalDist().inv_cdf(power)
    return math.ceil(2 * p0 * (1 - p0) * (z / effect) ** 2)
