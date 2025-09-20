import cocotb
from cocotb import start_soon
from cocotb.clock import Clock
from cocotb.regression import TestFactory
from cocotb.result import SimTimeoutError
from cocotb.triggers import RisingEdge, Combine, Join, with_timeout
from cocotb.utils import get_sim_time

import math
import numpy as np
import os
import pytest
import random

from hdl_utils.cocotb_utils.buses.axi_stream import (
    AXIStreamMaster, AXIStreamSlave)
from hdl_utils.cocotb_utils.tb_utils import width_converter_up

P_DWI = int(os.environ.get('P_DWI'))
P_DWO = int(os.environ.get('P_DWO'))
P_UWI = int(os.environ.get('P_UWI'))


class Testbench:

    clk_period = 10

    def __init__(self, dut):
        self.dut = dut
        self.m_axi = AXIStreamMaster(
            entity=dut, name='s_axis_', clock=self.dut.clk)
        self.s_axi = AXIStreamSlave(
            entity=dut, name='m_axis_', clock=self.dut.clk)

    @property
    def data_width_in(self):
        return P_DWI

    @property
    def data_width_out(self):
        return P_DWO

    @property
    def user_width_in(self):
        return P_UWI

    @property
    def user_width_out(self):
        return int(P_UWI * P_DWO / P_DWI)

    @property
    def keep_width_in(self):
        return P_DWI // 8

    @property
    def keep_width_out(self):
        return P_DWO // 8

    @property
    def scale_factor(self):
        return int(P_DWO / P_DWI)

    def get_reset_signal_name(self, domain: str = None):
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

    def reset(self, domain: str = None):
        signal_name = self.get_reset_signal_name(domain)
        signal = getattr(self.dut, signal_name)
        signal.value = 0 if signal_name.endswith('n') else 1

    def unreset(self, domain: str = None):
        signal_name = self.get_reset_signal_name(domain)
        signal = getattr(self.dut, signal_name)
        signal.value = 1 if signal_name.endswith('n') else 0

    def _init_signals(self):
        self.dut.s_axis__tvalid.value = 0
        self.dut.s_axis__tlast.value = 0
        self.dut.s_axis__tkeep.value = 0
        self.dut.s_axis__tuser.value = 0
        self.dut.s_axis__tdata.value = 0
        self.dut.m_axis__tready.value = 0

    async def init_test(self):
        # Start clock
        start_soon(Clock(self.dut.clk, self.clk_period, units='ns').start())
        # Init signals
        self._init_signals()
        # Reset core
        self.reset()
        for _ in range(3):
            await RisingEdge(self.dut.clk)
        self.unreset()
        await RisingEdge(self.dut.clk)


# @cocotb.test()
async def tb_check_signals_length(dut):
    assert P_DWO % P_DWI == 0
    assert len(dut.s_axis__tvalid) == 1
    assert len(dut.s_axis__tready) == 1
    assert len(dut.s_axis__tlast) == 1
    assert len(dut.s_axis__tkeep) == P_DWI // 8
    if P_UWI > 0:  # can\'t create zero-length signal
        assert len(dut.s_axis__tuser) == P_UWI
    assert len(dut.s_axis__tdata) == P_DWI
    assert len(dut.m_axis__tvalid) == 1
    assert len(dut.m_axis__tready) == 1
    assert len(dut.m_axis__tlast) == 1
    assert len(dut.m_axis__tkeep) == P_DWO // 8
    if P_UWI > 0:  # can\'t create zero-length signal
        assert len(dut.m_axis__tuser) == P_UWI / (P_DWI / P_DWO)
    assert len(dut.m_axis__tdata) == P_DWO


async def run_and_check_result(dut, tb, data_in, user_in, keep_in,
                               burps_in, burps_out):

    monitor_data_initial_len = len(tb.s_axi.get_monitor())

    expected_data_out = width_converter_up(
        data_in=data_in,
        width_in=tb.data_width_in,
        width_out=tb.data_width_out)
    expected_user_out = width_converter_up(
        data_in=user_in,
        width_in=tb.user_width_in,
        width_out=tb.user_width_out) or [0] * len(expected_data_out)
    expected_keep_out = width_converter_up(
        data_in=keep_in,
        width_in=tb.keep_width_in,
        width_out=tb.keep_width_out)

    p_send = start_soon(tb.m_axi.write(
        data=data_in, user=user_in, keep=keep_in, burps=burps_in))
    p_recv = start_soon(tb.s_axi.read(
        burps=burps_out))

    await Join(p_recv)
    for _ in range(2):
        await RisingEdge(dut.clk)

    monitor_data = tb.s_axi.get_monitor()
    assert len(monitor_data) == monitor_data_initial_len + 1

    capture = monitor_data[-1]  # last capture
    data_out = tb.s_axi.extract_capture_data(capture)
    user_out = tb.s_axi.extract_capture_user(capture)
    keep_out = tb.s_axi.extract_capture_keep(capture)
    assert data_out == expected_data_out, f'{data_out} != {expected_data_out}'
    assert user_out == expected_user_out, f'{user_out} != {expected_user_out}'
    assert keep_out == expected_keep_out, f'{keep_out} != {expected_keep_out}'


