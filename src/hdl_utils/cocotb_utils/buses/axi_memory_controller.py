from array import array as Array

from .axi_full import AXI4Slave

class Axi4MemoryController:

    def __init__(self, dut, prefix, clk, size):
        print(f"size={hex(size)}")
        self._memory = Array('B',[0 for _ in range(size)])
        self.axi = AXI4Slave(dut, prefix, clk, memory=self._memory)

    def __getitem__(self, idx):
        # print(f"idx={hex(idx)}")
        return self._memory[idx]

    def __setitem__(self, idx, value):
        self._memory[idx] = Array('B', value)
