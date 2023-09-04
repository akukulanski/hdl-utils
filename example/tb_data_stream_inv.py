import cocotb
from cocotb.clock import Clock
from cocotb import fork
from cocotb.triggers import RisingEdge
import numpy as np

from hdl_utils.cocotb_utils.buses import (DataStreamMaster,
                                          DataStreamSlave)


class Testbench:
    clk_period = 10

    def __init__(self, dut):
        self.dut = dut
        self.master = DataStreamMaster(entity=dut, name='sink_',
                                       clock=dut.clk)
        self.slave = DataStreamSlave(entity=dut, name='source_',
                                     clock=dut.clk)

    async def init_test(self):
        fork(Clock(self.dut.clk, self.clk_period, units='ns').start())
        self.dut.rst.value = 1
        for _ in range(3):
            await RisingEdge(self.dut.clk)
        self.dut.rst.value = 0
        await RisingEdge(self.dut.clk)


@cocotb.test()
async def check_core(dut):
    tb = Testbench(dut)
    await tb.init_test()

    data = [i for i in range(256)]

    p_reader = fork(tb.slave.read())
    await tb.master.write(data)
    rd = await p_reader

    assert len(data) == len(rd)

    for d, r in zip(data, rd):
        expected_r = ~np.uint8(d)
        assert r == expected_r, f'{r} != {expected_r}'
