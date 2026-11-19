# Segmentation RFM et prédiction du départ client

Projet de l'équipe 5, module Webmarketing et CRM (TDIA3, semestre 5, 2026/2027), Pr Sara OUALD CHAIB.
Équipe (d'après la capture du planning) : Siham Al yassoul, Rim Mazgout, Brahim Chehba.

À partir d'un jeu de données e-commerce public, le projet calcule les indicateurs RFM (récence, fréquence, montant), forme quatre segments de clients par K-means, prédit quels clients n'achèteront pas dans les 90 jours, puis simule trois campagnes ciblées avec un gain net attendu.

**Les gains de campagne sont des simulations.** Aucun message n'a été envoyé, les données ne contiennent ni adresse e-mail ni résultat de campagne, et le taux de réactivation, la marge et les coûts sont des hypothèses.

## 1. Source des données

- **Jeu :** Online Retail II, UCI Machine Learning Repository, https://archive.ics.uci.edu/dataset/502/online+retail+ii
- **Citation :** Chen, D. (2012). Online Retail II [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5CG6D
- **Licence :** Creative Commons Attribution 4.0 (CC BY 4.0) selon la page UCI : partage et adaptation autorisés avec citation de la source.
- **Contenu :** 1 067 371 lignes de transactions d'un détaillant en ligne britannique, du 2009-12-01 au 2011-12-09. Il vend surtout des articles cadeaux ; beaucoup de clients sont des grossistes.
- **Téléchargement :** automatique, par `src/data_prep.py` (zip de 45,6 Mo). Le script compare l'empreinte SHA-256 du zip à une valeur épinglée (`572E3627…E67BFB`). UCI ne publie pas d'empreinte : la valeur sert à détecter un changement de la source, pas à prouver son authenticité.
- **Les données ne sont pas dans le dépôt** (`data/` est ignoré par git).

## 2. Installation et exécution

**Prérequis :** Windows, PowerShell, Python 3.11, accès à Internet pour le premier téléchargement. Les commandes sont à lancer depuis la racine du dépôt.

```powershell
# a. Environnement (une seule fois)
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m ipykernel install --sys-prefix --name python3

# b. Étape 1 : téléchargement, nettoyage, bilan qualité
.\.venv\Scripts\python src/data_prep.py

# c. Étapes 2 à 4 : les trois notebooks, dans cet ordre
.\.venv\Scripts\python -m nbconvert --to notebook --execute --inplace notebooks\02_rfm_segmentation.ipynb
.\.venv\Scripts\python -m nbconvert --to notebook --execute --inplace notebooks\03_churn_prediction.ipynb
.\.venv\Scripts\python -m nbconvert --to notebook --execute --inplace notebooks\04_campaigns_simulation.ipynb

# d. Vérifications
.\.venv\Scripts\python -m pytest -q tests
.\.venv\Scripts\python src/data_prep.py --verify
.\.venv\Scripts\python src/check_notebook_repro.py        # exécute chaque notebook deux fois et compare
```

**L'ordre compte.** Le notebook 03 lit les segments produits par le 02 (pour les comparer aux siens) ; le 04 lit les prédictions produites par le 03. Chaque notebook commence par `data_prep.verify()` et s'arrête si les données ne correspondent pas au rapport de l'étape 1.

**Durées mesurées** sur cette machine, dans une copie propre (sans `data/`, `reports/` ni `.venv`) : création du venv 25 s, `pip install` 284 s, `data_prep.py` 135 s, notebook 02 30 s, notebook 03 109 s, notebook 04 15 s, tests 7 s, `--verify` 1 s, `check_notebook_repro.py` 301 s.

**À savoir :**
- Utiliser `python -m nbconvert` et non `python -m jupyter` : sur certaines machines, ce dernier appelle le `jupyter` d'une autre installation de Python, qui n'a pas pandas.
- `--inplace` réécrit le notebook avec ses sorties. Pour garder l'original, remplacer par `--output <nom>`.
- Pour ouvrir un notebook de façon interactive, choisir le noyau du `.venv` (Jupyter ou VS Code). Le notebook retrouve la racine du dépôt si le dossier de travail est la racine ou `notebooks/`.
- Premier lancement de `data_prep.py` : téléchargement et lecture du fichier Excel, environ 2 minutes (135 s mesurés, selon la connexion). Les lancements suivants réutilisent un cache parquet **uniquement s'il est cohérent** avec le zip, l'Excel et le manifeste ; sinon il est reconstruit. Si le zip lui-même a changé, le script s'arrête (`--accept-source-change` pour l'accepter).

## 3. Contenu du dépôt

| Chemin | Rôle |
|---|---|
| `src/data_prep.py` | téléchargement, vérification des empreintes, nettoyage, bilan qualité, `--verify` |
| `src/rfm.py` | RFM à une date de référence, `Segmenter`, nommage des segments |
| `src/churn.py` | variables, étiquettes à 90 jours, contrôle du plan temporel |
| `src/campaigns.py` | ciblage par rang de risque, formule du gain, tailles de test |
| `src/check_notebook_repro.py` | exécute chaque notebook deux fois et compare les résultats |
| `notebooks/02_rfm_segmentation.ipynb` | indicateurs RFM et quatre segments (version « 02 ») |
| `notebooks/03_churn_prediction.ipynb` | prédiction du churn (version « 03 » des segments) |
| `notebooks/04_campaigns_simulation.ipynb` | trois campagnes, gains **simulés** |
| `tests/` | 22 tests (RFM, churn, campagnes) |
| `reports/` | bilan qualité des données, tableaux de résultats (CSV), figures |
| `docs/etape1_donnees.md` … `etape4_campagnes.md` | documentation détaillée de chaque étape |

## 4. Principaux résultats

**Données (étape 1).** 1 067 371 lignes brutes, dont 22,77 % sans identifiant client. Après nettoyage : 788 127 lignes d'achat, 5 852 clients, 36 594 factures. Les retours (factures C*) ne sont pas déduits : les montants sont des **ventes brutes**.

**RFM et segments (étape 2, au 2011-09-01, 5 224 clients actifs).**

| Segment | Clients | Part des ventes brutes | Action |
|---|---:|---:|---|
| Champions | 851 | 67,2 % | fidéliser sans brader |
| Réguliers à risque | 1 530 | 23,0 % | relancer avant la dormance |
| Récents à développer | 753 | 4,5 % | encourager le prochain achat |
| Endormis | 2 090 | 5,3 % | réactiver à coût plafonné |

**Churn à 90 jours (étape 3).** Test au 2011-09-01 (fenêtre jusqu'au 2011-11-30), 5 224 clients, 57,2 % de départ. Entraînement : 4 instantanés trimestriels du 2010-06-01 au 2011-03-01 ; validation : 2011-06-01.

| | Précision | Rappel | F1 | AUC |
|---|---:|---:|---:|---:|
| Tous prédits churn | 0,572 | 1,000 | 0,728 | 0,500 |
| Règle de récence (> 105 jours) | 0,734 | 0,764 | 0,749 | 0,760 |
| Régression logistique (retenue) | 0,723 | 0,865 | 0,788 | 0,795 |
| Forêt aléatoire | 0,722 | 0,857 | 0,784 | 0,797 |

- Logistique et forêt ne se distinguent pas (écart d'AUC de +0,003, intervalle [-0,000 ; 0,006]). Elles dépassent la règle de récence de 0,035 d'AUC.
- Chez les clients encore actifs (récence ≤ 180 jours), l'AUC passe de 0,658 (règle) à 0,764 (logistique). Dans les 20 % de clients les plus à risque, la règle est aussi bonne que les modèles (précision de 0,869).

**Campagnes (étape 4, SIMULATION, gain net en GBP).**

| | Prudent | Central | Optimiste |
|---|---:|---:|---:|
| C1. Champions à risque (225 clients) | -1 819 | -483 | +648 |
| C2. Réguliers à risque (917 clients) | -1 596 | +570 | +3 508 |
| C3. Récents à développer (367 clients) | -415 | +328 | +1 174 |
| Total | -3 830 | +415 | +5 330 |

Le signe dépend des hypothèses. Les seuils de rentabilité du taux de réactivation (15,7 %, 4,5 % et 4,8 % au central) dépendent eux aussi de la marge, des coûts, de l'usage des offres, du panier et du taux de départ. Détails dans `docs/etape4_campagnes.md`.

## 5. Deux versions des segments

Les notebooks 02 et 03 donnent **les mêmes quatre noms**, mais **pas les mêmes frontières**. Elles partagent 90,8 % des clients (indice de Rand ajusté de 0,806).

| | Version « 02 » | Version « 03 » |
|---|---|---|
| Notebook | `02_rfm_segmentation.ipynb` | `03_churn_prediction.ipynb` |
| Ajustement (standardisation + K-means, k = 4, graine 42) | les 5 224 clients actifs au 2011-09-01 | 19 642 lignes de cinq instantanés (2010-06-01 à 2011-06-01) |
| Application | aux mêmes clients, à la même date | aux clients du 2011-09-01, sans réajustement |
| Usage | décrire une photographie à une date | relier les segments au modèle de churn, ajusté avant la période évaluée |
| Champions / Réguliers / Récents / Endormis | 851 / 1 530 / 753 / 2 090 | 899 / 1 833 / 367 / 2 125 |
| « Récents à développer » | récence médiane 30 j, 3 factures | récence médiane 16 j, 2 factures |
| Utilisée par | tableau de la section 4 ci-dessus (RFM) | notebooks 03 et 04 (churn par segment, campagnes) |

Sur les 753 « Récents » de la version 02, 367 le restent dans la version 03 ; 247 passent en « Réguliers à risque », 109 en « Endormis » et 30 en « Champions ». Les trois autres segments bougent peu. Le tableau croisé complet est dans `reports/churn_segments_nb02_vs_nb03.csv`.
**Les campagnes n'utilisent que la version 03.** Les effectifs de la section 4 (étape 2) et ceux des campagnes viennent donc de deux versions différentes.

## 6. Limites

- **Ventes brutes.** Les retours ne sont pas déduits (33 clients ont des retours supérieurs à la moitié de leurs ventes brutes au 2011-09-01). Le panier des campagnes est aussi brut.
- **Données.** Un détaillant britannique (90 % des lignes), beaucoup de grossistes, deux ans de données avec une forte saisonnalité, historique tronqué à gauche (début en décembre 2009), 22,77 % des lignes sans identifiant client exclues. Peu transposable tel quel à une entreprise marocaine.
- **Le churn est une inactivité de 90 jours**, pas une résiliation. Un client saisonnier peut être classé « parti » à tort.
- **Un seul test, en haute saison.** Le taux de départ des instantanés varie de 41,7 % à 67,1 %. Les probabilités du modèle surestiment le départ de 5 à 14 points selon les segments : elles servent à **classer** les clients, pas à chiffrer.
- **Le test n'est pas strictement vierge.** Le critère de seuil (F1 puis indice de Youden), des indicateurs, la règle de choix du modèle, les dates et le sous-groupe de clients actifs ont été fixés ou révisés après avoir vu des résultats du test. La liste complète est dans `docs/etape3_churn.md`. L'AUC, indépendante du seuil, est la mesure la plus robuste.
- **Campagnes : simulation.** Le taux de départ « sans campagne » est **observé rétrospectivement** : il n'était pas disponible à la date fictive de lancement. Les données ne permettent pas de savoir si les clients ont reçu d'autres campagnes. Les seuils de rentabilité dépendent des hypothèses.
- **Aucun effet mesuré.** Détecter l'écart supposé demanderait environ 2 200 à 3 200 clients par groupe, bien plus que les populations ciblées.

## 7. Scénario de démonstration de quatre minutes

Format du cours : 12 minutes de présentation et démonstration, dont 4 minutes de démonstration d'un prototype en fonctionnement, avec une vidéo courte de secours. La démonstration est faite par la personne 2.

**Avant la séance (à faire la veille).**
1. Lancer toute la chaîne (section 2) et `python src/check_notebook_repro.py`.
2. Ouvrir les trois notebooks **déjà exécutés** (leurs sorties sont enregistrées) dans trois onglets, et un terminal PowerShell à la racine du dépôt.
3. Enregistrer une vidéo de 60 à 90 secondes de ce parcours comme secours.
4. Ne pas relancer un notebook en direct : le 03 prend environ 2 minutes, et un incident réseau ou de noyau coûterait la démonstration.

| Temps | Quoi montrer | Message |
|---|---|---|
| 0:00 – 0:30 | Terminal : `python src/data_prep.py --verify` (quelques secondes), puis le début du README (source, licence) | Données publiques, source vérifiée par empreintes, rien d'ancien réutilisé en silence |
| 0:30 – 1:15 | Notebook 02 : tableau des segments et figure des profils | Quatre segments nommés, une action chacun ; ventes **brutes** ; test d'absence de fuite réussi |
| 1:15 – 2:30 | Notebook 03 : plan temporel (dates, effectifs, taux de churn), tableau de résultats, matrices de confusion | Variables avant la date, étiquette sur les 90 jours suivants ; les modèles battent la règle de récence (AUC 0,795 contre 0,760), surtout chez les clients encore actifs ; ce qui a été révisé après le test |
| 2:30 – 3:30 | Notebook 04 : bandeau « SIMULATION », tableau des gains, tableau de sensibilité du seuil | Trois campagnes, gains de -3 830 à +5 330 GBP selon les hypothèses ; seuils de rentabilité conditionnels ; aucun message envoyé |
| 3:30 – 4:00 | Section 6 du README | Limites ; test avec groupe témoin comme prochaine étape |

**Questions probables.** Pourquoi deux versions des segments (section 5) ? Pourquoi le seuil a-t-il changé (F1 puis Youden, `docs/etape3_churn.md`) ? D'où viennent la marge et le taux de réactivation (hypothèses, sans source dans les données) ?

## 8. Reproductibilité

- Graine 42 partout ; forêt aléatoire avec `n_jobs=1` ; versions des bibliothèques figées dans `requirements.txt`.
- `check_notebook_repro.py` exécute chaque notebook deux fois et compare le contenu des fichiers produits (parquet par valeurs, CSV par SHA-256).
- `data_prep.py --verify` compare les empreintes du zip, de l'Excel, du cache et des tables nettoyées à celles du rapport.
- Une autre version de Python ou de scikit-learn peut changer l'affectation des clusters ou des arbres.
- **Parcours complet vérifié dans une copie propre** (aucune donnée, aucun rapport, nouvel environnement virtuel, commandes de la section 2 telles quelles) : toutes les étapes se terminent sans erreur, les 22 tests passent, `--verify` ne signale aucun écart, `check_notebook_repro.py` confirme que les trois notebooks sont reproductibles. Les 11 CSV de `reports/`, le rapport Markdown et les cinq fichiers parquet produits sont identiques octet pour octet à ceux du dépôt de travail. Seul le rapport JSON diffère, par un champ qui indique si le cache brut a été réutilisé ou reconstruit lors de l'exécution.

## 9. Documentation détaillée

- `docs/etape1_donnees.md` : source, règle produit/non produit, cohérence zip, Excel, cache, rapport.
- `docs/etape2_rfm.md` : définitions RFM, préparation, segments, limites.
- `docs/etape3_churn.md` : plan temporel, protections contre l'utilisation du futur, résultats, révisions après observation du test, cohérence du seuil avec le modèle ré-ajusté, différence entre les segments 02 et 03.
- `docs/etape4_campagnes.md` : campagnes, formule, hypothèses, sensibilité, taille de test.
