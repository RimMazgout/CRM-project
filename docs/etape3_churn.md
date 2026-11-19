# Etape 3 : prediction du churn a 90 jours

Perimetre : definition du churn, plan temporel, regression logistique, foret aleatoire, regle de recence, evaluation. Les campagnes et les hypotheses de gain ne sont pas traitees ici.

## Fichiers

| Fichier | Role | Versionne |
|---|---|---|
| `notebooks/03_churn_prediction.ipynb` | notebook livrable, sorties incluses | oui |
| `src/churn.py` | `build_features`, `build_labels`, `build_snapshot`, `check_temporal_plan` | oui |
| `src/rfm.py` | ajout de `name_segments` et de la classe `Segmenter` (ajustement sur l'entrainement, `predict` sans reajustement) | oui |
| `tests/test_churn.py` | 7 tests (etiquettes, bornes, fuite, plan temporel, Segmenter) | oui |
| `src/check_notebook_repro.py` | execute chaque notebook deux fois et compare les resultats (02 et 03) | oui |
| `reports/churn_metrics.csv` | metriques validation et test | oui |
| `reports/churn_snapshots.csv` | effectifs et taux de churn par instantane | oui |
| `reports/churn_by_segment.csv` | churn reel et predit par segment | oui |
| `reports/churn_returns_sensitivity.csv` | effet des variables de retours | oui |
| `reports/churn_threshold_consistency.csv` | seuil et modele reajuste : comparaison sur le test | oui |
| `reports/churn_segments_nb02_vs_nb03.csv` | tableau croise des segments des notebooks 02 et 03 | oui |
| `reports/figures/churn_*.png` | matrices de confusion, ROC, variables | oui |
| `data/processed/churn_test_predictions.parquet` | probabilites par client pour le test | non |

## Executer et verifier

Apres l'etape 1, depuis la racine du depot (voir `docs/etape2_rfm.md` pour l'enregistrement du noyau) :

```powershell
.\.venv\Scripts\python -m nbconvert --to notebook --execute --inplace notebooks\03_churn_prediction.ipynb   # une a deux minutes
.\.venv\Scripts\python -m pytest -q tests                  # 22 tests depuis l'etape 4 (5 RFM, 7 churn, 10 campagnes)
.\.venv\Scripts\python src/check_notebook_repro.py 03      # deux executions du notebook 03 (sans argument : 02, 03 et 04)
.\.venv\Scripts\python src/data_prep.py --verify           # empreintes des donnees
```

Le notebook commence par `data_prep.verify()` et s'arrete si les donnees different du rapport de l'etape 1.
Reproductibilite : graine 42, `n_jobs=1` pour la foret (somme des arbres dans un ordre fixe), memes versions de bibliotheques. `check_notebook_repro.py` compare le contenu du parquet de predictions et le SHA-256 des quatre CSV.

## Definitions

- **Churn a 90 jours.** A une date de reference T, un client actif a achete au moins une fois avant T. `churn = 1` s'il n'effectue aucun achat dans `[T, T + 90 jours)`. Un retour (facture C*) n'est pas un achat. C'est une inactivite, pas une resiliation.
- **Variables** (toutes calculees avec les lignes `< T`) : recence, frequence, montant brut, anciennete, panier moyen, ecart moyen entre factures, rapport recence / ecart moyen, factures et depenses sur 90 jours, factures sur les 90 jours precedents, produits distincts, pays de la derniere commande. Montants : ventes brutes, retours non deduits.
- **Population d'un instantane** : clients identifies ayant achete au moins une fois avant T.

## Plan temporel

