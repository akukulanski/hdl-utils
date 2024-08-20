import cocotb
from cocotb.clock import Clock
from cocotb import start_soon
from cocotb.triggers import RisingEdge, Combine
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
        start_soon(Clock(self.dut.clk, self.clk_period, units='ns').start())
        self.dut.rst.value = 1
        for _ in range(3):
            await RisingEdge(self.dut.clk)
        self.dut.rst.value = 0
        await RisingEdge(self.dut.clk)


@cocotb.test()
async def check_core(dut):
    tb = Testbench(dut)
    await tb.init_test()

    # Start monitors
    start_soon(tb.master.run_monitor())
    start_soon(tb.slave.run_monitor())

    data_in = list(range((256)))
    expected_data_out = [np.uint8(d) for d in data_in]

    p_reader = start_soon(tb.slave.read())
    await tb.master.write(data_in)
    data_out = await p_reader

    assert len(data_in) == len(data_out)
    assert data_out == expected_data_out
    assert len(tb.master.monitor) == 1
    assert len(tb.slave.monitor) == 1
    assert tb.master.monitor[0] == data_in
    assert tb.slave.monitor[0] == expected_data_out
