# Splunk TA for HoneyDB

This Splunk App pulls bad host and sensor data form the HoneyDB API.

## Supported Splunk versions

Splunk Enterprise 9.x and 10.x. Dashboards are Simple XML version 1.1, and
the scripted inputs run under Splunk's bundled Python 3 interpreter. The app
ships its own copy of the `requests` library under `lib/`, so it has no
dependency on Splunk's bundled site-packages.

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

## Upgrading from 1.x

Version 2.0.0 is a drop-in replacement. Your configuration in
`bin/honeydb.json` and the `bin/from_id` checkpoint file are unchanged — if
you replace the app directory wholesale, copy those two files over to the
new version.

## Install

Place this app on your search head under `$SPLUNK_HOME/etc/apps/`
Create the index on your indexer, see Create Indexes section below for instructions.

In order for the app to pull data from HoneyDB you must add your API keys to the configuration. There are two files used to configure the app:

- `bin/honeydb.json`
- `default/inputs.conf`

At minimum, and recommended, you only need to add your HoneyDB API ID and API Key to `bin/honeydb.json`.

__Configuration file: `bin/honeydb.json`__

    {
        "X-HoneyDb-ApiId": "<your key ID>",
        "X-HoneyDb-ApiKey": "<your secret key>",
        "subscription": "<your subscription plan>"
    }

## Create Indexes

Create indexes.conf on your indexer with the default index name "honeydb" Below is the sample of index:

    [honeydb]
    homePath   = $SPLUNK_DB/honeydb/db
    coldPath   = $SPLUNK_DB/honeydb/colddb 
    thawedPath = $SPLUNK_DB/honeydb/thaweddb
    #1 day retention 
    frozenTimePeriodInSecs = 86400
    #14 day retention
    #frozenTimePeriodInSecs = 1209600

__**NOTE:__ If you change the index name, make sure you update `default/inputs.conf` to reflect the new index name, e.g. `index = <new index name >`

## Viewing data in Splunk

sourcetype="honeydb_badhosts"

sourcetype="honeydb_sensor_data"

_If you changed index name or sourcetype, please modify the above query accordingly._

## Troubleshooting

- You can view Splunk app error messages by querying `index=_internal source="*splunk/honeydb.log"` or `index=_internal source = *splunkd.log`

## Dashboards

1. Select splunk_ta_honeydb app in the Splunk UI. Go to Dashboards and click on __HoneyDB BadHosts__ or __HoneyDB Events__.

### Bad Hosts

![HoneyDB Bad Hosts](dashboard_badhosts.png)

### Sensor Data (Events)

![HoneyDB Sensor Data](dashboard_sensor_data.png)
