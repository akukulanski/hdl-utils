import cocotb
from cocotb.clock import Clock
from cocotb import start_soon
from cocotb.regression import TestFactory
from cocotb.triggers import RisingEdge, Combine
from cocotb.utils import get_sim_time
import os
import pytest

from hdl_utils.cocotb_utils.buses.axi_memory_controller import Memory, memory_init
from hdl_utils.cocotb_utils.buses.axi_stream import AXIStreamMaster, AXIStreamSlave
from hdl_utils.cocotb_utils.tb_utils import (
    pack,
    check_axi_stream_iface,
    check_axi_full_iface,
    check_memory_data,
    get_rand_stream,
    stream_to_hex as to_hex,
    as_int,
    send_data_repeatedly,
    wait_n_streams,
)


P_ADDR_W = int(os.environ['P_ADDR_W'])
P_DATA_W = int(os.environ['P_DATA_W'])
P_USER_W = int(os.environ['P_USER_W'])
P_BURST_LEN = int(os.environ['P_BURST_LEN'])

ADDR_JUMP = P_DATA_W // 8
MEM_SIZE = 0x10000


class Testbench:
    clk_period = 10

    def __init__(self, dut):
        self.dut = dut
        self.memory = Memory(size=MEM_SIZE)
        self.memory_ctrl = self.memory.create_axi(entity=dut, prefix="m_axi_", clock=dut.clk)
        self.m_axis = AXIStreamMaster(dut, "s_axis_", dut.clk)
        self.s_axis = AXIStreamSlave(dut, "m_axis_", dut.clk)

    def init_signals(self):
        self.dut.wr_enable.value = 0
        self.dut.rd_enable.value = 0
        self.dut.base_addr_0.value = 0
        self.dut.base_addr_1.value = 0
        self.dut.base_addr_2.value = 0
        self.dut.wr_qos.value = 0
        self.dut.rd_qos.value = 0
        self.dut.wr_len_beats.value = 0
        self.dut.rd_len_beats.value = 0
        self.dut.wr_dont_change_buffer_if_incomplete.value = 0

    async def init_test(self):
        self.reset_memory()
        start_soon(Clock(self.dut.clk, self.clk_period, units='ns').start())
        self.init_signals()
        self.dut.rst.value = 1
        for _ in range(3):
            await RisingEdge(self.dut.clk)
        self.dut.rst.value = 0
        await RisingEdge(self.dut.clk)

    def reset_memory(self):
        memory_init(
            memory=self.memory,
            addr=0,
            data=[0] * MEM_SIZE,
            element_size_bits=8,
        )


@cocotb.test()
async def check_ports(dut):
    # M_AXI
    check_axi_full_iface(
        dut=dut,
        prefix='m_axi__',
        data_w=P_DATA_W,
        addr_w=P_ADDR_W,
    )
    check_axi_stream_iface(
        dut=dut,
        prefix='s_axis__',
        data_w=P_DATA_W,
        user_w=P_USER_W,
        no_tkeep=True,
    )
    check_axi_stream_iface(
        dut=dut,
        prefix='m_axis__',
        data_w=P_DATA_W,
        user_w=P_USER_W,
        no_tkeep=True,
    )
    # Others
    assert len(dut.wr_enable) == 1
    assert len(dut.rd_enable) == 1
    assert len(dut.base_addr_0) == P_ADDR_W
    assert len(dut.base_addr_1) == P_ADDR_W
    assert len(dut.base_addr_2) == P_ADDR_W
    assert len(dut.wr_qos) == 4
    assert len(dut.rd_qos) == 4
    assert len(dut.wr_len_beats) == 32
    assert len(dut.rd_len_beats) == 32
    assert len(dut.wr_dont_change_buffer_if_incomplete) == 1


def check_buffer_size_consistent(
    length: int,
    buffer_address_array: list[int],
):
    minimum_buffer_size = length * ADDR_JUMP
    sorted_buff_addr = sorted([*buffer_address_array, MEM_SIZE])
    for i in range(len(sorted_buff_addr) - 1):
        assert minimum_buffer_size < (sorted_buff_addr[i+1] - sorted_buff_addr[i]), (
            f'Inconsistent input parameters: minimum_buffer_size={hex(minimum_buffer_size)}, but the size '
            f'of buffer #{i} is {hex(sorted_buff_addr[i+1] - sorted_buff_addr[i])}'
        )


