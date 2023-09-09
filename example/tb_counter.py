import cocotb
from cocotb.triggers import RisingEdge
import os

from hdl_utils.cocotb_utils.tb import BaseTestbench


# Parameters
P_WIDTH = int(os.environ['P_WIDTH'])


class Testbench(BaseTestbench):
    clk_period = 10


@cocotb.test()
async def check_port_sizes(dut):
    assert len(dut.count) == P_WIDTH, f'len(dut.count)={len(dut.count)}'


@cocotb.test()
async def check_count(dut):
    tb = Testbench(dut)
    await tb.init_test()

    for i in range(256):
        assert tb.dut.count.value.integer == i
        await RisingEdge(tb.dut.clk)
