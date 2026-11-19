# Etape 4 : trois campagnes ciblees et gains simules

> **Tout ce qui est chiffre ici est une simulation.** Les donnees ne contiennent ni adresse e-mail, ni resultat de campagne, ni marge, ni cout. **Aucun message n'a ete envoye, aucun effet reel n'a ete mesure.** Le taux de reactivation, la marge, les couts et les taux d'usage des offres sont des hypotheses fixees avant de calculer et non modifiees apres la lecture des resultats.
>
> **Le taux de depart « sans campagne » est observe retrospectivement** (periode du 2011-09-01 au 2011-11-30) : il n'etait pas disponible a la date fictive de lancement. **Les donnees ne permettent pas de savoir si les clients ont recu d'autres campagnes** : « sans campagne » veut dire « sans campagne connue ».

Perimetre : trois campagnes avec population, action, cout, marge, reactivation additionnelle supposee et formule du gain net, en trois scenarios. Pas de nouveau modele.

## Fichiers

| Fichier | Role | Versionne |
|---|---|---|
| `notebooks/04_campaigns_simulation.ipynb` | notebook livrable, sorties incluses | oui |
| `src/campaigns.py` | `risk_rank_in_segment`, `select_targets`, `simulate`, `minimum_detectable_effect`, `required_n_per_group` | oui |
| `tests/test_campaigns.py` | 10 tests, formule verifiee a la main | oui |
| `reports/campaigns_targets.csv` | populations ciblees et leurs chiffres issus des donnees | oui |
| `reports/campaigns_assumptions.csv` | hypotheses par campagne et scenario (colonne `type = SIMULATION`) | oui |
| `reports/campaigns_simulation.csv` | resultats par campagne et scenario (colonne `type = SIMULATION`) | oui |
| `reports/campaigns_breakeven_sensitivity.csv` | seuil de rentabilite recalcule en changeant une hypothese a la fois | oui |
| `reports/figures/campagnes_*.png` | calibration, sensibilite au taux de reactivation | oui |
| `data/processed/campaign_targets_2011-09-01.parquet` | identifiants clients cibles et rang de risque, sans contact | non |

## Executer et verifier

Apres les etapes 1 a 3 (le notebook 04 lit `churn_test_predictions.parquet`) :

```powershell
.\.venv\Scripts\python -m nbconvert --to notebook --execute --inplace notebooks\04_campaigns_simulation.ipynb
.\.venv\Scripts\python -m pytest -q tests                   # 22 tests
.\.venv\Scripts\python src/check_notebook_repro.py 04       # deux executions du notebook 04 (sans argument : 02, 03 et 04)
.\.venv\Scripts\python src/data_prep.py --verify
```

## Une seule version des segments

Les campagnes utilisent **uniquement les segments du notebook 03** (standardisation et K-means ajustes sur 2010-06-01 a 2011-06-01, appliques au 2011-09-01 sans reajustement). Le notebook 04 ne lit jamais les segments du notebook 02. Il verifie que les effectifs par segment sont identiques a `reports/churn_by_segment.csv`.
Les deux versions portent les memes noms mais pas les memes frontieres (« Recents a developper » : 753 clients au notebook 02, 367 au notebook 03). Explication et tableau croise : `docs/etape3_churn.md`, section « Segments : difference entre les notebooks 02 et 03 ».

## Classer par risque, pas par probabilite

Le score de la regression logistique ne sert qu'a **classer** les clients dans leur segment (egalites departagees par identifiant). Sur le test, la probabilite moyenne (65,3 %) depasse le depart observe (57,2 %) de 8,1 points, jusqu'a 13,8 points au cinquieme decile ; le classement, lui, est monotone : le depart observe va de 6,7 % (decile 1) a 88,9 % (decile 10).
Le taux de depart p0 de chaque population ciblee est donc **observe** (jamais lu sur la probabilite) ; voir plus bas pour son statut retrospectif. Un test unitaire verifie que le ciblage ne depend pas du resultat observe.

## Les trois campagnes

Chaque population est definie a l'avance par un segment et une part des clients les plus a risque du segment. Les parts n'ont pas ete optimisees. Les trois populations sont disjointes.

