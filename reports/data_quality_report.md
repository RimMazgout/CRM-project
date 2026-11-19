# Bilan qualite des donnees - Online Retail II

Genere par `python src/data_prep.py`. Ne pas editer a la main.

## Provenance
- URL : https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip
- Zip : 45,622,418 octets, SHA-256 `572E36277C2390FBFDE10664750731E0A86F55E33470D91919085F0408E67BFB`
- Valeur epinglee dans le script : `572E36277C2390FBFDE10664750731E0A86F55E33470D91919085F0408E67BFB` ; conforme : True ; changement accepte : False
- Excel extrait (`online_retail_II.xlsx`) : 45,622,278 octets, SHA-256 `BCBE73B35F5B7BABF197FB0CB983A11F5D9FF929078D4AA53D171B1F2DF2E980` ; identique au contenu du zip : True
- Le cache parquet n'est reutilise que si le manifeste porte ces deux empreintes (voir `--verify`).

## Donnees brutes
- Lignes : 1,067,371  ({'Year 2010-2011': 541910, 'Year 2009-2010': 525461})
- Periode par feuille : {'Year 2009-2010': ['2009-12-01 07:45:00', '2010-12-09 20:01:00'], 'Year 2010-2011': ['2010-12-01 08:26:00', '2011-12-09 12:50:00']}
- Customer ID manquant : 22.77 % des lignes
- Annulations (factures C*) : 1.83 % des lignes
- Quantites negatives hors annulation : 3,457
- Prix <= 0 : 6,207
- Valeurs manquantes par colonne : {'Invoice': 0, 'StockCode': 0, 'Description': 4382, 'Quantity': 0, 'InvoiceDate': 0, 'Price': 0, 'Customer ID': 243007, 'Country': 0}

## Etapes de nettoyage

| Etape | Lignes retirees | Lignes restantes | Note |
|---|---:|---:|---|
| lignes brutes | 0 | 1,067,371 |  |
| chevauchement entre feuilles (copie identique retiree) | 22,523 | 1,044,848 | 2010-12-01 au 2010-12-09, copie verifiee identique |
| doublons exacts dans une meme feuille (CONSERVES) | 0 | 1,044,848 | 11812 lignes concernees, a valider |
| annulations / retours (factures C*) mis de cote | 19,165 | 1,025,683 | ecrits dans returns.parquet, non deduits |
| lignes non produit (regle documented) | 4,702 | 1,020,981 | frais, ajustements, tests, bons cadeaux |
| quantite <= 0 ou prix <= 0 | 5,972 | 1,015,009 | ajustements de stock, dettes, prix a 0 |
| Customer ID manquant | 226,882 | 788,127 | 2,576,013 GBP de montant brut hors analyse client |

## Achats nettoyes
- Lignes : 788,127 ; clients : 5,852 ; factures : 36,594
- Periode : 2009-12-01 07:45:00 -> 2011-12-09 12:50:00
- Montant brut total : 17,123,741.00 GBP (Quantity*Price des factures de vente, retours NON deduits)
- Clients avec une seule facture : 27.65 % ; mediane de factures par client : 3.0
- Top 5 pays (part des lignes, %) : {'United Kingdom': 90.22, 'Germany': 2.01, 'EIRE': 1.95, 'France': 1.66, 'Netherlands': 0.63}
- Quantite : p99 = 128.0, max = 80995.0
- Prix : p99 = 12.75, max = 649.5 ; montant de ligne max = 168,469.6

## Retours (non deduits)
- Lignes : 17,641 ; clients concernes : 2,445 (41.78 % des clients)
- Montant des retours : -713,031.25 GBP, soit 4.16 % du montant brut

## Regle produit / non produit

Un code est un frais ou un ajustement s'il figure dans la liste explicite (POST, DOT, C2, C3, 23444, M, B, D, S, GIFT, CRUK, BANK CHARGES, AMAZONFEE) ou correspond aux motifs `ADJUST*`, `TEST<n>`, `gift_0001_<n>` (casse ignoree). Tout autre code est un produit.

### Codes retires (factures de vente, avant filtres quantite/prix/client)

| Code | Lignes | dont avec Customer ID | Description |
|---|---:|---:|---|
| POST | 1,858 | 1,803 | POSTAGE |
| DOT | 1,422 | 16 | DOTCOM POSTAGE |
| M | 868 | 698 | Manual |
| C2 | 270 | 248 | CARRIAGE |
| 23444 | 80 | 79 | Next Day Carriage |
| ADJUST | 36 | 32 | Adjustment by john on 26/01/2010 16 |
| BANK CHARGES | 34 | 31 | Bank Charges |
| GIFT_0001_20 | 29 | 0 | Dotcomgiftshop Gift Voucher £20.00 |
| GIFT_0001_30 | 29 | 0 | Dotcomgiftshop Gift Voucher £30.00 |
| GIFT_0001_10 | 16 | 0 | Dotcomgiftshop Gift Voucher £10.00 |
| TEST001 | 11 | 11 | This is a test product. |
| GIFT_0001_50 | 8 | 0 | Dotcomgiftshop Gift Voucher £50.00 |
| GIFT_0001_40 | 7 | 0 | Dotcomgiftshop Gift Voucher £40.00 |
| B | 6 | 0 | Adjust bad debt |
| D | 5 | 5 | Discount |
| ADJUST2 | 3 | 3 | Adjustment by Peter on Jun 25 2010  |
| AMAZONFEE | 3 | 0 | AMAZON FEE |
| S | 3 | 0 | SAMPLES |
| GIFT_0001_80 | 3 | 0 | Dotcomgiftshop Gift Voucher £80.00 |
| GIFT_0001_70 | 3 | 0 | Dotcomgiftshop Gift Voucher £70.00 |
| GIFT_0001_90 | 2 | 0 |  |
| TEST002 | 2 | 1 | This is a test product. |
| GIFT_0001_60 | 2 | 0 |  |
| C3 | 1 | 0 |  |
| GIFT | 1 | 0 |  |

