from amaranth import Elaboratable, Module
from amaranth.lib.fifo import SyncFIFOBuffered, AsyncFIFO

from hdl_utils.amaranth_utils.interfaces.axi4_stream import AXI4StreamSignature


class AXIStreamFIFO(Elaboratable):

    def __init__(
        self,
        data_w: int,
        user_w: int,
        depth: int,
        fifo_cls: Elaboratable = SyncFIFOBuffered,
        *args,
        **kwargs
    ):
        self.sink = AXI4StreamSignature.create_slave(
            data_w=data_w,
            user_w=user_w,
            path=['s_axis'],
        )
        self.source = AXI4StreamSignature.create_master(
            data_w=data_w,
            user_w=user_w,
            path=['m_axis'],
        )
        total_width = len(self.sink.flatten())
        self.fifo = fifo_cls(width=total_width, depth=depth, *args, **kwargs)

    def get_ports(self):
        return self.sink.extract_signals() + self.source.extract_signals()

    def elaborate(self, platform):
        m = Module()
        # Fifo Instance
        m.submodules.fifo_core = fifo = self.fifo
        # Sink
        m.d.comb += fifo.w_data.eq(self.sink.flatten())
        m.d.comb += fifo.w_en.eq(self.sink.accepted())
        m.d.comb += self.sink.tready.eq(fifo.w_rdy)
        # Source
        m.d.comb += self.source.tvalid.eq(fifo.r_rdy)
        m.d.comb += fifo.r_en.eq(self.source.accepted())
        m.d.comb += self.source.assign_from_flat(fifo.r_data)
        # Return module
        return m

    @classmethod
    def CreateCDC(
        cls,
        *args,
        r_domain,
        w_domain,
        fifo_cls: Elaboratable = AsyncFIFO,
        **kwargs
    ):
        return cls(
            *args,
            fifo_cls=fifo_cls,
            r_domain=r_domain,
            w_domain=w_domain,
            **kwargs
        )
