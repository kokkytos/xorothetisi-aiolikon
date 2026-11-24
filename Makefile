.PHONY: env run test lock codemeta check-codemeta
CFFCONVERT ?= cffconvert

env:
	conda env create -f environment.yml
run:
	python src/xorothetisi_aiolikon.py --config config.yaml
test:
	python -m pytest -q
lock:  # ακριβείς εκδόσεις πακέτων, να γίνεται commit μετά από επιτυχημένη εκτέλεση
	conda list --explicit > environment.lock.txt

# Παράγει το codemeta.json από το CITATION.cff (μοναδική πηγή αλήθειας) + codemeta.extra.json
codemeta: CITATION.cff codemeta.extra.json scripts/merge_codemeta.py
	$(CFFCONVERT) --validate
	$(CFFCONVERT) --format codemeta > codemeta.cff.tmp
	python scripts/merge_codemeta.py codemeta.extra.json < codemeta.cff.tmp > codemeta.json.tmp
	mv codemeta.json.tmp codemeta.json
	rm -f codemeta.cff.tmp
	@echo "codemeta.json ενημερώθηκε"

# Αποτυγχάνει αν το codemeta.json δεν είναι ενημερωμένο (χρήσιμο σε CI ή πριν το release)
check-codemeta:
	$(CFFCONVERT) --validate
	$(CFFCONVERT) --format codemeta | python scripts/merge_codemeta.py codemeta.extra.json | diff -u codemeta.json -
	@echo "codemeta.json είναι ενημερωμένο"