### Codes non numeriques conserves comme produits

| Code | Lignes | dont avec Customer ID | Description |
|---|---:|---:|---|
| DCGS0058 | 31 | 0 | MISO PRETTY  GUM |
| DCGSSGIRL | 25 | 0 | GIRLS PARTY BAG |
| DCGSSBOY | 23 | 0 | BOYS PARTY BAG |
| PADS | 18 | 18 | PADS TO MATCH ALL CUSHIONS |
| DCGS0076 | 14 | 0 | SUNJAR LED NIGHT NIGHT LIGHT |
| DCGS0003 | 14 | 0 | BOXED GLASS ASHTRAY |
| DCGS0069 | 6 | 0 | OOH LA LA DOGS COLLAR |
| DCGS0004 | 5 | 0 | HAYNES CAMPER SHOULDER BAG |
| DCGS0072 | 4 | 0 | CAT CAMOUFLAGUE COLLAR |
| DCGS0066N | 4 | 0 | NAVY CUDDLES DOG HOODIE |
| DCGS0068 | 3 | 0 | DOGS NIGHT COLLAR |
| DCGS0070 | 3 | 0 | CAMOUFLAGE DOG COLLAR |
| SP1002 | 3 | 2 | KID'S CHALKBOARD/EASEL |
| DCGS0037 | 2 | 0 | KEY-RING CORKSCREW |
| DCGS0062 | 2 | 0 | ROAD-RAGE CAR FRESHENER |
| DCGS0006 | 1 | 0 |  |
| DCGS0016 | 1 | 0 |  |
| DCGS0041 | 1 | 0 | HAYNES MINI-COOPER PLAYING CARDS |
| DCGS0036 | 1 | 0 |  |
| DCGS0027 | 1 | 0 |  |
| DCGS0066P | 1 | 0 |  |
| DCGS0060 | 1 | 0 |  |
| DCGS0057 | 1 | 0 |  |
| DCGS0059 | 1 | 0 |  |
| DCGS0056 | 1 | 0 |  |
| DCGS0044 | 1 | 0 | HANDZ-OFF CAR FRESHENER |
| DCGS0053 | 1 | 0 |  |
| DCGS0055 | 1 | 0 |  |
| DCGS0039 | 1 | 0 |  |
| DCGS0073 | 1 | 0 | ebay |

### Effet du changement de regle

Regle initiale = code ne commencant pas par 5 chiffres. Regle documentee = liste ci-dessus.

| Mesure | Regle initiale | Regle documentee | Ecart |
|---|---:|---:|---:|
| Lignes de vente avant filtre Customer ID | 1,014,945 | 1,015,009 | 64 |
| Montant brut avant filtre Customer ID (GBP) | 19,699,784.97 | 19,699,754.46 | -30.51 |
| Lignes d'achat (clients identifies) | 788,187 | 788,127 | -60 |
| Clients | 5,852 | 5,852 | 0 |
| Factures | 36,594 | 36,594 | 0 |
| Montant brut (GBP) | 17,124,926.23 | 17,123,741.00 | -1,185.23 |
| Lignes de retour | 17,641 | 17,641 | 0 |
| Montant des retours (GBP) | -713,009.65 | -713,031.25 | -21.60 |

## Controles d'integrite

- OK : zip_conforme_a_la_valeur_epinglee_ou_changement_accepte
- OK : xlsx_identique_au_contenu_du_zip
- OK : aucune_annulation_dans_achats
- OK : aucun_code_non_produit_dans_achats_ni_retours
- OK : quantite_et_prix_positifs
- OK : customer_id_sans_nan
- OK : aucun_doublon_inter_feuilles
- OK : retours_quantite_negative

## Lignes d'achat par mois

| Mois | Lignes |
|---|---:|
| 2009-12 | 30,690 |
| 2010-01 | 21,689 |
| 2010-02 | 23,287 |
| 2010-03 | 32,164 |
| 2010-04 | 27,124 |
| 2010-05 | 28,563 |
| 2010-06 | 31,095 |
| 2010-07 | 26,936 |
| 2010-08 | 26,311 |
| 2010-09 | 34,468 |
| 2010-10 | 49,413 |
| 2010-11 | 60,126 |
| 2010-12 | 26,056 |
| 2011-01 | 21,137 |
| 2011-02 | 19,851 |
| 2011-03 | 27,055 |
| 2011-04 | 22,555 |
| 2011-05 | 28,206 |
| 2011-06 | 27,070 |
| 2011-07 | 26,709 |
| 2011-08 | 26,891 |
| 2011-09 | 39,864 |
| 2011-10 | 49,359 |
| 2011-11 | 64,276 |
| 2011-12 | 17,232 |
