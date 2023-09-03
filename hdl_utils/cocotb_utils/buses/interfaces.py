from typing import Any, Sequence, Tuple, Union
import random

from cocotb.triggers import Lock, RisingEdge
from cocotb.handle import SimHandleBase
from cocotb_bus.drivers import BusDriver


__all__ = ['DataStreamMaster', 'DataStreamSlave']


class DataStreamBase(BusDriver):
    _signals = [
        "valid", "ready", "last", "data"]

    _optional_signals = []

    def __len__(self):
        return 2**len(self.bus.data)


class DataStreamMaster(DataStreamBase):
    """DataStreamMaster
    """

    def __init__(self, entity: SimHandleBase, name: str, clock: SimHandleBase,
                 **kwargs: Any):
        DataStreamBase.__init__(self, entity, name, clock, **kwargs)

        # Drive some sensible defaults (setimmediatevalue to avoid x asserts)
        self.bus.valid.setimmediatevalue(0)
        self.bus.last.setimmediatevalue(0)
        self.bus.data.setimmediatevalue(0)

        # Mutex for each channel to prevent contention
        self.wr_busy = Lock(name + "_wbusy")

    async def _send_write_data(self, data: int, last: bool) -> None:
        """Send a single data."""
        async with self.wr_busy:
            self.bus.valid.value = 1
            self.bus.last.value = int(last)
            self.bus.data.value = data
            await RisingEdge(self.clock)
            while self.bus.ready.value.integer == 0:
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


class DataStreamSlave(DataStreamBase):
    """DataStreamSlave
    """

    def __init__(self, entity: SimHandleBase, name: str, clock: SimHandleBase,
                 **kwargs: Any):
        DataStreamBase.__init__(self, entity, name, clock, **kwargs)

        # Drive some sensible defaults (setimmediatevalue to avoid x asserts)
        self.bus.ready.setimmediatevalue(0)

        # Mutex for each channel to prevent contention
        self.rd_busy = Lock(name + "_rbusy")

    async def _recv_rd_data(self) -> Tuple[int]:
        """Receive a single data.
        Returns the tuple (value, last).
        """
        async with self.rd_busy:
            self.bus.ready.value = 1
            await RisingEdge(self.clock)
            while self.bus.valid.value.integer == 0:
                await RisingEdge(self.clock)
        value = self.bus.data.value.integer
        last = self.bus.last.value.integer
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
