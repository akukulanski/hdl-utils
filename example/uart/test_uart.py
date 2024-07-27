import pytest

from hdl_utils.cocotb_utils.testcases import TemplateTestbenchVerilog


class TestbenchCoresVerilog(TemplateTestbenchVerilog):

    @pytest.mark.parametrize('uart_clk_div', [
                                15,
                                # 16
                            ])
    def test_uart_rx(self, uart_clk_div):
        verilog_sources = [
            'example/uart/uart_rx.v',
        ]
        # top level HDL
        top_level = 'uart_rx'
        # name of cocotb test module
        test_module = 'tb_uart_rx'
        # Waveform file
        vcd_file = './uart_rx.v.vcd'
        # Parameters
        parameters = {
            'UART_CLK_DIV': uart_clk_div,
        }
        self.run_testbench(
            verilog_sources, top_level, test_module,
            parameters=parameters, vcd_file=vcd_file)
