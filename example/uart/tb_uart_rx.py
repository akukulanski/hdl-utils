import cocotb
from cocotb import start_soon
from cocotb.triggers import RisingEdge, with_timeout
import numpy as np
import os
import random

from hdl_utils.cocotb_utils.tb import BaseTestbench


# Parameters
P_DIVIDER = int(os.environ['P_UART_CLK_DIV'])


class Testbench(BaseTestbench):
    clk_period = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.recv_buffer = []
        self.overflow_detected = False

    def _init_signals(self):
        self.dut.rx.value = 1
        self.dut.ready.value = 0

    async def wait_uart_clk(self):
        for _ in range(P_DIVIDER):
            await RisingEdge(self.dut.clk)

    async def send(self, data):
        # self.dut._log.info(f'Send: 0x{data:02x}')
        assert 0 <= data < 256
        await RisingEdge(self.dut.clk)
        # Start bit
        self.dut.rx.value = 0
        await self.wait_uart_clk()
        # Data
        for i in reversed(range(8)):  # MSB first.
            self.dut.rx.value = (data >> i) & 0x01
            await self.wait_uart_clk()
        # Stop bit
        self.dut.rx.value = 1
        await self.wait_uart_clk()

    async def receiver_always_available(self):
        self.dut.ready.value = 1
        while True:
            await RisingEdge(self.dut.clk)

    async def receiver_randomly_available(self):
        while True:
            self.dut.ready.value = np.random.randint(2)
            await RisingEdge(self.dut.clk)

    async def recv_monitor(self):
        while True:
            await RisingEdge(self.dut.clk)
            if self.dut.valid.value.integer & self.dut.ready.value.integer:
                self.recv_buffer.append(self.dut.data.value.integer)
                # self.dut._log.info(f'Dut received: 0x{self.dut.data.value.integer:02x}')
            if self.dut.overflow.value.integer:
                self.overflow_detected = True

    async def wait_until_recv_n_items(self, n):
        # Wait until recv_buffer length is n
        while len(self.recv_buffer) < n:
            await RisingEdge(self.dut.clk)


@cocotb.test()
async def check_port_sizes(dut):
    assert len(dut.data) == 8
    assert len(dut.rx) == 1


@cocotb.test()
async def check_typical(dut):
    tb = Testbench(dut)
    await tb.init_test()
    start_soon(tb.recv_monitor())
    start_soon(tb.receiver_always_available())
    # start_soon(tb.receiver_randomly_available())

    data_to_send = [random.getrandbits(8) for _ in range(30)]
    for i, data in enumerate(data_to_send):
        await tb.send(data)
        assert len(tb.recv_buffer) == i + 1, f'tb.recv_buffer={tb.recv_buffer}'
        assert tb.recv_buffer[-1] == data, f'{tb.recv_buffer[-1]} != {data}'

    assert len(tb.recv_buffer) == len(data_to_send), f'tb.recv_buffer={tb.recv_buffer}'
    assert tb.recv_buffer == data_to_send, f'{tb.recv_buffer} != {data_to_send}'
    assert tb.overflow_detected is False


@cocotb.test()
async def check_receiver_not_always_available(dut):
    tb = Testbench(dut)
    await tb.init_test()
    start_soon(tb.recv_monitor())
    start_soon(tb.receiver_randomly_available())

    data_to_send = [random.getrandbits(8) for _ in range(30)]
    for i, data in enumerate(data_to_send):
        await tb.send(data)
        # If the data wasnt read yet, wait for ready (random in tb) to be set.
        if len(tb.recv_buffer) < i + 1:
            await RisingEdge(dut.ready)
            await RisingEdge(dut.clk)
        assert len(tb.recv_buffer) == i + 1, f'tb.recv_buffer={tb.recv_buffer}'
        assert tb.recv_buffer[-1] == data, f'{tb.recv_buffer[-1]} != {data}'

    assert len(tb.recv_buffer) == len(data_to_send), f'tb.recv_buffer={tb.recv_buffer}'
    assert tb.recv_buffer == data_to_send, f'{tb.recv_buffer} != {data_to_send}'
    assert tb.overflow_detected is False


@cocotb.test()
async def check_overflow(dut):
    tb = Testbench(dut)
    await tb.init_test()
    start_soon(tb.recv_monitor())

    data = random.getrandbits(8)
    await tb.send(data)
    assert len(tb.recv_buffer) == 0, f'tb.recv_buffer={tb.recv_buffer}'
    assert dut.valid.value.integer == 1
    assert dut.overflow.value.integer == 0

    data = random.getrandbits(8)
    await tb.send(data)
    assert len(tb.recv_buffer) == 0, f'tb.recv_buffer={tb.recv_buffer}'
    assert dut.valid.value.integer == 1
    assert dut.overflow.value.integer == 1

    dut.ready.value = 1
    await RisingEdge(dut.clk)
    dut.ready.value = 0
    await RisingEdge(dut.clk)
    # Check Valid is cleared and Overflow remains set.
    assert dut.valid.value.integer == 0
    assert dut.overflow.value.integer == 1

    assert len(tb.recv_buffer) == 1, f'tb.recv_buffer={tb.recv_buffer}'
    assert tb.recv_buffer[0] == data, f'{tb.recv_buffer[0]} != {data}'
