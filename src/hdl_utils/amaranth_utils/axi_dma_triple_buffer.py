from amaranth import Elaboratable, Module, DomainRenamer, Signal, Mux, Array
from amaranth.lib import wiring

from hdl_utils.amaranth_utils.interfaces.axi4_stream import AXI4StreamSignature
from hdl_utils.amaranth_utils.axi_dma import AxiDma


class AXIDmaTripleBuffer(Elaboratable):
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
        self.axi_dma = AxiDma(
            addr_w=addr_w,
            data_w=data_w,
            user_w=user_w,
            burst_len=burst_len,
        )

        # Sink
        self.sink = AXI4StreamSignature.create_slave(
            data_w=data_w, user_w=user_w, no_tkeep=True, path=['s_axis'],
        )
        # Source
        self.source = AXI4StreamSignature.create_master(
            data_w=data_w, user_w=user_w, no_tkeep=True, path=['m_axis'],
        )
        # Axi full
        self.m_axi = self.axi_dma.m_axi
        # Config signals
        self.wr_enable = Signal(1)
        self.rd_enable = Signal(1)
        self.base_addr_0 = Signal.like(self.m_axi.ARADDR)
        self.base_addr_1 = Signal.like(self.m_axi.ARADDR)
        self.base_addr_2 = Signal.like(self.m_axi.ARADDR)
        self.wr_qos = Signal(4)
        self.rd_qos = Signal(4)
        self.wr_len_beats = Signal(32)
        self.rd_len_beats = Signal(32)
        self.wr_dont_change_buffer_if_incomplete = Signal()

    def get_ports(self, include_config_signals: bool = True):
        ports = [
            *self.sink.extract_signals(),
            *self.source.extract_signals(),
            *self.axi_dma.m_axi.extract_signals(),
        ]
        if include_config_signals:
            ports += [
                self.wr_enable,
                self.rd_enable,
                self.base_addr_0,
                self.base_addr_1,
                self.base_addr_2,
                self.wr_qos,
                self.rd_qos,
                self.wr_len_beats,
                self.rd_len_beats,
                self.wr_dont_change_buffer_if_incomplete,
            ]
        return ports

    def elaborate(self, platform):
        m = Module()
        m.submodules.axi_dma = self.axi_dma

        buffer_address_array = Array([
            self.base_addr_0,
            self.base_addr_1,
            self.base_addr_2,
        ])
        n_buffers = len(buffer_address_array)

        init_wr_addr_id = 1
        init_rd_addr_id = 0
        wr_addr_id = Signal(2, init=init_wr_addr_id)
        rd_addr_id = Signal(2, init=init_rd_addr_id)
        next_wr_addr_id = Signal.like(wr_addr_id)
        next_rd_addr_id = Signal.like(rd_addr_id)

        wr_beats_count = Signal(32)
        wr_early_tlast = Signal()
        wr_missing_tlast = Signal()
        wr_last_ok = Signal()

        m.d.comb += [
            next_wr_addr_id.eq((wr_addr_id + 1) % n_buffers),
            next_rd_addr_id.eq((rd_addr_id + 1) % n_buffers),
            self.axi_dma.wr_addr.eq(buffer_address_array[wr_addr_id]),  # self.axi_dma.wr_addr.eq(wr_addr_base_r),
            self.axi_dma.rd_addr.eq(buffer_address_array[rd_addr_id]),  # self.axi_dma.rd_addr.eq(rd_addr_base_r),
            self.axi_dma.wr_qos.eq(self.wr_qos),
            self.axi_dma.rd_qos.eq(self.rd_qos),
            self.axi_dma.wr_len_beats.eq(self.wr_len_beats),
            self.axi_dma.rd_len_beats.eq(self.rd_len_beats),
        ]

        m.d.comb += [
            wr_early_tlast.eq(self.sink.accepted() & self.sink.tlast & (wr_beats_count != 0)),
            wr_missing_tlast.eq(self.sink.accepted() & (~self.sink.tlast) & (wr_beats_count == 0)),
            wr_last_ok.eq(self.sink.accepted() & self.sink.tlast & (wr_beats_count == 0)),
        ]

        def set_dma_wr_busy() -> list:
            return [
                self.axi_dma.wr_start.eq(0),
            ]

        def disconnect_sink() -> list:
            return [
                self.sink.disconnect_from_sink(),
                *self.axi_dma.sink.connect_to_null_source(),
            ]

        def connect_sink_to_dma_wr() -> list:
            return [
                self.axi_dma.sink.tvalid.eq(self.sink.tvalid),
                self.axi_dma.sink.tdata.eq(self.sink.tdata),
                self.axi_dma.sink.tlast.eq(self.sink.tlast | (wr_beats_count == 0)),
                self.sink.tready.eq(self.axi_dma.sink.tready),
            ]

        with m.FSM() as fsm_wr:

            with m.State("WR_RESET"):
                m.d.comb += set_dma_wr_busy()
                m.d.comb += disconnect_sink()
                m.d.sync += wr_addr_id.eq(init_wr_addr_id)
                m.next = "WR_CONFIG"

            with m.State("WR_CONFIG"):
                m.d.comb += self.axi_dma.wr_start.eq(self.wr_enable)
                m.d.comb += disconnect_sink()
                with m.If(self.axi_dma.wr_start & self.axi_dma.wr_ack):
                    m.d.sync += wr_beats_count.eq(self.wr_len_beats - 1)
                    m.next = "WR_RUNNING"

            with m.State("WR_RUNNING"):
                m.d.comb += set_dma_wr_busy()
                m.d.comb += connect_sink_to_dma_wr()

                with m.If(self.sink.accepted() & (wr_beats_count > 0)):
                    m.d.sync += wr_beats_count.eq(wr_beats_count - 1)

                with m.If(wr_early_tlast):
                    with m.If(self.wr_dont_change_buffer_if_incomplete):
                        # Go to WR_CONFIG. Don't change the buffer where next
                        # write takes place because the current one was incomplete.
                        m.next = "WR_CONFIG"
                    with m.Else():
                        m.next = "WR_NEXT_BUFFER"
                with m.Elif(wr_missing_tlast):
                    m.next = "WR_WAIT_LAST"
                with m.Elif(wr_last_ok):
                    m.next = "WR_NEXT_BUFFER"

            with m.State("WR_NEXT_BUFFER"):
                m.d.comb += set_dma_wr_busy()
                m.d.comb += disconnect_sink()
                with m.If(next_wr_addr_id != rd_addr_id):
                    m.d.sync += wr_addr_id.eq(next_wr_addr_id)
                m.next = "WR_CONFIG"

            with m.State("WR_WAIT_LAST"):
                m.d.comb += set_dma_wr_busy()
                m.d.comb += disconnect_sink()
                with m.If(self.sink.accepted() & self.sink.tlast):
                    m.next = "WR_NEXT_BUFFER"

        def set_dma_rd_busy() -> list:
            return [
                self.axi_dma.rd_start.eq(0),
            ]

        def disconnect_source() -> list:
            return [
                *self.source.connect_to_null_source(),
                self.axi_dma.source.disconnect_from_sink(),
            ]

        with m.FSM() as fsm_rd:

            with m.State("RESET"):
                m.d.comb += set_dma_rd_busy()
                m.d.comb += disconnect_source()
                m.d.sync += rd_addr_id.eq(init_rd_addr_id)
                m.next = "RD_CONFIG"

            with m.State("RD_CONFIG"):
                m.d.comb += self.axi_dma.rd_start.eq(self.rd_enable)
                m.d.comb += disconnect_source()
                with m.If(self.axi_dma.rd_start & self.axi_dma.rd_ack):
                    m.next = "RD_IN_PROGRESS"

            with m.State("RD_IN_PROGRESS"):
                m.d.comb += set_dma_rd_busy()
                wiring.connect(m, self.axi_dma.source, self.source.as_slave())
                with m.If(self.axi_dma.source.accepted()):
                    with m.If(self.axi_dma.source.tlast):
                        m.next = "RD_NEXT_BUFFER"

            with m.State("RD_NEXT_BUFFER"):
                m.d.comb += set_dma_rd_busy()
                with m.If(self.rd_enable):
                    with m.If(next_rd_addr_id != wr_addr_id):
                        m.d.sync += rd_addr_id.eq(next_rd_addr_id)
                    m.next = "RD_CONFIG"

            with m.State("RD_REPEAT"):
                m.d.comb += set_dma_rd_busy()
                with m.If(self.rd_enable):
                    m.next = "RD_CONFIG"

        return m
