import cocotb
from cocotb.clock import Clock
from cocotb import start_soon
from cocotb.regression import TestFactory
from cocotb.triggers import RisingEdge
import os
import random

from hdl_utils.cocotb_utils.buses.axi_memory_controller import Memory, memory_init
from hdl_utils.cocotb_utils.buses.axi_stream import AXIStreamMaster, AXIStreamSlave
from hdl_utils.cocotb_utils.tb_utils import (
    unpack,
    pack,
    check_axi_stream_iface,
    check_axi_full_iface,
    check_memory_data,
    check_memory_bytes,
    get_rand_stream,
    stream_to_hex as to_hex,
    as_int,
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
        self.dut.wr_start.value = 0
        self.dut.rd_start.value = 0
        self.dut.wr_addr.value = 0
        self.dut.rd_addr.value = 0
        self.dut.wr_len_beats.value = 0
        self.dut.rd_len_beats.value = 0
        self.dut.wr_qos.value = 0
        self.dut.rd_qos.value = 0

    async def init_test(self):
        start_soon(Clock(self.dut.clk, self.clk_period, units='ns').start())
        self.init_signals()
        self.dut.rst.value = 1
        for _ in range(3):
            await RisingEdge(self.dut.clk)
        self.dut.rst.value = 0
        await RisingEdge(self.dut.clk)


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
    assert len(dut.wr_start) == 1
    assert len(dut.rd_start) == 1
    assert len(dut.wr_addr) == P_ADDR_W
    assert len(dut.rd_addr) == P_ADDR_W
    assert len(dut.wr_len_beats) == 32
    assert len(dut.rd_len_beats) == 32
    assert len(dut.wr_qos) == 4
    assert len(dut.rd_qos) == 4
    assert len(dut.wr_ack) == 1
    assert len(dut.rd_ack) == 1
    assert len(dut.wr_finish) == 1
    assert len(dut.rd_finish) == 1


async def dma_write(
    dut,
    tb: Testbench,
    addr: int,
    data: list,
    burps: bool,
    qos: int = 0,
):
    wr_len_beats = len(data)
    dut.wr_start.value = 1
    dut.wr_addr.value = addr
    dut.wr_len_beats.value = wr_len_beats
    dut.wr_qos.value = qos
    p_wr = start_soon(tb.m_axis.write(data, burps=burps))
    await RisingEdge(dut.clk)
    while dut.wr_ack.value.integer == 0:
        await RisingEdge(dut.clk)
    dut.wr_start.value = 0
    dut._log.info(f'Wairing dma write to finish...')
    await p_wr


async def dma_read(
    dut,
    tb: Testbench,
    addr: int,
    length: int,
    burps: bool,
    qos: int = 0,
):
    dut.rd_start.value = 1
    dut.rd_addr.value = addr
    dut.rd_len_beats.value = length
    dut.rd_qos.value = qos
    p_rd = start_soon(tb.s_axis.read(burps=burps))
    await RisingEdge(dut.clk)
    while dut.rd_ack.value.integer == 0:
        await RisingEdge(dut.clk)
    dut.rd_start.value = 0
    dut._log.info(f'Wairing dma read to finish...')
    rd = await p_rd
    return rd



async def tb_check_write(
    dut,
    burps_wr: bool,
    length: int,
    addr: int = 0x200,
):
    tb = Testbench(dut)
    await tb.init_test()

    for i in range(3):
        dut._log.info(f'Dma write #{i}')

        # Init memory and check it
        memory_init(
            memory=tb.memory,
            addr=0,
            data=[0] * MEM_SIZE,
            element_size_bits=8,
        )
        check_memory_data(
            memory=tb.memory,
            base_addr=0x0,
            expected=[0] * (MEM_SIZE // (P_DATA_W // 8)),
            data_width=P_DATA_W,
        )
        dut._log.info(f'Memory initial value ok')

        data = get_rand_stream(width=P_DATA_W, length=length)

        dut._log.info(f'Dma Write')
        await dma_write(
            dut=dut,
            tb=tb,
            addr=addr,
            data=data,
            qos=1,
            burps=burps_wr,
        )
        # Check memory data
        expected_zeros = [0] * (addr // (P_DATA_W // 8))
        check_memory_data(  # Zeros before
            memory=tb.memory,
            base_addr=0x0,
            expected=expected_zeros,
            data_width=P_DATA_W,
        )
        dut._log.info('zeros before ok')
        check_memory_data( # Written memory
            memory=tb.memory,
            base_addr=addr,
            expected=data,
            data_width=P_DATA_W,
        )
        dut._log.info('data ok')
        check_memory_data(  # Zeros after
            memory=tb.memory,
            base_addr=addr + len(data) * (P_DATA_W // 8),
            expected=expected_zeros,
            data_width=P_DATA_W,
        )
        dut._log.info('zeros after ok')


async def tb_check_read(
    dut,
    burps_rd: bool,
    length: int,
    addr: int = 0x200,
):
    tb = Testbench(dut)
    await tb.init_test()

    for i in range(3):

        # Init memory and check it
        memory_data = get_rand_stream(width=P_DATA_W, length=MEM_SIZE * 8 // P_DATA_W)
        memory_init(
            memory=tb.memory,
            addr=0x0,
            data=memory_data,
            element_size_bits=P_DATA_W,
        )
        check_memory_data(
            memory=tb.memory,
            base_addr=0x0,
            expected=memory_data,
            data_width=P_DATA_W,
        )

        # Dma Read
        dut._log.info(f'Dma read.')
        rd = await dma_read(
            dut=dut,
            tb=tb,
            addr=addr,
            length=length,
            qos=1,
            burps=burps_rd,
        )
        dut._log.info(f'Done.')

        # Check memory data (no changes expected)
        check_memory_data(
            memory=tb.memory,
            base_addr=0x0,
            expected=memory_data,
            data_width=P_DATA_W,
        )

        addr_end = addr + as_int(length * P_DATA_W / 8)
        mem = tb.memory[addr:addr_end].tolist()
        print()
        expected = list(pack(
            buffer=mem,
            elements=P_DATA_W // 8,
            element_width=8,
        ))
        # expected = memory_data[addr * 8 // P_DATA_W:addr * 8 // P_DATA_W + length]
        assert len(rd) == len(expected), (
            f"Length mismatch in read #{i}: {len(rd)} != {len(expected)}\n{to_hex(rd)}\n!=\n{to_hex(expected)}"
        )
        assert rd == expected, (
            f"Data mismatch in read #{i}:\n{to_hex(rd)}\n!=\n{to_hex(expected)}"
        )


async def tb_check_rw(
    dut,
    burps_wr: bool,
    burps_rd: bool,
    addr_wr: int,
    addr_rd: int,
    length_wr: int,
    lenght_rd: int,
):
    # Do simultaneous WR/RD (different areas)
    raise NotImplementedError()

    tb = Testbench(dut)
    await tb.init_test()

    # # Check memory initial value
    # check_memory_data(
    #     memory=tb.memory,
    #     base_addr=0x0,
    #     expected=[0] * (MEM_SIZE // (P_DATA_W // 8)),
    #     data_width=P_DATA_W,
    # )
    # dut._log.info(f'Memory initial value ok')

    # addr_wr = 0x200
    # burst_len = 16
    # n_bytes = burst_len * (P_DATA_W // 8)
    # data = [random.getrandbits(P_DATA_W) for _ in range(burst_len)]
    # # data = get_incr_data_128b(length=burst_len)
    # addr_rd = addr_wr + burst_len * (P_DATA_W // 8)

    # read_zone_data = list(range(n_bytes))[::-1]
    # tb.memory[addr_rd:addr_rd + n_bytes] = read_zone_data

    # # Write a complete burst of 256 beats
    # dut._log.info(f'Writing burst...')
    # p_write = write_burst(
    #     dut=dut,
    #     tb=tb,
    #     addr=addr_wr,
    #     data=data,
    #     qos=1,
    # )
    # dut._log.info(f'Reading burst...')
    # p_read = read_burst(
    #     dut=dut,
    #     tb=tb,
    #     addr=addr_rd,
    #     burst_len=burst_len,
    #     qos=2,
    # )
    # wr = await p_write
    # rd = await p_read

    # dut._log.info(f'Done.')
    # # Check memory data
    # expected_zeros = [0] * (addr_wr // (P_DATA_W // 8))
    # check_memory_data(  # Zeros before
    #     memory=tb.memory,
    #     base_addr=0x0,
    #     expected=expected_zeros,
    #     data_width=P_DATA_W,
    # )
    # dut._log.info('zeros before ok')
    # check_memory_data( # Written memory
    #     memory=tb.memory,
    #     base_addr=addr_wr,
    #     expected=data,
    #     data_width=P_DATA_W,
    # )
    # dut._log.info('data ok')
    # check_memory_bytes(
    #     memory=tb.memory,
    #     base_addr=addr_rd,
    #     expected=read_zone_data,
    # )
    # dut._log.info('read zone ok')
    # assert list(unpack(rd, elements=P_DATA_W // 8, element_width=8)) == read_zone_data, f"{rd}\n!=\n{read_zone_data}"
    # dut._log.info('read data ok')



tf_tb_check_write = TestFactory(test_function=tb_check_write)
tf_tb_check_read = TestFactory(test_function=tb_check_read)
# tf_tb_check_rw = TestFactory(test_function=tb_check_rw)

reduced_set_of_test_cases = False
if reduced_set_of_test_cases:
    tf_tb_check_write.add_option('burps_wr', [True])
    tf_tb_check_write.add_option('length', [
        3 * P_BURST_LEN,
        3 * P_BURST_LEN + 1,
    ])
    tf_tb_check_write.add_option('addr', [0x200])
    tf_tb_check_write_postfix = '_basic'

    tf_tb_check_read.add_option('burps_rd', [True])
    tf_tb_check_read.add_option('length', [
        3 * P_BURST_LEN,
        3 * P_BURST_LEN + 1,
    ])
    tf_tb_check_read.add_option('addr', [0x200])
    tf_tb_check_read_postfix = '_basic'

else:
    tf_tb_check_write.add_option('burps_wr', [False, True])
    tf_tb_check_write.add_option('length', [
        4 * P_BURST_LEN - 1,
        4 * P_BURST_LEN,
        4 * P_BURST_LEN + 1,
        4 * P_BURST_LEN + 2,
    ])
    tf_tb_check_write.add_option('addr', [0x200])
    tf_tb_check_write_postfix = '_full'

    tf_tb_check_read.add_option('burps_rd', [False, True])
    tf_tb_check_read.add_option('length', [
        4 * P_BURST_LEN - 1,
        4 * P_BURST_LEN,
        4 * P_BURST_LEN + 1,
        4 * P_BURST_LEN + 2,
    ])
    tf_tb_check_read.add_option('addr', [0x200])
    tf_tb_check_read_postfix = '_full'


tf_tb_check_write.generate_tests(postfix=tf_tb_check_write_postfix)
tf_tb_check_read.generate_tests(postfix=tf_tb_check_read_postfix)
