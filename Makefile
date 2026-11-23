.PHONY: env run test lock
env:
	conda env create -f environment.yml
run:
	python src/xorothetisi_aiolikon.py --config config.yaml
test:
	python -m pytest -q
lock:  # ακριβείς εκδόσεις πακέτων, να γίνεται commit μετά από επιτυχημένη εκτέλεση
	conda list --explicit > environment.lock.txt