| Role | Date T | Fin de la fenetre d'etiquette | Clients | Taux de churn |
|---|---|---|---:|---:|
| entrainement | 2010-06-01 | 2010-08-30 | 2 684 | 50,3 % |
| entrainement | 2010-09-01 | 2010-11-30 | 3 299 | 41,7 % |
| entrainement | 2010-12-01 | 2011-03-01 | 4 239 | 66,8 % |
| entrainement | 2011-03-01 | 2011-05-30 | 4 512 | 64,9 % |
| validation | 2011-06-01 | 2011-08-30 | 4 908 | 67,1 % |
| test | 2011-09-01 | 2011-11-30 | 5 224 | 57,2 % |

`check_temporal_plan` refuse tout plan dont une etiquette n'est connue qu'apres la date de la periode suivante. Les donnees vont jusqu'au 2011-12-09 : la fenetre du test est entierement observee. Un client apparait dans plusieurs instantanes avec des variables differentes (marche en avant).

## Protections contre l'utilisation du futur

1. Variables : filtre `InvoiceDate < T` (achats et retours), avec garde-fou. Etiquette : fenetre `[T, T + 90 j)`. Les deux fenetres ne se chevauchent pas.
2. Un instantane dont la fenetre d'etiquette depasse les donnees est refuse (erreur).
3. Tests (notebook et `tests/test_churn.py`) : les variables sont identiques si on falsifie tout ce qui est >= T ; les etiquettes sont identiques si on falsifie tout ce qui est >= T + 90 j ; les etiquettes changent si on retire la fenetre ; un achat exactement a T compte, un achat exactement a T + 90 j ne compte pas.
4. Imputation, `log1p`, standardisation et modeles : dans un `Pipeline` ajuste sur l'entrainement (puis entrainement + validation pour le modele final).
5. `Segmenter` (standardisation + K-means a 4 clusters) ajuste sur les lignes d'entrainement et de validation seulement, puis `predict` sur le test. Un test unitaire verifie que `predict` ne modifie ni les centres ni la moyenne de la standardisation. Les segments ne sont pas des variables d'entree des modeles : ils servent a lire le churn par groupe.
6. Hyperparametres et seuil choisis sur la validation ; le modele final est reajuste sur entrainement + validation puis evalue sur le test. **Le test n'est pas strictement vierge** : le critere de seuil et d'autres choix ont ete revises apres avoir vu des resultats du test (section « Choix revises apres avoir vu des resultats du test »).

## Resultats (test, 5 224 clients, 57,2 % de churn)

| | Precision | Rappel | F1 | AUC | Precision top 20 % |
|---|---:|---:|---:|---:|---:|
| Tous predits churn (reference) | 0,572 | 1,000 | 0,728 | 0,500 | 0,557 |
| Regle de recence (> 105 jours) | 0,734 | 0,764 | 0,749 | 0,760 | 0,869 |
| Regression logistique (seuil 0,59, C = 0,1) | 0,723 | 0,865 | 0,788 | 0,795 | 0,869 |
| Foret aleatoire (seuil 0,58, profondeur 5, feuille 20) | 0,722 | 0,857 | 0,784 | 0,797 | 0,873 |

Matrices de confusion (tn / fp / fn / tp) : regle 1 410 / 826 / 705 / 2 283 ; logistique 1 243 / 993 / 402 / 2 586 ; foret 1 251 / 985 / 428 / 2 560.

- AUC des deux modeles au-dessus de la regle : +0,035 et +0,037 (intervalles bootstrap a 95 % : [0,028 ; 0,043] et [0,030 ; 0,044]).
- Logistique et foret ne se distinguent pas : +0,003, intervalle [-0,000 ; 0,006].
- Clients encore actifs (recence <= 180 jours, 2 780 clients, 39,4 % de churn) : AUC 0,658 (regle), 0,764 (logistique), 0,763 (foret) ; rappel 0,357, 0,642, 0,609.
- Dans les 20 % de clients les plus a risque, la regle atteint la meme precision que les modeles.

**Modele retenu : la regression logistique.** AUC non distinguable de celui de la foret, lisible, plus facile a recalibrer. Details et arguments dans la section 11 du notebook.

## Choix revises apres avoir vu des resultats du test

