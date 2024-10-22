from amaranth import Elaboratable, Module, Signal, Cat, Const  # , ResetSignal

from hdl_utils.amaranth_utils.interfaces.axi4_stream import AXI4StreamSignature


class AXIStreamWidthConverterDown(Elaboratable):

    def __init__(
        self,
        data_w_i: int,
        data_w_o: int,
        user_w_i: int,
    ):
        assert data_w_i > 0
        assert data_w_o > 0
        assert user_w_i > 0
        assert data_w_o % 8 == 0
        assert data_w_i % data_w_o == 0
        assert (user_w_i * data_w_o) % data_w_i == 0
        user_w_o = (user_w_i * data_w_o) // data_w_i
        self.sink = AXI4StreamSignature.create_slave(
            data_w=data_w_i,
            user_w=user_w_i,
            path=['s_axi'],
        )
        self.source = AXI4StreamSignature.create_master(
            data_w=data_w_o,
            user_w=user_w_o,
            path=['m_axi'],
        )

    def get_ports(self):
        return self.sink.extract_signals() + self.source.extract_signals()

    def elaborate(self, platform):
        m = Module()

        data_w_i = len(self.sink.tdata)
        user_w_i = len(self.sink.tuser)
        keep_w_i = len(self.sink.tkeep)
        data_w_o = len(self.source.tdata)
        user_w_o = len(self.source.tuser)
        keep_w_o = len(self.source.tkeep)
        convertion_ratio = data_w_i // data_w_o

        buffer_tlast = Signal.like(self.sink.tlast)
        buffer_tdata = Signal.like(self.sink.tdata)
        buffer_tuser = Signal.like(self.sink.tuser)
        buffer_tkeep = Signal.like(self.sink.tkeep)
        beats_remaining = Signal(range(convertion_ratio))
        is_last_subchunk = Signal()
        # only_null_bytes_remaining: if only null bytes (bytes w/ tkeep = 0) are
        # remaining in the last chunk (chunk w/ tlast = 1), then is_last_chunk is
        # true to finish the conversion early and avoid introducing null bytes that
        # are not always properly handled by third-party ip.
        only_null_bytes_remaining = Signal()
        is_last_chunk = Signal()

        m.d.comb += [
            # assign is_last_subchunk = (counter_r == SCALING_FACTOR - 1) ? 1'b1 : 1'b0;
            is_last_subchunk.eq(beats_remaining == 0),
            # assign only_null_bytes_remaining = ~ (|(keep_buffer_r[DWI - 1 : DWO]));
            only_null_bytes_remaining.eq(
                ~ (buffer_tkeep[keep_w_o:]).any()
            ),
            # assign is_last_chunk = (is_last_subchunk | only_null_bytes_remaining) & last_buffer_r;
            is_last_chunk.eq(
                buffer_tlast & (is_last_subchunk | only_null_bytes_remaining)
            ),
        ]

        with m.FSM():
            with m.State("IDLE"):
                m.d.comb += [
                    self.sink.tready.eq(1),
                    self.source.tvalid.eq(0),
                    self.source.tlast.eq(0),
                    self.source.tdata.eq(0),
                    self.source.tuser.eq(0),
                    self.source.tkeep.eq(0),
                ]
                with m.If(self.sink.accepted()):
                    m.d.sync += [
                        buffer_tlast.eq(self.sink.tlast),
                        buffer_tdata.eq(self.sink.tdata),
                        buffer_tuser.eq(self.sink.tuser),
                        buffer_tkeep.eq(self.sink.tkeep),
                        beats_remaining.eq(convertion_ratio - 1),
                    ]
                    m.next = "CONVERTING"

            with m.State("CONVERTING"):
                m.d.comb += [
                    self.sink.tready.eq(self.source.accepted() &
                                        is_last_subchunk),
                    self.source.tvalid.eq(1),
                    self.source.tlast.eq(is_last_chunk),
                    self.source.tdata.eq(buffer_tdata[0:data_w_o]),
                    self.source.tuser.eq(buffer_tuser[0:user_w_o]),
                    self.source.tkeep.eq(buffer_tkeep[0:keep_w_o]),
                ]
                with m.If(self.source.accepted()):
                    with m.If(~is_last_subchunk & ~is_last_chunk):
                        m.d.sync += [
                            # shift register buffer_tdata
                            buffer_tdata.eq(Cat(
                                buffer_tdata[data_w_o:],
                                Const(0, shape=data_w_o))
                            ),
                            # shift register buffer_tuser
                            buffer_tuser.eq(Cat(
                                buffer_tuser[user_w_o:],
                                Const(0, shape=user_w_o))
                            ),
                            # shift register buffer_tkeep
                            buffer_tkeep.eq(Cat(
                                buffer_tkeep[keep_w_o:],
                                Const(0, shape=keep_w_o))
                            ),
                            # decrease beats remaining by 1
                            beats_remaining.eq(beats_remaining - 1)
                        ]
                    with m.Elif(self.sink.accepted()):
                        m.d.sync += [
                            buffer_tlast.eq(self.sink.tlast),
                            buffer_tdata.eq(self.sink.tdata),
                            buffer_tuser.eq(self.sink.tuser),
                            buffer_tkeep.eq(self.sink.tkeep),
                            beats_remaining.eq(convertion_ratio - 1),
                        ]
                    with m.Else():
                        m.d.sync += [
                            buffer_tlast.eq(0),
                            buffer_tdata.eq(0),
                            buffer_tuser.eq(0),
                            buffer_tkeep.eq(0),
                            beats_remaining.eq(0),
                        ]
                        m.next = "IDLE"

        return m


