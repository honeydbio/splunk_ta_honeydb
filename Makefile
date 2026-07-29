VERSION = 3.0.0
PYTHON ?= python3.12
UCC_VENV = .uccenv
APP_TARBALL = splunk_ta_honeydb-$(VERSION).tar.gz

$(UCC_VENV):
	$(PYTHON) -m venv $(UCC_VENV)
	$(UCC_VENV)/bin/pip install --upgrade pip
	$(UCC_VENV)/bin/pip install splunk-add-on-ucc-framework requests pylint

build: $(UCC_VENV)
	find package tests -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	. $(UCC_VENV)/bin/activate && ucc-gen build --ta-version $(VERSION)
	$(UCC_VENV)/bin/python scripts/patch_output.py

package: build
	. $(UCC_VENV)/bin/activate && ucc-gen package --path output/splunk_ta_honeydb

inspect:
	$(PYTHON) -m venv .env
	.env/bin/pip install --upgrade pip
	.env/bin/pip install splunk-appinspect
	.env/bin/splunk-appinspect inspect $(APP_TARBALL)

test: $(UCC_VENV)
	$(UCC_VENV)/bin/python -m unittest discover -s tests -v

lint: $(UCC_VENV)
	$(UCC_VENV)/bin/pylint package/bin/honeydb_utils.py
	$(UCC_VENV)/bin/pylint package/bin/honeydb_account.py
	$(UCC_VENV)/bin/pylint package/bin/honeydb_badhosts_helper.py
	$(UCC_VENV)/bin/pylint package/bin/honeydb_sensor_data_helper.py

smoke-test:
	sh smoke_test.sh

clean:
	-rm $(APP_TARBALL)
	-rm -rf output
	-rm -rf .env
	-rm -rf $(UCC_VENV)
