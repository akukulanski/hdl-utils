from cocotb.clock import Clock
from cocotb import start_soon
from cocotb.triggers import RisingEdge


class BaseTestbench:
    clk_period = 10

    def __init__(self, dut):
        self.dut = dut

    @property
    def reset_dut(self):
        """
        Read the reset signal, agnostic of active-high (rst) or
        active-low (rsn_n) signal.
        """
        try:
            value = self.dut.rst.value.integer
        except AttributeError:
            value = self.dut.rst_n.value.integer
            value = int(not value)
        return value

    @reset_dut.setter
    def reset_dut(self, value):
        """
        Set/Clear the reset signal, agnostic of active-high (rst) or
        active-low (rsn_n) signal.
        """
        try:
            self.dut.rst.value = value
        except AttributeError:
            value = int(not value)
            self.dut.rst_n.value = value

    def _start_clock(self):
        start_soon(Clock(self.dut.clk, self.clk_period, units='ns').start())

    def _init_signals(self):
        """
        Override me!
        """
        pass

    async def init_test(self):
        self._start_clock()
        self._init_signals()
        self.reset_dut = 1
        for _ in range(3):
            await RisingEdge(self.dut.clk)
        self.reset_dut = 0
        await RisingEdge(self.dut.clk)
