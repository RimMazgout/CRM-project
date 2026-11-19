# Etape 1 : source, chargement, nettoyage, bilan qualite

Equipe 5 : Segmentation RFM et prediction du depart client (churn).
Perimetre : cette etape ne calcule ni RFM, ni segments, ni churn.

## Exigences de la capture « Capture d'ecran 2026-11-18 233606.png »

Travail : a partir d'un jeu de donnees e-commerce public (Online Retail UCI ou Olist), calculer Recence, Frequence et Montant, segmenter par K-means, entrainer un modele de churn (regression logistique ou foret aleatoire), evaluer (precision, rappel, AUC).
Livrables : notebook Python, 4 segments nommes avec une action marketing par segment, 3 campagnes ciblees avec gain attendu chiffre.

## Source verifiee

- Jeu : Online Retail II, UCI Machine Learning Repository (page : https://archive.ics.uci.edu/dataset/502/online+retail+ii).
- Citation : Chen, D. (2012). Online Retail II [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5CG6D
- Licence indiquee sur la page UCI : Creative Commons Attribution 4.0 (CC BY 4.0). Partage et adaptation autorises pour tout usage, a condition de citer la source. Citer la reference ci-dessus dans les diapositives.
- Contenu annonce par UCI : transactions d'un detaillant en ligne britannique du 01/12/2009 au 09/12/2011, 1 067 371 instances, valeurs manquantes presentes. L'entreprise vend surtout des articles cadeaux et beaucoup de clients sont des grossistes.
- Le nombre de lignes lu (1 067 371) correspond a celui annonce par UCI.

## Coherence zip, Excel, cache parquet, rapport

UCI ne publie pas d'empreinte. Nous avons epingle dans le script (`PINNED_ZIP_SHA256`) celle du zip telecharge le premier jour. Elle detecte un changement de la source, elle ne prouve pas l'authenticite du fichier d'origine.

| Maillon | Controle a chaque execution | Si le controle echoue |
|---|---|---|
| Zip `online_retail_ii.zip` | SHA-256 egal a la valeur epinglee ; CRC internes valides (`testzip`) ; un seul `.xlsx` dedans | Arret avec message, aucun fichier ecrit. Option `--accept-source-change` pour accepter une nouvelle version (le rapport l'indique), puis mettre a jour la valeur epinglee |
| Excel `online_retail_II.xlsx` | SHA-256 egal a celui du fichier lu dans le zip | Extrait a nouveau depuis le zip |
| Cache `data/interim/raw.parquet` | Reutilise seulement si `manifest.json` porte les memes SHA-256 de zip et d'Excel, le meme `schema_version`, le meme SHA-256 du parquet et le meme nombre de lignes | Reconstruit depuis l'Excel, avec la raison affichee |
| Tables nettoyees et rapport | Recalculees a chaque execution a partir du cache valide ; le rapport contient les empreintes zip et Excel de cette execution | - |

Le manifeste est supprime au debut d'une reconstruction et ecrit en dernier : une reconstruction interrompue ne laisse pas de cache declare valide. Les fichiers sont ecrits dans un `.tmp` puis renommes.
`python src/data_prep.py --verify` recalcule toutes les empreintes sans rien reconstruire et compare zip, Excel, parquet, manifeste et rapport (code de sortie 1 en cas d'ecart). Il compare notamment les SHA-256 de `raw.parquet`, `purchases.parquet` et `returns.parquet` a ceux de la section `caches` du rapport JSON, ainsi que leur nombre de lignes. Un parquet illisible est signale comme ECHEC, sans interrompre le controle.

Limites :
- Un parquet modifie ET son manifeste reecrit a la main ne seraient pas detectes. Le controle protege contre l'obsolescence et l'alteration accidentelle, pas contre une falsification volontaire.
- Si la valeur epinglee est mise a jour apres un changement de source, c'est a l'equipe de verifier que la nouvelle version est legitime (comparer le nombre de lignes et le bilan).
- Les SHA-256 des fichiers parquet peuvent varier avec la version de pyarrow. Ils sont ecrits dans le JSON du rapport (section `caches`), pas dans le Markdown.

## Reproduire

Depuis la racine du depot, sous Windows PowerShell (Python 3.11) :

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python src/data_prep.py          # 1re execution : telechargement + lecture Excel (quelques minutes)
.\.venv\Scripts\python src/data_prep.py          # ensuite : cache valide reutilise, quelques secondes
.\.venv\Scripts\python src/data_prep.py --verify # controle des empreintes sans reconstruction
.\.venv\Scripts\python src/data_prep.py --force  # relit l'Excel meme si le cache est valide
.\.venv\Scripts\python src/data_prep.py --refresh-source  # retelecharge le zip
```

Sorties :

| Fichier | Versionne | Contenu |
|---|---|---|
| `data/raw/*` | non | zip et xlsx telecharges |
| `data/interim/raw.parquet`, `manifest.json` | non | donnees brutes (colonne `source_sheet` ajoutee) et leurs empreintes |
| `data/processed/purchases.parquet` | non | achats nettoyes de clients identifies |
| `data/processed/returns.parquet` | non | retours (factures C*) de clients identifies |
| `reports/data_quality_report.md` et `.json` | oui | bilan qualite chiffre |

## Regles de nettoyage (dans l'ordre)

1. Chevauchement du 1er au 9 decembre 2010 : les deux feuilles contiennent les memes 22 523 lignes. On verifie l'identite des deux copies (memes lignes et memes multiplicites), puis on retire celle de la feuille 2010-2011. Le script s'arrete si les copies different.
2. Doublons exacts a l'interieur d'une feuille : 11 812 lignes. **Conservees** par defaut, car une ligne repetee peut etre une vraie vente. Option `--drop-within-sheet-duplicates` pour les retirer. A valider.
3. Retours : factures dont le numero commence par `C`. Mises de cote dans `returns.parquet`.
4. Frais et ajustements : regle produit documentee ci-dessous.
5. Quantite ou prix inferieur ou egal a 0 dans les factures de vente.
6. `Customer ID` manquant : retire des tables clients.

## Regle produit / non produit

Premiere version : « le code commence par 5 chiffres ». Elle retirait a tort des articles reels (DCGS0058, DCGS0076, PADS, SP1002) et gardait un frais de transport a code numerique (23444, « Next Day Carriage »).

Regle retenue : un code est un frais ou un ajustement s'il figure dans la liste ci-dessous ou correspond a un motif (casse ignoree). **Tout autre code est un produit.** On part donc du principe qu'un code inconnu est un produit, et on liste ce qui ne l'est pas.

| Code | Nature |
|---|---|
| POST, DOT, C2, 23444 | frais de port et transport |
| M | saisie manuelle |
| B, D, C3, GIFT | ajustement de creance, remise, ajustements sans description |
| S | echantillons |
| CRUK | frais associatifs (n'apparait que dans des retours) |
| BANK CHARGES, AMAZONFEE | frais bancaires et Amazon |
| `ADJUST*` | ajustements |
| `TEST<n>` | produits de test |
| `gift_0001_<n>` | bons cadeaux : instrument de paiement, pas un article |

Construction de la liste : examen des 61 codes non numeriques (code, description, prix median, nombre de clients), puis recherche de mots-cles (postage, carriage, fee, adjust, discount, manual, sample, test, voucher, etc.) dans les descriptions des codes numeriques. Un seul code numerique est apparu comme service : 23444.

Codes non numeriques **conserves** comme produits : les articles `DCGS*` du site Dotcomgiftshop (aucun n'a de `Customer ID`, donc aucun n'entre dans les tables clients), `SP1002` (chevalet) et `PADS` (coussins, prix de 0,001 GBP). PADS est un cas limite : article reel mais prix symbolique, effet financier nul.

### Effet mesure sur les resultats

| Mesure | Regle initiale | Regle documentee | Ecart |
|---|---:|---:|---:|
| Lignes de vente avant filtre Customer ID | 1 014 945 | 1 015 009 | +64 |
| Montant brut avant filtre Customer ID (GBP) | 19 699 784,97 | 19 699 754,46 | -30,51 |
| Lignes d'achat (clients identifies) | 788 187 | 788 127 | -60 |
| Clients | 5 852 | 5 852 | 0 |
| Factures | 36 594 | 36 594 | 0 |
| Montant brut (GBP) | 17 124 926,23 | 17 123 741,00 | -1 185,23 |
| Lignes de retour | 17 641 | 17 641 | 0 |
| Montant des retours (GBP) | -713 009,65 | -713 031,25 | -21,60 |
| Clients avec au moins un retour | 2 444 | 2 445 | +1 |

Detail de l'ecart sur les achats de clients identifies : 79 lignes de `23444` retirees (1 200 GBP, 63 clients concernes) et 19 lignes ajoutees (17 `PADS` pour 0,02 GBP et 2 `SP1002` pour 14,75 GBP, 17 clients).
Conclusion : l'effet sur les tables clients est tres faible (0,007 % du montant brut, aucun client en plus ou en moins). Les articles `DCGS*` et les bons cadeaux, sujets de la correction, n'ont pas de `Customer ID` : ils n'entrent dans aucune table client, avant comme apres. La correction rend la regle exacte et justifiable, elle ne change pas la RFM de maniere mesurable.

Limites de la regle :
- La liste vient d'un examen manuel de ce jeu, pas d'une specification du detaillant. Un code non liste est suppose etre un produit.
- Le classement des bons cadeaux comme non-produit est un choix : ils n'ont aucun `Customer ID` et n'affectent donc pas les tables clients.
- `M` (saisie manuelle) peut contenir de vraies ventes saisies a la main : 698 lignes avec identifiant sont retirees, soit environ 150 000 GBP de montant brut (0,9 % du total ; mediane par ligne 6,5 GBP, maximum environ 11 000 GBP ; estimation faite sur le brut avant dedoublonnage). A valider.
- Le prix des lignes `PADS` (0,001 GBP) est probablement une valeur de remplacement.

## Traitement des retours

Les retours ne sont pas deduits des achats. Le montant des achats s'appelle `montant_brut_gbp` (Quantity x Price des factures de vente). Le mot « net » n'est utilise nulle part, car les retours ne sont pas retranches.
Les retours restent disponibles dans `returns.parquet` (`Quantity` negative et `montant_retour_gbp` negatif), apres la meme regle produit et la meme exigence de `Customer ID`. A l'etape RFM, ils pourront servir de variable (par exemple nombre de retours avant la date de coupure) ou, si l'equipe le decide, etre deduits du montant en le renommant explicitement.
Limite : les factures C* ne portent pas la reference de la facture d'origine, on ne peut donc pas les rattacher a un achat precis.

## Regle anti-fuite posee des cette etape

- `purchases.parquet` et `returns.parquet` conservent `InvoiceDate` : le filtrage temporel (`InvoiceDate < T`) se fera dans la fonction de construction des variables a l'etape 2.
- Aucune statistique calculee sur l'ensemble des donnees n'est stockee dans ces fichiers (pas de recence, pas de total par client).
- Le plan prevu : variables construites sur la fenetre avant la date de coupure T, churn defini sur les 90 jours suivants (T, T+90 j], test sur un instantane ulterieur.

## Premier bilan (extraits du rapport)

- 1 067 371 lignes brutes, 22,77 % sans `Customer ID`, 1,83 % d'annulations.
- Apres nettoyage : 788 127 lignes d'achat, 5 852 clients, 36 594 factures, du 2009-12-01 au 2011-12-09.
- 27,65 % des clients n'ont qu'une facture ; mediane de 3 factures par client.
- Royaume-Uni : 90,22 % des lignes.
- Montant brut : 17 123 741 GBP. Retours : 713 031 GBP (4,16 % du montant brut), 41,78 % des clients en ont au moins un.
- Quantite maximale 80 995 et montant de ligne maximal 168 470 GBP : valeurs extremes a traiter a l'etape RFM (ecretage ou logarithme).
- Saisonnalite forte (pic septembre a novembre) ; decembre 2011 est incomplet (arret le 9).

## Points a valider

1. Conserver ou retirer les 11 812 doublons internes ?
2. Les 22,77 % de lignes sans identifiant sont exclues de l'analyse client : acceptable ?
3. Retours : variable explicative seulement, ou deduits du montant (avec renommage) ?
4. Valeurs extremes de quantite : ecretage ou transformation logarithmique ?
5. Code `M` (saisie manuelle) : confirmer son exclusion.