async def tb_check_data_consistency_wo_ro(
    dut,
    burps_wr: bool,
    burps_rd: bool,
    length: int,
    buffer_address_array: list[int],
    wr_dont_change_buffer_if_incomplete: int,
):
    check_buffer_size_consistent(length=length, buffer_address_array=buffer_address_array)
    wr_qos = rd_qos = 1
    wr_len_beats = rd_len_beats = length
    wr_dont_change_buffer_if_incomplete = int(bool(wr_dont_change_buffer_if_incomplete))
    n_streams_wo_ro = 5

    check_buffer_size_consistent(length=length, buffer_address_array=buffer_address_array)

    tb = Testbench(dut)
    await tb.init_test()

    dut.wr_qos.value = wr_qos
    dut.rd_qos.value = rd_qos
    dut.wr_len_beats.value = wr_len_beats
    dut.rd_len_beats.value = rd_len_beats
    dut.base_addr_0.value = buffer_address_array[0]
    dut.base_addr_1.value = buffer_address_array[1]
    dut.base_addr_2.value = buffer_address_array[2]
    dut.wr_dont_change_buffer_if_incomplete.value = wr_dont_change_buffer_if_incomplete

    data_wo_ro = [
        get_rand_stream(width=P_DATA_W, length=length)
        for _ in range(n_streams_wo_ro)
    ]

    p_wr = start_soon(tb.m_axis.write_multiple(
        datas=data_wo_ro,
        burps=burps_wr,
    ))
    p_rd = start_soon(tb.s_axis.read_multiple(
        n_streams=n_streams_wo_ro,
        burps=burps_rd,
    ))

    # Write only
    dut._log.info(f'Write only')
    dut.wr_enable.value = 1
    dut.rd_enable.value = 0
    await p_wr

    non_optimal_workaround = False

    # Optimal case: the last two written streams
    # available in memory.
    expected_data_buffers = [
        [0] * length,
        data_wo_ro[-1],  # or: data_wo_ro[-2],
        data_wo_ro[-2],  # or: data_wo_ro[-1],
    ]

    # FIXME: workaround as the behavior is (while correct) not
    # optimal and it's the same buffer that gets overwritten with
    # new data, instead of overwriting the buffer with the oldest data.
    if non_optimal_workaround:
        dut._log.warning(f'Behavior not optimal. The same buffer that gets '
                        f'overwritten with new data, instead of overwriting '
                        f'the buffer with the oldest data.')
        expected_data_buffers = [
            [0] * length,
            data_wo_ro[0],
            data_wo_ro[-1],
        ]

    for i in range(len(expected_data_buffers)):
        dut._log.info(f'Checking buffer #{i}')
        buff_addr = buffer_address_array[i]
        dut._log.info(f'Buffer address: {hex(buff_addr)}')
        dut._log.info(f'end_addr = {hex(buff_addr + length * ADDR_JUMP)}')
        check_memory_data(
            memory=tb.memory,
            base_addr=buffer_address_array[i],
            data_width=P_DATA_W,
            expected=expected_data_buffers[i],
        )

    # Read only
    dut._log.info(f'Read only')
    dut.wr_enable.value = 0
    dut.rd_enable.value = 1
    rd_streams = await p_rd

    # The last stream written should be read
    expected_streams = [
        [0] * length,
        data_wo_ro[-1],
        data_wo_ro[-1],
    ]

    # FIXME: This is a workaround as currently the core is consistent but not optimal.
    # It will read correct data, but not the last available.
    if non_optimal_workaround:
        dut._log.warning(f'Modified value to allow test pass. Behavior is correct, but not optimal.')
        expected_streams = [
            [0] * length,
            data_wo_ro[0],
            data_wo_ro[0],
        ]

    for i in range(len(expected_streams), n_streams_wo_ro):
        expected_streams.append(expected_streams[-1])

    for i in range(n_streams_wo_ro):
        rd = rd_streams[i]
        expected = expected_streams[i]
        assert len(rd) == len(expected), (
            f"Length mismatch in read #{i}: {len(rd)} != {len(expected)}\n{to_hex(rd)}\n!=\n{to_hex(expected)}"
        )
        assert rd == expected, (
            f"Data mismatch in read #{i}:\n{to_hex(rd)}\n!=\n{to_hex(expected)}"
        )


