import amaranth_cocotb
from cocotb_test.simulator import run as cocotb_run
import os
import pytest
import tempfile

from utils import set_env


class TestCores:

    @pytest.mark.parametrize('width', [4, 7])
    def test_counter(self, width):
        from counter import Counter
        core = Counter(width=width)
        ports = core.get_ports()
        test_module = 'tb_counter'
        vcd_file = './counter.py.vcd'
        env = {
            'P_WIDTH': str(width)
        }
        with set_env(**env):
            amaranth_cocotb.run(core, test_module, ports=ports,
                                vcd_file=vcd_file)

    def test_data_stream_inv(self):
        from data_stream_inv import DataStreamInv
        core = DataStreamInv(width=8)
        ports = core.get_ports()
        test_module = 'tb_data_stream_inv'
        vcd_file = './data_stream_inv.vcd'
        amaranth_cocotb.run(core, test_module, ports=ports, vcd_file=vcd_file)


compile_args_waveforms = ['-s', 'cocotb_waveform_module']

verilog_waveforms = """

module cocotb_waveform_module;
   initial begin
      $dumpfile ("{}");
      $dumpvars (0, {});
      #1;
   end
endmodule
"""


class TestbenchCoresVerilog:

    def run_testbench(self,
                      verilog_sources: list,
                      top_level: str,
                      test_module: str,
                      parameters: dict = None,
                      vcd_file: str = None,
                      extra_args: list = None,
                      ):

        """

        parameters
            verilog_sources: list
                verilog files

            top_level: str
                top level HDL

            test_module: str
                name of the cocotb test module

            parameters: dict
                dictionary with parameters and values of the top level module

            vcd_file: str
                Waveform file (.vcd)

            extra_args: list
                extra compile args for icarus verilog
        """

        # Compile args
        compile_args = []
        if parameters:
            compile_args += [
                f'-P{top_level}.{param}={value}'
                for param, value in parameters.items()]
        if vcd_file:
            compile_args += compile_args_waveforms
        if extra_args:
            compile_args += extra_args

        # Environment variables
        env = {}
        if parameters:
            # Add P_* env vars to be accesible in testbench
            env.update({
                f'P_{param}': str(value)
                for param, value in parameters.items()
            })

        with tempfile.TemporaryDirectory() as d:
            if vcd_file:
                vcd_file = os.path.abspath(vcd_file)
                verilog_dump_file = os.path.join(d, 'waveforms.v')
                with open(verilog_dump_file, 'w') as f:
                    f.write(verilog_waveforms.format(vcd_file, top_level))
                verilog_sources.append(verilog_dump_file)

            with set_env(**env):
                cocotb_run(
                    simulator='icarus',
                    verilog_sources=verilog_sources,
                    toplevel=top_level,
                    module=test_module,
                    compile_args=compile_args,
                    sim_build=d,
                    )

    @pytest.mark.parametrize('width', [4, 7])
    def test_counter(self, width):
        verilog_sources = [
            'example/counter.v',
        ]
        # top level HDL
        top_level = 'Counter'
        # name of cocotb test module
        test_module = 'tb_counter'
        # Waveform file
        vcd_file = './counter.v.vcd'
        # Parameters
        parameters = {
            'WIDTH': width,
        }
        self.run_testbench(
            verilog_sources, top_level, test_module,
            parameters=parameters, vcd_file=vcd_file)