class AXIStreamWidthConverterUp(Elaboratable):

    def __init__(
        self,
        data_w_i: int,
        data_w_o: int,
        user_w_i: int,
    ):
        assert data_w_i > 0
        assert data_w_o > 0
        assert user_w_i > 0
        assert data_w_i % 8 == 0
        assert data_w_o % data_w_i == 0
        assert (user_w_i * data_w_o) % data_w_i == 0
        user_w_o = (user_w_i * data_w_o) // data_w_i
        self.sink = AXI4StreamSignature.create_slave(
            data_w=data_w_i,
            user_w=user_w_i,
            path=['s_axi'],
        )
        self.source = AXI4StreamSignature.create_master(
            data_w=data_w_o,
            user_w=user_w_o,
            path=['m_axi'],
        )

    def get_ports(self):
        return self.sink.extract_signals() + self.source.extract_signals()

    def elaborate(self, platform):
        m = Module()

        data_w_i = len(self.sink.tdata)
        user_w_i = len(self.sink.tuser)
        keep_w_i = len(self.sink.tkeep)
        data_w_o = len(self.source.tdata)
        user_w_o = len(self.source.tuser)
        keep_w_o = len(self.source.tkeep)
        convertion_ratio = data_w_o // data_w_i

        buffer_tlast = Signal.like(self.source.tlast)
        buffer_tdata = Signal.like(self.source.tdata)
        buffer_tuser = Signal.like(self.source.tuser)
        buffer_tkeep = Signal.like(self.source.tkeep)
        beats_remaining = Signal(range(convertion_ratio),
                                 init=convertion_ratio-1)
        is_last_subchunk = Signal()

        m.d.comb += [
            # assign is_last_subchunk = (counter_r == (SCALING_FACTOR - 1)) ? 1'b1 : 1'b0;
            is_last_subchunk.eq(beats_remaining == 0),
            #
            self.source.tdata.eq(buffer_tdata),
            self.source.tuser.eq(buffer_tuser),
            self.source.tkeep.eq(buffer_tkeep),
            self.source.tlast.eq(buffer_tlast),
        ]

        with m.FSM():
            with m.State("CONVERTING"):
                m.d.comb += [
                    self.sink.tready.eq(1),
                    self.source.tvalid.eq(0),
                ]
                with m.If(self.sink.accepted()):
                    # data_buffer_r <= {s_axi_tdata, data_buffer_r[DWO_BITS - 1:DWI_BITS]};
                    # user_buffer_r <= {s_axi_tuser, user_buffer_r[UWO-1:UWI]};
                    # keep_buffer_r <= {s_axi_tkeep, keep_buffer_r[DWO-1:DWI]};
                    # last_buffer_r <= s_axi_tlast;
                    # counter_r <= counter_r + 'd1;
                    # if (is_last_subchunk) begin
                    #     state_r <= ST_WAITING_FOR_SLAVE;
                    # end else if (s_axi_tlast) begin
                    #     state_r <= ST_PADDING;
                    # end
                    m.d.sync += [
                        buffer_tdata.eq(Cat(buffer_tdata[data_w_i:],
                                            self.sink.tdata)),
                        buffer_tuser.eq(Cat(buffer_tuser[user_w_i:],
                                            self.sink.tuser)),
                        buffer_tkeep.eq(Cat(buffer_tkeep[keep_w_i:],
                                            self.sink.tkeep)),
                        buffer_tlast.eq(self.sink.tlast),
                        beats_remaining.eq(beats_remaining - 1),
                    ]
                    with m.If(is_last_subchunk):
                        m.next = "WAITING_FOR_SLAVE"
                    with m.Elif(self.sink.tlast):
                        m.next = "PADDING"

            with m.State("PADDING"):
                m.d.comb += [
                    self.sink.tready.eq(0),
                    self.source.tvalid.eq(0),
                ]
                # data_buffer_r <= {{DWI_BITS{1'b0}}, data_buffer_r[DWO_BITS - 1:DWI_BITS]};
                # user_buffer_r <= {{UWI{1'b0}}, user_buffer_r[UWO-1:UWI]};
                # keep_buffer_r <= {{DWI{1'b0}}, keep_buffer_r[DWO-1:DWI]};
                # counter_r <= counter_r + 'd1;
                # if (is_last_subchunk) begin
                #     state_r <= ST_WAITING_FOR_SLAVE;
                # end
                m.d.sync += [
                    buffer_tdata.eq(Cat(buffer_tdata[data_w_i:],
                                        Const(0, shape=data_w_i))),
                    buffer_tuser.eq(Cat(buffer_tuser[user_w_i:],
                                        Const(0, shape=user_w_i))),
                    buffer_tkeep.eq(Cat(buffer_tkeep[keep_w_i:],
                                        Const(0, shape=keep_w_i))),
                    beats_remaining.eq(beats_remaining - 1),
                ]
                with m.If(is_last_subchunk):
                    m.next = "WAITING_FOR_SLAVE"

            with m.State("WAITING_FOR_SLAVE"):
                m.d.comb += [
                    self.sink.tready.eq(self.source.accepted()),
                    self.source.tvalid.eq(1),
                ]
                with m.If(self.source.accepted()):
                    with m.If(self.sink.accepted()):
                        m.d.sync += [
                            buffer_tdata.eq(Cat(
                                Const(0, shape=data_w_o-data_w_i),
                                self.sink.tdata
                            )),
                            buffer_tuser.eq(Cat(
                                Const(0, shape=user_w_o-user_w_i),
                                self.sink.tuser
                            )),
                            buffer_tkeep.eq(Cat(
                                Const(0, shape=keep_w_o-keep_w_i),
                                self.sink.tkeep
                            )),
                            buffer_tlast.eq(self.sink.tlast),
                            beats_remaining.eq(convertion_ratio - 1 - 1),
                        ]
                        if convertion_ratio == 1:
                            m.next = "WAITING_FOR_SLAVE"
                        else:
                            with m.If(self.sink.tlast):
                                m.next = "PADDING"
                            with m.Else():
                                m.next = "CONVERTING"
                    with m.Else():
                        m.d.sync += [
                            buffer_tdata.eq(0),
                            buffer_tuser.eq(0),
                            buffer_tkeep.eq(0),
                            buffer_tlast.eq(0),
                            beats_remaining.eq(convertion_ratio - 1),
                        ]
                        m.next = "CONVERTING"

        return m


