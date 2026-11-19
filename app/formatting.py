"""Formats français : séparateur de milliers (espace insécable), virgule décimale, signe moins typographique.

Aucune dépendance à Streamlit : ces fonctions sont testées seules (tests/test_app.py).
"""

from __future__ import annotations

import math

NBSP = "\u00a0"
MINUS = "\u2212"
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
          "septembre", "octobre", "novembre", "décembre"]


def fr_num(x: float, decimals: int = 1) -> str:
    """12345.678 -> '12 345,7' (sans signe + ; le signe moins est typographique)."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/d"
    s = f"{abs(x):,.{decimals}f}".replace(",", "\x00").replace(".", ",").replace("\x00", NBSP)
    return (MINUS if x < 0 and float(s.replace(NBSP, "").replace(",", ".")) != 0 else "") + s


def fr_int(x: float) -> str:
    return fr_num(round(x), 0)


def fr_pct(x: float, decimals: int = 1) -> str:
    """Part comprise entre 0 et 1 -> '57,2 %'."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/d"
    return f"{fr_num(100 * x, decimals)}{NBSP}%"


def fr_gbp(x: float, decimals: int = 0, signed: bool = False) -> str:
    """Montant en livres sterling ; `signed` ajoute + devant les valeurs positives."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/d"
    body = fr_num(x, decimals)
    if signed and not body.startswith(MINUS) and x != 0:
        body = "+" + body
    return f"{body}{NBSP}GBP"


def fr_date(iso: str) -> str:
    """'2011-09-01' -> '1 septembre 2011' (le premier jour du mois s'écrit '1er')."""
    y, m, d = (int(p) for p in str(iso)[:10].split("-"))
    day = "1er" if d == 1 else str(d)
    return f"{day} {MONTHS[m - 1]} {y}"


def fr_month_year(iso: str) -> str:
    y, m, _ = (int(p) for p in str(iso)[:10].split("-"))
    return f"{MONTHS[m - 1]} {y}"
