#!/bin/sh
# Docker smoke test for splunk_ta_honeydb.
#
# Prereq: real HoneyDB API credentials in splunk_ta_honeydb/bin/honeydb.json
# (do NOT commit them). Requires a running Docker daemon.
#
# Stands up splunk/splunk:latest, installs the app, creates the honeydb
# index, then verifies: app log, event counts by sourcetype, and the
# first-run from_id checkpoint.
#
# Cleanup when done: docker rm -f splunk-smoke
set -e
cd "$(dirname "$0")"

SPLUNK_PW='Sm0keTest!Pass'

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

# install app + index; Splunk CLI commands must run as the splunk user
docker cp splunk_ta_honeydb splunk-smoke:/opt/splunk/etc/apps/
docker exec -u root splunk-smoke chown -R splunk:splunk /opt/splunk/etc/apps/splunk_ta_honeydb
docker exec -u splunk splunk-smoke /opt/splunk/bin/splunk add index honeydb -auth admin:"$SPLUNK_PW"
docker exec -u splunk splunk-smoke /opt/splunk/bin/splunk restart

echo 'waiting for splunkd after restart...'
until [ "$(docker inspect -f '{{.State.Health.Status}}' splunk-smoke)" = "healthy" ]; do sleep 5; done

echo 'waiting for ingest (120s)...'
sleep 120

echo '--- honeydb.log (app errors) ---'
docker exec -u splunk splunk-smoke tail -10 /opt/splunk/var/log/splunk/honeydb.log || true
echo '--- event counts by sourcetype ---'
docker exec -u splunk splunk-smoke /opt/splunk/bin/splunk search 'index=honeydb | stats count by sourcetype' -auth admin:"$SPLUNK_PW"
echo '--- from_id checkpoint (first-run regression check) ---'
docker exec -u splunk splunk-smoke cat /opt/splunk/etc/apps/splunk_ta_honeydb/bin/from_id; echo

echo "Dashboards: open http://localhost:8000 (admin / $SPLUNK_PW), app splunk_ta_honeydb."
echo 'Cleanup: docker rm -f splunk-smoke'
