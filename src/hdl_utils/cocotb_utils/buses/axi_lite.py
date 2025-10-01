from cocotb.triggers import Lock, RisingEdge
from cocotb.handle import SimHandleBase

from .bus import Bus, SignalInfo, DIR_OUTPUT, DIR_INPUT
from .reg_map import RegMap, Reg


__all__ = [
    'AXI4LiteMasterBus',
    'AXI4LiteSlaveBus',
    'AXI4LiteBase',
    'AXI4LiteMasterDriver',
    'AXI4LiteMaster',
]


class AXI4LiteMasterBus(Bus):

    layout = [
        # Read address channel
        SignalInfo(name='ARADDR', direction=DIR_OUTPUT, fixed_width=None, optional=False),
        SignalInfo(name='ARVALID', direction=DIR_OUTPUT, fixed_width=1, optional=False),
        SignalInfo(name='ARREADY', direction=DIR_INPUT, fixed_width=1, optional=False),
        # Read channel
        SignalInfo(name='RVALID', direction=DIR_INPUT, fixed_width=1, optional=False),
        SignalInfo(name='RREADY', direction=DIR_OUTPUT, fixed_width=1, optional=False),
        SignalInfo(name='RDATA', direction=DIR_INPUT, fixed_width=None, optional=False),
        SignalInfo(name='RRESP', direction=DIR_INPUT, fixed_width=None, optional=False),
        # Write address channel
        SignalInfo(name='AWADDR', direction=DIR_OUTPUT, fixed_width=None, optional=False),
        SignalInfo(name='AWVALID', direction=DIR_OUTPUT, fixed_width=1, optional=False),
        SignalInfo(name='AWREADY', direction=DIR_INPUT, fixed_width=1, optional=False),
        # Write channel
        SignalInfo(name='WVALID', direction=DIR_OUTPUT, fixed_width=1, optional=False),
        SignalInfo(name='WREADY', direction=DIR_INPUT, fixed_width=1, optional=False),
        SignalInfo(name='WDATA', direction=DIR_OUTPUT, fixed_width=None, optional=False),
        SignalInfo(name='WSTRB', direction=DIR_OUTPUT, fixed_width=None, optional=False),
        # Write response channel
        SignalInfo(name='BVALID', direction=DIR_INPUT, fixed_width=1, optional=False),
        SignalInfo(name='BREADY', direction=DIR_OUTPUT, fixed_width=1, optional=False),
        SignalInfo(name='BRESP', direction=DIR_INPUT, fixed_width=None, optional=False),
    ]


class AXI4LiteSlaveBus(AXI4LiteMasterBus.flipped_bus()):
    pass


class AXI4LiteBase:

    def __init__(
        self,
        entity: SimHandleBase,
        name: str,
        clock: SimHandleBase
    ):
        self.entity = entity
        self.name = name
        self.clock = clock
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

    async def run_monitor(self):
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
            await RisingEdge(self.clock)

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


class AXI4LiteMasterDriver(AXI4LiteBase):

    def __init__(
        self,
        entity: SimHandleBase,
        name: str,
        clock: SimHandleBase,
        reg_map: list[tuple | list | Reg] = None,
    ):
        super().__init__(entity, name, clock)
        self.reg_map = self.create_reg_map(reg_map)
        self.bus = AXI4LiteMasterBus(entity, name, clock)
        self.bus.init_signals()
        # Mutex for each channel to prevent contention
        self.wr_busy = Lock(name + "_wr_busy")
        self.rd_busy = Lock(name + "_rd_busy")

    def create_reg_map(self, reg_map: list[tuple | list | Reg | None]):
        reg_map = reg_map or []
        is_raw_list = len(reg_map) and isinstance(reg_map[0], (tuple, list))
        reg_map_cls = RegMap.from_reg_map_raw_list if is_raw_list else RegMap
        return reg_map_cls(reg_map)

    async def write_reg(self, addr: int, value: int):
        async with self.wr_busy:
            self.bus.AWADDR.value = addr
            self.bus.AWVALID.value = 1
            await RisingEdge(self.clock)
            while not self.aw_accepted():
                await RisingEdge(self.clock)
            self.bus.AWVALID.value = 0
            self.bus.WDATA.value = value
            self.bus.WVALID.value = 1
            await RisingEdge(self.clock)
            while not self.w_accepted():
                await RisingEdge(self.clock)
            self.bus.WVALID.value = 0
            self.bus.BREADY.value = 1
            while not self.b_accepted():
                await RisingEdge(self.clock)
            self.bus.BREADY.value = 0
            await RisingEdge(self.clock)

    async def read_reg(self, addr: int):
        async with self.rd_busy:
            self.bus.ARADDR.value = addr
            self.bus.ARVALID.value = 1
            await RisingEdge(self.clock)
            while not self.ar_accepted():
                await RisingEdge(self.clock)
            self.bus.ARVALID.value = 0
            self.bus.RREADY.value = 1
            await RisingEdge(self.clock)
            while not self.r_accepted():
                await RisingEdge(self.clock)
            self.bus.RREADY.value = 0
            rd = self.rdata
            await RisingEdge(self.clock)
        return rd

    def _get_reg_addr(self, reg: int | str | Reg) -> Reg:
        if isinstance(reg, int):
            return reg
        elif isinstance(reg, str):
            reg_name = reg
            reg = self.reg_map.get_reg_by_name(reg_name)
            if reg is None:
                raise ValueError(f'Register not found: {reg_name}')
            return reg.addr
        elif isinstance(reg, Reg):
            return reg.addr

        raise TypeError(f'Invalid register type: {reg} ({type(reg)})')

    async def write(self, reg: int | str | Reg, value: int):
        addr = self._get_reg_addr(reg)
        ret = await self.write_reg(addr, value)
        return ret

    async def read(self, reg: int | str | Reg):
        addr = self._get_reg_addr(reg)
        ret = await self.read_reg(addr)
        return ret


AXI4LiteMaster = AXI4LiteMasterDriver
