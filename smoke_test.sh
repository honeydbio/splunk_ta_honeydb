#!/bin/sh
# Docker smoke test for splunk_ta_honeydb v3 (UCC).
#
# Prereq: real HoneyDB API credentials in honeydb.json.dev at the repo
# root (gitignored). Requires Docker and the ucc build venv (make build).
#
# Builds the add-on, stands up splunk/splunk:latest, installs the built
# app, creates the "default" account via the UCC REST handler, enables
# both shipped inputs, then verifies ingest, logs, and the checkpoint.
#
# Cleanup when done: docker rm -f splunk-smoke
set -e
cd "$(dirname "$0")"

SPLUNK_PW='Sm0keTest!Pass'

make build

docker run -d --name splunk-smoke -p 8000:8000 -p 8089:8089 \
  -e SPLUNK_GENERAL_TERMS='--accept-sgt-current-at-splunk-com' \
  -e SPLUNK_START_ARGS='--accept-license' -e SPLUNK_PASSWORD="$SPLUNK_PW" \
  splunk/splunk:latest

echo 'waiting for splunkd (healthcheck)...'
until [ "$(docker inspect -f '{{.State.Health.Status}}' splunk-smoke)" = "healthy" ]; do
  if [ "$(docker inspect -f '{{.State.Status}}' splunk-smoke)" = "exited" ]; then
    echo 'CONTAINER EXITED:'; docker logs splunk-smoke 2>&1 | tail -20; exit 1
  fi
  sleep 5
done

# install built app + index; Splunk CLI commands must run as the splunk user
docker cp output/splunk_ta_honeydb splunk-smoke:/opt/splunk/etc/apps/
docker exec -u root splunk-smoke chown -R splunk:splunk /opt/splunk/etc/apps/splunk_ta_honeydb
docker exec -u splunk splunk-smoke /opt/splunk/bin/splunk add index honeydb -auth admin:"$SPLUNK_PW"
docker exec -u splunk splunk-smoke /opt/splunk/bin/splunk restart

echo 'waiting for splunkd after restart...'
until [ "$(docker inspect -f '{{.State.Health.Status}}' splunk-smoke)" = "healthy" ]; do sleep 5; done

# create the "default" account from honeydb.json.dev and enable the inputs
docker cp honeydb.json.dev splunk-smoke:/tmp/honeydb.json.dev
docker exec -i -u splunk splunk-smoke /opt/splunk/bin/splunk cmd python3 - <<'PYEOF'
import base64, json, ssl, urllib.parse, urllib.request

creds = json.load(open('/tmp/honeydb.json.dev'))
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
auth = 'Basic ' + base64.b64encode(b'admin:Sm0keTest!Pass').decode()

def post(path, params):
    req = urllib.request.Request(f'https://127.0.0.1:8089{path}?output_mode=json',
                                 data=urllib.parse.urlencode(params).encode())
    req.add_header('Authorization', auth)
    try:
        urllib.request.urlopen(req, context=ctx)
        print('ok:', path)
    except urllib.error.HTTPError as err:
        print('HTTP', err.code, path, err.read()[:300])

post('/servicesNS/nobody/splunk_ta_honeydb/splunk_ta_honeydb_account', {
    'name': 'honeydb',
    'api_id': creds['X-HoneyDb-ApiId'],
    'api_key': creds['X-HoneyDb-ApiKey'],
    'subscription': creds.get('subscription', 'community'),
})
post('/servicesNS/nobody/splunk_ta_honeydb/data/inputs/honeydb_sensor_data/honeydb/enable', {})
post('/servicesNS/nobody/splunk_ta_honeydb/data/inputs/honeydb_badhosts/honeydb/enable', {})
PYEOF
docker exec -u root splunk-smoke rm -f /tmp/honeydb.json.dev

echo 'waiting for ingest (120s)...'
sleep 120

echo '--- input logs (framework) ---'
docker exec -u splunk splunk-smoke sh -c 'tail -6 /opt/splunk/var/log/splunk/splunk_ta_honeydb_honeydb.log 2>/dev/null; ls /opt/splunk/var/log/splunk/ | grep splunk_ta_honeydb'
echo '--- event counts by sourcetype ---'
docker exec -u splunk splunk-smoke /opt/splunk/bin/splunk search 'index=honeydb | stats count by sourcetype' -auth admin:"$SPLUNK_PW"
echo '--- from_id checkpoint ---'
docker exec -u splunk splunk-smoke cat /opt/splunk/var/lib/splunk/splunk_ta_honeydb/from_id; echo

echo "Dashboards: open http://localhost:8000 (admin / $SPLUNK_PW), app splunk_ta_honeydb."
echo 'Cleanup: docker rm -f splunk-smoke'
