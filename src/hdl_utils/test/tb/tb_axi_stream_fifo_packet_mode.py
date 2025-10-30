import cocotb
from cocotb import start_soon
from cocotb.clock import Clock
from cocotb.regression import TestFactory
from cocotb.triggers import RisingEdge
import os
import random

from hdl_utils.cocotb_utils.buses.axi_stream import (
    AXIStreamMaster,
    AXIStreamSlave,
)

P_DATA_W = int(os.environ['P_DATA_W'])
P_USER_W = int(os.environ['P_USER_W'])
P_HAS_TKEEP = bool(int(os.environ.get('P_HAS_TKEEP', True)))
P_TEST_LENGTH = int(os.environ['P_TEST_LENGTH'])
P_DEPTH = int(os.environ['P_DEPTH'])


class Testbench:

    period_ns = 10

    def __init__(self, dut):
        self.dut = dut
        self.master = AXIStreamMaster(entity=dut, name='s_axis_', clock=dut.clk)
        self.slave = AXIStreamSlave(entity=dut, name='m_axis_', clock=dut.clk)

    def get_reset_signal_name(self, domain: str):
        sig_pos = f'{domain}_rst' if domain else 'rst'
        sig_neg = f'{domain}_rstn' if domain else 'rstn'
        if hasattr(self.dut, sig_pos):
            assert not hasattr(self.dut, sig_neg), f'both {sig_pos} and {sig_neg} present'
            return sig_pos
        elif hasattr(self.dut, sig_neg):
            assert not hasattr(self.dut, sig_pos), f'2both {sig_pos} and {sig_neg} present'
            return sig_neg
        else:
            raise AttributeError(f'Reset signal not found for {domain}')

    def reset(self, domain: str):
        signal_name = self.get_reset_signal_name(domain)
        signal = getattr(self.dut, signal_name)
        signal.value = 0 if signal_name.endswith('n') else 1

    def unreset(self, domain: str):
        signal_name = self.get_reset_signal_name(domain)
        signal = getattr(self.dut, signal_name)
        signal.value = 1 if signal_name.endswith('n') else 0

    def _init_signals(self):
        pass

    async def init_test(self):
        self._init_signals()
        start_soon(Clock(self.dut.clk, self.period_ns, 'ns').start())
        self.reset('')
        for _ in range(3):
            await RisingEdge(self.dut.clk)
        self.unreset('')
        for _ in range(2):
            await RisingEdge(self.dut.clk)


def _getrandbits(width: int, length: int):
    return [
        random.getrandbits(width)
        for _ in range(length)
    ]


async def tb_check_core(
    dut,
    burps_in: bool = False,
    burps_out: bool = False,
):
    tb = Testbench(dut)

    await tb.init_test()

    # Start monitors
    start_soon(tb.master.run_monitor())
    start_soon(tb.slave.run_monitor())

    length = P_DEPTH
    data = _getrandbits(len(tb.master.bus.tdata), length)

    # Write one packet - Read one packet
    await tb.master.write(data, burps=burps_in)
    rd = await tb.slave.read(burps=burps_out)
    assert rd == data

    # Write 3 packets - Read 3 packets
    length = P_DEPTH // 3
    assert length > 0
    data = _getrandbits(len(tb.master.bus.tdata), length)
    for _ in range(3):
        await tb.master.write(data, burps=burps_in)
    for _ in range(3):
        rd = await tb.slave.read(burps=burps_out)
        assert rd == data

    # Write data without tlast and check there is nothing to read
    n_write = 10
    for i in range(n_write):
        tb.master.bus.tdata.value = i
        tb.master.bus.tlast.value = 0
        tb.master.bus.tvalid.value = 1
        await RisingEdge(dut.clk)
        assert int(tb.slave.bus.tready.value) == 0
        while not tb.master.accepted():
            await RisingEdge(dut.clk)
            assert int(tb.slave.bus.tready.value) == 0

    tb.master.bus.tdata.value = 0
    tb.master.bus.tlast.value = 0
    tb.master.bus.tvalid.value = 0
    for _ in range(10):
        assert int(tb.slave.bus.tready.value) == 0

    tb.master.bus.tdata.value = n_write
    tb.master.bus.tlast.value = 1
    tb.master.bus.tvalid.value = 1
    await RisingEdge(dut.clk)
    while not tb.master.accepted():
        await RisingEdge(dut.clk)

    tb.master.bus.tdata.value = 0
    tb.master.bus.tlast.value = 0
    tb.master.bus.tvalid.value = 0
    rd = await tb.slave.read(burps=burps_out)
    assert rd == list(range(n_write + 1))

    # Write without tlast until filling the fifo completely,
    # and check that it allows to read when fifo is full.
    count = 0
    tb.master.bus.tdata.value = count
    tb.master.bus.tlast.value = 0
    tb.master.bus.tvalid.value = 1
    await RisingEdge(dut.clk)
    while tb.master.accepted():
        count += 1
        tb.master.bus.tdata.value = count
        await RisingEdge(dut.clk)
    assert count == P_DEPTH, f'{count} != {P_DEPTH}'

    tb.master.bus.tdata.value = 0
    tb.master.bus.tlast.value = 0
    tb.master.bus.tvalid.value = 0
    await RisingEdge(dut.clk)
    assert int(tb.slave.bus.tvalid) == 1
    tb.slave.bus.tready.value = 1
    await RisingEdge(dut.clk)
    assert tb.slave.accepted()
    assert int(tb.slave.bus.tdata.value) == 0  # first element
    await RisingEdge(dut.clk)
    assert int(tb.slave.bus.tvalid.value) == 0
    assert not tb.slave.accepted()


tf_check_core = TestFactory(test_function=tb_check_core)
tf_check_core.add_option('burps_in',  [False, True])
tf_check_core.add_option('burps_out', [False, True])
tf_check_core.generate_tests()
