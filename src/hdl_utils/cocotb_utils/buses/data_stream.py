import copy
from cocotb.triggers import Lock, RisingEdge
from cocotb.handle import SimHandleBase
import random
from typing import Sequence, Tuple, Union

from .bus import Bus, SignalInfo, DIR_OUTPUT, DIR_INPUT


__all__ = [
    'DataStreamMasterBus',
    'DataStreamSlaveBus',
    'DataStreamMonitorMixin',
    'DataStreamBase',
    'DataStreamMasterDriver',
    'DataStreamSlaveDriver',
    'DataStreamMaster',
    'DataStreamSlave',
]


class DataStreamMasterBus(Bus):

    layout = [
        SignalInfo(name='valid', direction=DIR_OUTPUT, fixed_width=1, optional=False),
        SignalInfo(name='ready', direction=DIR_INPUT, fixed_width=1, optional=False),
        SignalInfo(name='data', direction=DIR_OUTPUT, fixed_width=None, optional=False),
        SignalInfo(name='last', direction=DIR_OUTPUT, fixed_width=1, optional=True),
    ]


class DataStreamSlaveBus(DataStreamMasterBus.flipped_bus()):
    pass


class DataStreamMonitorMixin:

    def __init__(self):
        self._data_monitor = []
        self._current_data_stream = []

    async def run_data_monitor(self):
        self.reset_data_monitor()
        while True:
            await RisingEdge(self.clock)
            if self.accepted():
                self._current_data_stream.append(int(self.bus.data.value))
                if self.bus.last.value:
                    self._data_monitor.append(self._current_data_stream)
                    self._current_data_stream = []

    def reset_data_monitor(self):
        self._data_monitor.clear()
        self._current_data_stream.clear()

    def get_current_data_stream(self):
        return copy.deepcopy(self._current_data_stream)

    def get_data_streams_from_monitor(self):
        data_streams = self._data_monitor
        current_data_stream = self.get_current_data_stream()
        if len(current_data_stream):
            data_streams = [*data_streams, current_data_stream]
        data_streams = copy.deepcopy(data_streams)
        return data_streams

    async def run_monitor(self):
        await self.run_data_monitor()

    @property
    def monitor(self) -> list:
        return self.get_data_streams_from_monitor()


class DataStreamBase:

    def __init__(self, entity: SimHandleBase, name: str, clock: SimHandleBase):
        self.entity = entity
        self.name = name
        self.clock = clock

    def accepted(self):
        return bool(self.bus.valid.value and
                    self.bus.ready.value)

    def data_int(self):
        return int(self.bus.data.value)

    def last_int(self):
        if hasattr(self.bus, 'last'):
            return int(self.bus.last.value)
        return None


class DataStreamMasterDriver(DataStreamBase, DataStreamMonitorMixin):
    """DataStreamMasterDriver
    """

    def __init__(self, entity: SimHandleBase, name: str, clock: SimHandleBase):
        DataStreamBase.__init__(self, entity, name, clock)
        DataStreamMonitorMixin.__init__(self)
        self.bus = DataStreamMasterBus(entity, name, clock)
        self.bus.init_signals()
        # Mutex for each channel to prevent contention
        self.wr_busy = Lock(name + "_wbusy")

    async def _send_write_data(self, data: int, last: bool) -> None:
        """Send a single data."""
        async with self.wr_busy:
            self.bus.valid.value = 1
            self.bus.last.value = int(last)
            self.bus.data.value = data
            await RisingEdge(self.clock)
            while int(self.bus.ready.value) == 0:
                await RisingEdge(self.clock)
            self.bus.valid.value = 0
            self.bus.last.value = 0

    async def write(self, data: Union[int, Sequence[int]],
                    burps: bool = False) -> None:
        """Send data."""

        try:
            iter(data)
        except TypeError:
            data = [data]

        for d in data[:-1]:
            while burps and random.getrandbits(1):
                await RisingEdge(self.clock)
            await self._send_write_data(data=d, last=0)
        while burps and random.getrandbits(1):
            await RisingEdge(self.clock)
        await self._send_write_data(data=data[-1], last=1)


class DataStreamSlaveDriver(DataStreamBase, DataStreamMonitorMixin):
    """DataStreamSlaveDriver
    """

    def __init__(self, entity: SimHandleBase, name: str, clock: SimHandleBase):
        DataStreamBase.__init__(self, entity, name, clock)
        DataStreamMonitorMixin.__init__(self)
        self.bus = DataStreamSlaveBus(entity, name, clock)
        self.bus.init_signals()
        # Mutex for each channel to prevent contention
        self.rd_busy = Lock(name + "_rbusy")

    async def _recv_rd_data(self) -> Tuple[int]:
        """Receive a single data.
        Returns the tuple (value, last).
        """
        async with self.rd_busy:
            self.bus.ready.value = 1
            await RisingEdge(self.clock)
            while int(self.bus.valid.value) == 0:
                await RisingEdge(self.clock)
        value = int(self.bus.data.value)
        last = int(self.bus.last.value)
        self.bus.ready.value = 0
        return (value, last)

    async def read(self, length: int = None, ignore_last=False,
                   burps: bool = False) -> Sequence[int]:
        """Receive data."""
        data = []
        count = 0
        while True:
            while burps and random.getrandbits(1):
                await RisingEdge(self.clock)
            value, last = await self._recv_rd_data()
            data.append(value)
            count += 1
            if (last and not ignore_last) or (count == length):
                return data


# Backward compatibility
DataStreamMaster = DataStreamMasterDriver
DataStreamSlave = DataStreamSlaveDriver
