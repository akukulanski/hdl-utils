import array
import cocotb
from cocotb.binary import BinaryValue
from cocotb.handle import SimHandleBase
from cocotb.triggers import RisingEdge

from .bus import Bus, SignalInfo, DIR_OUTPUT, DIR_INPUT


__all__ = [
    'AXIProtocolError',
    'AXI4SlaveBus',
    'AXI4SlaveDriver',
    'AXI4MasterDriver',
    'AXI4Slave',
]

class AXIProtocolError(Exception):
    pass


class AXI4SlaveBus(Bus):

    layout = [
        # Read address channel
        SignalInfo(name='ARREADY', direction=DIR_OUTPUT, fixed_width=1, optional=False),
        SignalInfo(name='ARVALID', direction=DIR_INPUT, fixed_width=1, optional=False),
        SignalInfo(name='ARADDR', direction=DIR_INPUT, fixed_width=None, optional=False),
        SignalInfo(name='ARLEN', direction=DIR_INPUT, fixed_width=8, optional=False),
        SignalInfo(name='ARSIZE', direction=DIR_INPUT, fixed_width=3, optional=False),
        SignalInfo(name='ARBURST', direction=DIR_INPUT, fixed_width=2, optional=False),
        SignalInfo(name='ARPROT', direction=DIR_INPUT, fixed_width=3, optional=False),
        SignalInfo(name='ARLOCK', direction=DIR_INPUT, fixed_width=1, optional=True),
        SignalInfo(name='ARCACHE', direction=DIR_INPUT, fixed_width=4, optional=True),
        SignalInfo(name='ARQOS', direction=DIR_INPUT, fixed_width=4, optional=True),
        SignalInfo(name='ARID', direction=DIR_INPUT, fixed_width=None, optional=True),
        # Read channel
        SignalInfo(name='RREADY', direction=DIR_INPUT, fixed_width=1, optional=False),
        SignalInfo(name='RVALID', direction=DIR_OUTPUT, fixed_width=1, optional=False),
        SignalInfo(name='RDATA', direction=DIR_OUTPUT, fixed_width=None, optional=False),
        SignalInfo(name='RLAST', direction=DIR_OUTPUT, fixed_width=1, optional=False),
        SignalInfo(name='RRESP', direction=DIR_OUTPUT, fixed_width=None, optional=True),
        SignalInfo(name='RID', direction=DIR_OUTPUT, fixed_width=None, optional=True),
        # Write address channel
        SignalInfo(name='AWREADY', direction=DIR_OUTPUT, fixed_width=1, optional=False),
        SignalInfo(name='AWADDR', direction=DIR_INPUT, fixed_width=None, optional=False),
        SignalInfo(name='AWVALID', direction=DIR_INPUT, fixed_width=1, optional=False),
        SignalInfo(name='AWPROT', direction=DIR_INPUT, fixed_width=3, optional=False),
        SignalInfo(name='AWSIZE', direction=DIR_INPUT, fixed_width=3, optional=False),
        SignalInfo(name='AWBURST', direction=DIR_INPUT, fixed_width=2, optional=False),
        SignalInfo(name='AWLEN', direction=DIR_INPUT, fixed_width=8, optional=False),
        SignalInfo(name='AWLOCK', direction=DIR_INPUT, fixed_width=1, optional=True),
        SignalInfo(name='AWCACHE', direction=DIR_INPUT, fixed_width=4, optional=True),
        SignalInfo(name='AWQOS', direction=DIR_INPUT, fixed_width=4, optional=True),
        SignalInfo(name='AWID', direction=DIR_INPUT, fixed_width=None, optional=True),
        # Write channel
        SignalInfo(name='WREADY', direction=DIR_OUTPUT, fixed_width=1, optional=False),
        SignalInfo(name='WVALID', direction=DIR_INPUT, fixed_width=1, optional=False),
        SignalInfo(name='WDATA', direction=DIR_INPUT, fixed_width=None, optional=False),
        SignalInfo(name='WLAST', direction=DIR_INPUT, fixed_width=1, optional=True),
        SignalInfo(name='WSTRB', direction=DIR_INPUT, fixed_width=None, optional=True),
        # Write response channel
        SignalInfo(name='BVALID', direction=DIR_OUTPUT, fixed_width=1, optional=True),
        SignalInfo(name='BREADY', direction=DIR_INPUT, fixed_width=1, optional=True),
        SignalInfo(name='BRESP', direction=DIR_OUTPUT, fixed_width=None, optional=True),
        SignalInfo(name='BID', direction=DIR_OUTPUT, fixed_width=None, optional=True),
    ]


class AXI4MasterBus(AXI4SlaveBus.flipped_bus()):
    pass


