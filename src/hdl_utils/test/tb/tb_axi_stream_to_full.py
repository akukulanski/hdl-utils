import cocotb
from cocotb.clock import Clock
from cocotb import start_soon
from cocotb.triggers import RisingEdge
import os
import random

from hdl_utils.cocotb_utils.buses.axi_memory_controller import Axi4MemoryController
from hdl_utils.cocotb_utils.buses.axi_stream import AXIStreamMaster, AXIStreamSlave
from hdl_utils.cocotb_utils.tb_utils import unpack, pack


P_ADDR_W = int(os.environ['P_ADDR_W'])
P_DATA_W = int(os.environ['P_DATA_W'])
P_USER_W = int(os.environ['P_USER_W'])

ADDR_JUMP = P_DATA_W // 8
MEM_SIZE = 0x10000


class Testbench:
    clk_period = 10

    def __init__(self, dut):
        self.dut = dut
        self.memory_ctrl = Axi4MemoryController(dut, prefix="m_axi_", clk=dut.clk, size=MEM_SIZE)
        self.m_axis = AXIStreamMaster(dut, "s_axis_", dut.clk)
        self.s_axis = AXIStreamSlave(dut, "m_axis_", dut.clk)

    def init_signals(self):
        self.dut.wr_qos.value = 0
        self.dut.rd_qos.value = 0
        self.dut.wr_burst.value = 0
        self.dut.rd_burst.value = 0
        self.dut.wr_addr.value = 0
        self.dut.rd_addr.value = 0
        self.dut.wr_valid.value = 0
        self.dut.rd_valid.value = 0

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
    # assert len(dut.m_axi__AWID) == 0
    assert len(dut.m_axi__AWADDR) == P_ADDR_W
    assert len(dut.m_axi__AWLEN) == 8
    assert len(dut.m_axi__AWSIZE) == 3
    assert len(dut.m_axi__AWBURST) == 2
    assert len(dut.m_axi__AWLOCK) == 1
    assert len(dut.m_axi__AWCACHE) == 4
    assert len(dut.m_axi__AWPROT) == 3
    assert len(dut.m_axi__AWQOS) == 4
    assert len(dut.m_axi__AWREGION) == 4
    # assert len(dut.m_axi__AWUSER) == P_USER_W
    assert len(dut.m_axi__AWVALID) == 1
    assert len(dut.m_axi__AWREADY) == 1
    # Write channel
    # assert len(dut.m_axi__WID) == 0
    assert len(dut.m_axi__WDATA) == P_DATA_W
    assert len(dut.m_axi__WSTRB) == P_DATA_W // 8
    assert len(dut.m_axi__WLAST) == 1
    # assert len(dut.m_axi__WUSER) == P_USER_W
    assert len(dut.m_axi__WVALID) == 1
    assert len(dut.m_axi__WREADY) == 1
    # Write response channel
    # assert len(dut.m_axi__BID) == 0
    assert len(dut.m_axi__BRESP) == 2
    # assert len(dut.m_axi__BUSER) == P_USER_W
    assert len(dut.m_axi__BVALID) == 1
    assert len(dut.m_axi__BREADY) == 1
    # Address read channel
    # assert len(dut.m_axi__ARID) == 0
    assert len(dut.m_axi__ARADDR) == P_ADDR_W
    assert len(dut.m_axi__ARLEN) == 8
    assert len(dut.m_axi__ARSIZE) == 3
    assert len(dut.m_axi__ARBURST) == 2
    assert len(dut.m_axi__ARLOCK) == 1
    assert len(dut.m_axi__ARCACHE) == 4
    assert len(dut.m_axi__ARPROT) == 3
    assert len(dut.m_axi__ARQOS) == 4
    assert len(dut.m_axi__ARREGION) == 4
    # assert len(dut.m_axi__ARUSER) == P_USER_W
    assert len(dut.m_axi__ARVALID) == 1
    assert len(dut.m_axi__ARREADY) == 1
    # Read channel
    # assert len(dut.m_axi__RID) == 0
    assert len(dut.m_axi__RDATA) == P_DATA_W
    assert len(dut.m_axi__RLAST) == 1
    # assert len(dut.m_axi__RUSER) == P_USER_W
    assert len(dut.m_axi__RVALID) == 1
    assert len(dut.m_axi__RREADY) == 1
    assert len(dut.m_axi__RRESP) == 2

    # S_AXIS
    assert len(dut.s_axis__tvalid) == 1
    assert len(dut.s_axis__tready) == 1
    assert len(dut.s_axis__tdata) == P_DATA_W
    # assert len(dut.s_axis__tuser) == 0
    # assert len(dut.s_axis__tkeep) == 0

    # M_AXIS
    assert len(dut.m_axis__tvalid) == 1
    assert len(dut.m_axis__tready) == 1
    assert len(dut.m_axis__tdata) == P_DATA_W
    # assert len(dut.m_axis__tuser) == 0
    # assert len(dut.m_axis__tkeep) == 0

    # Others
    assert len(dut.wr_qos) == 4
    assert len(dut.rd_qos) == 4
    assert len(dut.wr_burst) == 8
    assert len(dut.rd_burst) == 8
    assert len(dut.wr_addr) == P_ADDR_W
    assert len(dut.rd_addr) == P_ADDR_W
    assert len(dut.wr_valid) == 1
    assert len(dut.wr_ready) == 1
    assert len(dut.rd_valid) == 1
    assert len(dut.rd_ready) == 1


