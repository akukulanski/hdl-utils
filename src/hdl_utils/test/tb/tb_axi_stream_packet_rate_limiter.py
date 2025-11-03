import cocotb
from cocotb import start_soon
from cocotb.clock import Clock
from cocotb.regression import TestFactory
from cocotb.triggers import RisingEdge, Combine, with_timeout
import os
import random

from hdl_utils.cocotb_utils.buses.axi_stream import (
    AXIStreamMaster,
    AXIStreamSlave,
    extract_capture_data,
    extract_capture_user,
    extract_capture_keep,
)

P_DATA_W = int(os.environ['P_DATA_W'])
P_USER_W = int(os.environ['P_USER_W'])
P_HAS_TKEEP = bool(int(os.environ.get('P_HAS_TKEEP', True)))
P_TEST_LENGTH = int(os.environ['P_TEST_LENGTH'])


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


@cocotb.test()
async def check_ports(dut):
    assert len(dut.max_cycles_per_packet) == 32


@cocotb.test()
async def tb_check_core_rate_limiter(dut):
    tb = Testbench(dut)

    await tb.init_test()

    # tb.master.write(
    #     data=_getrandbits(len(tb.master.bus.tdata), test_length),
    #     user=_getrandbits(len(tb.master.bus.tuser), test_length),
    #     keep=_getrandbits(len(tb.master.bus.tkeep), test_length) if P_HAS_TKEEP else None,
    #     burps=burps_in,
    #     force_sync_clk_edge=True,
    # ),
    # tb.slave.read(
    #     # length=test_length,
    #     ignore_last=False,
    #     burps=burps_out,
    #     force_sync_clk_edge=True,
    # ),

    # Test frame rate limit

    async def send_continuously(iface, data, packet_length):
        import itertools
        iface.bus.tvalid.value = 1
        iface.bus.tdata.value = data
        for i in itertools.count():
            iface.bus.tlast.value = int((i + 1) % packet_length == 0)
            await RisingEdge(iface.clock)
            while not iface.accepted():
                await RisingEdge(iface.clock)

    max_cycles_per_packet = 10
    packet_length = 4
    not_ready_cycles = max_cycles_per_packet - packet_length

    start_soon(send_continuously(
        iface=tb.master,
        data=1,
        packet_length=packet_length,
    ))

    dut.max_cycles_per_packet.value = max_cycles_per_packet
    tb.slave.bus.tready.value = 1

    # Wait until a tlast to start counting
    await RisingEdge(dut.clk)
    while not (int(tb.slave.bus.tvalid.value) and int(tb.slave.bus.tlast.value)):
        await RisingEdge(dut.clk)

    for _ in range(4):
        # Check tvalid not set until cycle count reached
        for i in range(not_ready_cycles):
            await RisingEdge(dut.clk)
            assert int(tb.slave.bus.tvalid.value) == 0, f'tvalid=1 earlier than expected (count={i} of {not_ready_cycles})'

        # Check tvalid=1 until the end of the packet
        for i in range(packet_length):
            await RisingEdge(dut.clk)
            assert int(tb.slave.bus.tvalid.value) == 1, f'tvalid=0 earlier than expected (count={i} of {packet_length})'

    await RisingEdge(dut.clk)
    assert int(tb.slave.bus.tvalid.value) == 0, f'tvalid=0'