Le test (2011-09-01) n'est pas strictement vierge. Voici ce qui a ete decide ou modifie apres avoir vu des resultats du test, dans l'ordre :

1. **Critere de seuil.** Un premier seuil maximisait le F1 sur la validation. Il predisait churn pour 82 a 83 % du test (rappel de 0,92 a 0,96, F1 de 0,76 a 0,79), alors que la reference « tous predits churn » donne un F1 de 0,728 : le F1 favorise la classe majoritaire quand plus de la moitie des clients partent. Nous avons remplace ce critere par l'indice de Youden (rappel + specificite - 1), qui ne depend pas du taux de churn. La degenerescence etait deja visible sur la validation (rappel de 0,95), mais le changement a ete decide apres avoir vu le test.
2. **Indicateurs ajoutes** apres la premiere lecture du test : la reference « tous predits churn », la precision dans les 20 % de clients les plus a risque et le score de Brier.
3. **Choix du modele.** A la validation, la regression logistique et la foret ont un AUC presque identique (0,8213 contre 0,8219) : sur la validation seule, le choix aurait ete arbitraire. La regle « a performance statistiquement egale, on garde le modele simple » a ete formulee apres avoir vu les intervalles du test. La logistique est retenue.
4. **Plan temporel et sous-groupe actif.** Les taux de churn et l'AUC de la recence de tous les instantanes, test compris, ont ete consultes avant de figer les dates. Le seuil de 180 jours du sous-groupe « clients encore actifs » a ete fixe apres avoir vu les effectifs du test. Les dates n'ont pas ete ajustees pour ameliorer un score.

Fixes a l'avance et non modifies : horizon de 90 jours, k = 4, graine 42, grilles d'hyperparametres, regle de departage a 0,0005 d'AUC.
Consequence pour la lecture : l'**AUC**, qui ne depend pas du seuil, est la mesure la plus robuste. Precision, rappel et F1 dependent d'un seuil dont le critere a ete revise. Toute conclusion sur le gain des modeles par rapport a la regle de recence doit tenir compte de ce statut.

## Coherence entre le seuil et le modele reajuste

Le seuil est choisi sur la validation avec un modele ajuste sur l'entrainement seul. Le modele final est reajuste sur entrainement + validation, puis evalue avec le meme seuil. Verification sur le test (section 6 du notebook, `reports/churn_threshold_consistency.csv`) :

| Regression logistique, seuil 0,59 | AUC | Precision | Rappel | F1 | Part predite churn | Proba. moyenne |
|---|---:|---:|---:|---:|---:|---:|
| ajuste sur l'entrainement seul | 0,794 | 0,728 | 0,852 | 0,785 | 66,9 % | 63,6 % |
| reajuste sur entrainement + validation (final) | 0,795 | 0,723 | 0,865 | 0,788 | 68,5 % | 65,3 % |

- Correlation de rang entre les deux versions : 0,9987 (logistique), 0,9927 (foret).
- Le reajustement deplace peu les scores : la probabilite moyenne monte de 1,7 point, la part predite churn de 1,6 point. Le meme seuil reste applicable.
- Le decalage important vient du **taux de churn** : 67,1 % a la validation, 57,2 % au test. Diagnostic (non utilise pour un choix) : un seuil choisi sur le test lui-meme augmenterait l'indice de Youden de 0,02 a 0,03.
- Conclusion : le seuil est coherent avec le modele reajuste a cette precision. Evaluer le modele ajuste sur l'entrainement seul donnerait des resultats quasi identiques.
## Retours

Ventes brutes conservees. Effets mesures dans le notebook (section 9) :
- 33 clients (0,63 %) avec des retours > 50 % de leurs ventes brutes (notebook 02).
- 24 des 2 236 clients non churn du test (1,07 %) ont, dans la fenetre, des retours >= 50 % de leurs achats : l'etiquette est un peu trop optimiste (borne haute).
- Les clients avec retour avant T partent moins (42,4 % contre 67,5 %), surtout parce qu'ils sont plus actifs. Ajouter des variables de retours ne change presque rien : AUC 0,795 → 0,795 (logistique), 0,797 → 0,798 (foret).

