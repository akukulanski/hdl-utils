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
P_DEPTH = int(os.environ['P_DEPTH'])


class Testbench:
    clk_period = 10

    def __init__(self, dut, period_ns_w, period_ns_r):
        self.dut = dut
        self.period_ns_w = period_ns_w
        self.period_ns_r = period_ns_r
        self.master = AXIStreamMaster(entity=dut, name='s_axis_',
                                      clock=dut.wr_domain_clk)
        self.slave = AXIStreamSlave(entity=dut, name='m_axis_',
                                    clock=dut.rd_domain_clk)

    def _init_signals(self):
        pass

    async def init_test(self):
        self._init_signals()
        start_soon(Clock(self.dut.wr_domain_clk, self.period_ns_w, 'ns').start())
        start_soon(Clock(self.dut.rd_domain_clk, self.period_ns_r, 'ns').start())
        self.dut.wr_domain_rst.value = 1
        self.dut.rd_domain_rst.value = 1
        for _ in range(3):
            await RisingEdge(self.dut.wr_domain_clk)
        for _ in range(3):
            await RisingEdge(self.dut.rd_domain_clk)
        self.dut.wr_domain_rst.value = 0
        self.dut.rd_domain_rst.value = 0
        for _ in range(2):
            await RisingEdge(self.dut.wr_domain_clk)
            await RisingEdge(self.dut.rd_domain_clk)


def _getrandbits(width: int, length: int):
    return [
        random.getrandbits(width)
        for _ in range(length)
    ]


@cocotb.test()
async def check_ports(dut):
    assert len(dut.s_axis__tvalid) == 1
    assert len(dut.s_axis__tready) == 1
    assert len(dut.s_axis__tlast) == 1
    assert len(dut.s_axis__tdata) == P_DATA_W
    assert len(dut.s_axis__tuser) == P_USER_W
    assert len(dut.s_axis__tkeep) == P_DATA_W // 8
    assert len(dut.m_axis__tvalid) == 1
    assert len(dut.m_axis__tready) == 1
    assert len(dut.m_axis__tlast) == 1
    assert len(dut.m_axis__tdata) == P_DATA_W
    assert len(dut.m_axis__tuser) == P_USER_W
    assert len(dut.m_axis__tkeep) == P_DATA_W // 8
    assert len(dut.rd_domain_clk) == 1
    assert len(dut.rd_domain_rst) == 1
    assert len(dut.wr_domain_clk) == 1
    assert len(dut.wr_domain_rst) == 1


async def tb_check_core(
    dut,
    period_ns_w,
    period_ns_r,
    burps_in: bool,
    burps_out: bool,
    dummy: int = 0
):
    tb = Testbench(dut, period_ns_w, period_ns_r)

    test_length = 32 * P_DEPTH
    timeout_ns = 100 * test_length * max(tb.period_ns_w, tb.period_ns_r)
    timeout_unit = 'ns'

    await tb.init_test()

    # Start monitors
    start_soon(tb.master.run_monitor())
    start_soon(tb.slave.run_monitor())

    dut._log.info('Launching writers...')
    proc_wr = start_soon(
        with_timeout(
            tb.master.write(
                data=_getrandbits(len(tb.master.bus.tdata), test_length),
                user=_getrandbits(len(tb.master.bus.tuser), test_length),
                keep=_getrandbits(len(tb.master.bus.tkeep), test_length),
                burps=burps_in,
                force_sync_clk_edge=True,
            ),
            timeout_ns,
            timeout_unit
        )
    )
    dut._log.info('Launching readers...')
    proc_rd = start_soon(
        with_timeout(
            tb.slave.read(
                # length=test_length,
                ignore_last=False,
                burps=burps_out,
                force_sync_clk_edge=True,
            ),
            timeout_ns,
            timeout_unit
        )
    )

    dut._log.info('Waiting...')
    await Combine(proc_wr, proc_rd)

    data_wr = tb.master.get_monitor()
    assert len(data_wr) == 1  # 1 stream
    stream_wr = data_wr[0]
    assert len(stream_wr) == test_length, f'{len(stream_wr)} != {test_length}'

    data_rd = tb.slave.get_monitor()
    assert len(data_rd) == 1  # 1 stream
    stream_rd = data_rd[0]
    assert len(stream_rd) == test_length, (
        f'{len(stream_rd)} != {test_length}')
    assert (
        extract_capture_data(stream_wr) ==
        extract_capture_data(stream_rd)
    ), (
        f'tdata does not match: '
        f'{extract_capture_data(stream_wr)} != '
        f'{extract_capture_data(stream_rd)}'
    )
    assert (
        extract_capture_user(stream_wr) ==
        extract_capture_user(stream_rd)
    ), (
        f'tuser does not match: '
        f'{extract_capture_user(stream_wr)} != '
        f'{extract_capture_user(stream_rd)}'
    )
    assert (
        extract_capture_keep(stream_wr) ==
        extract_capture_keep(stream_rd)
    ), (
        f'tkeep does not match: '
        f'{extract_capture_keep(stream_wr)} != '
        f'{extract_capture_keep(stream_rd)}'
    )


# FULL
tf_check_core = TestFactory(test_function=tb_check_core)
tf_check_core.add_option('period_ns_w', [10])
tf_check_core.add_option('period_ns_r', [10, 22, 3])
tf_check_core.add_option('burps_in',  [False, True])
tf_check_core.add_option('burps_out', [False, True])
tf_check_core.add_option('dummy', [0] * 3)
tf_check_core.generate_tests(postfix='_cdc')
