from amaranth import Elaboratable, Module, ResetSignal, Signal, Mux, Cat, Array

from hdl_utils.amaranth_utils.interfaces.axi4_stream import AXI4StreamSignature


class AXIStreamSplitter(Elaboratable):

    def __init__(
        self,
        data_w: int,
        user_w: int,
        no_tkeep: bool,
        n_split: int,
    ):
        self.sink = AXI4StreamSignature.create_slave(
            data_w=data_w,
            user_w=user_w,
            no_tkeep=no_tkeep,
            path=['s_axis'],
        )
        self.sources = [
            AXI4StreamSignature.create_master(
                data_w=data_w,
                user_w=user_w,
                no_tkeep=no_tkeep,
                path=[f'm_axis_{i:02d}'],
            )
            for i in range(n_split)
        ]
        self.n_split = n_split

    def get_ports(self):
        ports = []
        ports += self.sink.extract_signals()
        for src in self.sources:
            ports += src.extract_signals()
        return ports

    def elaborate(self, platform):
        m = Module()

        pending_accepts = Array(Signal(name=f"pending_accept_{i}", init=0) for i in range(self.n_split))
        pending_accept_cat = Signal.like(Cat(pending_accepts))
        any_pending_accept = Signal(self.n_split, init=0)
        all_pending_accept = Signal(self.n_split, init=0)
        readys = Signal(self.n_split, init=0)

        m.d.comb += [
            pending_accept_cat.eq(Cat(pending_accepts)),
            any_pending_accept.eq(pending_accept_cat.any()),
            all_pending_accept.eq(pending_accept_cat.all()),
            readys.eq(Cat([src.tready for src in self.sources]))
        ]

        with m.If(any_pending_accept):
            # ready if all pending readys are set
            m.d.comb += [
                self.sink.tready.eq(
                    ((pending_accept_cat & readys) == pending_accept_cat)
                    & (~ResetSignal())
                )
            ]

            for i, src in enumerate(self.sources):
                m.d.comb += [
                    src.tvalid.eq(pending_accepts[i]),
                    src.tlast.eq(Mux(pending_accepts[i], self.sink.tlast, 0)),
                    src.tdata.eq(Mux(pending_accepts[i], self.sink.tdata, 0)),
                ]

                if hasattr(self.sink, "tuser"):
                    m.d.comb += [
                        src.tuser.eq(Mux(pending_accepts[i], self.sink.tuser, 0)),
                    ]

                if hasattr(self.sink, "tkeep"):
                    m.d.comb += [
                        src.tkeep.eq(Mux(pending_accepts[i], self.sink.tkeep, 0)),
                    ]

                with m.If(src.tready):
                    m.d.sync += pending_accepts[i].eq(0)

        with m.Else():
            # ready if all readys are set
            m.d.comb += [
                self.sink.tready.eq(readys.all() & ~ResetSignal()),
            ]

            for i, src in enumerate(self.sources):
                m.d.comb += [
                    src.tvalid.eq(self.sink.tvalid),
                    src.tlast.eq(self.sink.tlast),
                    src.tdata.eq(self.sink.tdata),
                ]

                if hasattr(self.sink, "tuser"):
                    m.d.comb += src.tuser.eq(self.sink.tuser)

                if hasattr(self.sink, "tkeep"):
                    m.d.comb += src.tkeep.eq(self.sink.tkeep)

                with m.If(self.sink.tvalid & readys.any() & ~src.tready):
                    m.d.sync += pending_accepts[i].eq(1)

        return m