async def tb_check_data_consistency_rw(
    dut,
    burps_wr: bool,
    burps_rd: bool,
    length: int,
    buffer_address_array: list[int],
    wr_dont_change_buffer_if_incomplete: int,
):
    check_buffer_size_consistent(length=length, buffer_address_array=buffer_address_array)

    wr_qos = rd_qos = 1
    wr_len_beats = rd_len_beats = length
    wr_dont_change_buffer_if_incomplete = int(bool(wr_dont_change_buffer_if_incomplete))

    tb = Testbench(dut)
    await tb.init_test()

    dut.wr_qos.value = wr_qos
    dut.rd_qos.value = rd_qos
    dut.wr_len_beats.value = wr_len_beats
    dut.rd_len_beats.value = rd_len_beats
    dut.base_addr_0.value = buffer_address_array[0]
    dut.base_addr_1.value = buffer_address_array[1]
    dut.base_addr_2.value = buffer_address_array[2]
    dut.wr_dont_change_buffer_if_incomplete.value = wr_dont_change_buffer_if_incomplete

    n_streams_rw = 20
    data_rw = [
        get_rand_stream(width=P_DATA_W, length=length)
        for _ in range(n_streams_rw)
    ]
    # Write and Read
    dut._log.info(f'Write and Read')
    tb.reset_memory()
    p_wr = start_soon(tb.m_axis.write_multiple(
        datas=data_rw,
        burps=burps_wr,
    ))
    p_rd = start_soon(tb.s_axis.read_multiple(
        n_streams=n_streams_rw,
        burps=burps_rd,
    ))
    dut.wr_enable.value = 1
    dut.rd_enable.value = 1
    await p_wr
    rd_streams = await p_rd
    # Check memory
    possible_values = [*data_rw]
    for buff_addr in buffer_address_array:
        buff_data = list(pack(
            buffer=tb.memory[buff_addr:buff_addr + ADDR_JUMP * length].tolist(),
            elements=P_DATA_W // 8,
            element_width=8,
        ))
        assert buff_data in possible_values
        possible_values.remove(buff_data)
    # Check read data
    assert len(rd_streams) == n_streams_rw
    possible_values = [[0] * length, *data_rw]
    for i in range(n_streams_rw):
        rd = rd_streams[i]
        assert rd in possible_values, (
            f'Mismatch in read stream #{i} during rw:\n'
            f'{to_hex(rd)}\n'
            f'not in\n'
            + '\n'.join([str(to_hex(x)) for x in possible_values])
        )
        idx = possible_values.index(rd)
        if idx > 0:
            # Streams can be repeated or missing, but always in the right order.
            # Remove previous streams from possible values.
            possible_values = possible_values[idx - 1:]


