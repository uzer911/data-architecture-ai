PYTHON ?= python3

.PHONY: check test smoke prod-check ui

check:
	$(PYTHON) -m compileall src scripts run_smoke.py

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -p "test_*.py" -v

smoke:
	$(PYTHON) run_smoke.py

prod-check: check test smoke

ui:
	$(PYTHON) -m pip install -q -r requirements.txt
	PYTHONPATH=src $(PYTHON) -m streamlit run scripts/streamlit_app.py
