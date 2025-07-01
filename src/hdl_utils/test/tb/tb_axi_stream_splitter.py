import cocotb
from cocotb import start_soon
from cocotb.clock import Clock
from cocotb.regression import TestFactory
from cocotb.result import SimTimeoutError
from cocotb.triggers import RisingEdge, Combine, Join, with_timeout
from cocotb.utils import get_sim_time

import os
import random

from hdl_utils.cocotb_utils.buses.axi_stream import (
    AXIStreamMaster,
    AXIStreamSlave,
    extract_capture_data,
    extract_capture_user,
    extract_capture_keep,
)


P_DATA_W = int(os.environ.get('P_DATA_W'))
P_USER_W = int(os.environ.get('P_USER_W'))
P_NO_TKEEP = int(os.environ.get('P_NO_TKEEP'))
P_N_SPLIT = int(os.environ.get('P_N_SPLIT'))


class Testbench:

    clk_period = 10

    def __init__(self, dut):
        self.dut = dut
        self.master = AXIStreamMaster(
            entity=dut, name='s_axis_', clock=self.dut.clk)
        self.slaves = [
            AXIStreamSlave(entity=dut, name=f'm_axis_{i:02d}_', clock=self.dut.clk)
            for i in range(P_N_SPLIT)
        ]

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
        if P_USER_W:
            self.dut.s_axis__tuser.value = 0
        if not P_NO_TKEEP:
            self.dut.s_axis__tkeep.value = 0
        self.dut.s_axis__tdata.value = 0
        for i, slave in enumerate(self.slaves):
            # self.dut.m_axi__tready.value = 0
            slave.bus.tready.value = 0

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


def check_axi_iface(
    dut,
    prefix,
    data_w,
    user_w,
    no_tkeep,
):
    assert len(getattr(dut, f"{prefix}tvalid")) == 1
    assert len(getattr(dut, f"{prefix}tready")) == 1
    assert len(getattr(dut, f"{prefix}tlast")) == 1
    assert len(getattr(dut, f"{prefix}tdata")) == data_w
    if user_w > 0:
        assert len(getattr(dut, f"{prefix}tuser")) == user_w
    else:
        assert not hasattr(dut, f"{prefix}tuser")
    if no_tkeep:
        assert not hasattr(dut, f"{prefix}tkeep")
    else:
        assert len(getattr(dut, f"{prefix}tkeep")) == data_w // 8


def _getrandbits(width: int, length: int):
    return [
        random.getrandbits(width)
        for _ in range(length)
    ]


@cocotb.test()
async def tb_check_signals_length(dut):
    check_axi_iface(
        dut=dut,
        prefix="s_axis__",
        data_w=P_DATA_W,
        user_w=P_USER_W,
        no_tkeep=P_NO_TKEEP,
    )
    for i in range(P_N_SPLIT):
        check_axi_iface(
            dut=dut,
            prefix=f"m_axis_{i:02d}__",
            data_w=P_DATA_W,
            user_w=P_USER_W,
            no_tkeep=P_NO_TKEEP,
        )


async def tb_check_core(
    dut,
    test_length: int,
    stream_size: int,
    burps_in: bool,
    burps_out: bool,
):
    tb = Testbench(dut)
    await tb.init_test()

    # Start monitors
    for iface in [tb.master] + tb.slaves:
        start_soon(iface.run_monitor())

    await RisingEdge(dut.clk)

    timeout_args = 100 * stream_size * test_length * tb.clk_period, 'ns'

    data_in = [_getrandbits(P_DATA_W, length=stream_size) for _ in range(test_length)]
    user_in = [_getrandbits(P_USER_W, length=stream_size) for _ in range(test_length)] if P_USER_W else None
    keep_in = [_getrandbits(P_DATA_W // 8, length=stream_size) for _ in range(test_length)] if not P_NO_TKEEP else None

    dut._log.info('Launching writer...')
    proc_wr = start_soon(
        with_timeout(
            tb.master.write_multiple(
                datas=data_in,
                users=user_in,
                keeps=keep_in,
                burps=burps_in,
                force_sync_clk_edge=False,
            ),
            *timeout_args
        )
    )

    dut._log.info('Launching readers...')
    proc_rd = [
        start_soon(
            with_timeout(
                s.read_multiple(
                    n_streams=test_length,
                    ignore_last=False,
                    burps=burps_out,
                    force_sync_clk_edge=False,
                ),
                *timeout_args
            )
        )
        for s in tb.slaves
    ]

    dut._log.info('Waiting...')
    await Combine(proc_wr, *proc_rd)


    data_wr = tb.master.get_monitor()
    assert len(data_wr) == test_length
    for slave_id, slave in enumerate(tb.slaves):
        data_rd = slave.get_monitor()
        for stream_id in range(test_length):
            stream_wr = data_wr[stream_id]
            stream_rd = data_rd[stream_id]
            assert len(stream_wr) == len(stream_rd)
            assert (
                extract_capture_data(stream_wr) ==
                extract_capture_data(stream_rd)
            ), (
                f'[ch-{slave_id:02d}_stream-{stream_id:02d}] data does not match: '
                f'{extract_capture_data(stream_wr)} != '
                f'{extract_capture_data(stream_rd)}'
            )
            if P_USER_W:
                assert (
                    extract_capture_user(stream_wr) ==
                    extract_capture_user(stream_rd)
                ), (
                    f'[ch-{slave_id:02d}_stream-{stream_id:02d}] user does not match: '
                    f'{extract_capture_user(stream_wr)} != '
                    f'{extract_capture_user(stream_rd)}'
                )
            if not P_NO_TKEEP:
                assert (
                    extract_capture_keep(stream_wr) ==
                    extract_capture_keep(stream_rd)
                ), (
                    f'[ch-{slave_id:02d}_stream-{stream_id:02d}] keep does not match: '
                    f'{extract_capture_keep(stream_wr)} != '
                    f'{extract_capture_keep(stream_rd)}'
                )




tf_tb_check_core_basic = TestFactory(test_function=tb_check_core)
tf_tb_check_core_basic.add_option('burps_in', [True])
tf_tb_check_core_basic.add_option('burps_out', [True])
tf_tb_check_core_basic.add_option('test_length', [3])
tf_tb_check_core_basic.add_option('stream_size', [5])
tf_tb_check_core_basic.generate_tests(postfix='_basic')


tf_tb_check_core_full = TestFactory(test_function=tb_check_core)
tf_tb_check_core_full.add_option('burps_in', [False, True])
tf_tb_check_core_full.add_option('burps_out', [False, True])
tf_tb_check_core_full.add_option('test_length', [3])
tf_tb_check_core_full.add_option('stream_size', [20])
# tf_tb_check_core_full.generate_tests(postfix='_full')
