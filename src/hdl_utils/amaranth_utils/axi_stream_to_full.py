from amaranth import Elaboratable, Module, Signal, Mux
import math

from hdl_utils.amaranth_utils.interfaces.axi4_stream import AXI4StreamSignature
from hdl_utils.amaranth_utils.interfaces.axi_full import (
    AXI4Signature,
    BURST_TYPE_INCR,
    CACHE_BUFFERABLE_MASK,
    CACHE_CACHEABLE_MASK,
)


class AxiStreamToFull(Elaboratable):
    def __init__(
        self,
        addr_w: int,
        data_w: int,
        user_w: int,
    ):
        # AXI Stream sink (memory write)
        self.s_axis = AXI4StreamSignature.create_slave(
            data_w=data_w,
            user_w=user_w,
            no_tkeep=True,
            path=['s_axis'],
        )
        # AXI Stream source (memory read)
        self.m_axis = AXI4StreamSignature.create_master(
            data_w=data_w,
            user_w=user_w,
            no_tkeep=True,
            path=['m_axis'],
        )
        # AXI master (Memory R/W)
        self.m_axi = AXI4Signature.create_master(
            data_w=data_w,
            addr_w=addr_w,
            user_w=0,
            id_w=0,
            path=['m_axi'],
        )
        # Ports
        self.wr_qos = Signal.like(self.m_axi.AWQOS)
        self.rd_qos = Signal.like(self.m_axi.ARQOS)
        self.wr_burst = Signal.like(self.m_axi.AWLEN)
        self.rd_burst = Signal.like(self.m_axi.ARLEN)
        self.wr_addr = Signal.like(self.m_axi.AWADDR)
        self.rd_addr = Signal.like(self.m_axi.ARADDR)
        self.wr_valid = Signal()  # In: start writing new burst
        self.wr_ready = Signal()  # Out: ready for writing new burst
        self.rd_valid = Signal()  # In: start reading new burst
        self.rd_ready = Signal()  # Out: ready for reading new burst
        self.wr_idle = Signal()  # Out: Idle, available for new burst
        self.rd_idle = Signal()  # Out: Idle, available for new burst

    def get_ports(self):
        return [
            *self.s_axis.extract_signals(),
            *self.m_axis.extract_signals(),
            *self.m_axi.extract_signals(),
            self.wr_valid, self.wr_ready, self.wr_idle,
            self.rd_valid, self.rd_ready, self.rd_idle,
            self.wr_addr,
            self.rd_addr,
            self.wr_burst,
            self.rd_burst,
            self.wr_qos,
            self.rd_qos,
        ]

    def elaborate(self, platform):
        m = Module()

        _w_width = len(self.m_axi.WDATA)
        _r_width = len(self.m_axi.RDATA)

        _awsize_const = math.ceil(math.log2(_w_width // 8))
        assert _awsize_const == int(_awsize_const)
        AWSIZE_CONST = int(_awsize_const)

        _arsize_const = math.ceil(math.log2(_r_width // 8))
        assert _arsize_const == int(_arsize_const)
        ARSIZE_CONST = int(_arsize_const)

        # as the number of beats of a full frame is multiple of the
        # highest burst size (256), fixed bursts at max size.
        AWLEN_CONST = 255
        ARLEN_CONST = 255
        supported_resolutions = [(1920, 1080), (1280, 720)]
        bits_per_pixel = 32
        for width, height in supported_resolutions:
            ff_wr_bursts = width*height*bits_per_pixel/_w_width / (AWLEN_CONST + 1)  # 32400
            ff_rd_bursts = width*height*bits_per_pixel/_r_width / (ARLEN_CONST + 1)  # 32400
            # Check the statement above is true
            assert (ff_wr_bursts % 1) == 0
            assert (ff_rd_bursts % 1) == 0

        # Assign fixed signals
        m.d.comb += [
            # M_AXI
            # self.m_axi.AWID.eq(0),
            self.m_axi.AWADDR.eq(self.wr_addr),
            self.m_axi.AWLEN.eq(self.wr_burst),
            self.m_axi.AWSIZE.eq(AWSIZE_CONST),
            self.m_axi.AWBURST.eq(BURST_TYPE_INCR),
            self.m_axi.AWLOCK.eq(0),
            self.m_axi.AWCACHE.eq(CACHE_BUFFERABLE_MASK | CACHE_CACHEABLE_MASK),
            self.m_axi.AWPROT.eq(0),
            self.m_axi.AWQOS.eq(self.wr_qos),
            self.m_axi.AWREGION.eq(0),
            # self.m_axi.AWUSER.eq(0),
            # self.m_axi.AWVALID.eq(...),
            # self.m_axi.WID.eq(0),
            # self.m_axi.WDATA.eq(...),
            # self.m_axi.WSTRB.eq(...),
            # self.m_axi.WLAST.eq(...),
            # self.m_axi.WUSER.eq(0),
            # self.m_axi.WVALID.eq(...),
            # self.m_axi.BREADY.eq(self.m_axi.BVALID),  # ignored, accept all transactions
            # self.m_axi.ARID.eq(0),
            self.m_axi.ARADDR.eq(self.rd_addr),
            self.m_axi.ARLEN.eq(self.rd_burst),
            self.m_axi.ARSIZE.eq(ARSIZE_CONST),
            self.m_axi.ARBURST.eq(BURST_TYPE_INCR),
            self.m_axi.ARLOCK.eq(0),
            self.m_axi.ARCACHE.eq(CACHE_BUFFERABLE_MASK | CACHE_CACHEABLE_MASK),
            self.m_axi.ARPROT.eq(0),
            self.m_axi.ARQOS.eq(self.rd_qos),
            self.m_axi.ARREGION.eq(0),
            # self.m_axi.ARUSER.eq(0),
            # self.m_axi.ARVALID.eq(...),
            # self.m_axi.RREADY.eq(...),

            # S_AXIS
            # self.s_axis.tready.eq(...),

            # M_AXIS
            # self.m_axis.tvalid.eq(...),
            # self.m_axis.tlast.eq(...),
            # self.m_axis.tdata.eq(...),
            # self.m_axis.tuser.eq(0),
            # self.m_axis.tkeep.eq(-1),
        ]

        # Burst counters logic
        wr_burst_r = Signal.like(self.m_axi.AWLEN)
        rd_burst_r = Signal.like(self.m_axi.ARLEN)
        wr_last_of_burst = Signal()
        rd_last_of_burst = Signal()
        m.d.comb += [
            wr_last_of_burst.eq(Mux((wr_burst_r == 0) & (self.m_axi.WVALID), 1, 0)),
            rd_last_of_burst.eq(Mux((rd_burst_r == 0) & (self.m_axis.tvalid), 1, 0)),
        ]

        with m.If(self.m_axi.w_accepted()):
            with m.If(wr_burst_r > 0):
                m.d.sync += wr_burst_r.eq(wr_burst_r - 1)

        with m.If(self.m_axi.r_accepted()):
            with m.If(rd_burst_r > 0):
                m.d.sync += rd_burst_r.eq(rd_burst_r - 1)

        # FSM Write Burst
        with m.FSM() as fsm_wr:

            with m.State("WR_WAITING_ADDR"):
                m.d.comb += [
                    self.m_axi.WDATA.eq(0),
                    self.m_axi.WSTRB.eq(0),
                    self.m_axi.WVALID.eq(0),
                    self.m_axi.WLAST.eq(0),
                    self.s_axis.tready.eq(0),
                    self.m_axi.AWVALID.eq(self.wr_valid),
                    self.m_axi.BREADY.eq(0),
                    self.wr_ready.eq(self.m_axi.AWREADY),
                    self.wr_idle.eq(1),
                ]
                with m.If(self.m_axi.aw_accepted()):
                    m.next = "WR_DATA"
                    m.d.sync += [
                        wr_burst_r.eq(self.m_axi.AWLEN),
                    ]

            with m.State("WR_DATA"):
                m.d.comb += [
                    self.m_axi.WDATA.eq(self.s_axis.tdata),
                    self.m_axi.WSTRB.eq(-1),  # All ones!
                    self.m_axi.WVALID.eq(self.s_axis.tvalid),
                    self.m_axi.WLAST.eq(self.m_axi.WVALID & wr_last_of_burst),
                    self.s_axis.tready.eq(self.m_axi.WREADY),
                    self.m_axi.AWVALID.eq(0),
                    self.m_axi.BREADY.eq(0),
                    self.wr_ready.eq(0),
                    self.wr_idle.eq(0),
                ]
                with m.If(self.m_axi.w_accepted() & wr_last_of_burst):
                    m.next = "WR_WAIT_WRITE_RESPONSE"
                with m.Elif(self.m_axi.w_accepted() & self.s_axis.tlast):
                    m.next = "WR_DUMMY_CYCLES"

            with m.State("WR_DUMMY_CYCLES"):
                m.d.comb += [
                    self.m_axi.WDATA.eq(0),
                    self.m_axi.WSTRB.eq(0),  # Zero, don't write. Only completing burst transaction.
                    self.m_axi.WVALID.eq(1),
                    self.m_axi.WLAST.eq(self.m_axi.WVALID & wr_last_of_burst),
                    self.s_axis.tready.eq(0),
                    self.m_axi.AWVALID.eq(0),
                    self.m_axi.BREADY.eq(0),
                    self.wr_ready.eq(0),
                    self.wr_idle.eq(0),
                ]
                with m.If(self.m_axi.w_accepted() & wr_last_of_burst):
                    m.next = "WR_WAIT_WRITE_RESPONSE"

            with m.State("WR_WAIT_WRITE_RESPONSE"):
                m.d.comb += [
                    self.m_axi.WDATA.eq(0),
                    self.m_axi.WSTRB.eq(0),
                    self.m_axi.WVALID.eq(0),
                    self.m_axi.WLAST.eq(0),
                    self.s_axis.tready.eq(0),
                    self.m_axi.AWVALID.eq(0),
                    self.m_axi.BREADY.eq(1),
                    self.wr_ready.eq(0),
                    self.wr_idle.eq(0),
                ]
                with m.If(self.m_axi.b_accepted()):
                    m.next = "WR_WAITING_ADDR"

        # FSM Read Burst
        with m.FSM() as fsm_rd:

            with m.State("RD_WAITING_ADDR"):
                m.d.comb += [
                    self.m_axi.ARVALID.eq(self.rd_valid),
                    self.rd_ready.eq(self.m_axi.ARREADY),
                    self.m_axi.RREADY.eq(0),
                    self.m_axis.tvalid.eq(0),
                    self.m_axis.tlast.eq(0),
                    self.m_axis.tdata.eq(0),
                ]
                with m.If(self.m_axi.ar_accepted()):
                    m.next = "RD_DATA"
                    m.d.sync += [
                        rd_burst_r.eq(self.m_axi.ARLEN),
                    ]

            with m.State("RD_DATA"):
                m.d.comb += [
                    self.m_axi.ARVALID.eq(0),
                    self.rd_ready.eq(0),
                    self.m_axi.RREADY.eq(self.m_axis.tready),
                    self.m_axis.tvalid.eq(self.m_axi.RVALID),
                    self.m_axis.tlast.eq(self.m_axi.RLAST),
                    self.m_axis.tdata.eq(self.m_axi.RDATA),
                ]
                with m.If(self.m_axi.r_accepted() & self.m_axi.RLAST):
                    m.next = "RD_WAITING_ADDR"

        return m


def main(sys_args=None):
    raise NotImplementedError()


if __name__ == '__main__':
    main()
