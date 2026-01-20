#!/usr/bin/env bash

export PYTHONPATH="${PYTHONPATH}:${PWD}/custom_components"

# Start Home Assistant with debugpy listening on port 5678
python -m debugpy --listen 0.0.0.0:5678 --wait-for-client -m homeassistant -c .devcontainer/config --debug
