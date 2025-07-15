from amaranth import Elaboratable, Module, Signal, Mux, Const
from amaranth.lib import wiring

from hdl_utils.amaranth_utils.interfaces.axi4_stream import AXI4StreamSignature
from hdl_utils.amaranth_utils.axi_stream_to_full import AxiStreamToFull


class AxiDma(Elaboratable):
    def __init__(
        self,
        addr_w: int = 40,
        data_w: int = 128,
        user_w: int = 0,
        burst_len: int = 256,
    ):
        self.addr_w = addr_w
        self.data_w = data_w
        self.user_w = user_w
        self.burst_len = burst_len

        # Modules
        self.axi_stream_to_full = AxiStreamToFull(
            addr_w=addr_w,
            data_w=data_w,
            user_w=user_w,
        )

        # Sink
        self.sink = AXI4StreamSignature.create_slave(
            data_w=data_w, user_w=user_w, no_tkeep=True, path=['s_axis'],
        )
        # Source
        self.source = AXI4StreamSignature.create_master(
            data_w=data_w, user_w=user_w, no_tkeep=True, path=['m_axis'],
        )
        # M_AXI
        self.m_axi = self.axi_stream_to_full.m_axi
        # Config signals
        self.wr_start = Signal()
        self.rd_start = Signal()
        self.wr_addr = Signal.like(self.m_axi.ARADDR)
        self.rd_addr = Signal.like(self.m_axi.ARADDR)
        self.wr_len_beats = Signal(32)
        self.rd_len_beats = Signal(32)
        self.wr_qos = Signal(4)
        self.rd_qos = Signal(4)
        self.wr_ack = Signal()  # Out
        self.rd_ack = Signal()  # Out
        self.wr_finish = Signal()
        self.rd_finish = Signal()

    def get_ports(self, include_config_signals: bool = True):
        ports = [
            *self.sink.extract_signals(),
            *self.source.extract_signals(),
            *self.axi_stream_to_full.m_axi.extract_signals(),
        ]
        if include_config_signals:
            ports += [
                self.wr_start,
                self.rd_start,
                self.wr_addr,
                self.rd_addr,
                self.wr_len_beats,
                self.rd_len_beats,
                self.wr_qos,
                self.rd_qos,
                self.wr_ack,
                self.rd_ack,
                self.wr_finish,
                self.rd_finish,
            ]
        return ports

    def elaborate(self, platform):
        m = Module()
        m.submodules.axi_stream_to_full = self.axi_stream_to_full

        # as the number of beats of a full frame is multiple of the
        # highest burst size (256), fixed bursts at max size.
        AWLEN_CONST = self.burst_len - 1
        ARLEN_CONST = self.burst_len - 1

        bytes_per_beat = self.data_w // 8
        addr_jump = Const(self.burst_len * bytes_per_beat)

        wr_addr_r = Signal.like(self.m_axi.AWADDR)
        rd_addr_r = Signal.like(self.m_axi.ARADDR)
        wr_qos_r = Signal.like(self.axi_stream_to_full.wr_qos)
        rd_qos_r = Signal.like(self.axi_stream_to_full.rd_qos)
        wr_offset = Signal(32)
        rd_offset = Signal(32)
        wr_beats_remaining = Signal(32)
        rd_beats_remaining = Signal(32)

        def minimum(a, b) -> Signal:
            return Mux(a > b, b, a)

        # Sink and Memory Write assignments
        def disconnect_sink() -> list:
            return [
                self.sink.disconnect_from_sink(),
                *self.axi_stream_to_full.s_axis.connect_to_null_source(),
            ]

        def connect_sink_to_mem_wr() -> list:
            return [

            ]

        # Dma Write Config assignments
        def recv_wr_config() -> list:
            return [
                self.axi_stream_to_full.wr_valid.eq(self.wr_start),
                self.axi_stream_to_full.wr_addr.eq(self.wr_addr),
                self.axi_stream_to_full.wr_qos.eq(self.wr_qos),
                self.axi_stream_to_full.wr_burst.eq(minimum(AWLEN_CONST, self.wr_len_beats - 1)),
                self.wr_ack.eq(self.wr_start & self.axi_stream_to_full.wr_ready),
            ]

        def set_dma_wr_busy() -> list:
            return [
                self.axi_stream_to_full.wr_valid.eq(0),
                self.axi_stream_to_full.wr_addr.eq(0),
                self.axi_stream_to_full.wr_qos.eq(0),
                self.axi_stream_to_full.wr_burst.eq(0),
                self.wr_ack.eq(0),
            ]

        def configure_new_wr_burst() -> list:
            return [
                self.axi_stream_to_full.wr_valid.eq(1),
                self.axi_stream_to_full.wr_addr.eq(wr_addr_r + wr_offset + addr_jump),
                self.axi_stream_to_full.wr_qos.eq(wr_qos_r),
                self.axi_stream_to_full.wr_burst.eq(minimum(AWLEN_CONST, wr_beats_remaining)),
                self.wr_ack.eq(0),
            ]

        with m.FSM() as fsm_wr:

            with m.State("WR_RESET"):
                m.d.comb += set_dma_wr_busy()
                m.d.comb += disconnect_sink()
                m.next = "WR_PREPARE"

            with m.State("WR_PREPARE"):
                m.d.comb += recv_wr_config()
                m.d.comb += disconnect_sink()
                with m.If(self.axi_stream_to_full.wr_valid & self.axi_stream_to_full.wr_ready):
                    m.d.sync += [
                        wr_addr_r.eq(self.wr_addr),
                        wr_qos_r.eq(self.wr_qos),
                        wr_offset.eq(0),
                        wr_beats_remaining.eq(self.wr_len_beats - 1),
                        self.wr_finish.eq(0),
                    ]
                    m.next = "WR_BURST_STARTED"

            with m.State("WR_BURST_STARTED"):

                with m.If(self.axi_stream_to_full.wr_idle):
                    # Beats remaining, configure the new burst
                    m.d.comb += configure_new_wr_burst()
                    m.d.comb += disconnect_sink()
                    with m.If(self.axi_stream_to_full.wr_valid & self.axi_stream_to_full.wr_ready):
                        m.d.sync += [
                            wr_offset.eq(wr_offset + addr_jump),
                        ]

                with m.Else():
                    m.d.comb += set_dma_wr_busy()
                    wiring.connect(m, self.sink.as_master(), self.axi_stream_to_full.s_axis)

                    with m.If(self.sink.accepted() & (wr_beats_remaining > 0)):
                        m.d.sync += wr_beats_remaining.eq(wr_beats_remaining - 1)

                    with m.If(self.sink.accepted() & (self.sink.tlast | (wr_beats_remaining == 0))):
                        m.d.sync += self.wr_finish.eq(1)
                        m.next = "WR_PREPARE"


        # Memory read and Source assignments
        def disconnect_source() -> list:
            return [
                *self.source.connect_to_null_source(),
                self.axi_stream_to_full.m_axis.disconnect_from_sink(),
            ]

        def connect_mem_rd_to_source() -> list:
            return [
                self.source.tvalid.eq(self.axi_stream_to_full.m_axis.tvalid),
                self.source.tdata.eq(self.axi_stream_to_full.m_axis.tdata),
                self.source.tlast.eq(
                    self.axi_stream_to_full.m_axis.tvalid & (rd_beats_remaining == 0)
                ),
                self.axi_stream_to_full.m_axis.tready.eq(self.source.tready),
            ]

        # Dma Read Config assignments
        def recv_rd_config() -> list:
            return [
                self.axi_stream_to_full.rd_valid.eq(self.rd_start),
                self.axi_stream_to_full.rd_addr.eq(self.rd_addr),
                self.axi_stream_to_full.rd_qos.eq(self.rd_qos),
                self.axi_stream_to_full.rd_burst.eq(minimum(ARLEN_CONST, self.rd_len_beats - 1)),
                self.rd_ack.eq(self.rd_start & self.axi_stream_to_full.rd_ready),
            ]

        def set_dma_rd_busy() -> list:
            return [
                self.axi_stream_to_full.rd_valid.eq(0),
                self.axi_stream_to_full.rd_addr.eq(0),
                self.axi_stream_to_full.rd_qos.eq(0),
                self.axi_stream_to_full.rd_burst.eq(0),
                self.rd_ack.eq(0),
            ]

        def configure_new_rd_burst() -> list:
            return [
                self.axi_stream_to_full.rd_valid.eq(1),
                self.axi_stream_to_full.rd_addr.eq(rd_addr_r + rd_offset + addr_jump),
                self.axi_stream_to_full.rd_qos.eq(rd_qos_r),
                self.axi_stream_to_full.rd_burst.eq(minimum(ARLEN_CONST, rd_beats_remaining)),
                self.rd_ack.eq(0),
            ]

        with m.FSM() as fsm_rd:

            with m.State("RD_RESET"):
                m.d.comb += set_dma_rd_busy()
                m.d.comb += disconnect_source()
                m.next = "RD_PREPARE"

            with m.State("RD_PREPARE"):
                m.d.comb += recv_rd_config()
                m.d.comb += disconnect_source()
                with m.If(self.axi_stream_to_full.rd_valid & self.axi_stream_to_full.rd_ready):
                    m.d.sync += [
                        rd_addr_r.eq(self.rd_addr),
                        rd_qos_r.eq(self.rd_qos),
                        rd_offset.eq(0),
                        rd_beats_remaining.eq(self.rd_len_beats - 1),
                        self.rd_finish.eq(0),
                    ]
                    m.next = "RD_BURST_STARTED"

            with m.State("RD_BURST_STARTED"):

                with m.If(self.axi_stream_to_full.rd_idle):
                    m.d.comb += configure_new_rd_burst()
                    m.d.comb += disconnect_source()
                    with m.If(self.axi_stream_to_full.rd_valid & self.axi_stream_to_full.rd_ready):
                        m.d.sync += [
                            rd_offset.eq(rd_offset + addr_jump),
                        ]

                with m.Else():
                    m.d.comb += set_dma_rd_busy()
                    m.d.comb += connect_mem_rd_to_source()

                    with m.If(self.source.accepted() & (rd_beats_remaining > 0)):
                        m.d.sync += rd_beats_remaining.eq(rd_beats_remaining - 1)

                    with m.If(self.source.accepted() & self.source.tlast):
                        m.d.sync += self.rd_finish.eq(1)
                        with m.If(self.axi_stream_to_full.m_axis.tlast):
                            m.next = "RD_PREPARE"
                        with m.Else():
                            # Finished reading but no tlast
                            m.next = "RD_WAIT_LAST"

            with m.State("RD_WAIT_LAST"):
                m.d.comb += set_dma_rd_busy()
                m.d.comb += self.source.connect_to_null_source()
                m.d.comb += self.axi_stream_to_full.m_axis.connect_to_null_sink()
                with m.If(self.axi_stream_to_full.rd_idle):
                    m.next = "RD_PREPARE"

        return m
