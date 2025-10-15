#!/bin/bash
set -eu

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

OUTPUT_DIR=${SCRIPT_DIR}/../output/verilog

mkdir -p ${OUTPUT_DIR}
uv run python3 example/counter.py 8 > ${OUTPUT_DIR}/counter.v
uv run python3 example/stream_signature.py > ${OUTPUT_DIR}/inverter.v
uv run python3 -m pytest -s example/test_cores.py
