# HDL-Utils

Utils for an HDL workflow with Amaranth as HDL framework and Cocotb as testing framework.

## Install

```bash
python3 -m venv venv
. venv/bin/activate
python3 -m pip install git+https://github.com/akukulanski/hdl-utils.git
```

## Run example

* Counter:
    - HDL: [example/counter.py](example/counter.py)
    - Testbench: [example/tb_counter.py](example/tb_counter.py)
* DataStreamInv:
    - HDL: [example/data_stream_inv.py](example/data_stream_inv.py)
    - Testbench: [example/tb_data_stream_inv.py](example/tb_data_stream_inv.py)
* Stream inverter with signatures:
    - HDL: [example/stream_signature.py](example/stream_signature.py)
    - Testbench: [example/tb_stream_signature.py](example/tb_stream_signature.py)
* Test runner: [example/test_cores.py](example/test_cores.py)

Generate Verilog for Counter with:
```bash
python3 example/counter.py 8 > counter.v
cat counter.v
```

Generate Verilog for stream inverter with signatures:
```bash
python3 example/stream_signature.py > inverter.v
cat inverter.v
```

Run all testbenches with:
```bash
python3 -m pytest -o log_cli=True -vs example/test_cores.py
```

## Workflow

![hdl-workflow](./doc/hdl-workflow.png)
