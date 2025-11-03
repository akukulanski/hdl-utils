from amaranth import Elaboratable, Module, Signal, Cat, Const, ResetSignal, Record

from hdl_utils.amaranth_utils.interfaces.axi4_stream import AXI4StreamSignature


class AXIStreamWidthConverterDown(Elaboratable):

    def __init__(
        self,
        data_w_i: int,
        data_w_o: int,
        user_w_i: int,
        no_tkeep = False,
    ):
        assert data_w_i > 0
        assert data_w_o > 0
        assert user_w_i >= 0
        # assert data_w_o % 8 == 0
        assert data_w_i % data_w_o == 0
        assert (user_w_i * data_w_o) % data_w_i == 0
        user_w_o = (user_w_i * data_w_o) // data_w_i
        self.sink = AXI4StreamSignature.create_slave(
            data_w=data_w_i,
            user_w=user_w_i,
            no_tkeep=no_tkeep,
            path=['s_axis'],
        )
        self.source = AXI4StreamSignature.create_master(
            data_w=data_w_o,
            user_w=user_w_o,
            no_tkeep=no_tkeep,
            path=['m_axis'],
        )

        self.has_tkeep = not no_tkeep
        self.has_tuser = user_w_i > 0

    def get_ports(self):
        return self.sink.extract_signals() + self.source.extract_signals()

    def elaborate(self, platform):
        m = Module()

        data_w_i = len(self.sink.tdata)
        data_w_o = len(self.source.tdata)
        convertion_ratio = data_w_i // data_w_o

        buffer = Record([
            (name, member.shape) for name, member in self.sink.signature.members.items() if name not in ['tvalid', 'tready']
        ])

        beats_remaining  = Signal(range(convertion_ratio))
        is_last_subchunk = Signal()
        # only_null_bytes_remaining: if only null bytes (bytes w/ tkeep = 0) are
        # remaining in the last chunk (chunk w/ tlast = 1), then is_last_chunk is
        # true to finish the conversion early and avoid introducing null bytes that
        # are not always properly handled by third-party ip.
        if self.has_tkeep:
            only_null_bytes_remaining = Signal()
            m.d.comb += only_null_bytes_remaining.eq(~(buffer.tkeep[len(self.source.tkeep):]).any())
        else:
            only_null_bytes_remaining = Const(0, 1)

        is_last_chunk = Signal()

        m.d.comb += [
            is_last_subchunk        .eq(~beats_remaining.any() | only_null_bytes_remaining),
            is_last_chunk           .eq(buffer.tlast & is_last_subchunk),
            self.sink.tready        .eq(~self.source.tvalid | (self.source.tready & is_last_subchunk)),
            *[self.source[key]      .eq(buffer[key]) for key in buffer.fields if key != 'tlast'],
            self.source.tlast       .eq(is_last_chunk),
        ]

        with m.If(self.source.accepted()):
            m.d.sync += [
                *[buffer[key]       .eq(buffer[key][len(self.source[key]):]) for key in buffer.fields if key != 'tlast'],
                beats_remaining     .eq(beats_remaining - 1),
                self.source.tvalid  .eq(~is_last_subchunk),
            ]

        with m.If(self.sink.accepted()):
            m.d.sync += [
                *[buffer[key]       .eq(self.sink[key]) for key in buffer.fields],
                beats_remaining     .eq(convertion_ratio - 1),
                self.source.tvalid  .eq(1),
            ]

        return m

class AXIStreamWidthConverterUp(Elaboratable):

    def __init__(
        self,
        data_w_i: int,
        data_w_o: int,
        user_w_i: int,
        no_tkeep = False,
    ):
        assert data_w_i > 0
        assert data_w_o > 0
        assert user_w_i >= 0
        # assert data_w_i % 8 == 0
        assert data_w_o % data_w_i == 0
        assert (user_w_i * data_w_o) % data_w_i == 0
        user_w_o = (user_w_i * data_w_o) // data_w_i
        self.sink = AXI4StreamSignature.create_slave(
            data_w=data_w_i,
            user_w=user_w_i,
            no_tkeep=no_tkeep,
            path=['s_axis'],
        )
        self.source = AXI4StreamSignature.create_master(
            data_w=data_w_o,
            user_w=user_w_o,
            no_tkeep=no_tkeep,
            path=['m_axis'],
        )

        self.has_tkeep = not no_tkeep
        self.has_tuser = user_w_i > 0

    def get_ports(self):
        return self.sink.extract_signals() + self.source.extract_signals()

    def elaborate(self, platform):
        m = Module()

        data_w_i = len(self.sink.tdata)
        data_w_o = len(self.source.tdata)
        convertion_ratio = data_w_o // data_w_i

        buffer = Record([
            (name, member.shape) for name, member in self.source.signature.members.items() if name not in ['tvalid', 'tready']
        ])

        beats_remaining     = Signal(range(convertion_ratio), init=convertion_ratio-1)
        is_last_subchunk    = Signal()
        padding             = Signal()
        ready               = Signal()

        m.d.comb += [
            is_last_subchunk    .eq(~beats_remaining.any()),
            *[self.source[key]  .eq(buffer[key]) for key in buffer.fields],
            ready               .eq(~self.source.tvalid | self.source.tready),
            self.sink.tready    .eq(~padding & ready),
        ]
        with m.If(self.source.tready):
            m.d.sync += self.source.tvalid.eq(0)

        with m.If(ready & (self.sink.tvalid | padding)):
            with m.If(padding):
                m.d.sync += [buffer[key].eq(buffer[key][len(self.sink[key]):]) for key in buffer.fields if key != 'tlast']
            with m.Else():
                m.d.sync += [
                    *[buffer[key]       .eq(Cat(buffer[key][len(self.sink[key]):], self.sink[key])) for key in buffer.fields if key != 'tlast'],
                    buffer.tlast        .eq(self.sink.tlast),
                    padding             .eq(self.sink.tlast),
                ]

            with m.If(is_last_subchunk):
                m.d.sync += [
                    beats_remaining     .eq(convertion_ratio - 1),
                    padding             .eq(0),
                    self.source.tvalid  .eq(1),
                ]
            with m.Else():
                m.d.sync += beats_remaining.eq(beats_remaining - 1)

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
