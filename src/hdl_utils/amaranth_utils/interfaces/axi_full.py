from __future__ import annotations

from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from hdl_utils.amaranth_utils.interfaces.interfaces import (
    extract_signals_from_wiring,
)


__all__ = [
    'AXI4Signature',
    'AXI4Interface',
    'SlaveAXI4Interface',
    'MasterAXI4Interface',
]

BURST_TYPE_FIXED = 0
BURST_TYPE_INCR = 1
BURST_TYPE_WRAP = 2
BURST_TYE_RESERVED = 3

RESP_OKAY = 0
RESP_EXOKAY = 1
RESP_SLVERR = 2
RESP_DECERR = 3
# • for wrapping bursts, the burst length must be 2, 4, 8, or 16
# • a burst must not cross a 4KB address boundary
# • early termination of bursts it not supported.

# When this bit is asserted, the interconnect, or any component, can delay the transaction reaching its final destination for any number of cycles.
CACHE_BUFFERABLE_MASK = (1 << 0)

# When this bit is deasserted, allocation of the transaction is forbidden.
CACHE_CACHEABLE_MASK = (1 << 1)

# When this bit is asserted, read allocation of the transaction is recommended but is not mandatory.
# The RA bit must not be asserted if the C bit is deasserted
CACHE_READ_ALLOCATE_MASK = (1 << 2)

# When this bit is asserted, write allocation of the transaction is recommended but is not mandatory.
# The WA bit must not be asserted if the C bit is deasserted
CACHE_WRITE_ALLOCATE_MASK = (1 << 3)


# from: https://amaranth-lang.org/docs/amaranth/latest/stdlib/wiring.html#reusable-interfaces
class AXI4Signature(wiring.Signature):

    def __init__(
        self,
        addr_w: int,
        data_w: int,
        user_w: int,
        id_w: int
    ):
        # www.gstitt.ece.ufl.edu/courses/fall15/eel4720_5721/labs/refs/AXI4_specification.pdf#page=122
        assert data_w in (32, 64, 128)
        self.addr_w = addr_w
        self.data_w = data_w
        layout = {
            # Address write channel
            "AWID": In(id_w),
            "AWADDR": In(addr_w),
            "AWLEN": In(8),  # burst length = awlen + 1
            "AWSIZE": In(3),  # Bytes in transfer = 2 ** AWSIZE (se usa para calcular addr con bursts. Fijar por ancho del bus!)
            "AWBURST": In(2),
            "AWLOCK": In(1),  # keep at 0
            "AWCACHE": In(4),  # keep at 0x3
            "AWPROT": In(3),  # keep at 0
            "AWQOS": In(4),  # set to 0xf for SDI IN/OUT, set to 0 for others
            "AWREGION": In(4),  # keep at 0
            "AWUSER": In(user_w),
            "AWVALID": In(1),
            "AWREADY": Out(1),
            # Write channel
            "WID": In(id_w),
            "WDATA": In(data_w),
            "WSTRB": In(data_w // 8),
            "WLAST": In(1),
            "WUSER": In(user_w),
            "WVALID": In(1),
            "WREADY": Out(1),
            # Write response channel
            "BID": Out(id_w),
            "BRESP": Out(2),
            "BUSER": Out(user_w),
            "BVALID": Out(1),
            "BREADY": In(1),
            # Address read channel
            "ARID": In(id_w),
            "ARADDR": In(addr_w),
            "ARLEN": In(8),  # burst length = awlen + 1
            "ARSIZE": In(3),  # Bytes in transfer = 2 ** AWSIZE (se usa para calcular addr con bursts. Fijar por ancho del bus!)
            "ARBURST": In(2),
            "ARLOCK": In(1),  # keep at 0
            "ARCACHE": In(4),  # keep at 0x3
            "ARPROT": In(3),  # keep at 0
            "ARQOS": In(4),  # set to 0xf for SDI IN/OUT, set to 0 for others
            "ARREGION": In(4),  # keep at 0
            "ARUSER": In(user_w),
            "ARVALID": In(1),
            "ARREADY": Out(1),
            # Read channel
            "RID": Out(id_w),
            "RDATA": Out(data_w),
            "RLAST": Out(1),
            "RUSER": Out(user_w),
            "RVALID": Out(1),
            "RREADY": In(1),
            "RRESP": Out(2),
        }
        if user_w == 0:
            del layout['AWUSER'], layout['WUSER'], layout['ARUSER'], layout['RUSER'], layout['BUSER']
        if id_w == 0:
            del layout['AWID'], layout['WID'], layout['ARID'], layout['RID'], layout['BID']
        super().__init__(layout)

    def __eq__(self, other):
        return self.members == other.members

    def create(self, *, path=None, src_loc_at=0):
        return AXI4Interface(self, path=path, src_loc_at=1 + src_loc_at)

    @classmethod
    def create_master(
        cls,
        *,
        addr_w: int,
        data_w: int,
        user_w: int = 0,
        id_w: int = 0,
        path=None,
        src_loc_at=0
    ) -> MasterAXI4Interface:
        return MasterAXI4Interface(
            cls(addr_w=addr_w, data_w=data_w, user_w=user_w, id_w=id_w),
            path=path,
            src_loc_at=1+src_loc_at
        )

    @classmethod
    def create_slave(
        cls,
        *,
        addr_w: int,
        data_w: int,
        user_w: int = 0,
        id_w: int = 0,
        path=None,
        src_loc_at=0
    ) -> SlaveAXI4Interface:
        return SlaveAXI4Interface(
            cls(addr_w=addr_w, data_w=data_w, user_w=user_w, id_w=id_w).flip(),
            path=path,
            src_loc_at=1+src_loc_at
        )

    @classmethod
    def connect_m2s(cls, *, m, master, slave):
        wiring.connect(m, master, slave)


class AXI4Interface(wiring.PureInterface):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __getattr__(self, key: str):
        try:
            return getattr(self, key.upper())
        except RecursionError:
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{key}'")

    @property
    def data_w(self):
        return len(self.WDATA)

    @property
    def addr_w(self):
        return len(self.AWADDR)

    @property
    def user_w(self):
        return len(self.WUSER)

    @property
    def id_w(self):
        return len(self.WID)

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


class SlaveAXI4Interface(AXI4Interface):

    def as_master(self):
        return wiring.flipped(self)

    def connect(self, m, master):
        return wiring.connect(m, master, self)


class MasterAXI4Interface(AXI4Interface):

    def as_slave(self):
        return wiring.flipped(self)

    def connect(self, m, slave):
        return wiring.connect(m, self, slave)
