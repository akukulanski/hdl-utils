import json
from pathlib import Path
import tomllib
import urllib.request


def get_version_pypi(package: str, base_url: str = 'https://pypi.org') -> str:
    req = urllib.request.Request(f'{base_url}/pypi/{package}/json')
    r = urllib.request.urlopen(req)
    if r.code == 200:
        t = json.loads(r.read())
        releases = t.get('releases', [])
        if releases:
            return sorted(releases)[-1]

def get_version_pyproject_toml(filename: str = 'pyproject.toml') -> str:
    pyproject_path = Path(filename)

    if pyproject_path.exists():
        with open(pyproject_path, "rb") as f: # Open in binary read mode for tomllib
            data = tomllib.load(f)
        version = data['project']['version']
        return version
    else:
        return None


def get_package_name_pyproject_toml(filename: str = 'pyproject.toml') -> str:
    pyproject_path = Path(filename)

    if pyproject_path.exists():
        with open(pyproject_path, "rb") as f: # Open in binary read mode for tomllib
            data = tomllib.load(f)
        version = data['project']['name']
        return version
    else:
        return None


if __name__ == '__main__':
    import argparse
    CHOICE_PYPI = 'pypi'
    CHOICE_TEST_PYPI = 'test-pypi'
    CHOICE_PYPROJECT_TOML = 'toml'
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=str, choices=(
        CHOICE_PYPI, CHOICE_TEST_PYPI, CHOICE_PYPROJECT_TOML
        ), help='Version source')
    args = parser.parse_args()

    if args.source in (CHOICE_PYPI, CHOICE_TEST_PYPI):
        package_name = get_package_name_pyproject_toml()
        base_url = 'https://pypi.org' if args.source == CHOICE_PYPI else 'https://test.pypi.org'
        version = get_version_pypi(package=package_name, base_url=base_url)
    elif args.source == CHOICE_PYPROJECT_TOML:
        version = get_version_pyproject_toml()
    print(version)