async def tb_check_throughput(
    dut,
    length: int,
    buffer_address_array: list[int],
    wr_dont_change_buffer_if_incomplete: int,
):
    check_buffer_size_consistent(length=length, buffer_address_array=buffer_address_array)
    n_streams = 10
    wr_qos = rd_qos = 0
    wr_len_beats = rd_len_beats = length
    wr_dont_change_buffer_if_incomplete = int(bool(wr_dont_change_buffer_if_incomplete))

    tb = Testbench(dut)
    await tb.init_test()
    dut.wr_qos.value = wr_qos
    dut.rd_qos.value = rd_qos
    dut.wr_len_beats.value = wr_len_beats
    dut.rd_len_beats.value = rd_len_beats
    dut.base_addr_0.value = buffer_address_array[0]
    dut.base_addr_1.value = buffer_address_array[1]
    dut.base_addr_2.value = buffer_address_array[2]
    dut.wr_dont_change_buffer_if_incomplete.value = wr_dont_change_buffer_if_incomplete

    data = get_rand_stream(width=P_DATA_W, length=length)
    start_soon(tb.s_axis.run_data_monitor())
    start_soon(send_data_repeatedly(
        driver=tb.m_axis,
        data=data,
        burps=False,
    ))
    start_soon(tb.s_axis.read_driver(burps=False))
    dut.wr_enable.value = 1
    dut.rd_enable.value = 1
    await wait_n_streams(bus=tb.s_axis.bus, clock=dut.clk, n_streams=1)
    t_start = get_sim_time('ns')
    await wait_n_streams(bus=tb.s_axis.bus, clock=dut.clk, n_streams=n_streams)
    t_end = get_sim_time('ns')
    elapsed_ns = t_end - t_start
    elapsed_clk_cycles = elapsed_ns / tb.clk_period
    tolerance = 2 / P_BURST_LEN  # 2 clock cycles on each burst
    assert elapsed_clk_cycles == pytest.approx(n_streams * length, rel=tolerance)

    recv_streams = tb.s_axis.get_data_streams_from_monitor()
    recv_streams = recv_streams[2:-1]  # discard first two (memory garbage) and last (incomplete)
    assert len(recv_streams)
    for rd in recv_streams:
        assert rd == data


async def tb_check_wr_early_last(
    dut,
    burps_wr: bool,
    burps_rd: bool,
    length: int,
    buffer_address_array: list[int],
    wr_dont_change_buffer_if_incomplete: int,
):
    check_buffer_size_consistent(length=length, buffer_address_array=buffer_address_array)
    wr_qos = rd_qos = 0
    wr_len_beats = rd_len_beats = length
    wr_dont_change_buffer_if_incomplete = int(bool(wr_dont_change_buffer_if_incomplete))

    tb = Testbench(dut)
    await tb.init_test()
    dut.wr_qos.value = wr_qos
    dut.rd_qos.value = rd_qos
    dut.wr_len_beats.value = wr_len_beats
    dut.rd_len_beats.value = rd_len_beats
    dut.base_addr_0.value = buffer_address_array[0]
    dut.base_addr_1.value = buffer_address_array[1]
    dut.base_addr_2.value = buffer_address_array[2]
    dut.wr_dont_change_buffer_if_incomplete.value = wr_dont_change_buffer_if_incomplete

    data_length = length - 1  # early tlast
    data = get_rand_stream(width=P_DATA_W, length=data_length)
    dut.wr_enable.value = 1
    dut.rd_enable.value = 0
    await tb.m_axis.write(data=data, burps=burps_wr)
    dut.wr_enable.value = 0
    dut.rd_enable.value = 1
    rd_streams = await tb.s_axis.read_multiple(n_streams=2, burps=burps_rd)

    if wr_dont_change_buffer_if_incomplete:
        expected_streams = [
            [0] * length,
            [0] * length,
        ]
    else:
        expected_streams = [
            [0] * length,
            [*data, 0]
        ]

    for i in range(len(expected_streams)):
        rd = rd_streams[i]
        expected = expected_streams[i]
        assert len(rd) == len(expected), (
            f"Length mismatch in read #{i}: {len(rd)} != {len(expected)}\n{to_hex(rd)}\n!=\n{to_hex(expected)}"
        )
        assert rd == expected, (
            f"Data mismatch in read #{i}:\n{to_hex(rd)}\n!=\n{to_hex(expected)}"
        )

    # Check behavior is restored with complete write
    prv_data = data
    data = get_rand_stream(width=P_DATA_W, length=length)
    dut.wr_enable.value = 1
    dut.rd_enable.value = 0
    await tb.m_axis.write(data=data, burps=burps_wr)
    dut.wr_enable.value = 0
    dut.rd_enable.value = 1
    rd_streams = await tb.s_axis.read_multiple(n_streams=2, burps=burps_rd)
    dut.wr_enable.value = 0
    dut.rd_enable.value = 0

    if wr_dont_change_buffer_if_incomplete:
        expected_streams = [
            [0] * length,
            data,
        ]
    else:
        expected_streams = [
            [*prv_data, 0],
            data,
        ]

    for i in range(len(expected_streams)):
        rd = rd_streams[i]
        expected = expected_streams[i]
        assert len(rd) == len(expected), (
            f"Length mismatch in read #{i}: {len(rd)} != {len(expected)}\n{to_hex(rd)}\n!=\n{to_hex(expected)}"
        )
        assert rd == expected, (
            f"Data mismatch in read #{i}:\n{to_hex(rd)}\n!=\n{to_hex(expected)}"
        )