| | Population | Clients | Action | Remise |
|---|---|---:|---|---|
| C1 | 25 % des Champions les plus a risque | 225 sur 899 | Fideliser sans brader : contact personnalise, acces anticipe | aucune |
| C2 | 50 % des Reguliers a risque les plus a risque | 917 sur 1 833 | Relancer avant la dormance : e-mail personnalise, offre limitee | 10 % |
| C3 | tous les Recents a developper | 367 | **Encourager le prochain achat** : bienvenue, produits complementaires | 5 % |

Les Endormis ne sont pas cibles (gain espere par client le plus faible, sans que ce soit prouve) ; les Champions les moins a risque ne recoivent rien.

| Mesure issue des donnees | C1 | C2 | C3 |
|---|---:|---:|---:|
| Depart observe sans campagne connue (p0, **observe retrospectivement**, non disponible au 2011-09-01) | 34,7 % | 66,4 % | 43,1 % |
| Probabilite moyenne predite (non calibree) | 43,1 % | 76,7 % | 57,3 % |
| Panier median historique (ventes brutes, GBP) | 360 | 303 | 258 |

## Formule du gain net (par campagne et scenario)

- clients qui partiraient = N x p0
- reactivation additionnelle = N x p0 x r, avec r = part des clients qui seraient partis et que la campagne fait racheter (**hypothese**)
- marge gagnee = reactivation x commandes x panier x facteur de panier x (m - d), avec m la marge et d la remise ; 1 commande par client reactive
- cannibalisation = N x (1 - p0) x s x panier x d : remises accordees a des clients qui auraient achete de toute facon (s = part d'entre eux qui utilise l'offre)
- **gain net = marge gagnee - cannibalisation - N x cout par contact - cout fixe**
- seuil de rentabilite : valeur de r pour laquelle le gain net est nul, **sous les hypotheses retenues** (il change des qu'on change la marge, un cout, l'usage des offres, le panier ou p0)

## Hypotheses (toutes sans source dans les donnees)

| | Prudent | Central | Optimiste |
|---|---|---|---|
| Reactivation r, C1 / C2 / C3 | 5 % / 3 % / 5 % | 10 % / 6 % / 8 % | 15 % / 10 % / 12 % |
| Marge m | 25 % | 30 % | 35 % |
| Cout par contact C1 (contact personnalise) | 8,00 GBP | 5,00 GBP | 3,00 GBP |
| Cout par contact C2 et C3 (e-mail) | 0,10 GBP | 0,05 GBP | 0,03 GBP |
| Cout fixe par campagne | 300 GBP | 200 GBP | 150 GBP |
| Usage de l'offre par les clients qui auraient achete, C2 / C3 | 20 % / 15 % | 15 % / 10 % | 10 % / 5 % |
| Facteur de panier des clients reactives | 0,8 | 1,0 | 1,0 |

Le scenario prudent cumule toutes les hypotheses defavorables : il est plus severe que chacune prise seule. A verifier sur les sites officiels avant usage reel : les limites d'envoi des offres gratuites d'outils comme Brevo.

## Resultats : SIMULATION, gain net en GBP

| | Prudent | Central | Optimiste | Seuil de rentabilite de r (central, sous hypotheses) | r suppose (central) |
|---|---:|---:|---:|---:|---:|
| C1. Champions a risque | -1 819 | -483 | +648 | 15,7 % | 10 % |
| C2. Reguliers a risque | -1 596 | +570 | +3 508 | 4,5 % | 6 % |
| C3. Recents a developper | -415 | +328 | +1 174 | 4,8 % | 8 % |
| **Total** | **-3 830** | **+415** | **+5 330** | | |

Scenario central, composantes (GBP) :

| | Clients qui partiraient | Clients reactives | Marge gagnee | Cannibalisation | Contacts | Cout fixe | Gain net |
|---|---:|---:|---:|---:|---:|---:|---:|
| C1 | 78 | 7,8 | 842 | 0 | 1 125 | 200 | -483 |
| C2 | 609 | 36,5 | 2 218 | 1 402 | 46 | 200 | +570 |
| C3 | 158 | 12,6 | 816 | 270 | 18 | 200 | +328 |

