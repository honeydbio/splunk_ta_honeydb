'''
Post-build fixups on the ucc-gen output (run by `make build`):
- strip compiled-python artifacts (appinspect failure if packaged)
- add python.required to the generated restmap.conf handler stanzas
  (appinspect future-failure; ucc-gen does not emit it yet)

Known unfixable appinspect finding: check_for_custom_mako_templates
------------------------------------------------------------------
AppInspect 4.3.0 raises a FUTURE_FAILURE on appserver/templates/base.html:
"Custom Mako template file ... is deprecated in Splunk Enterprise 10.4 ...
regenerate the app with UCC framework version '6.3.0' or later."

Do not act on that message: we already build on UCC 6.5.3, and the emitted
base.html is byte-identical to UCC's canonical template (zero Mako '${}'
expressions). UCC PR #1998 ("remove Mako and CherryPy", shipped in 6.3.0)
stripped the Mako *syntax* but left the file in appserver/templates/ and left
the generated views pointing at it, so regenerating does not clear the finding.

It is NOT merely cosmetic. configuration.xml, inputs.xml and dashboard.xml are
generated as:

    <view template="splunk_ta_honeydb:/templates/base.html" type="html" ...>

The `template="app:/templates/..."` form is what routes the file through
splunkweb's Mako pipeline, regardless of the file's contents. Splunk 10.4 added
a `deactivate_custom_mako_templates` feature flag; when it is enabled splunkweb
accepts only first-party templates from
$SPLUNK_HOME/share/splunk/search_mrsparkle/templates/pages, and our
Configuration / Inputs / Monitoring Dashboard pages stop rendering.

We cannot fix this locally without breaking the UCC UI: base.html is required by
those three generated views, and UCC hardcodes the template path (see
generators/xml_files/create_configuration_xml.py). Tracked upstream at
https://github.com/splunk/addonfactory-ucc-generator/issues/2086 (open, no
milestone as of 2026-08-07). The fix is blocked on an open compatibility
question: the first-party replacement template (splunk_ui_app.html) was
introduced in Splunk 10.4, so a naive swap may break UCC apps on Splunk < 10.4 —
which matters here, as app.manifest declares _standalone and _distributed.

Action on each UCC bump: re-run appinspect and check whether #2086 has landed.
If Splunk announces a date for enabling deactivate_custom_mako_templates, or a
user reports a 10.4 stack with it on, this becomes urgent — at that point the
workaround from the #2086 thread is to rewrite the three view XMLs to
`template="pages/page_from_package.html"` with
`packageName="../../app/splunk_ta_honeydb/pages"`, delete base.html, and
relocate the UCC entry bundle. That workaround is unverified by Splunk, leaves
the page title stuck at "LOADING...", and has an unconfirmed minimum Splunk
version, so it needs testing against a real instance before shipping.
'''
import os
import shutil

OUTPUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      'output', 'splunk_ta_honeydb')
PYTHON_REQUIRED = 'python.required = 3.9, 3.13'


def strip_pycache():
    for root, dirs, files in os.walk(OUTPUT):
        for name in list(dirs):
            if name == '__pycache__':
                shutil.rmtree(os.path.join(root, name))
                dirs.remove(name)
        for name in files:
            if name.endswith(('.pyc', '.pyo')):
                os.remove(os.path.join(root, name))


def patch_restmap():
    path = os.path.join(OUTPUT, 'default', 'restmap.conf')
    with open(path, encoding='utf-8') as conf:
        lines = conf.read().splitlines()
    patched = []
    for line in lines:
        patched.append(line)
        if line.strip() == 'python.version = python3':
            patched.append(PYTHON_REQUIRED)
    with open(path, 'w', encoding='utf-8') as conf:
        conf.write('\n'.join(patched) + '\n')


if __name__ == '__main__':
    strip_pycache()
    patch_restmap()
    print('output patched: pycache stripped, restmap python.required added')