async def tb_write_read_single(dut, burps_in, burps_out, mid_packet_last):
    tb = Testbench(dut)
    await tb.init_test()

    # Start monitors
    start_soon(tb.s_axi.run_monitor())
    start_soon(tb.m_axi.run_monitor())

    STREAM_LENGTH = 100 * tb.scale_factor
    if mid_packet_last and tb.scale_factor > 1:
        # Force length not multiple of output width
        STREAM_LENGTH += random.randint(1, tb.scale_factor - 1)

    # DEBUG: incremental data # data_in = [x % (2**tb.data_width_in) for x in range(STREAM_LENGTH)]
    data_in = [random.getrandbits(tb.data_width_in) for _ in range(STREAM_LENGTH)]
    user_in = [random.getrandbits(P_UWI) for _ in range(STREAM_LENGTH)]
    keep_in = [2**(P_DWI // 8) - 1] * len(data_in)

    await run_and_check_result(dut, tb, data_in, user_in, keep_in,
                               burps_in=burps_in, burps_out=burps_out)


async def tb_write_read_multiple(dut, burps_in, burps_out, mid_packet_last):
    tb = Testbench(dut)
    await tb.init_test()

    # Start monitors
    start_soon(tb.s_axi.run_monitor())
    start_soon(tb.m_axi.run_monitor())

    STREAM_LENGTH = 10 * tb.scale_factor
    if mid_packet_last and tb.scale_factor > 1:
        # Force length not multiple of output width
        STREAM_LENGTH += random.randint(1, tb.scale_factor - 1)

    for _ in range(5):
        data_in = [random.getrandbits(tb.data_width_in) for _ in range(STREAM_LENGTH)]
        user_in = [random.getrandbits(P_UWI) for _ in range(STREAM_LENGTH)]
        keep_in = [2**(P_DWI // 8) - 1] * len(data_in)

        await run_and_check_result(dut, tb, data_in, user_in, keep_in,
                                   burps_in=burps_in, burps_out=burps_out)


# @cocotb.test()
async def tb_check_no_clock_wasted(dut):
    tb = Testbench(dut)
    await tb.init_test()

    # Start monitors
    start_soon(tb.s_axi.run_monitor())
    start_soon(tb.m_axi.run_monitor())

    expected_clk_cycles_per_input = 1

    # Start measuring time
    t_start = get_sim_time('ns')

    STREAM_LENGTH = 100 * tb.scale_factor
    data_in = [random.getrandbits(tb.data_width_in) for _ in range(STREAM_LENGTH)]
    user_in = [random.getrandbits(P_UWI) for _ in range(STREAM_LENGTH)]
    keep_in = [2**(P_DWI // 8) - 1] * len(data_in)
    await run_and_check_result(dut, tb, data_in, user_in, keep_in,
                               burps_in=False, burps_out=False)

    # End measuring time
    t_end = get_sim_time('ns')
    elapsed_ns = t_end - t_start
    elapsed_clk_cycles = int(np.round(elapsed_ns / tb.clk_period))
    elapsed_clk_cycles_per_input = elapsed_clk_cycles / STREAM_LENGTH

    assert math.isclose(
        elapsed_clk_cycles_per_input,
        expected_clk_cycles_per_input,
        rel_tol=0.1
    ), f'{elapsed_clk_cycles_per_input} != {expected_clk_cycles_per_input}'


# --- Tests Generation ---

# Test Check Signals' length
TestFactory(test_function=tb_check_signals_length).generate_tests()

# Test Single Write/Read
tf_tb_write_read_single = TestFactory(test_function=tb_write_read_single)
tf_tb_write_read_single.add_option("burps_in", (False, True))
tf_tb_write_read_single.add_option("burps_out", (False, True))
tf_tb_write_read_single.add_option("mid_packet_last",
                                   (False, True) if P_DWO > P_DWI else (False,))
tf_tb_write_read_single.generate_tests()

# Test Multiple Write/Read
tf_tb_write_read_multiple = TestFactory(test_function=tb_write_read_multiple)
tf_tb_write_read_multiple.add_option("burps_in", (False, True))
tf_tb_write_read_multiple.add_option("burps_out", (False, True))
tf_tb_write_read_multiple.add_option("mid_packet_last",
                                     (False, True) if P_DWO > P_DWI else (False,))
tf_tb_write_read_multiple.generate_tests()

# Test Check No Clock Cycle is Wasted
TestFactory(test_function=tb_check_no_clock_wasted).generate_tests()
