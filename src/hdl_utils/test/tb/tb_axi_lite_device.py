import cocotb
from cocotb.clock import Clock
from cocotb import start_soon
from cocotb.triggers import RisingEdge
import os

from hdl_utils.cocotb_utils.buses.axi_lite import AXI4LiteMaster


P_ADDR_W = int(os.environ['P_ADDR_W'])
P_DATA_W = int(os.environ['P_DATA_W'])
P_HIGHEST_ADDR = int(os.environ['P_HIGHEST_ADDR'])

ADDR_JUMP = P_DATA_W // 8


class Testbench:
    clk_period = 10

    def __init__(self, dut):
        self.dut = dut
        self.m_axil = AXI4LiteMaster(entity=dut, name='s_axil_', clock=dut.clk)

    def init_signals(self):
        self.dut.field_10.value = 0
        self.dut.field_20.value = 0
        self.dut.field_30.value = 0
        self.dut.field_40.value = 0
        self.dut.field_50.value = 0

    async def init_test(self):
        start_soon(Clock(self.dut.clk, self.clk_period, units='ns').start())
        self.init_signals()
        self.dut.rst.value = 1
        for _ in range(3):
            await RisingEdge(self.dut.clk)
        self.dut.rst.value = 0
        await RisingEdge(self.dut.clk)

    def iterate_addr(self, highest_addr: int = P_HIGHEST_ADDR):
        for addr in range(0, highest_addr + 1, ADDR_JUMP):
            yield addr

    def get_signal_values(self):
        sig_values = []
        for addr in self.iterate_addr():
            sig_name = f'reg_0x{addr:08x}'
            s = getattr(self.dut, sig_name)
            sig_values.append(s.value)
        return sig_values

    async def get_reg_values(self):
        read_values = []
        for addr in self.iterate_addr():
            rd = await self.m_axil.read_reg(addr=addr)
            read_values.append(rd)
        return read_values


@cocotb.test()
async def check_core(dut):
    tb = Testbench(dut)
    await tb.init_test()

    dut._log.info(f'P_ADDR_W: {P_ADDR_W}')
    dut._log.info(f'P_DATA_W: {P_DATA_W}')
    dut._log.info(f'P_HIGHEST_ADDR: {P_HIGHEST_ADDR}')

    n_registers = (P_HIGHEST_ADDR // ADDR_JUMP) + 1
    dut._log.info(f'n_registers: {n_registers}')

    # Initial values
    expected_values = [0] * n_registers
    assert tb.get_signal_values() == expected_values
    reg_values = await tb.get_reg_values()
    assert reg_values == expected_values

    # Write two registers
    await tb.m_axil.write_reg(addr=0x0, value=0x12345678)
    await tb.m_axil.write_reg(addr=0x4, value=0xaabbccdd)

    # Check modified values
    expected_values[0:2] = [0x12345678, 0xaabbccdd]
    assert tb.get_signal_values() == expected_values
    reg_values = await tb.get_reg_values()
    assert reg_values == expected_values

    # Change read singals
    # ('reg_ro_1', 'ro', 0x0000000C, [
    #     ('field_10', 32,  0),
    # ]),
    dut.field_10.value = 0x40302010
    # ('reg_ro_2', 'ro', 0x00000010, [
    #     ('field_20',  1,  0),
    #     ('field_30', 15,  1),
    #     ('field_40', 16, 16),
    # ]),
    dut.field_20.value = 1
    dut.field_30.value = 3
    dut.field_40.value = 4
    # ('reg_ro_3', 'ro', 0x00000014, [
    #     ('field_50', 32,  0),
    # ]),
    dut.field_50.value = 0xaaaa5555
    await RisingEdge(dut.clk)

    # Check modified values
    expected_values[3:6] = [
        0x40302010,
        0x1 | (0x3 << 1) | (0x4 << 16),
        0xaaaa5555
    ]
    assert tb.get_signal_values() == expected_values
    reg_values = await tb.get_reg_values()
    assert reg_values == expected_values
