from cocotb.handle import SimHandleBase
from cocotb.triggers import Lock, RisingEdge
import copy
import random
from typing import Sequence, Tuple, Union

from .bus import Bus, SignalInfo, DIR_OUTPUT, DIR_INPUT


__all__ = [
    'AXI4StreamMasterBus',
    'AXI4StreamSlaveBus',
    'AXIStreamMonitorMixin',
    'AXIStreamBase',
    'AXIStreamMasterDriver',
    'AXIStreamSlaveDriver',
    'AXIStreamMaster',
    'AXIStreamSlave',
    'extract_capture_data',
    'extract_capture_user',
    'extract_capture_keep',
]


def extract_capture_data(capture):
    return [d for d, u, k in capture]


def extract_capture_user(capture):
    return [u for d, u, k in capture]


def extract_capture_keep(capture):
    return [k for d, u, k in capture]


class AXI4StreamMasterBus(Bus):

    layout = [
        SignalInfo(name='tvalid', direction=DIR_OUTPUT, fixed_width=1, optional=False),
        SignalInfo(name='tready', direction=DIR_INPUT, fixed_width=1, optional=False),
        SignalInfo(name='tdata', direction=DIR_OUTPUT, fixed_width=None, optional=False),
        SignalInfo(name='tlast', direction=DIR_OUTPUT, fixed_width=1, optional=True),
        SignalInfo(name='tuser', direction=DIR_OUTPUT, fixed_width=None, optional=True),
        SignalInfo(name='tkeep', direction=DIR_OUTPUT, fixed_width=None, optional=True),
    ]


class AXI4StreamSlaveBus(AXI4StreamMasterBus.flipped_bus()):
    pass


class AXIStreamMonitorMixin:

    def __init__(self):
        self._data_monitor = []
        self._current_data_stream = []
        self._full_monitor_streams = []
        self._full_monitor_current_stream = []


    async def run_full_monitor(self):
        """Monitor that registers tdata, tuser and tkeep.
        """
        self._full_monitor_streams.clear()
        self._full_monitor_current_stream.clear()
        while True:
            await RisingEdge(self.clock)
            if self.accepted():
                self._full_monitor_current_stream.append(self._capture_current_values())
                if self.bus.tlast.value.integer:
                    self._full_monitor_streams.append(self._full_monitor_current_stream)
                    self._full_monitor_current_stream = []

    def get_full_monitor_current_stream(self):
        return copy.deepcopy(self._full_monitor_current_stream)

    def get_full_monitor_streams(self):
        streams = self._full_monitor_streams
        current_stream = self.get_full_monitor_current_stream()
        if len(current_stream):
            streams = [*streams, current_stream]
        streams = copy.deepcopy(streams)
        return streams

    # Method names backward compatibility
    def get_monitor(self):
        return self.get_full_monitor_streams()

    def get_current_stream(self):
        return self.get_full_monitor_current_stream()

    @property
    def monitor(self):
        return self.get_full_monitor_streams()

    async def run_monitor(self):
        await self.run_full_monitor()

    # Data monitor
    async def run_data_monitor(self):
        """Monitor that registers tdata only (no tuser, no tkeep)
        """
        self._data_monitor.clear()
        self._current_data_stream.clear()
        while True:
            await RisingEdge(self.clock)
            if self.accepted():
                self._current_data_stream.append(self.tdata_int())
                if self.bus.tlast.value.integer:
                    self._data_monitor.append(self._current_data_stream)
                    self._current_data_stream = []

    def get_current_data_stream(self):
        return copy.deepcopy(self._current_data_stream)

    def get_data_streams_from_monitor(self):
        data_streams = self._data_monitor
        current_data_stream = self.get_current_data_stream()
        if len(current_data_stream):
            data_streams = [*data_streams, current_data_stream]
        data_streams = copy.deepcopy(data_streams)
        return data_streams


class AXIStreamBase:

    def __init__(self, entity: SimHandleBase, name: str, clock: SimHandleBase):
        self.entity = entity
        self.name = name
        self.clock = clock

    def accepted(self):
        return bool(self.bus.tvalid.value.integer and
                    self.bus.tready.value.integer)

    def tdata_int(self):
        return self.bus.tdata.value.integer

    def tuser_int(self):
        if hasattr(self.bus, 'tuser'):
            return self.bus.tuser.value.integer
        return None

    def tkeep_int(self):
        if hasattr(self.bus, 'tkeep'):
            return self.bus.tkeep.value.integer
        return None

    def tlast_int(self):
        if hasattr(self.bus, 'tlast'):
            return self.bus.tlast.value.integer
        return None

    def _capture_current_values(self):
        return (self.tdata_int(), self.tuser_int(), self.tkeep_int())

    def extract_capture_data(self, capture):
        # TODO: Deprecate (kept for compatibility).
        return extract_capture_data(capture)

    def extract_capture_user(self, capture):
        # TODO: Deprecate (kept for compatibility).
        return extract_capture_user(capture)

    def extract_capture_keep(self, capture):
        # TODO: Deprecate (kept for compatibility).
        return extract_capture_keep(capture)