class AXI4SlaveDriver:

    def __init__(
        self,
        dut: SimHandleBase,
        name,
        clock: SimHandleBase,
        memory,
        baseaddr: int = 0,
        big_endian: bool = False,
        run_drivers: bool = True,
    ):
        self.dut = dut
        self.name = name
        self.clock = clock
        self.big_endian = big_endian
        self.baseaddr = baseaddr
        self._memory = memory
        self.bus = AXI4SlaveBus(dut, name, clock)
        self.bus.init_signals()

        if run_drivers:
            self.run_drivers()

    def run_drivers(self):
        cocotb.start_soon(self._read_data())
        cocotb.start_soon(self._write_data())

    def _size_to_bytes_in_beat(self, AxSIZE):
        if AxSIZE <= 7:
            return 2 ** AxSIZE
        return None

    async def _write_data(self):
        await RisingEdge(self.clock)
        while True:
            self.bus.BRESP.value = 0
            self.bus.WREADY.value = 0
            self.bus.BVALID.value = 0
            self.bus.AWREADY.value = 1
            await RisingEdge(self.clock)
            while not self.bus.AWVALID.value:
                await RisingEdge(self.clock)
            _awaddr = int(self.bus.AWADDR)
            _awlen = int(self.bus.AWLEN)
            _awsize = int(self.bus.AWSIZE)
            self.bus.AWREADY.value = 0

            burst_length = _awlen + 1
            bytes_in_beat = self._size_to_bytes_in_beat(_awsize)

            burst_count = burst_length

            for b in range(burst_length):
                self.bus.WREADY.value = 1
                await RisingEdge(self.clock)
                while not self.bus.WVALID.value:
                    await RisingEdge(self.clock)
                word = self.bus.WDATA.value
                word.big_endian = self.big_endian
                _burst_diff = burst_length - burst_count
                start_addr = _awaddr + b * bytes_in_beat
                end_addr = start_addr + bytes_in_beat
                assert end_addr <= len(self._memory), f"out of range: {hex(end_addr)} > {hex(len(self._memory))}"
                self._memory[start_addr:end_addr] = array.array('B', word.buff)

            if not self.bus.WLAST.value:
                raise AXIProtocolError('WLAST != 1 when BURST Finished')

            self.bus.WREADY.value = 0
            self.bus.BVALID.value = 1
            self.bus.BRESP.value = 0
            while not self.bus.BREADY.value:
                await RisingEdge(self.clock)

            self.bus.BVALID.value = 0

    async def _read_data(self):
        await RisingEdge(self.clock)
        while True:
            # Receive Read Address
            self.bus.ARREADY.value = 1
            await RisingEdge(self.clock)
            while not self.bus.ARVALID.value.integer:
                await RisingEdge(self.clock)
            self.bus.ARREADY.value = 0

            _araddr = int(self.bus.ARADDR)
            _arlen = int(self.bus.ARLEN)
            _arsize = int(self.bus.ARSIZE)
            _arburst = int(self.bus.ARBURST)
            _arprot = int(self.bus.ARPROT)
            # FIXME: ARBURST ignored and assumed to be INCR.

            burst_length = _arlen + 1
            bytes_in_beat = self._size_to_bytes_in_beat(_arsize)
            word = BinaryValue(n_bits=bytes_in_beat*8, bigEndian=self.big_endian)
            burst_count = burst_length

            # Send data burst
            while burst_count:
                # Calculate start and end address to send in this data beat
                _burst_diff = burst_length - burst_count
                _st = _araddr - self.baseaddr + \
                    (_burst_diff * bytes_in_beat)
                _end = _araddr - self.baseaddr + \
                    ((_burst_diff + 1) * bytes_in_beat)
                assert _end <= len(self._memory), f"out of range: {hex(_end)} > {hex(len(self._memory))}"
                word = self._memory[_st:_end]
                word = ''.join(["{:02x}".format(x) for x in word[::-1]])
                # Send data beat
                self.bus.RDATA.value = int(word, 16)
                self.bus.RVALID.value = 1
                self.bus.RLAST.value = 1 if (burst_count == 1) else 0
                await RisingEdge(self.clock)
                while not (self.bus.RREADY.value.integer):
                    await RisingEdge(self.clock)
                burst_count -= 1

            # End of burst, restore signals value
            self.bus.RVALID.value = 0
            self.bus.RLAST.value = 0
            self.bus.RDATA.value = 0


class AXI4MasterDriver:

    def __init__(
        self,
        dut: SimHandleBase,
        name,
        clock: SimHandleBase,
    ):
        self.dut = dut
        self.name = name
        self.clock = clock
        self.bus = AXI4MasterBus(dut, name, clock)
        self.bus.init_signals()


# Backward compatibility
AXI4Slave = AXI4SlaveDriver
