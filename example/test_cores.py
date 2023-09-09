import pytest

from hdl_utils.cocotb_utils.testcases import (
    TemplateTestbenchVerilog, TemplateTestbenchAmaranth)


class TestbenchCoresAmaranth(TemplateTestbenchAmaranth):

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
        self.run_testbench(core, test_module, ports,
                           vcd_file=vcd_file, env=env)

    def test_data_stream_inv(self):
        from data_stream_inv import DataStreamInv
        core = DataStreamInv(width=8)
        ports = core.get_ports()
        test_module = 'tb_data_stream_inv'
        vcd_file = './data_stream_inv.vcd'
        self.run_testbench(core, test_module, ports, vcd_file=vcd_file)


class TestbenchCoresVerilog(TemplateTestbenchVerilog):

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
