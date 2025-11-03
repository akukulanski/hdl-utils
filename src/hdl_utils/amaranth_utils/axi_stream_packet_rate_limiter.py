import amaranth as am
from amaranth.lib import wiring

from hdl_utils.amaranth_utils.interfaces.axi4_stream import (
    AXI4StreamSignature,
)


class AXISPacketRateLimiter(am.Elaboratable):

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
        self.max_cycles_per_packet = am.Signal(32)

    def get_ports(self):
        return [
            *self.sink.extract_signals(),
            *self.source.extract_signals(),
            self.max_cycles_per_packet,
        ]

    def elaborate(self, platform):
        m = am.Module()

        cycles_counter = am.Signal(32, init=0)
        # Start of packet
        sop = am.Signal(init=1)

        # If SOP, only connect when the count reaches 0.
        # If not SOP, always connect until the end of packet
        with m.If(~sop | ~cycles_counter.any()):
            wiring.connect(m, self.sink.as_master(), self.source.as_slave())

        # After a tlast, it's a sop
        with m.If(self.sink.accepted()):
            m.d.sync += sop.eq(self.sink.tlast)

        # Reset count on accepted SOP
        # Decrease count on each clock cycle (saturate at 0)
        with m.If(self.sink.accepted() & sop):
            m.d.sync += cycles_counter.eq(am.Mux(self.max_cycles_per_packet > 0, self.max_cycles_per_packet - 1, 0))
        with m.Else():
            m.d.sync += cycles_counter.eq(am.Mux(cycles_counter > 0, cycles_counter - 1, cycles_counter))

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
                        default='axis_packet_rate_limiter', help='Core name')
    parser.add_argument('--prefix', type=str,
                        default='', help='Module names prefix')

    return parser.parse_args(sys_args)


def main(sys_args=None):
    from hdl_utils.amaranth_utils.generate_verilog import generate_verilog
    args = parse_args(sys_args)
    name = args.name
    core = AXISPacketRateLimiter(
        data_w=args.data_width,
        user_w=args.user_width,
        no_tkeep=True,
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
