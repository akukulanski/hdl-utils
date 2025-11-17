#!/bin/bash
set -xeu

PYPROJECT_TOML_VERSION=$(python3 scripts/get_version.py toml)
CURRENT_VERSION=$(python3 scripts/get_version.py test-pypi)
echo "Current version in pyproject.toml: $PYPROJECT_TOML_VERSION"
echo "Current version in Test PyPi: $CURRENT_VERSION"
uv run bumpversion --current-version 0.1.0 --new-version $CURRENT_VERSION pyproject.toml
uv run bumpversion patch --current-version $CURRENT_VERSION pyproject.toml --allow-dirty
