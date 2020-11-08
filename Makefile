package:
	tar -czf splunk_ta_honeydb.tar.gz splunk_ta_honeydb

inspect:
	wget https://download.splunk.com/misc/appinspect/splunk-appinspect-latest.tar.gz
	python3 -m venv .env
	.env/bin/pip -V
	.env/bin/pip install --upgrade pip
	.env/bin/pip install splunk-appinspect-latest.tar.gz
	.env/bin/splunk-appinspect inspect splunk_ta_honeydb.tar.gz	

lint:
	pylint splunk_ta_honeydb/bin/spl_honeydb_badhosts.py
	pylint splunk_ta_honeydb/bin/spl_honeydb_sensor_data.py

clean:
	-rm splunk_ta_honeydb.tar.gz
	-rm splunk-appinspect-latest.tar.gz
	-rm -rf .env
