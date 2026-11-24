[![DOI](https://sandbox.zenodo.org/badge/DOI/10.5072/zenodo.647573.svg)](https://handle.test.datacite.org/10.5072/zenodo.647573)

# Περιγραφή

Αναπαραγώγιμη ανάλυση χωροθέτησης ανεμογεννητριών στην ΠΕ Ιωαννίνων. Εφαρμόζει κριτήρια ταχύτητας ανέμου, κλίσης
εδάφους, ορατότητας από οικισμούς (viewshed) και αποκλεισμού περιοχών Natura 2000.

## Δομή

```
config.yaml          παράμετροι, διαδρομές εισόδων, μεταδεδομένα
environment.yml      περιβάλλον conda (conda-forge)
src/                 κώδικας
tests/               μοναδιαίοι έλεγχοι
data/raw/            δεδομένα εισόδου (δεν γίνονται commit, βλ. data/raw/README.md)
data/processed/      αποτελέσματα + provenance.json + datapackage.json
CITATION.cff, codemeta.json, LICENSE
```


## Αναπαραγωγή

```bash
conda env create -f environment.yml && conda activate xorothetisi
# τοποθέτησε τα δεδομένα στο data/raw/ (βλ. data/raw/README.md)
make test      # έλεγχοι του κώδικα
make run       # παράγει data/processed/*
```

Σε κάθε εκτέλεση αποθηκεύονται αυτόματα οι παράμετροι, τα SHA-256 των εισόδων, οι εκδόσεις
των βιβλιοθηκών και το git commit στο `data/processed/provenance.json`.
Μετά από επιτυχημένη εκτέλεση τρέξε `make lock` και κάνε commit το `environment.lock.txt`.

Το `codemeta.json παράγεται αυτόματα από το `CITATION.cff`
και το `codemeta.extra.json` (τεχνικά πεδία). Μετά από κάθε αλλαγή στο `CITATION.cff` ή πριν από κάθε release:

```bash
make codemeta          # επικύρωση του CITATION.cff + αναπαραγωγή του codemeta.json
make check-codemeta    # αποτυγχάνει αν το codemeta.json είναι παλιό (για CI)
```


## Μεθοδολογικές παραδοχές

- Το viewshed συνδυάζεται ως ένωση: ένα σημείο είναι μη επιτρεπόμενο αν φαίνεται από οποιονδήποτε οικισμό.
- `max_slope`: το κριτήριο είναι `κλίση < τιμή`.
- Όλα τα raster προσαρμόζονται στον κάναβο (grid) του DEM. Τα nodata του DEM συμπληρώνονται μόνο για το viewshed.
- Αν το layer οικισμών δεν έχει σημεία, χρησιμοποιείται το κέντρο (centroid) κάθε πολυγώνου.

## FAIR

| Αρχή | Πώς καλύπτεται | Κατάσταση |
|---|---|---|
| F1 Μόνιμο αναγνωριστικό | DOI από το Zenodo |
| F2 Πλούσια μεταδεδομένα | `CITATION.cff`, `codemeta.json`, `datapackage.json` |
| F3 Τα μεταδεδομένα περιέχουν το αναγνωριστικό των δεδομένων | path + SHA-256 στο `datapackage.json`, DOI στο `CITATION.cff` |
| F4 Ευρετηρίαση | Το Zenodo ευρετηριάζεται από μηχανές αναζήτησης και υπηρεσίες όπως το DataCite. Χρήση keywords |
| A1 Πρόσβαση με τυπικό πρωτόκολλο | HTTPS (GitHub, Zenodo), χωρίς λογαριασμό, με ανοιχτό API |
| A2 Μεταδεδομένα διαθέσιμα και χωρίς τα δεδομένα | Το Zenodo διατηρεί τα μεταδεδομένα ακόμη κι αν ένα αρχείο αφαιρεθεί | 
| I1 Τυπική γλώσσα | Ανοιχτές μορφές (GeoPackage, JSON, YAML), EPSG, SPDX,codemeta και συνδέσεις με τις πηγές μέσω Related identifiers | 
| I2 Λεξιλόγια | Σύστημα αναφοράς: EPSG, Άδειες: MIT και CC-BY-4.0 είναι αναγνωριστικά SPDX, Ημερομηνίες: ISO 8601 | 
| I3 Αναφορές σε άλλα δεδομένα | `metadata.sources` με URL/έκδοση/άδεια | 
| R1 Επαρκή χαρακτηριστικά | schema πεδίων στο `datapackage.json` |
| R1.1 Άδεια χρήσης | MIT για τον κώδικα, CC BY 4.0 για τα αποτελέσματα | 
| R1.2 Provenance | `provenance.json` (παράμετροι, hashes, εκδόσεις, commit)|
| R1.3 Πρότυπα κοινότητας | Frictionless, CFF, CodeMeta | Προαιρετικά: ISO 19115/INSPIRE |


## Άδειες

Κώδικας: MIT. Αποτελέσματα: CC BY 4.0. Τα δεδομένα εισόδου διατηρούν τις άδειες των παρόχων τους.
