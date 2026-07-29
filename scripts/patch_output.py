'''
Post-build fixups on the ucc-gen output (run by `make build`):
- strip compiled-python artifacts (appinspect failure if packaged)
- add python.required to the generated restmap.conf handler stanzas
  (appinspect future-failure; ucc-gen does not emit it yet)
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
