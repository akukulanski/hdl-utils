# HDL-Utils

Utils for an HDL workflow with Amaranth as HDL framework and Cocotb as testing framework.

## Install

```bash
python3 -m venv venv
. venv/bin/activate
python3 -m pip install git+https://github.com/akukulanski/hdl-utils.git
```

## Examples

Files:
```console
$ tree example/
example/
├── counter.py
├── counter.v
├── data_stream_inverter.py
├── data_stream_pass_through.py
├── stream_signature.py
├── tb
│   ├── tb_counter.py
│   ├── tb_data_stream_inverter.py
│   ├── tb_data_stream_pass_through.py
│   ├── tb_stream_signature.py
│   └── tb_uart_rx.py
├── test_cores.py
└── uart_rx.v

2 directories, 12 files
```

Generate Verilog from Counter in Amaranth:
```bash
python3 example/counter.py 8 > counter.v
cat counter.v
```

Generate Verilog from stream inverter with signatures in Amaranth:
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