async def tb_check_wr_missing_last(
    dut,
    wr_dont_change_buffer_if_incomplete: bool,
):
    raise NotImplementedError()


TESTCASE_CONFIG_FULL = 'full'
TESTCASE_CONFIG_REDUCED = 'reduced'
TESTCASE_CONFIG_MINUMUM = 'minimum'

# testcase_config = TESTCASE_CONFIG_FULL
testcase_config = TESTCASE_CONFIG_REDUCED
# testcase_config = TESTCASE_CONFIG_MINUMUM

if testcase_config == TESTCASE_CONFIG_MINUMUM:
    set_of_burps_wr = [True]
    set_of_burps_rd = [True]
    set_of_lengths = [3 * P_BURST_LEN]
    set_of_buff_addr = [[0x100, 0x500, 0x900]]
    set_of_wr_dont_change_buffer_if_incomplete = [0]
    postfix = '_minimum'

elif testcase_config == TESTCASE_CONFIG_REDUCED:
    set_of_burps_wr = [True]
    set_of_burps_rd = [True]
    set_of_lengths = [3 * P_BURST_LEN, 3 * P_BURST_LEN + 1, 3 * P_BURST_LEN - 1]
    set_of_buff_addr = [[0x100, 0x500, 0x900]]
    set_of_wr_dont_change_buffer_if_incomplete = [0, 1]
    postfix = '_basic'

else:
    set_of_burps_wr = [False, True]
    set_of_burps_rd = [False, True]
    set_of_lengths = [
        4 * P_BURST_LEN - 1,
        4 * P_BURST_LEN,
        4 * P_BURST_LEN + 1,
        4 * P_BURST_LEN + 2,
    ]
    set_of_buff_addr = [[0x100, 0x500, 0x900]]
    set_of_wr_dont_change_buffer_if_incomplete = [0, 1]
    postfix = '_full'


tf_tb_check_data_consistency_wo_ro = TestFactory(test_function=tb_check_data_consistency_wo_ro)
tf_tb_check_data_consistency_rw = TestFactory(test_function=tb_check_data_consistency_rw)
tf_tb_check_throughput = TestFactory(test_function=tb_check_throughput)
tf_tb_chewr_ck_early_last = TestFactory(test_function=tb_check_wr_early_last)
tf_tb_chewr_ck_missing_last = TestFactory(test_function=tb_check_wr_missing_last)


for tf in (
    tf_tb_check_data_consistency_wo_ro,
    tf_tb_check_data_consistency_rw,
    tf_tb_chewr_ck_early_last,
    tf_tb_chewr_ck_missing_last,
):
    tf.add_option('burps_wr', set_of_burps_wr)
    tf.add_option('burps_rd', set_of_burps_rd)
    tf.add_option('length', set_of_lengths)
    tf.add_option('buffer_address_array', set_of_buff_addr)
    tf.add_option('wr_dont_change_buffer_if_incomplete', set_of_wr_dont_change_buffer_if_incomplete)

tf_tb_check_throughput.add_option('length', set_of_lengths)
tf_tb_check_throughput.add_option('buffer_address_array', set_of_buff_addr)
tf_tb_check_throughput.add_option('wr_dont_change_buffer_if_incomplete', set_of_wr_dont_change_buffer_if_incomplete)


tf_tb_check_data_consistency_wo_ro.generate_tests(postfix=postfix)
tf_tb_check_data_consistency_rw.generate_tests(postfix=postfix)
tf_tb_check_throughput.generate_tests(postfix=postfix)
tf_tb_chewr_ck_early_last.generate_tests(postfix=postfix)
# tf_tb_chewr_ck_missing_last.generate_tests(postfix=postfix)
