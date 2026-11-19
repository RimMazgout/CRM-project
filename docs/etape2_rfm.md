# Etape 2 : RFM et quatre segments K-means

Perimetre : indicateurs RFM a une date de reference explicite, preparation des variables, quatre segments K-means nommes avec une action marketing chacun. Le modele de churn et les campagnes chiffrees ne sont pas traites ici.

## Fichiers

| Fichier | Role | Versionne |
|---|---|---|
| `notebooks/02_rfm_segmentation.ipynb` | notebook livrable, sorties incluses | oui |
| `src/rfm.py` | `build_rfm`, `returns_summary_before`, `log_features` ; `name_segments` et `Segmenter` ajoutes a l'etape 3 | oui |
| `tests/test_rfm.py` | 5 tests sur un jeu construit a la main (l'etape 3 ajoute `tests/test_churn.py`) | oui |
| `src/check_notebook_repro.py` | execute un notebook deux fois et compare les resultats (02 et 03) | oui |
| `reports/rfm_segments_summary.csv` | profil des 4 segments | oui |
| `reports/figures/rfm_*.png` | 4 figures du notebook | oui |
| `data/processed/rfm_segments_2011-09-01.parquet` | un client par ligne : R, F, M, segment | non |

## Executer

Apres l'etape 1 (`python src/data_prep.py`), depuis la racine du depot, sous PowerShell :

```powershell
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m ipykernel install --sys-prefix --name python3    # une seule fois
.\.venv\Scripts\python -m nbconvert --to notebook --execute --inplace notebooks\02_rfm_segmentation.ipynb
```

Utiliser `python -m nbconvert` et non `python -m jupyter` : ce dernier appelle le `jupyter` du PATH, qui peut appartenir a une autre installation de Python (c'est le cas sur cette machine) et ne trouve alors pas pandas.
Pour ouvrir le notebook de maniere interactive, lancer Jupyter ou VS Code avec le noyau du `.venv`. Le notebook retrouve la racine du depot si le dossier de travail est la racine ou `notebooks/`.

Au debut, le notebook appelle `data_prep.verify()` et s'arrete si les fichiers de donnees ne correspondent pas au rapport de l'etape 1.

## Verifier

```powershell
.\.venv\Scripts\python -m pytest -q tests                  # 12 tests depuis l'etape 3 (5 pour test_rfm.py)
.\.venv\Scripts\python src/check_notebook_repro.py 02      # 2 executions du notebook 02, comparaison des resultats
.\.venv\Scripts\python src/data_prep.py --verify           # empreintes des donnees (inclut purchases et returns)
```

`--verify` compare maintenant les SHA-256 de `purchases.parquet` et `returns.parquet` (et de `raw.parquet`) a ceux enregistres dans la section `caches` de `reports/data_quality_report.json`.

## Definitions et choix

**Date de reference T = 2011-09-01.** Seules les lignes avec `InvoiceDate < T` sont lues. Les donnees finissent le 2011-12-09 : T laisse 99 jours, donc la fenetre de 90 jours du futur churn sera entierement observable. A valider.

| Indicateur | Definition |
|---|---|
| `recency_days` | jours entiers entre le dernier achat et T (0 = achat de la veille) |
| `frequency` | nombre de factures de vente distinctes avant T |
| `monetary_brut_gbp` | somme de `Quantity x Price` avant T, **retours non deduits** |

Les montants sont des ventes brutes. Le mot « net » n'est pas utilise. Les retours avant T servent uniquement a decrire les segments (part de clients avec retour, liste des clients dont les retours depassent la moitie des ventes).

**Preparation.** `log(1 + x)` sur R, F, M (asymetries avant : 0,69 / 10,43 / 24,04 ; apres : -0,98 / 1,06 / 0,27), puis `StandardScaler`. Aucun client n'est supprime pour valeur extreme.

**K-means.** k = 4 (impose), `n_init=20`, graine 42.

## Protection contre l'utilisation du futur

1. `build_rfm` filtre `InvoiceDate < T` avant tout calcul et verifie que le dernier achat retenu est anterieur a T.
2. Le notebook et `tests/test_rfm.py` montrent que le resultat est identique si on supprime les lignes datees de T ou apres, ou si on les falsifie (montants x 1 000, identifiants decales).
3. Test de bord : une ligne datee exactement de T est exclue.
4. La recence se calcule par rapport a T, pas a la derniere date du jeu.

Ce qui n'est pas encore protege : le `StandardScaler` et le K-means sont ajustes sur la population de T. C'est correct pour decrire les segments. Pour le modele de churn, ils devront etre ajustes sur la periode d'entrainement seulement.

## Resultats (T = 2011-09-01, 5 224 clients)

| Segment | Clients | Part des clients | Part des ventes brutes | R mediane (j) | F mediane | M mediane (GBP) |
|---|---:|---:|---:|---:|---:|---:|
| Champions | 851 | 16,3 % | 67,2 % | 21 | 14 | 5 288 |
| Reguliers a risque | 1 530 | 29,3 % | 23,0 % | 168 | 5 | 1 484 |
| Recents a developper | 753 | 14,4 % | 4,5 % | 30 | 3 | 644 |
| Endormis | 2 090 | 40,0 % | 5,3 % | 318 | 1 | 294 |

Actions proposees : voir la section 6 du notebook. Pour « Recents a developper », l'action est formulee « encourager le prochain achat ».
Qualite du decoupage : silhouette de 0,379 pour k = 4 (0,454 pour k = 2) ; les segments decoupent un continuum. Stabilite : indice de Rand ajuste minimal de 0,977 sur 10 graines.

## Reproductibilite

| Verification | Resultat |
|---|---|
| `python -m pytest -q tests` | 12 passes (dont 5 pour `test_rfm.py`) |
| `python src/check_notebook_repro.py 02` | 2 executions identiques (contenu du parquet de segments et SHA-256 du CSV de profil), identiques a l'etat precedent |
| Execution du notebook (`nbconvert`) | code 0, aucune cellule en erreur |
| `python src/data_prep.py --verify` | tous les controles OK |

Hypotheses de reproductibilite : memes versions de bibliotheques (`requirements.txt`), memes donnees (empreintes verifiees), graine fixe. Un autre systeme ou une autre version de scikit-learn peut changer l'ordre ou l'affectation des clusters. Les noms des segments viennent d'une regle sur les medianes, donc ils ne dependent pas de la numerotation.

## Limites

- Ventes brutes : 33 clients (0,63 %) ont des retours avant T superieurs a la moitie de leurs ventes ; le client 12346 a 77 353 GBP de ventes brutes et 77 184 GBP de retours. Il est classe « Reguliers a risque » alors que sa valeur reelle est proche de zero.
- 22,77 % des lignes brutes sans identifiant client sont hors analyse.
- Un detaillant britannique, beaucoup de grossistes, deux ans de donnees, forte saisonnalite.
- 628 clients qui achetent apres T n'avaient jamais achete avant : ils n'ont pas de segment a T.
- Les noms et la regle de nommage sont calibres sur ce jeu et cette date.
- Les segments sont descriptifs. Ils ne mesurent aucun effet d'une action marketing.

## Points a valider

1. Date de reference T = 2011-09-01.
2. Noms des segments et actions marketing.
3. Garder les ventes brutes comme montant du RFM, ou deduire les retours (avec renommage explicite) ?
4. Le notebook embarque ses images : il pese environ 300 Ko. Garder les sorties dans le depot, ou les retirer ?
