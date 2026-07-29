REQUESTS_VERSION = 2.32.4

package:
	tar --exclude='__pycache__' --exclude='*.pyc' --exclude='from_id' --exclude='.DS_Store' -czf splunk_ta_honeydb.tar.gz splunk_ta_honeydb

vendor:
	rm -rf splunk_ta_honeydb/lib
	pip3 install --target splunk_ta_honeydb/lib --only-binary=:all: --implementation py --no-compile requests==$(REQUESTS_VERSION)
	rm -rf splunk_ta_honeydb/lib/bin
	find splunk_ta_honeydb/lib -name __pycache__ -type d -exec rm -rf {} +
	find splunk_ta_honeydb/lib -type f -exec chmod 644 {} +

inspect:
	python3 -m venv .env
	.env/bin/pip install --upgrade pip
	.env/bin/pip install splunk-appinspect
	.env/bin/splunk-appinspect inspect splunk_ta_honeydb.tar.gz

smoke-test:
	sh smoke_test.sh

lint:
	pylint splunk_ta_honeydb/bin/spl_honeydb_badhosts.py
	pylint splunk_ta_honeydb/bin/spl_honeydb_sensor_data.py

clean:
	-rm splunk_ta_honeydb.tar.gz
	-rm splunk-appinspect-latest.tar.gz
	-rm -rf .env
