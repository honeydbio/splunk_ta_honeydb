# Splunk TA for HoneyDB

This Splunk App pulls bad host and sensor data from the HoneyDB API.

Version 3.x is built on Splunk's UCC framework: configuration is done in
the Splunk UI, credentials are stored encrypted, and the data inputs are
modular inputs.

## Supported Splunk versions

Splunk Enterprise 9.x and 10.x. Dashboards are Simple XML version 1.1 and
inputs run under Splunk's bundled Python 3.

## Install

Install a release tarball (`splunk_ta_honeydb-<version>.tar.gz`) via
Splunk Web ("Install app from file"), or place the built app on your
search head under `$SPLUNK_HOME/etc/apps/`.

To build from source:

    make package     # requires python3.12; produces splunk_ta_honeydb-3.0.0.tar.gz

Create the `honeydb` index on your indexer (see Create Indexes below).

## Configure

1. Open the **splunk_ta_honeydb** app > **Configuration** > **Accounts**
   and add an account with your HoneyDB API ID and API Key
   (honeydb.io > Threat Information > API). The key is stored encrypted.
   Name the account `honeydb` to use the shipped inputs as-is.
2. Go to **Inputs** and enable (or create) the two inputs:
   - **HoneyDB Bad Hosts** — polls the bad-hosts feed (default every 30
     minutes).
   - **HoneyDB Sensor Data** — polls sensor data (default every 60
     seconds), paginated with checkpointing.

## Upgrading from 2.x

- Credentials: `bin/honeydb.json` and the 2.1 credential-store realm are
  no longer read — enter your API credentials once in the Configuration
  UI.
- The sensor-data checkpoint location and format are unchanged
  (`$SPLUNK_HOME/var/lib/splunk/splunk_ta_honeydb/from_id`), so ingestion
  resumes exactly where 2.1 left off.
- Dashboards, sourcetypes, the index macro, CIM mappings, and the
  bad-hosts lookup are unchanged.

## Create Indexes

Create indexes.conf on your indexer with the default index name "honeydb". Below is a sample:

    [honeydb]
    homePath   = $SPLUNK_DB/honeydb/db
    coldPath   = $SPLUNK_DB/honeydb/colddb 
    thawedPath = $SPLUNK_DB/honeydb/thaweddb
    #1 day retention 
    frozenTimePeriodInSecs = 86400
    #14 day retention
    #frozenTimePeriodInSecs = 1209600

__**NOTE:__ If you change the index name, select it on each input in the
Inputs UI and override the dashboard search scope once in
`local/macros.conf` (survives upgrades):

    [honeydb_index]
    definition = index=<new index name>

## Viewing data in Splunk

sourcetype="honeydb_badhosts"

sourcetype="honeydb_sensor_data"

_If you changed index name or sourcetype, please modify the above query accordingly._

## Enriching your own data

The app maintains a KV-store lookup (`honeydb_badhosts_lookup`) of the
current bad-hosts list, refreshed every 30 minutes by the scheduled search
"HoneyDB - Update BadHosts Lookup". Use the `honeydb_badhost(<field>)`
macro to annotate any events with HoneyDB reputation:

    index=firewall action=allowed
    | `honeydb_badhost(src_ip)`
    | where isnotnull(honeydb_count)
    | table _time, src_ip, honeydb_count, honeydb_last_seen

Matched events gain `honeydb_count` (sightings) and `honeydb_last_seen`.

## CIM compliance

`honeydb_sensor_data` events are mapped to the CIM **Intrusion Detection**
data model (tags `ids` + `attack`) with these fields:

| CIM field | Source |
|---|---|
| `src` | `remote_host` |
| `signature` | `event` + `service` (e.g. `CONNECT VNC`) |
| `transport` | `protocol` (lowercased) |
| `ids_type` | `network` |
| `category` | `service` (lowercased) |
| `severity` | `informational` |
| `vendor_product` | `HoneyDB` |

`dest` is not populated — the sensor-data feed does not include the
honeypot's identity. `honeydb_badhosts` records are reputation data, not
attack events: they get `src` and `vendor_product` aliases but are
intentionally not tagged into the data model.

## Troubleshooting

- Input logs: `index=_internal source="*splunk_ta_honeydb*.log"` (one log
  file per input under `$SPLUNK_HOME/var/log/splunk/`), or
  `index=_internal source=*splunkd.log`.
- Log level is configurable on the add-on's Configuration > Logging tab.

## Dashboards

1. Select splunk_ta_honeydb app in the Splunk UI. Go to Dashboards and click on __HoneyDB BadHosts__ or __HoneyDB Events__.

### Bad Hosts

![HoneyDB Bad Hosts](dashboard_badhosts.png)

### Sensor Data (Events)

![HoneyDB Sensor Data](dashboard_sensor_data.png)

## Development

    make test        # unit tests (no Splunk needed)
    make lint        # pylint on package/bin
    make build       # ucc-gen build into output/
    make package     # build + tarball
    make inspect     # splunk-appinspect on the tarball
    make smoke-test  # end-to-end Docker validation (needs honeydb.json.dev)
