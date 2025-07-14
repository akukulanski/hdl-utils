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
            data_w=data_w, user_w=user_w, path=['s_axi'],
        )
        # Source
        self.source = AXI4StreamSignature.create_master(
            data_w=data_w, user_w=user_w, path=['m_axi'],
        )
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
            ]
        return ports

    def elaborate(self, platform):
        m = Module()
        m.submodules.axi_dma = self.axi_dma

        wr_addr_base_r = Signal.like(self.m_axi.AWADDR)
        rd_addr_base_r = Signal.like(self.m_axi.ARADDR)
        buffer_address_array = Array([
            self.base_addr_0,
            self.base_addr_1,
            self.base_addr_2,
        ])
        n_buffers = len(buffer_address_array)
        next_wr_addr_id = Signal.like(wr_addr_id)
        next_rd_addr_id = Signal.like(rd_addr_id)

        init_rd_addr_id = 0
        init_wr_addr_id = 1
        rd_addr_id = Signal(2, init=init_rd_addr_id)
        wr_addr_id = Signal(2, init=init_wr_addr_id)

        wr_beats_count = Signal(32)
        rd_beats_count = Signal(32)

        m.d.comb += [
            next_wr_addr_id.eq((wr_addr_id + 1) % n_buffers),
            next_rd_addr_id.eq((rd_addr_id + 1) % n_buffers),
            self.axi_dma.wr_addr_base.eq(wr_addr_base_r),
            self.axi_dma.rd_addr_base.eq(rd_addr_base_r),
            self.axi_dma.wr_qos.eq(self.wr_qos),
            self.axi_dma.rd_qos.eq(self.rd_qos),
            self.axi_dma.wr_len_beats.eq(self.wr_len_beats),
            self.axi_dma.rd_len_beats.eq(self.rd_len_beats),
        ]

        with m.FSM() as fsm_wr:

            with m.State("RESET"):
                m.d.comb += [
                    self.axi_dma.wr_start.eq(0),
                    *self.sink.disconnect_from_sink(),
                    *self.axi_dma.sink.connect_to_null_source(),
                ]
                m.d.sync += [
                    wr_addr_id.eq(init_wr_addr_id),
                ]
                m.next = "WR_PREPARE"

            with m.State("WR_PREPARE"):
                m.d.comb += [
                    self.axi_dma.wr_start.eq(0),
                    *self.sink.disconnect_from_sink(),
                    *self.axi_dma.sink.connect_to_null_source(),
                ]
                with m.If(self.wr_enable):
                    with m.If(
                        next_wr_addr_id != rd_addr_id
                    ):
                        m.d.sync += [
                            wr_addr_id.eq(next_wr_addr_id),
                            wr_addr_base_r.eq(buffer_address_array[next_wr_addr_id]),
                        ]
                    with m.Else():
                        m.d.sync += [
                            wr_addr_base_r.eq(buffer_address_array[wr_addr_id]),
                        ]
                    m.next = "WR_CONFIG"

            with m.State("WR_REPEAT"):
                m.d.comb += [
                    self.axi_dma.wr_start.eq(0),
                    *self.sink.disconnect_from_sink(),
                    *self.axi_dma.sink.connect_to_null_source(),
                ]
                with m.If(self.wr_enable):
                    m.d.sync += [
                        wr_addr_base_r.eq(buffer_address_array[wr_addr_id]),
                    ]
                    m.next = "WR_CONFIG"

            with m.State("WR_CONFIG"):
                m.d.comb += [
                    self.axi_dma.wr_start.eq(1),
                    *self.sink.disconnect_from_sink(),
                    *self.axi_dma.sink.connect_to_null_source(),
                ]
                with m.If(self.axi_dma.wr_ack):
                    m.d.sync += wr_beats_count.eq(self.wr_len_beats - 1)
                    m.next = "WR_IN_PROGRESS"

            with m.State("WR_IN_PROGRESS"):
                m.d.comb += [
                    self.axi_dma.wr_start.eq(0),
                ]
                wiring.connect(m, self.sink.as_master(), self.axi_dma.sink)
                with m.If(self.axi_dma.sink.accepted()):
                    with m.If(wr_beats_count > 0):
                        m.d.sync += wr_beats_count.eq(self.wr_len_beats - 1)
                        with m.If(self.axi_dma.sink.tlast):
                            # Go to WR_REPEAT. Don't change the buffer where next
                            # write takes place because the current one was incomplete.
                            m.next = "WR_REPEAT"
                    with m.Else():
                        with m.If(self.axi_dma.sink.tlast):
                            m.next = "WR_PREPARE"
                        with m.Else():
                            m.next = "WR_WAIT_LAST"

            with m.State("WR_WAIT_LAST"):
                # NOTE: the tlast is not sent to the axi_dma. It should handle it properly.
                m.d.comb += [
                    self.axi_dma.wr_start.eq(0),
                    *self.sink.connect_to_null_sink(),
                    *self.axi_dma.sink.connect_to_null_source(),
                ]
                with m.If(self.sink.accepted() & self.sink.tlast):
                    m.next = "WR_PREPARE"


        with m.FSM() as fsm_rd:

            with m.State("RESET"):
                m.d.comb += [
                    self.axi_dma.rd_start.eq(0),
                ]
                m.d.sync += [
                    rd_addr_id.eq(init_rd_addr_id),
                ]
                m.next = "RD_PREPARE"

            with m.State("RD_PREPARE"):
                m.d.comb += [
                    self.axi_dma.rd_start.eq(0),
                ]
                with m.If(self.rd_enable):
                    with m.If(
                        next_rd_addr_id != wr_addr_id
                    ):
                        m.d.sync += [
                            rd_addr_id.eq(next_rd_addr_id),
                            rd_addr_base_r.eq(buffer_address_array[next_rd_addr_id]),
                        ]
                    with m.Else():
                        m.d.sync += [
                            rd_addr_id.eq(rd_addr_id),
                            rd_addr_base_r.eq(buffer_address_array[rd_addr_id]),
                        ]
                    m.next = "RD_CONFIG"

            with m.State("RD_REPEAT"):
                m.d.comb += [
                    self.axi_dma.rd_start.eq(0),
                ]
                with m.If(self.rd_enable):
                    m.d.sync += [
                        rd_addr_base_r.eq(buffer_address_array[rd_addr_id]),
                    ]
                    m.next = "RD_CONFIG"

            with m.State("RD_CONFIG"):
                m.d.comb += [
                    self.axi_dma.rd_start.eq(1),
                ]
                with m.If(self.axi_dma.rd_ack):
                    m.d.sync += rd_beats_count.eq(self.rd_len_beats - 1)
                    m.next = "RD_IN_PROGRESS"

            with m.State("RD_IN_PROGRESS"):
                m.d.comb += [
                    self.axi_dma.rd_start.eq(0),
                ]
                wiring.connect(m, self.axi_dma.source, self.source.as_slave())
                with m.If(self.axi_dma.source.accepted()):
                    with m.If(self.axi_dma.source.tlast):
                        m.next = "RD_PREPARE"

        return m
