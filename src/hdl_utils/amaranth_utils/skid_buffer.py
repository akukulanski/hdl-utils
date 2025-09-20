from amaranth import Elaboratable, Module, ResetSignal, Signal
from amaranth.lib import wiring

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
        no_tkeep: bool = False,
    ):
        self.sink = AXI4StreamSignature.create_slave(
            data_w=data_w,
            user_w=user_w,
            no_tkeep=no_tkeep,
            path=['s_axis'],
        )
        self.source = AXI4StreamSignature.create_master(
            data_w=data_w,
            user_w=user_w,
            no_tkeep=no_tkeep,
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

    @classmethod
    def wrap_core(
        cls,
        core: Elaboratable,
        add_input_buffer: bool = True,
        add_output_buffer: bool = True,
        core_sink: Signal = None,
        core_source: Signal = None,
    ) -> Elaboratable:
        return AXISkidBufferWrapper(
            core=core,
            add_input_buffer=add_input_buffer,
            add_output_buffer=add_output_buffer,
            core_sink=core_sink,
            core_source=core_source,
        )


def object_in_list(obj, l: list) -> bool:
    """Same as x in list but for signals or other objects that override the "==" where
    native "in" doesn't work.

    Example of what does NOT work natively:
        a, b, c = [Signal() for _ in range(3)]
        my_list = [a, b]
        assert a in my_list
        assert b in my_list
        assert c not in my_list

    Example of what works:
        a, b, c = [Signal() for _ in range(3)]
        my_list = [a, b]
        assert object_in_list(a, my_list)
        assert object_in_list(b, my_list)
        assert not object_in_list(c, my_list)
    """
    return any([obj is y for y in l])



class AXISkidBufferWrapper(Elaboratable):
    def __init__(
        self,
        core: Elaboratable,
        add_input_buffer: bool = True,
        add_output_buffer: bool = True,
        core_sink: Signal = None,
        core_source: Signal = None,
    ):
        assert core_sink is not None or not add_input_buffer, (
            'add_input_buffer is True, but no sink interface was specified'
        )
        assert core_source is not None or not add_output_buffer, (
            'add_output_buffer is True, but no source interface was specified'
        )
        self.wrapped_core = core
        self.add_input_buffer = add_input_buffer
        self.add_output_buffer = add_output_buffer
        self.core_sink = core_sink
        self.core_source = core_source

        if core_sink:
            data_w = len(self.core_sink.tdata)
            user_w = len(self.core_sink.tuser) if hasattr(self.core_sink, 'tuser') else 0
            no_tkeep = not hasattr(self.core_sink, 'tkeep')
            self.skid_buffer_in = AXISkidBuffer(
                data_w=data_w,
                user_w=user_w,
                no_tkeep=no_tkeep,
            ) if add_input_buffer else None
            self.sink = self.skid_buffer_in.sink if add_input_buffer else core_sink

        if core_source:
            data_w = len(self.core_source.tdata)
            user_w = len(self.core_source.tuser) if hasattr(self.core_source, 'tuser') else 0
            no_tkeep = not hasattr(self.core_source, 'tkeep')
            self.skid_buffer_out = AXISkidBuffer(
                data_w=data_w,
                user_w=user_w,
                no_tkeep=no_tkeep,
            ) if add_output_buffer else None
            self.source = self.skid_buffer_out.source if add_output_buffer else core_source

    def get_ports(self) -> list:
        ports = []
        ignore_ports = []

        if self.core_sink:
            ignore_ports += self.core_sink.extract_signals()
            ports += self.sink.extract_signals()

        if self.core_source:
            ignore_ports += self.core_source.extract_signals()
            ports += self.source.extract_signals()

        ports += [
            p for p in self.wrapped_core.get_ports()
            if not object_in_list(p, ignore_ports)
        ]
        return ports

    def elaborate(self, platform):
        m = Module()
        m.submodules.wrapped_core = self.wrapped_core

        if self.skid_buffer_in is not None:
            m.submodules.skid_buffer_in = self.skid_buffer_in
            wiring.connect(m, self.skid_buffer_in.source, self.core_sink)

        if self.skid_buffer_out is not None:
            m.submodules.skid_buffer_out = self.skid_buffer_out
            wiring.connect(m, self.core_source, self.skid_buffer_out.sink)

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
