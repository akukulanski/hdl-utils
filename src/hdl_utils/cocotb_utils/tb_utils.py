from cocotb.handle import SimHandleBase
from cocotb.triggers import RisingEdge
import random

from hdl_utils.cocotb_utils.buses.axi_stream import (
    AXIStreamMaster,
)
from hdl_utils.cocotb_utils.buses.bus import Bus


__all__ = [
    'pack',
    'unpack',
    'width_converter_up',
    'width_converter_down',
]


def pack(buffer, elements, element_width):
    """
        pack generator groups the buffer in packets of "elements"
        considering they have "element_width" bit length.

        args:
            elements: how many elements do you want to join
            element_with: which is the width of each element
        example:
            a = [0, 1, 2, 3, 4, 5]
            b = [p for p in pack(a, 3, 8)]
            result: [0x020100, 0x050403]
    """
    adicionales = (elements - (len(buffer) % elements)) % elements
    buff = buffer + [0]*adicionales
    for i in range(0, len(buff), elements):
        b = 0
        for j in range(elements):
            b = (b << element_width) + buff[i+elements-j-1]
        yield b


def unpack(buffer, elements, element_width):
    """
        unpack generator ungroups the buffer items in "elements"
        parts of "element_with" bit length.

        args:
            elements: In how many parts do you want to split an item.
            element_with: bit length of each part.
        example:
            a = [0x020100, 0x050403]
            b = [p for p in unpack(a, 3, 8)]
            result: [0, 1, 2, 3, 4, 5,]]
    """
    mask = (1 << element_width) - 1
    for b in buffer:
        for _ in range(elements):
            yield (b & mask)
            b = b >> element_width


def width_converter_up(data_in, width_in, width_out):
    if (width_in == width_out == 0):
        return []
    assert width_out % width_in == 0
    scale = int(width_out / width_in)
    return list(pack(buffer=data_in, elements=scale, element_width=width_in))


def width_converter_down(data_in, width_in, width_out):
    if (width_in == width_out == 0):
        return []
    assert width_in % width_out == 0
    scale = int(width_in / width_out)
    return list(unpack(buffer=data_in, elements=scale, element_width=width_out))


def as_int(x):
    assert x == int(x)
    return int(x)


def get_rand_stream(width: int, length: int) -> list[int]:
    return [
        random.getrandbits(width)
        for _ in range(length)
    ]


def check_axi_stream_iface(
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


def check_axi_full_iface(
    dut,
    prefix,
    data_w,
    addr_w,
):
    assert len(getattr(dut, f'{prefix}ARVALID')) == 1
    assert len(getattr(dut, f'{prefix}ARADDR')) == addr_w
    assert len(getattr(dut, f'{prefix}RVALID')) == 1
    assert len(getattr(dut, f'{prefix}RDATA')) == data_w
    assert len(getattr(dut, f'{prefix}AWVALID')) == 1
    assert len(getattr(dut, f'{prefix}AWADDR')) == addr_w
    assert len(getattr(dut, f'{prefix}WVALID')) == 1
    assert len(getattr(dut, f'{prefix}WDATA')) == data_w


def stream_to_hex(arr: list) -> list[str]:
    return [hex(x) for x in arr]


def check_memory_bytes(memory, base_addr: int, expected: list[int]):
    for offset, value in enumerate(expected):
        addr = base_addr + offset
        # print(f'addr={hex(base_addr)}+{hex(offset)}: exp={hex(value)} ; got={hex(memory[addr])}')
        assert memory[addr] == value, (
            f"Error in address {hex(addr)}: Expected {hex(value)}, Got {hex(memory[addr])}"
        )


def check_memory_data(
    memory,
    base_addr: int,
    expected: list[int],
    data_width: int,
):
    check_memory_bytes(
        memory=memory,
        base_addr=base_addr,
        expected=unpack(
            buffer=expected,
            elements=data_width // 8,
            element_width=8,
        ),
    )


async def wait_n_streams(
    bus: Bus,
    clock: SimHandleBase,
    n_streams: int,
):
    for _ in range(n_streams):
        await RisingEdge(clock)
        while not (bus.tvalid.value and bus.tlast.value and bus.tready.value):
            await RisingEdge(clock)
    await RisingEdge(clock)


async def send_data_repeatedly(
    driver: AXIStreamMaster,
    data: list[int],
    burps: bool,
    n_repeat: int = 0,
    force_sync_clk_edge: bool = True,
):
    if force_sync_clk_edge:
        await RisingEdge(driver.clock)
    while True:
        await driver.write(data=data, burps=burps, force_sync_clk_edge=False)
        n_repeat -= 1
        if n_repeat == 0:
            break