## Limites

- Un seul test, en haute saison (septembre a novembre 2011). Taux de churn de 41,7 % a 67,1 % selon l'instantane.
- Le seuil vient d'une validation a 67 % de churn et sert sur un test a 57 % : la precision baisse (0,83 → 0,72). Les probabilites moyennes depassent le churn reel dans chaque segment de 5 a 14 points. Elles ne sont pas calibrees pour chiffrer un gain.
- Le churn est une inactivite : un client saisonnier ou un grossiste peut etre classe parti a tort.
- Historique tronque a gauche (donnees depuis decembre 2009). Clients identifies seulement (22,77 % des lignes brutes exclues). Un detaillant britannique.
- Modeles de risque, pas d'effet d'une action. Les coefficients sont correles entre eux : la recence a un coefficient negatif (-0,20) alors qu'elle augmente le risque seule.
- Les intervalles bootstrap ne mesurent que la variabilite du jeu de test.
- Les lignes d'entrainement ne sont pas independantes (un client dans plusieurs instantanes) ; les grilles d'hyperparametres sont petites.

## Segments : difference entre les notebooks 02 et 03

Les deux notebooks donnent les memes quatre noms, mais pas les memes frontieres. Ils partagent 90,8 % des clients (indice de Rand ajuste de 0,806).

| | Notebook 02 | Notebook 03 |
|---|---|---|
| Ajustement (standardisation + K-means, k = 4, graine 42) | 5 224 clients actifs au 2011-09-01 | 19 642 lignes de cinq instantanes (2010-06-01 a 2011-06-01) |
| Application | memes clients, a la meme date | clients du 2011-09-01, sans reajustement |
| Usage | description d'une photographie a une date | lien avec le modele de churn, ajuste avant la periode evaluee |
| Recents a developper | 753 clients (recence mediane 30 j, 3 factures) | 367 clients (16 j, 2 factures) |

Tableau croise (lignes : notebook 02 ; colonnes : notebook 03) :

| | Champions | Reguliers a risque | Recents a developper | Endormis |
|---|---:|---:|---:|---:|
| Champions | 849 | 2 | 0 | 0 |
| Reguliers a risque | 20 | 1 510 | 0 | 0 |
| Recents a developper | 30 | 247 | 367 | 109 |
| Endormis | 0 | 74 | 0 | 2 016 |

Les « Recents a developper » sont le segment qui bouge : sur 753 clients du notebook 02, 367 le restent, 247 passent en « Reguliers a risque », 109 en « Endormis » et 30 en « Champions ». Les centres du notebook 03 sont estimes sur plusieurs saisons et sur un premier instantane a historique tronque, donc la frontiere entre « recent » et « regulier » se deplace.
**Version utilisee pour la suite : celle du notebook 03**, ajustee avant la periode evaluee et reliee au modele. Le notebook 02 reste une description exploratoire. Les campagnes de l'etape 4 n'utilisent que la version 03.

### Segments du notebook 03 et churn (modele retenu)

Churn reel : Champions 16,5 %, Reguliers a risque 54,3 %, Recents a developper 43,1 %, Endormis 79,4 %.
Action pour « Recents a developper » : **encourager le prochain achat**.
## Points a valider

1. Plan temporel : quatre instantanes d'entrainement, validation au 2011-06-01, test au 2011-09-01.
2. Modele retenu : logistique plutot que foret.
3. Critere de seuil (Youden) et le statut du test, non vierge (section « Choix revises apres avoir vu des resultats du test »).
4. Recalibration des probabilites avant le calcul de gains des campagnes (etape suivante).
5. Retours : ventes brutes en version 1, ou montant net en version 2.