async def write_burst(
    dut,
    tb,
    addr: int,
    data: list,
    burst_len: int = None,
    qos: int = 0,
):
    if burst_len is None:
        burst_len = len(data) - 1
    assert burst_len < 256

    dut.wr_qos.value = qos
    dut.wr_burst.value = burst_len
    dut.wr_addr.value = addr
    dut.wr_valid.value = 1
    p_wr = start_soon(tb.m_axis.write(data))
    await RisingEdge(dut.clk)
    while dut.wr_ready.value.integer == 0:
        await RisingEdge(dut.clk)

    dut.wr_valid.value = 0
    await p_wr


async def read_burst(
    dut,
    tb,
    addr: int,
    burst_len: int,
    qos: int = 0,
) -> list:
    assert burst_len <= 256

    dut.rd_qos.value = qos
    dut.rd_burst.value = burst_len - 1
    dut.rd_addr.value = addr
    dut.rd_valid.value = 1
    p_rd = start_soon(tb.s_axis.read())
    await RisingEdge(dut.clk)
    while dut.rd_ready.value.integer == 0:
        await RisingEdge(dut.clk)

    dut.rd_valid.value = 0
    rd = await p_rd
    return rd


def check_memory(memory, base_addr: int, expected: list[int]):
    for offset, value in enumerate(list(unpack(
        buffer=expected,
        elements=P_DATA_W // 8,
        element_width=8,
    ))):
        addr = base_addr + offset
        # print(f'addr={hex(base_addr)}+{hex(offset)}: exp={hex(value)} ; got={hex(memory[addr])}')
        assert memory[addr] == value, (
            f"Error in address {hex(addr)}: Expected {hex(value)}, Got {hex(memory[addr])}"
        )

def check_memory_bytes(memory, base_addr: int, expected: list[int]):
    for offset, value in enumerate(expected):
        addr = base_addr + offset
        # print(f'addr={hex(base_addr)}+{hex(offset)}: exp={hex(value)} ; got={hex(memory[addr])}')
        assert memory[addr] == value, (
            f"Error in address {hex(addr)}: Expected {hex(value)}, Got {hex(memory[addr])}"
        )


def get_incr_data_128b(length: int) -> list:
    return [
        (
            (((8 * i + 0) % 256) << (0 * 8)) |
            (((8 * i + 1) % 256) << (1 * 8)) |
            (((8 * i + 2) % 256) << (2 * 8)) |
            (((8 * i + 3) % 256) << (3 * 8)) |
            (((8 * i + 4) % 256) << (4 * 8)) |
            (((8 * i + 5) % 256) << (5 * 8)) |
            (((8 * i + 6) % 256) << (6 * 8)) |
            (((8 * i + 7) % 256) << (7 * 8)) |
            (((8 * i + 8) % 256) << (8 * 8)) |
            (((8 * i + 9) % 256) << (9 * 8)) |
            (((8 * i + 10) % 256) << (10 * 8)) |
            (((8 * i + 11) % 256) << (11 * 8)) |
            (((8 * i + 12) % 256) << (12 * 8)) |
            (((8 * i + 13) % 256) << (13 * 8)) |
            (((8 * i + 14) % 256) << (14 * 8)) |
            (((8 * i + 15) % 256) << (15 * 8))
        )
        for i in range(length)
    ]




