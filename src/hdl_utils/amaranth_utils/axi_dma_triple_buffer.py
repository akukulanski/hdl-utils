from amaranth import Elaboratable, Module, DomainRenamer, Signal, Mux, Array
from amaranth.lib import wiring

from hdl_utils.amaranth_utils.interfaces.axi4_stream import AXI4StreamSignature
from hdl_utils.amaranth_utils.axi_dma import AxiDma


def at_least_one(signal: Signal):
    return Mux(signal == 0, 1, signal)


class AXIDmaTripleBuffer(Elaboratable):
    def __init__(
        self,
        addr_w: int = 40,
        data_w: int = 128,
        user_w: int = 0,
        burst_len: int = 256,
        ignore_rd_size_signal: bool = False,
        init_rd_size: int = None,
    ):
        self.addr_w = addr_w
        self.data_w = data_w
        self.user_w = user_w
        self.burst_len = burst_len
        self.ignore_rd_size_signal = ignore_rd_size_signal
        self.init_rd_size = init_rd_size or burst_len

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

        init_last_wr_buff_id = 0
        init_wr_buff_id = 1
        wr_buff_id = Signal(2, init=init_wr_buff_id)
        rd_buff_id = Signal(2, init=init_last_wr_buff_id)
        last_wr_buff_id = Signal.like(2, init=init_last_wr_buff_id)
        next_wr_buff_id = Signal.like(wr_buff_id)

        wr_beats_remaining = Signal(32)
        wr_early_tlast = Signal()
        wr_missing_tlast = Signal()
        wr_last_ok = Signal()

        last_wr_beat_count = Signal(32, init=self.init_rd_size)
        wr_beats_counter = Signal(32)
        rd_len_beats_to_dma = Signal(32, init=self.init_rd_size)

        if not self.ignore_rd_size_signal:
            m.d.comb += rd_len_beats_to_dma.eq(at_least_one(self.rd_len_beats))

        m.d.comb += [
            next_wr_buff_id.eq(
                Mux(
                    ((wr_buff_id + 1) % n_buffers) != rd_buff_id,
                    (wr_buff_id + 1) % n_buffers,
                    (wr_buff_id + 2) % n_buffers,
                )
            ),
            self.axi_dma.wr_addr.eq(buffer_address_array[wr_buff_id]),
            self.axi_dma.rd_addr.eq(buffer_address_array[rd_buff_id]),
            self.axi_dma.wr_qos.eq(self.wr_qos),
            self.axi_dma.rd_qos.eq(self.rd_qos),
            self.axi_dma.wr_len_beats.eq(self.wr_len_beats),
            self.axi_dma.rd_len_beats.eq(rd_len_beats_to_dma),
        ]

        m.d.comb += [
            wr_early_tlast.eq(self.sink.accepted() & self.sink.tlast & (wr_beats_remaining != 0)),
            wr_missing_tlast.eq(self.sink.accepted() & (~self.sink.tlast) & (wr_beats_remaining == 0)),
            wr_last_ok.eq(self.sink.accepted() & self.sink.tlast & (wr_beats_remaining == 0)),
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

        def discard_sink_until_tlast() -> list:
            return [
                self.sink.connect_to_null_sink(),
                *self.axi_dma.sink.connect_to_null_source(),
            ]

        def connect_sink_to_dma_wr() -> list:
            return [
                self.axi_dma.sink.tvalid.eq(self.sink.tvalid),
                self.axi_dma.sink.tdata.eq(self.sink.tdata),
                self.axi_dma.sink.tlast.eq(self.sink.tlast | (wr_beats_remaining == 0)),
                self.sink.tready.eq(self.axi_dma.sink.tready),
            ]

        go_to_next_wr_buffer = Signal()
        go_to_next_rd_buffer = Signal()

        next_wr_beats_counter = Signal.like(wr_beats_counter)
        m.d.comb += next_wr_beats_counter.eq(
            Mux(self.axi_dma.sink.accepted(), wr_beats_counter + 1, wr_beats_counter)
        )

        def assign_next_wr_buffer() -> list:
            return [
                last_wr_buff_id.eq(wr_buff_id),
                last_wr_beat_count.eq(next_wr_beats_counter),
                wr_buff_id.eq(next_wr_buff_id),
            ]

        def assign_next_rd_buffer() -> list:
            ret = [
                rd_buff_id.eq(last_wr_buff_id),
            ]
            if self.ignore_rd_size_signal:
                ret += [
                    rd_len_beats_to_dma.eq(at_least_one(last_wr_beat_count)),
            ]
            return ret

        def assign_next_wr_buffer_and_next_rd_buffer() -> list:
            ret = [
                last_wr_buff_id.eq(wr_buff_id),
                last_wr_beat_count.eq(next_wr_beats_counter),
                wr_buff_id.eq(rd_buff_id),
                rd_buff_id.eq(wr_buff_id),
            ]
            if self.ignore_rd_size_signal:
                ret += [
                    rd_len_beats_to_dma.eq(at_least_one(next_wr_beats_counter)),
                ]
            return ret

        with m.If(go_to_next_wr_buffer & ~go_to_next_rd_buffer):
            m.d.sync += assign_next_wr_buffer()
        with m.Elif((~go_to_next_wr_buffer) & go_to_next_rd_buffer):
            m.d.sync += assign_next_rd_buffer()
        with m.Elif(go_to_next_wr_buffer & go_to_next_rd_buffer):
            m.d.sync += assign_next_wr_buffer_and_next_rd_buffer()

        with m.FSM() as fsm_wr:

            with m.State("WR_RESET"):
                m.d.comb += set_dma_wr_busy()
                m.d.comb += disconnect_sink()
                m.d.comb += go_to_next_wr_buffer.eq(0)
                m.d.sync += last_wr_buff_id.eq(init_last_wr_buff_id)
                m.d.sync += last_wr_beat_count.eq(self.init_rd_size),
                m.d.sync += wr_buff_id.eq(init_wr_buff_id)
                m.next = "WR_CONFIG"

            with m.State("WR_CONFIG"):
                m.d.comb += self.axi_dma.wr_start.eq(self.wr_enable)
                m.d.comb += disconnect_sink()
                m.d.comb += go_to_next_wr_buffer.eq(0)
                with m.If(self.axi_dma.wr_start & self.axi_dma.wr_ack):
                    m.d.sync += wr_beats_remaining.eq(self.wr_len_beats - 1)
                    m.d.sync += wr_beats_counter.eq(0)
                    m.next = "WR_RUNNING"

            with m.State("WR_RUNNING"):
                m.d.comb += set_dma_wr_busy()
                m.d.comb += connect_sink_to_dma_wr()
                m.d.comb += go_to_next_wr_buffer.eq(
                    (wr_early_tlast & ~self.wr_dont_change_buffer_if_incomplete)
                    | (wr_last_ok)
                )

                with m.If(self.sink.accepted()):
                    m.d.sync += wr_beats_counter.eq(next_wr_beats_counter)

                with m.If(self.sink.accepted() & (wr_beats_remaining > 0)):
                    m.d.sync += wr_beats_remaining.eq(wr_beats_remaining - 1)

                with m.If(wr_early_tlast | wr_last_ok):
                    m.next = "WR_CONFIG"
                with m.Elif(wr_missing_tlast):
                    m.next = "WR_WAIT_LAST"

            with m.State("WR_WAIT_LAST"):
                m.d.comb += set_dma_wr_busy()
                m.d.comb += discard_sink_until_tlast()
                m.d.comb += go_to_next_wr_buffer.eq(self.sink.accepted() & self.sink.tlast)
                with m.If(self.sink.accepted() & self.sink.tlast):
                    m.next = "WR_CONFIG"

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

            with m.State("RD_RESET"):
                m.d.comb += set_dma_rd_busy()
                m.d.comb += disconnect_source()
                m.d.comb += go_to_next_rd_buffer.eq(0)
                m.d.sync += rd_buff_id.eq(init_last_wr_buff_id)
                if self.ignore_rd_size_signal:
                    m.d.sync += rd_len_beats_to_dma.eq(self.init_rd_size)
                m.next = "RD_CONFIG"

            with m.State("RD_CONFIG"):
                m.d.comb += self.axi_dma.rd_start.eq(self.rd_enable)
                m.d.comb += disconnect_source()
                m.d.comb += go_to_next_rd_buffer.eq(0)
                with m.If(self.axi_dma.rd_start & self.axi_dma.rd_ack):
                    m.next = "RD_IN_PROGRESS"

            with m.State("RD_IN_PROGRESS"):
                m.d.comb += set_dma_rd_busy()
                wiring.connect(m, self.axi_dma.source, self.source.as_slave())
                m.d.comb += go_to_next_rd_buffer.eq(self.axi_dma.source.accepted() & self.axi_dma.source.tlast)
                with m.If(self.axi_dma.source.accepted()):
                    with m.If(self.axi_dma.source.tlast):
                        m.next = "RD_CONFIG"

        return m
