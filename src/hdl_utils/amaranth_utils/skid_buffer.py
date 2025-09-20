from amaranth import Elaboratable, Module, ResetSignal, Signal

from hdl_utils.amaranth_utils.interfaces.axi4_stream import AXI4StreamSignature


class SkidBuffer(Elaboratable):

    def __init__(
        self,
        width: int,
    ):
        self.sink_valid = Signal()
        self.sink_ready = Signal()
        self.sink_data = Signal(width)
        self.source_valid = Signal()
        self.source_ready = Signal()
        self.source_data = Signal(width)

    def elaborate(self, platform):

        OPT_LOWPOWER = 0
        OPT_OUTREG = 1

        sink_valid = self.sink_valid
        sink_ready = self.sink_ready
        sink_data = self.sink_data
        source_valid = self.source_valid
        source_ready = self.source_ready
        source_data = self.source_data

        m = Module()

        r_valid = Signal()
        r_data = Signal.like(sink_data)

        w_data = Signal.like(r_data)

        # r_valid
        with m.If((sink_valid & sink_ready) & (source_valid & ~source_ready)):
            # We have incoming data, but the output is stalled
            m.d.sync += r_valid.eq(1)
        with m.Elif(source_ready):
            m.d.sync += r_valid.eq(0)

        # r_data
        with m.If(OPT_LOWPOWER & (~source_valid | source_ready)):
            m.d.sync += r_data.eq(0)
        with m.Elif((int(not OPT_OUTREG) | sink_valid) & sink_ready):
            m.d.sync += r_data.eq(sink_data)

        m.d.comb += w_data.eq(r_data)

        # sink_ready
        m.d.comb += sink_ready.eq(~r_valid)

        i_reset = ResetSignal()
        # And then move on to the output port
        if not OPT_OUTREG:
            # Outputs are combinatorially determined from inputs
            # source_valid
            m.d.comb += source_valid.eq(~i_reset & (sink_valid | r_valid))

            # source_data
            with m.If(r_valid):
                m.d.comb += source_data.eq(r_data)
            with m.Elif(int(not OPT_LOWPOWER) | sink_valid):
                m.d.comb += source_data.eq(sink_data)
            with m.Else():
                m.d.comb += source_data.eq(0)
        else:
            # Register our outputs
            # source_valid
            # reg	rsource_valid;
            rsource_valid = Signal()

            with m.If(~source_valid | source_ready):
                m.d.sync += rsource_valid.eq(sink_valid | r_valid)

            m.d.comb += source_valid.eq(rsource_valid)

            # source_data
            with m.If(~source_valid | source_ready):
                with m.If(r_valid):
                    m.d.sync += source_data.eq(r_data)
                with m.Elif(int (not OPT_LOWPOWER) | sink_valid):
                    m.d.sync += source_data.eq(sink_data)
                with m.Else():
                     m.d.sync += source_data.eq(0)

        return m


class AXISkidBuffer(Elaboratable):

    def __init__(
        self,
        data_w: int,
        user_w: int,
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
        self.skid_buffer = SkidBuffer(width=total_width)

    def get_ports(self):
        return self.sink.extract_signals() + self.source.extract_signals()

    def elaborate(self, platform):
        m = Module()
        m.submodules.skid_buffer = skid_buffer = self.skid_buffer
        m.d.comb += skid_buffer.sink_valid.eq(self.sink.tvalid)
        m.d.comb += skid_buffer.sink_data.eq(self.sink.flatten())
        m.d.comb += self.sink.tready.eq(skid_buffer.sink_ready)
        m.d.comb += self.source.tvalid.eq(skid_buffer.source_valid)
        m.d.comb += self.source.assign_from_flat(skid_buffer.source_data)
        m.d.comb += skid_buffer.source_ready.eq(self.source.tready)
        return m


def parse_args(sys_args=None):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-dw', '--data-width', type=int, required=True,
                        help='Data width in bits')
    parser.add_argument('-uw', '--user-width', type=int, required=True,
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
    name = args.name or 'axi_skid_buffer'
    core = AXISkidBuffer(
        data_w=args.data_width,
        user_w=args.user_width,
    )
    if args.active_low_reset:
        from hdl_utils.amaranth_utils.rstn_wrapper import RstnWrapper
        core = RstnWrapper(core=core, domain="sync")
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
