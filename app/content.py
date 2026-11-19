"""Textes et choix éditoriaux de l'interface.

Ce fichier ne contient AUCUN résultat chiffré : les nombres affichés viennent des fichiers de
`reports/` (voir data_access.py). On n'y trouve que des noms, des couleurs et des phrases.
"""

SEGMENT_ORDER = ["Champions", "Réguliers à risque", "Récents à développer", "Endormis"]
SEGMENT_COLORS = {
    "Champions": "#1f5f8b",
    "Réguliers à risque": "#d9902f",
    "Récents à développer": "#3f8f62",
    "Endormis": "#9a4b4b",
}
SEGMENT_DESCRIPTION = {
    "Champions": "Achètent souvent, récemment et pour des montants élevés.",
    "Réguliers à risque": "Clients installés dont le rythme d'achat se ralentit.",
    "Récents à développer": "Clients actifs récemment, avec peu de commandes pour l'instant.",
    "Endormis": "N'ont pas acheté depuis longtemps, le plus souvent une seule fois.",
}
SEGMENT_ACTION = {
    "Champions": ("Fidéliser sans brader",
                  "Accès anticipé aux nouveautés, service dédié, offre de volume plutôt que remise générale."),
    "Réguliers à risque": ("Relancer avant la dormance",
                           "E-mail personnalisé qui rappelle les catégories habituelles, offre limitée dans le temps."),
    "Récents à développer": ("Encourager le prochain achat",
                             "Séquence de bienvenue et recommandations de produits complémentaires."),
    "Endormis": ("Réactiver à coût plafonné",
                 "Une seule campagne de retour, puis retrait des envois en l'absence de réponse."),
}

RETAINED_MODEL = "Régression logistique"
BASELINE_MODEL = "Règle de récence"
TRIVIAL_MODEL = "Tous prédits churn"
MODELS_COMPARED = [BASELINE_MODEL, "Régression logistique", "Forêt aléatoire"]

SCENARIOS = ["prudent", "central", "optimiste"]
SCENARIO_HELP = {
    "prudent": "Toutes les hypothèses défavorables à la fois : faible réactivation, marge basse, coûts élevés.",
    "central": "Hypothèses intermédiaires, choisies avant de calculer.",
    "optimiste": "Toutes les hypothèses favorables à la fois.",
}

CAMPAIGN_META = {
    "C1": {"nom": "Champions à risque", "action": "Fidéliser sans brader",
           "detail": "Contact personnalisé et accès anticipé aux nouveautés, sans remise.",
           "ciblage": "les Champions les plus à risque"},
    "C2": {"nom": "Réguliers à risque", "action": "Relancer avant la dormance",
           "detail": "E-mail personnalisé et offre limitée dans le temps.",
           "ciblage": "la moitié des Réguliers à risque la plus à risque"},
    "C3": {"nom": "Récents à développer", "action": "Encourager le prochain achat",
           "detail": "Séquence de bienvenue et recommandations de produits complémentaires.",
           "ciblage": "tous les Récents à développer"},
}

SIMULATION_BANNER = "Simulation, aucun message envoyé"
SIMULATION_SUBTEXT = ("Les montants ci-dessous sont des hypothèses, pas des mesures. Les données ne contiennent ni adresse "
                      "e-mail ni résultat de campagne, et le taux de réactivation, la marge et les coûts ne viennent pas des données.")

STEPS = [
    ("1. Données", "Nettoyage d'Online Retail II : doublons, retours, frais, clients sans identifiant."),
    ("2. Segments RFM", "Récence, fréquence et montant à une date de référence, puis quatre segments K-means."),
    ("3. Départ des clients", "Prédire qui n'achètera pas dans les 90 jours, avec un découpage temporel sans fuite."),
    ("4. Campagnes simulées", "Trois campagnes ciblées par rang de risque, avec un gain net en trois scénarios."),
]
