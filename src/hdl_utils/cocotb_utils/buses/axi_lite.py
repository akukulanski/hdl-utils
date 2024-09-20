from cocotb.triggers import Lock, RisingEdge
from cocotb.handle import SimHandleBase
from cocotb_bus.drivers import BusDriver


__all__ = [
    'AXI4LiteBase',
    'AXI4LiteMaster',
]


class AXI4LiteBase(BusDriver):
    _signals = [
        'AWADDR', 'AWVALID', 'AWREADY',
        'WDATA', 'WSTRB', 'WVALID', 'WREADY',
        'BRESP', 'BVALID', 'BREADY',
        'ARADDR', 'ARVALID', 'ARREADY',
        'RDATA', 'RRESP', 'RVALID', 'RREADY',
    ]

    def __init__(
        self,
        entity: SimHandleBase,
        name: str,
        clock: SimHandleBase
    ):
        super().__init__(entity, name, clock)
        self.clk = clock
        self.registers = {}
        self.transactions = []

    def aw_accepted(self):
        return bool(self.bus.AWVALID.value.integer &
                    self.bus.AWREADY.value.integer)

    def w_accepted(self):
        return bool(self.bus.WVALID.value.integer &
                    self.bus.WREADY.value.integer)

    def b_accepted(self):
        return bool(self.bus.BVALID.value.integer &
                    self.bus.BREADY.value.integer)

    def ar_accepted(self):
        return bool(self.bus.ARVALID.value.integer &
                    self.bus.ARREADY.value.integer)

    def r_accepted(self):
        return bool(self.bus.RVALID.value.integer &
                    self.bus.RREADY.value.integer)

    async def monitor(self):
        while True:
            if self.aw_accepted():
                addr_w = self.awaddr
            if self.w_accepted():
                data_w = self.wdata
            if self.ar_accepted():
                addr_r = self.araddr
            if self.r_accepted():
                data_r = self.rdata
            if addr_w is not None and data_w is not None:
                self.transactions.append(('wr', addr_w, data_w))
                self.registers[addr_w] = data_w
                addr_w, data_w = None, None
            if addr_r is not None and data_r is not None:
                self.transactions.append(('rd', addr_r, data_r))
                addr_r, data_r = None, None
            await RisingEdge(self.clk)

    @property
    def awaddr(self):
        return self.bus.AWADDR.value.integer

    @property
    def wdata(self):
        return self.bus.WDATA.value.integer

    @property
    def araddr(self):
        return self.bus.ARADDR.value.integer

    @property
    def rdata(self):
        return self.bus.RDATA.value.integer


class AXI4LiteMaster(AXI4LiteBase):

    def __init__(
        self,
        entity: SimHandleBase,
        name: str,
        clock: SimHandleBase
    ):
        super().__init__(entity, name, clock)
        # Drive some sensible defaults (setimmediatevalue to avoid x asserts)
        _sig_to_init = [
            'AWADDR', 'AWVALID', 'WDATA', 'WSTRB', 'WVALID',
            'BREADY', 'ARADDR', 'ARVALID', 'RVALID',
        ]
        for sig in _sig_to_init:
            getattr(self.bus, sig).setimmediatevalue(0)
        # Mutex for each channel to prevent contention
        self.wr_busy = Lock(name + "_wr_busy")
        self.rd_busy = Lock(name + "_rd_busy")

    async def write_reg(self, addr: int, value: int):
        async with self.wr_busy:
            self.bus.AWADDR.value = addr
            self.bus.AWVALID.value = 1
            await RisingEdge(self.clk)
            while not self.aw_accepted():
                await RisingEdge(self.clk)
            self.bus.AWVALID.value = 0
            self.bus.WDATA.value = value
            self.bus.WVALID.value = 1
            await RisingEdge(self.clk)
            while not self.w_accepted():
                await RisingEdge(self.clk)
            self.bus.WVALID.value = 0
            self.bus.BREADY.value = 1
            while not self.b_accepted():
                await RisingEdge(self.clk)
            self.bus.BREADY.value = 0
            await RisingEdge(self.clk)

    async def read_reg(self, addr: int):
        async with self.rd_busy:
            self.bus.ARADDR.value = addr
            self.bus.ARVALID.value = 1
            await RisingEdge(self.clk)
            while not self.ar_accepted():
                await RisingEdge(self.clk)
            self.bus.ARVALID.value = 0
            self.bus.RREADY.value = 1
            await RisingEdge(self.clk)
            while not self.r_accepted():
                await RisingEdge(self.clk)
            self.bus.RREADY.value = 0
            rd = self.rdata
            await RisingEdge(self.clk)
        return rd
