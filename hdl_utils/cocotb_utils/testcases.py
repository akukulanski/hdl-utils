from cocotb_test.simulator import run as cocotb_run
from amaranth_cocotb import run as amaranth_cocotb_run
import os
import tempfile

from .utils import set_env


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


class TemplateTestbenchVerilog:

    def run_testbench(self,
                      verilog_sources: list,
                      top_level: str,
                      test_module: str,
                      parameters: dict = None,
                      vcd_file: str = None,
                      extra_args: list = None,
                      includes: list = None,
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
                    includes=includes,
                )


class TemplateTestbenchAmaranth:

    def run_testbench(self,
                      core,  # Elaboratable,
                      test_module: str,
                      ports: list,
                      vcd_file: str = None,
                      env: dict = None,
                      # extra_args: list = None,
                      ):
        env = env or {}
        with set_env(**env):
            amaranth_cocotb_run(
                core,
                test_module,
                ports=ports,
                vcd_file=vcd_file)