Lecture :
- Le signe du resultat depend des hypotheses : le total va de -3 830 a +5 330 GBP. Le central, +415 GBP pour 1 509 clients, soit environ 0,28 GBP par client, est a peine positif.
- C1 est negative au central : les contacts coutent 1 125 GBP pour 842 GBP de marge. A r = 10 %, il faudrait un cout par contact d'au plus 2,85 GBP pour atteindre l'equilibre en couvrant le cout fixe.
- C2 : la cannibalisation absorbe 63 % de la marge gagnee.
- Les seuils de rentabilite donnent un ordre de grandeur de l'effort necessaire **pour ce jeu d'hypotheses** ; ils ne sont pas plus fiables que les hypotheses (voir le tableau de sensibilite ci-dessous).
- Utiliser les probabilites brutes comme p0 gonflerait le gain central de 773 GBP pour C2 (570 a 1 343), de 338 GBP pour C3 (328 a 666) et de 204 GBP pour C1 (-483 a -280).

### Les seuils de rentabilite dependent des hypotheses

Seuil de r (scenario central), en changeant **une seule hypothese a la fois** (`reports/campaigns_breakeven_sensitivity.csv`) :

| Variation | C1 | C2 | C3 |
|---|---:|---:|---:|
| Reference (central) | 15,7 % | 4,5 % | 4,8 % |
| Marge 25 % au lieu de 30 % | 18,9 % | 5,9 % | 6,0 % |
| Marge 35 % au lieu de 30 % | 13,5 % | 3,6 % | 4,0 % |
| Cout par contact x 2 | 29,1 % | 4,6 % | 5,0 % |
| Cout par contact / 2 | 9,1 % | 4,4 % | 4,7 % |
| Usage de l'offre x 2 (clients qui auraient achete) | 15,7 % | 8,3 % | 7,4 % |
| Panier historique - 20 % | 19,7 % | 4,6 % | 5,3 % |
| p0 - 10 points | 22,1 % | 6,6 % | 6,8 % |
| p0 + 10 points | 12,2 % | 2,9 % | 3,5 % |

## Mesurer un effet reel : pas possible avec ces effectifs

Avec un groupe temoin tire au sort (moitie des clients), l'ecart minimal detectable (risque 5 %, puissance 80 %) est de 17,8 points (C1), 8,7 points (C2) et 14,5 points (C3), contre un ecart suppose de 3,5, 4,0 et 3,4 points. Il faudrait environ 2 959, 2 206 et 3 245 clients par groupe. Aucun gain ne peut etre attribue a une campagne sans groupe temoin ; avec une seule vague de cette taille, il ne serait pas detectable.

## Limites

- Simulation : r, m, couts, usage des offres et facteur de panier sans source. A remplacer par la marge reelle, le cout reel d'un envoi ou d'un appel, l'historique de reponse aux offres.
- p0 est observe retrospectivement (2011-09-01 a 2011-11-30) : il n'etait pas disponible a la date fictive de lancement. Pour une campagne reelle, il faut l'estimer sur une periode precedente ; le taux de depart des instantanes varie de 41,7 % a 67,1 %.
- Les donnees ne contiennent rien sur les messages, promotions ou appels recus par les clients : on ne sait pas s'ils ont recu d'autres campagnes. p0 peut inclure l'effet d'actions marketing inconnues.
- Les seuils de rentabilite sont conditionnels aux hypotheses et a p0 : ce ne sont pas des resultats des donnees.
- Risque n'est pas receptivite : un client tres a risque n'est pas forcement recuperable. Cibler ceux qui reagiraient demande un test avec groupe temoin.
- Paniers bruts : retours non deduits. Environ 8 Champions sur 10 ont un retour avant la date (segment Champions du notebook 02) : le panier de C1 peut etre surevalue.
- Une commande par client reactive, sans valeur sur la duree de vie. Pas de cout de fatigue marketing, de TVA ou de change. Monnaie : GBP.
- Populations petites (225, 917, 367 clients). Les effectifs dependent de la version des segments.
- Endormis non simules.
- Le test du notebook 03 n'est pas vierge (voir `docs/etape3_churn.md`). Le ciblage de l'etape 4 n'utilise ni le seuil ni le churn observe : seulement le segment et le rang de risque.

## Points a valider

1. Les parts ciblees (25 %, 50 %, 100 %) et le choix de ne pas cibler les Endormis.
2. Les hypotheses du tableau, en particulier r, la marge et le cout par contact de C1.
3. Le choix de la version 03 des segments pour les campagnes.
4. Le panier historique en ventes brutes, ou deduit des retours.
