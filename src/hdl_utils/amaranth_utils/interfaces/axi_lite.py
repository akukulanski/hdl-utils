from __future__ import annotations

from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from hdl_utils.amaranth_utils.interfaces.interfaces import (
    extract_signals_from_wiring,
)


__all__ = [
    'AXI4LiteSignature',
    'AXI4LiteInterface',
    'SlaveAXI4LiteInterface',
    'MasterAXI4LiteInterface',
]


# from: https://amaranth-lang.org/docs/amaranth/latest/stdlib/wiring.html#reusable-interfaces
class AXI4LiteSignature(wiring.Signature):

    def __init__(self, data_w: int, addr_w: int):
        # www.gstitt.ece.ufl.edu/courses/fall15/eel4720_5721/labs/refs/AXI4_specification.pdf#page=122
        assert data_w in (32, 64)
        self.addr_w = addr_w
        self.data_w = data_w
        layout = {
            "AWADDR": In(addr_w),
            "AWVALID": In(1),
            "AWREADY": Out(1),
            "WDATA": In(data_w),
            "WSTRB": In(data_w // 8),
            "WVALID": In(1),
            "WREADY": Out(1),
            "BRESP": Out(2),
            "BVALID": Out(1),
            "BREADY": In(1),
            "ARADDR": In(addr_w),
            "ARVALID": In(1),
            "ARREADY": Out(1),
            "RDATA": Out(data_w),
            "RRESP": Out(2),
            "RVALID": Out(1),
            "RREADY": In(1),

        }
        super().__init__(layout)
        # Overload with lowercase version of signals.
        # for s in layout:
        #     setattr(self, s.lower(), getattr(self, s))

    def __eq__(self, other):
        return self.members == other.members

    def create(self, *, path=None, src_loc_at=0):
        return AXI4LiteInterface(self, path=path, src_loc_at=1 + src_loc_at)

    @classmethod
    def create_master(
        cls,
        *,
        data_w: int,
        addr_w: int,
        path=None,
        src_loc_at=0
    ) -> MasterAXI4LiteInterface:
        return MasterAXI4LiteInterface(
            cls(data_w=data_w, addr_w=addr_w),
            path=path,
            src_loc_at=1+src_loc_at
        )

    @classmethod
    def create_slave(
        cls,
        *,
        data_w: int,
        addr_w: int,
        path=None,
        src_loc_at=0
    ) -> SlaveAXI4LiteInterface:
        return SlaveAXI4LiteInterface(
            cls(data_w=data_w, addr_w=addr_w).flip(),
            path=path,
            src_loc_at=1+src_loc_at
        )

    @classmethod
    def connect_m2s(cls, *, m, master, slave):
        wiring.connect(m, master, slave)


class AXI4LiteInterface(wiring.PureInterface):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Overload with lowercase version of signals.
        for s in self.signature.members.keys():
            setattr(self, s.lower(), getattr(self, s))

    @property
    def data_w(self):
        return len(self.tdata)

    @property
    def user_w(self):
        return len(self.tuser)

    def aw_accepted(self):
        return self.AWVALID & self.AWREADY

    def w_accepted(self):
        return self.WVALID & self.WREADY

    def b_accepted(self):
        return self.BVALID & self.BREADY

    def ar_accepted(self):
        return self.ARVALID & self.ARREADY

    def r_accepted(self):
        return self.RVALID & self.RREADY

    def extract_signals(self):
        return list(extract_signals_from_wiring(self))


class SlaveAXI4LiteInterface(AXI4LiteInterface):

    def as_master(self):
        return wiring.flipped(self)

    def connect(self, m, master):
        return wiring.connect(m, master, self)


class MasterAXI4LiteInterface(AXI4LiteInterface):

    def as_slave(self):
        return wiring.flipped(self)

    def connect(self, m, slave):
        return wiring.connect(m, self, slave)
