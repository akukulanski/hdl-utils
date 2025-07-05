from array import array as Array
from cocotb.handle import SimHandleBase

from .axi_full import AXI4SlaveDriver
from ..tb_utils import pack, unpack


class Memory:

    def __init__(self, size: int):
        self._memory = Array('B',[0 for _ in range(size)])

    def __getitem__(self, idx):
        # print(f"idx={hex(idx)}")
        return self._memory[idx]

    def __setitem__(self, idx, value):
        self._memory[idx] = Array('B', value)

    @property
    def memory(self):
        return self._memory

    def create_axi(self, dut: SimHandleBase, prefix: str, clock: SimHandleBase, **kwargs) -> AXI4SlaveDriver:
        return AXI4SlaveDriver(dut, prefix, clock, memory=self._memory, **kwargs)


def memory_init(
    memory,
    addr: int,
    data: list,
    element_size_bits: int,
):
    assert element_size_bits % 8 == 0
    element_size_bytes = int(element_size_bits / 8)
    n_bytes = len(data) * element_size_bytes
    data_bytes = list(unpack(
        buffer=data,
        elements=element_size_bytes,
        element_width=8,
    ))
    memory[addr:addr + n_bytes] = data_bytes
