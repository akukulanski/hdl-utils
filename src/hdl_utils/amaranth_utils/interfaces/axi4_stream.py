from __future__ import annotations

from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from hdl_utils.amaranth_utils.interfaces.interfaces import (
    extract_signals_from_wiring,
)

__all__ = [
    'extract_signals_from_wiring',
    'AXI4StreamInterface',
    'SlaveAXI4StreamInterface',
    'MasterAXI4StreamInterface',
]


# from: https://amaranth-lang.org/docs/amaranth/latest/stdlib/wiring.html#reusable-interfaces
class AXI4Stream(wiring.Signature):

    def __init__(self, data_w: int, user_w: int):
        super().__init__({
            "tvalid": Out(1),
            "tready": In(1),
            "tlast": Out(1),
            "tdata": Out(data_w),
            "tuser": Out(user_w),
        })

    def __eq__(self, other):
        return self.members == other.members

    def create(self, *, path=None, src_loc_at=0):
        return AXI4StreamInterface(self, path=path, src_loc_at=1 + src_loc_at)

    @classmethod
    def create_master(cls, *, data_w: int, path=None, src_loc_at=0):
        return MasterAXI4StreamInterface(cls(data_w=data_w), path=path,
                                         src_loc_at=1+src_loc_at)

    @classmethod
    def create_slave(cls, *, data_w: int, path=None, src_loc_at=0):
        return SlaveAXI4StreamInterface(cls(data_w=data_w).flip(), path=path,
                                        src_loc_at=1+src_loc_at)

    @classmethod
    def connect_m2s(cls, *, m, master, slave):
        wiring.connect(m, master, slave)


def connect_to_null_source(m, iface: AXI4StreamInterface):
    return [
        iface.tvalid.eq(0),
        iface.tlast.eq(0),
        iface.tdata.eq(0),
        iface.tuser.eq(0),
    ]


def connect_to_null_sink(m, iface: AXI4StreamInterface):
    return [
        iface.tready.eq(1),
    ]


class AXI4StreamInterface(wiring.PureInterface):

    @property
    def data_w(self):
        return len(self.tdata)

    @property
    def user_w(self):
        return len(self.tuser)

    def accepted(self):
        return self.tvalid & self.tready

    def extract_signals(self):
        return list(extract_signals_from_wiring(self))


class SlaveAXI4StreamInterface(AXI4StreamInterface):

    def as_master(self):
        return wiring.flipped(self)

    def connect(self, m, master):
        return wiring.connect(m, master, self)

    def connect_to_null_source(self):
        return connect_to_null_source(self)

    def connect_to_null_sink(self):
        return connect_to_null_sink(self.as_master())


class MasterAXI4StreamInterface(AXI4StreamInterface):

    def as_slave(self):
        return wiring.flipped(self)

    def connect(self, m, slave):
        return wiring.connect(m, self, slave)

    def connect_to_null_source(self):
        return connect_to_null_source(self.as_slave())

    def connect_to_null_sink(self):
        return connect_to_null_sink(self)
