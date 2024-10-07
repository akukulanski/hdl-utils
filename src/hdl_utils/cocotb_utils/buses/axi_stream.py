from typing import Any, Sequence, Tuple, Union
import random

from cocotb.triggers import Lock, RisingEdge
from cocotb.handle import SimHandleBase
from cocotb_bus.drivers import BusDriver


__all__ = [
    'AXIStreamBase',
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


class AXIStreamBase(BusDriver):
    _signals = [
        "tvalid", "tready", "tlast", "tdata"
    ]

    _optional_signals = [
        "tuser", "tkeep"
    ]

    def __init__(self, *args, **kwargs):
        self.monitor = []
        self.current_stream = []
        super().__init__(*args, **kwargs)

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

    async def run_monitor(self):
        self.monitor.clear()
        self.current_stream.clear()
        while True:
            await RisingEdge(self.clock)
            if self.accepted():
                self.current_stream.append(self._capture_current_values())
                if self.bus.tlast.value.integer:
                    self.monitor.append(self.current_stream)
                    self.current_stream = []

    def get_monitor(self):
        return list(self.monitor)  # a copy

    def get_current_stream(self):
        return list(self.current_stream)  # a copy

    def extract_capture_data(self, capture):
        # TODO: Deprecate (kept for compatibility).
        return extract_capture_data(capture)

    def extract_capture_user(self, capture):
        # TODO: Deprecate (kept for compatibility).
        return extract_capture_user(capture)

    def extract_capture_keep(self, capture):
        # TODO: Deprecate (kept for compatibility).
        return extract_capture_keep(capture)


class AXIStreamMaster(AXIStreamBase):
    """AXIStreamMaster
    """

    def __init__(self, entity: SimHandleBase, name: str, clock: SimHandleBase,
                 **kwargs: Any):
        super().__init__(entity, name, clock, **kwargs)

        # Drive some sensible defaults (setimmediatevalue to avoid x asserts)
        self.bus.tvalid.setimmediatevalue(0)
        self.bus.tlast.setimmediatevalue(0)
        self.bus.tdata.setimmediatevalue(0)
        try:
            self.bus.tkeep.setimmediatevalue(0)
        except Exception:
            pass
        try:
            self.bus.tuser.setimmediatevalue(0)
        except Exception:
            pass

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


class AXIStreamSlave(AXIStreamBase):
    """AXIStreamSlave
    """

    def __init__(self, entity: SimHandleBase, name: str, clock: SimHandleBase,
                 **kwargs: Any):
        super().__init__(entity, name, clock, **kwargs)

        # Drive some sensible defaults (setimmediatevalue to avoid x asserts)
        self.bus.tready.setimmediatevalue(0)

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
        value = self.bus.tdata.value.integer
        last = self.bus.tlast.value.integer
        self.bus.tready.value = 0
        return (value, last)

    async def read(
        self,
        length: int = None,
        ignore_last: bool = False,
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
            value, last = await self._recv_rd_data()
            data.append(value)
            count += 1
            if (last and not ignore_last) or (count == length):
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
