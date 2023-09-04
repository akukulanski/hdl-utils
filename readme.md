# HDL-Utils

Utils for an HDL workflow with Amaranth as HDL framework and Cocotb as testing framework.

![hdl-workflow](./doc/hdl-workflow.png)

## Install

```bash
python3 -m venv venv
. venv/bin/activate
python3 -m pip install git+https://github.com/akukulanski/hdl-utils.git
```

## Run example

Test:
```bash
python3 -m pytest -o log_cli=True -vs example/test_cores.py
```

Generate verilog:
```bash
python3 example/counter.py 8 > counter.v
cat counter.v
```
