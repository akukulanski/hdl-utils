import cocotb
from cocotb.clock import Clock
from cocotb import start_soon
from cocotb.triggers import RisingEdge


class Testbench:
    clk_period = 10

    def __init__(self, dut):
        self.dut = dut

    async def init_test(self):
        start_soon(Clock(self.dut.clk, self.clk_period, units='ns').start())
        self.dut.rst.value = 1
        for _ in range(3):
            await RisingEdge(self.dut.clk)
        self.dut.rst.value = 0
        await RisingEdge(self.dut.clk)


@cocotb.test()
async def check_count(dut):
    tb = Testbench(dut)
    await tb.init_test()

    for i in range(256):
        assert tb.dut.count.value.integer == i
        await RisingEdge(tb.dut.clk)