class AXIStreamMasterDriver(AXIStreamBase, AXIStreamMonitorMixin):
    """AXIStreamMasterDriver
    """

    def __init__(self, entity: SimHandleBase, name: str, clock: SimHandleBase):
        AXIStreamBase.__init__(self, entity, name, clock)
        AXIStreamMonitorMixin.__init__(self)
        self.bus = AXI4StreamMasterBus(entity, name, clock)
        self.bus.init_signals()
        # Mutex for each channel to prevent contention
        self.wr_busy = Lock(name + "_wbusy")

    async def _send_write_data(
        self,
        data: int,
        last: bool,
        keep=None,
        user=None
    ) -> None:
        """Send a single data."""
        async with self.wr_busy:
            self.bus.tvalid.value = 1
            self.bus.tlast.value = int(last)
            self.bus.tdata.value = data
            if user:
                self.bus.tuser.value = user
            if keep:
                self.bus.tkeep.value = keep
            await RisingEdge(self.clock)
            while self.bus.tready.value.integer == 0:
                await RisingEdge(self.clock)
            self.bus.tvalid.value = 0
            self.bus.tlast.value = 0
            self.bus.tdata.value = 0
            if user:
                self.bus.tuser.value = 0
            if keep:
                self.bus.tkeep.value = 0

    async def write(
        self,
        data: Union[int, Sequence[int]],
        keep: Union[int, Sequence[int]] = None,
        user: Union[int, Sequence[int]] = None,
        burps: bool = False,
        force_sync_clk_edge: bool = True,
    ) -> None:
        """Send data."""

        def _as_iter(x):
            try:
                iter(x)
            except TypeError:
                x = [x]
            return x

        data = _as_iter(data)
        keep = _as_iter(keep) if keep is not None else [None] * len(data)
        user = _as_iter(user) if user is not None else [None] * len(data)

        assert len(data) == len(keep)
        assert len(data) == len(user)

        if force_sync_clk_edge:
            await RisingEdge(self.clock)
        for d, k, u in zip(data[:-1], keep[:-1], user[:-1]):
            while burps and random.getrandbits(1):
                await RisingEdge(self.clock)
            await self._send_write_data(
                data=d,
                last=0,
                keep=k,
                user=u
            )
        while burps and random.getrandbits(1):
            await RisingEdge(self.clock)
        await self._send_write_data(
            data=data[-1],
            last=1,
            keep=keep[-1],
            user=user[-1]
        )

    async def write_multiple(
        self,
        datas: list[Union[int, Sequence[int]]],
        keeps: list[Union[int, Sequence[int]]] = None,
        users: list[Union[int, Sequence[int]]] = None,
        **kwargs
    ) -> None:
        keeps = keeps or [None for _ in range(len(datas))]
        users = users or [None for _ in range(len(datas))]
        assert len(datas) == len(keeps)
        assert len(datas) == len(users)
        for data, user, keep in zip(datas, users, keeps):
            await self.write(
                data=data,
                keep=keep,
                user=user,
                **kwargs
            )


class AXIStreamSlaveDriver(AXIStreamBase, AXIStreamMonitorMixin):
    """AXIStreamSlaveDriver
    """

    def __init__(self, entity: SimHandleBase, name: str, clock: SimHandleBase):
        AXIStreamBase.__init__(self, entity, name, clock)
        AXIStreamMonitorMixin.__init__(self)
        self.bus = AXI4StreamSlaveBus(entity, name, clock)
        self.bus.init_signals()
        # Mutex for each channel to prevent contention
        self.rd_busy = Lock(name + "_rbusy")

    async def _recv_rd_data(self) -> Tuple[int]:
        """Receive a single data.
        Returns the tuple (value, last).
        """
        async with self.rd_busy:
            self.bus.tready.value = 1
            await RisingEdge(self.clock)
            while self.bus.tvalid.value.integer == 0:
                await RisingEdge(self.clock)
        current_values = self._capture_current_values()
        last = self.tlast_int()
        self.bus.tready.value = 0
        return current_values, last

    async def read(
        self,
        length: int = None,
        ignore_last: bool = False,
        all_signals: bool = False,
        burps: bool = False,
        force_sync_clk_edge: bool = True,
    ) -> Sequence[int]:
        """Receive data."""
        data = []
        count = 0
        if force_sync_clk_edge:
            await RisingEdge(self.clock)
        while True:
            while burps and random.getrandbits(1):
                await RisingEdge(self.clock)
            current_values, tlast = await self._recv_rd_data()
            if all_signals:
                data.append(current_values)
            else:
                tdata = current_values[0]
                data.append(tdata)
            count += 1
            if (tlast and not ignore_last) or (count == length):
                return data

    async def read_multiple(
        self,
        *,
        n_streams: int,
        **kwargs
    ) -> list:
        streams = []
        for i in range(n_streams):
            s = await self.read(**kwargs)
            streams.append(s)
        return streams

    async def read_driver(
        self,
        burps: int,
    ):
        while True:
            while burps and random.getrandbits(1):
                await RisingEdge(self.clock)

            async with self.rd_busy:
                self.bus.tready.value = 1
                await RisingEdge(self.clock)
                while self.bus.tvalid.value.integer == 0:
                    await RisingEdge(self.clock)
            self.bus.tready.value = 0


# For backward compatibility
AXIStreamSlave = AXIStreamSlaveDriver
AXIStreamMaster = AXIStreamMasterDriver