def parse_args(sys_args=None):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-dwi', '--data-width-in', type=int, required=True,
                        help='Data width in bits')
    parser.add_argument('-dwo', '--data-width-out', type=int, required=True,
                        help='Data width out bits')
    parser.add_argument('-uwi', '--user-width-in', type=int, required=True,
                        help='User width in bits')
    parser.add_argument('-rstn', '--active-low-reset', action='store_true',
                        help='Use active low reset (default is active high)')
    parser.add_argument('-n', '--name', type=str,
                        default=None, help='Core name')
    parser.add_argument('--prefix', type=str,
                        default='', help='Module names prefix')

    return parser.parse_args(sys_args)


def main(sys_args=None):
    from hdl_utils.amaranth_utils.generate_verilog import generate_verilog
    args = parse_args(sys_args)
    if args.data_width_in > args.data_width_out:
        name = args.name or 'axi_stream_width_converter_down'
        core = AXIStreamWidthConverterDown(
            data_w_i=args.data_width_in,
            data_w_o=args.data_width_out,
            user_w_i=args.user_width_in,
        )
    elif args.data_width_in < args.data_width_out:
        name = args.name or 'axi_stream_width_converter_up'
        core = AXIStreamWidthConverterUp(
            data_w_i=args.data_width_in,
            data_w_o=args.data_width_out,
            user_w_i=args.user_width_in,
        )
    else:
        raise NotImplementedError()
        # name = args.name or 'axi_stream_width_converter_up'
        # core = AXIStreamWidthConverterPassThrough(
        #     data_w_i=args.data_width_in,
        #     data_w_o=args.data_width_out,
        #     user_w_i=args.user_width_in,
        # )

    if args.active_low_reset:
        from hdl_utils.amaranth_utils.rstn_wrapper import RstnWrapper
        core = RstnWrapper(core=core, domain=args.rd_domain)
    ports = core.get_ports()
    output = generate_verilog(
        core=core,
        name=name,
        ports=ports,
        prefix=args.prefix
    )
    print(output)


if __name__ == '__main__':
    main()