@cocotb.test()
async def check_write_then_read(dut):
    tb = Testbench(dut)
    await tb.init_test()

    dut._log.info(f'P_ADDR_W: {P_ADDR_W}')
    dut._log.info(f'P_DATA_W: {P_DATA_W}')
    dut._log.info(f'P_USER_W: {P_USER_W}')

    # Check memory initial value
    check_memory(
        memory=tb.memory_ctrl,
        base_addr=0x0,
        expected=[0] * (MEM_SIZE // (P_DATA_W // 8))
    )
    dut._log.info(f'Memory initial value ok')

    addr = 0x200
    burst_len = 16
    data = [random.getrandbits(P_DATA_W) for _ in range(burst_len)]
    # data = get_incr_data_128b(length=burst_len)

    # Write a complete burst of 256 beats
    dut._log.info(f'Writing burst...')
    await write_burst(
        dut=dut,
        tb=tb,
        addr=addr,
        data=data,
        qos=1,
    )
    dut._log.info(f'Done.')
    # Check memory data
    expected_zeros = [0] * (addr // (P_DATA_W // 8))
    check_memory(  # Zeros before
        memory=tb.memory_ctrl,
        base_addr=0x0,
        expected=expected_zeros,
    )
    dut._log.info('zeros before ok')
    check_memory( # Written memory
        memory=tb.memory_ctrl,
        base_addr=addr,
        expected=data,
    )
    dut._log.info('data ok')
    check_memory(  # Zeros after
        memory=tb.memory_ctrl,
        base_addr=addr + burst_len * (P_DATA_W // 8),
        expected=expected_zeros,
    )
    dut._log.info('zeros after ok')

    # Read a complete burst of 256 beats
    dut._log.info(f'Reading burst...')
    rd = await read_burst(
        dut=dut,
        tb=tb,
        addr=addr,
        burst_len=burst_len,
        qos=2,
    )
    dut._log.info(f'Done.')
    # Check memory data (no changes expected)
    check_memory(  # Zeros before
        memory=tb.memory_ctrl,
        base_addr=0x0,
        expected=expected_zeros,
    )
    dut._log.info('zeros before ok')
    check_memory(  # Written memory
        memory=tb.memory_ctrl,
        base_addr=addr,
        expected=data,
    )
    dut._log.info('data ok')
    check_memory(  # Zeros after
        memory=tb.memory_ctrl,
        base_addr=0x200 + burst_len * (P_DATA_W // 8),
        expected=expected_zeros,
    )
    dut._log.info('zeros after ok')

    assert len(rd) == len(data)
    assert rd == data, f"rd != data\n{rd}\n!=\n{data}"


@cocotb.test()
async def check_write_read(dut):
    # Do simultaneous WR/RD (different areas)

    tb = Testbench(dut)
    await tb.init_test()

    # Check memory initial value
    check_memory(
        memory=tb.memory_ctrl,
        base_addr=0x0,
        expected=[0] * (MEM_SIZE // (P_DATA_W // 8))
    )
    dut._log.info(f'Memory initial value ok')

    addr_wr = 0x200
    burst_len = 16
    n_bytes = burst_len * (P_DATA_W // 8)
    data = [random.getrandbits(P_DATA_W) for _ in range(burst_len)]
    # data = get_incr_data_128b(length=burst_len)
    addr_rd = addr_wr + burst_len * (P_DATA_W // 8)

    read_zone_data = list(range(n_bytes))[::-1]
    tb.memory_ctrl[addr_rd:addr_rd + n_bytes] = read_zone_data

    # Write a complete burst of 256 beats
    dut._log.info(f'Writing burst...')
    p_write = write_burst(
        dut=dut,
        tb=tb,
        addr=addr_wr,
        data=data,
        qos=1,
    )
    dut._log.info(f'Reading burst...')
    p_read = read_burst(
        dut=dut,
        tb=tb,
        addr=addr_rd,
        burst_len=burst_len,
        qos=2,
    )
    wr = await p_write
    rd = await p_read

    dut._log.info(f'Done.')
    # Check memory data
    expected_zeros = [0] * (addr_wr // (P_DATA_W // 8))
    check_memory(  # Zeros before
        memory=tb.memory_ctrl,
        base_addr=0x0,
        expected=expected_zeros,
    )
    dut._log.info('zeros before ok')
    check_memory( # Written memory
        memory=tb.memory_ctrl,
        base_addr=addr_wr,
        expected=data,
    )
    dut._log.info('data ok')
    check_memory_bytes(
        memory=tb.memory_ctrl,
        base_addr=addr_rd,
        expected=read_zone_data,
    )
    dut._log.info('read zone ok')
    assert list(unpack(rd, elements=P_DATA_W // 8, element_width=8)) == read_zone_data, f"{rd}\n!=\n{read_zone_data}"
    dut._log.info('read data ok')



@cocotb.test()
async def check_multiple_writes_reads(dut):
    # Perform multiple consecutive writes
    tb = Testbench(dut)
    await tb.init_test()

    burst_len = 16
    n_bytes = burst_len * (P_DATA_W // 8)

    addresses = (0x200, 0x400, 0x200)
    datas = [
        [random.getrandbits(P_DATA_W) for _ in range(burst_len)]
        for _ in range(len(addresses))
    ]

    for addr, data in zip(addresses, datas):
        dut._log.info(f"Writing address: {hex(addr)}")
        await write_burst(
            dut=dut,
            tb=tb,
            addr=addr,
            data=data,
            qos=1,
        )

    addr_read = []
    for addr in set(addresses):
        if addr in addr_read:
            dut._log.info(f"Already read address {hex(addr)}. Skipping.")
        addr_read.append(addr)
        expected_data = None
        for i in range(len(addresses))[::-1]:  # reversed as last write is the data to retrieve
            if addresses[i] == addr:
                expected_data = datas[i]
                break
        # Check memory
        check_memory(
            memory=tb.memory_ctrl,
            base_addr=addr,
            expected=expected_data,
        )
        # Check read
        dut._log.info(f"Reading address: {hex(addr)}")
        rd = await read_burst(
            dut=dut,
            tb=tb,
            addr=addr,
            burst_len=burst_len,
            qos=2,
        )
        assert rd == expected_data, f"{rd}\n!=\n{expected_data}"


@cocotb.test()
async def check_write_early_tlast(dut):
    # Perform an incomplete write with early tlast

    tb = Testbench(dut)
    await tb.init_test()

    # Check memory initial value
    check_memory(
        memory=tb.memory_ctrl,
        base_addr=0x0,
        expected=[0] * (MEM_SIZE // (P_DATA_W // 8))
    )
    dut._log.info(f'Memory initial value ok')

    addr = 0x200
    burst_len = 16
    n_bytes = burst_len * (P_DATA_W // 8)
    data = [random.getrandbits(P_DATA_W) for _ in range(burst_len)]
    n_missing = 3
    data = data[:-n_missing]

    mem_init = [0xff] * n_bytes
    mem_init_packed = list(pack(
        buffer=mem_init,
        elements=P_DATA_W // 8,
        element_width=8,
    ))
    tb.memory_ctrl[addr:addr + n_bytes] = mem_init

    check_memory(
        memory=tb.memory_ctrl,
        base_addr=addr,
        expected=mem_init_packed,
    )

    dut._log.info(f"Writing address: {hex(addr)}")
    await write_burst(
        dut=dut,
        tb=tb,
        addr=addr,
        data=data,
        qos=1,
    )

    # Check memory
    expected_data = data + mem_init_packed[-n_missing:]
    check_memory(
        memory=tb.memory_ctrl,
        base_addr=addr,
        expected=expected_data,
    )
    # Check read
    dut._log.info(f"Reading address: {hex(addr)}")
    rd = await read_burst(
        dut=dut,
        tb=tb,
        addr=addr,
        burst_len=burst_len,
        qos=2,
    )
    assert rd == expected_data, f'{rd}\n!=\n{expected_data}'

    # Check normal operation after early tlast
    addr = 0x220
    burst_len = 16
    data = [random.getrandbits(P_DATA_W) for _ in range(burst_len)]
    # data = get_incr_data_128b(length=burst_len)

    # Write a complete burst of 256 beats
    dut._log.info(f'Writing burst...')
    await write_burst(
        dut=dut,
        tb=tb,
        addr=addr,
        data=data,
        qos=1,
    )
    check_memory( # Written memory
        memory=tb.memory_ctrl,
        base_addr=addr,
        expected=data,
    )
    dut._log.info('data ok')
    # Read a complete burst of 256 beats
    dut._log.info(f'Reading burst...')
    rd = await read_burst(
        dut=dut,
        tb=tb,
        addr=addr,
        burst_len=burst_len,
        qos=2,
    )
    assert len(rd) == len(data)
    assert rd == data, f"rd != data\n{rd}\n!=\n{data}"
