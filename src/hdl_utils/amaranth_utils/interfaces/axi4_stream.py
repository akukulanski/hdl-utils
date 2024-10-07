from __future__ import annotations

from amaranth import Signal, Cat
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out
from amaranth.hdl._ast import Assign, Operator

from hdl_utils.amaranth_utils.interfaces.interfaces import (
    extract_signals_from_wiring,
)

__all__ = [
    'extract_signals_from_wiring',
    'AXI4StreamSignature',
    'AXI4StreamInterface',
    'SlaveAXI4StreamInterface',
    'MasterAXI4StreamInterface',
]


# from: https://amaranth-lang.org/docs/amaranth/latest/stdlib/wiring.html#reusable-interfaces
class AXI4StreamSignature(wiring.Signature):

    def __init__(self, data_w: int, user_w: int, no_tkeep: bool = False):
        layout = {
            "tvalid": Out(1),
            "tready": In(1),
            "tlast": Out(1),
            "tdata": Out(data_w),
            "tuser": Out(user_w),
            "tkeep": Out(data_w // 8),
        }
        if user_w == 0:
            del layout['tuser']
        if no_tkeep:
            del layout['tkeep']
        super().__init__(layout)

    def __eq__(self, other):
        return self.members == other.members

    def create(self, *, path=None, src_loc_at=0) -> AXI4StreamInterface:
        return AXI4StreamInterface(self, path=path, src_loc_at=1 + src_loc_at)

    @classmethod
    def create_master(
        cls,
        *,
        data_w: int,
        user_w: int,
        no_tkeep: bool = False,
        path=None,
        src_loc_at=0
    ) -> MasterAXI4StreamInterface:
        return MasterAXI4StreamInterface(
            cls(data_w=data_w, user_w=user_w, no_tkeep=no_tkeep),
            path=path,
            src_loc_at=1+src_loc_at
        )

    @classmethod
    def create_slave(
        cls,
        *,
        data_w: int,
        user_w: int,
        no_tkeep: bool = False,
        path=None,
        src_loc_at=0
    ) -> SlaveAXI4StreamInterface:
        return SlaveAXI4StreamInterface(
            cls(data_w=data_w, user_w=user_w, no_tkeep=no_tkeep).flip(),
            path=path,
            src_loc_at=1+src_loc_at
        )

    @classmethod
    def connect_m2s(cls, *, m, master, slave):
        wiring.connect(m, master, slave)


def connect_to_null_source(iface: AXI4StreamInterface) -> list[Assign]:
    connections = [
        iface.tvalid.eq(0),
        iface.tlast.eq(0),
        iface.tdata.eq(0),
    ]
    if hasattr(iface, 'tuser'):
        connections += [iface.tuser.eq(0)]
    if hasattr(iface, 'tkeep'):
        connections += [iface.tkeep.eq(0)]
    return


def connect_to_null_sink(iface: AXI4StreamInterface) -> Assign:
    return iface.tready.eq(1)


def disconnect_from_sink(iface: AXI4StreamInterface) -> Assign:
    return iface.tready.eq(0)


class AXI4StreamInterface(wiring.PureInterface):

    @property
    def data_w(self) -> int:
        return len(self.tdata)

    @property
    def user_w(self) -> int:
        return len(self.tuser) if self.has_tuser() else 0

    @property
    def keep_w(self) -> int:
        return len(self.tkeep) if self.has_tkeep() else 0

    def accepted(self) -> Operator:
        return self.tvalid & self.tready

    def extract_signals(self) -> list:
        return list(extract_signals_from_wiring(self))

    def has_tuser(self):
        return hasattr(self, 'tuser')

    def has_tkeep(self):
        return hasattr(self, 'tkeep')

    def _safe_tuser(self):
        return self.tuser if self.has_tuser() else None

    def _safe_tkeep(self):
        return self.tkeep if self.has_tkeep() else None

    @property
    def _data_fields(self):
        fields = [self.tdata]
        fields += [self.tuser] if self.has_tuser() else []
        fields += [self.tkeep] if self.has_tkeep() else []
        fields += [self.tlast]
        return fields

    def flatten(self) -> Signal:
        return Cat(*self._data_fields)

    def assign_from_flat(self, flat_data: Signal) -> Assign:
        concat = Cat(*self._data_fields)
        assert len(flat_data) == len(concat)
        return concat.eq(flat_data)
        # ops = []
        # start_bit = 0
        # assert len(flat_data) == len(concat)
        # for sig, width in self._data_fields:
        #     ops += [sig.eq(flat_data[start_bit:start_bit+width])]
        #     start_bit += width
        # return ops


class SlaveAXI4StreamInterface(AXI4StreamInterface):

    def as_master(self):
        return wiring.flipped(self)

    def connect(self, m, master):
        return wiring.connect(m, master, self)

    def connect_to_null_source(self):
        return connect_to_null_source(self)

    def connect_to_null_sink(self):
        return connect_to_null_sink(self.as_master())

    def disconnect_from_sink(self):
        return disconnect_from_sink(self.as_master())


class MasterAXI4StreamInterface(AXI4StreamInterface):

    def as_slave(self):
        return wiring.flipped(self)

    def connect(self, m, slave):
        return wiring.connect(m, self, slave)

    def connect_to_null_source(self):
        return connect_to_null_source(self.as_slave())

    def connect_to_null_sink(self):
        return connect_to_null_sink(self)

    def disconnect_from_sink(self):
        return disconnect_from_sink(self)
