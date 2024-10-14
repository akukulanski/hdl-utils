from amaranth import Elaboratable, Module, ResetSignal
from amaranth.lib.fifo import SyncFIFOBuffered, AsyncFIFO

from hdl_utils.amaranth_utils.interfaces.axi4_stream import AXI4StreamSignature


class AXIStreamFIFO(Elaboratable):

    def __init__(
        self,
        data_w: int,
        user_w: int,
        depth: int,
        fifo_cls: Elaboratable = SyncFIFOBuffered,
        *args,
        **kwargs
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
        self.fifo = fifo_cls(width=total_width, depth=depth, *args, **kwargs)

    def get_ports(self):
        return self.sink.extract_signals() + self.source.extract_signals()

    def elaborate(self, platform):
        m = Module()

        w_domain = self.fifo._w_domain if hasattr(self.fifo, '_w_domain') else 'sync'
        # Fifo Instance
        m.submodules.fifo_core = fifo = self.fifo
        # Sink
        m.d.comb += fifo.w_data.eq(self.sink.flatten())
        m.d.comb += fifo.w_en.eq(self.sink.accepted())
        m.d.comb += self.sink.tready.eq(fifo.w_rdy & ~ResetSignal(w_domain))
        # Source
        m.d.comb += self.source.tvalid.eq(fifo.r_rdy)
        m.d.comb += fifo.r_en.eq(self.source.accepted())
        m.d.comb += self.source.assign_from_flat(fifo.r_data)
        # Return module
        return m

    @classmethod
    def CreateCDC(
        cls,
        *args,
        r_domain,
        w_domain,
        fifo_cls: Elaboratable = AsyncFIFO,
        **kwargs
    ):
        return cls(
            *args,
            fifo_cls=fifo_cls,
            r_domain=r_domain,
            w_domain=w_domain,
            **kwargs
        )


def parse_args(sys_args=None):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-dw', '--data-width', type=int, required=True,
                        help='Data width in bits')
    parser.add_argument('-uw', '--user-width', type=int, required=True,
                        help='User width in bits')
    parser.add_argument('-d', '--fifo-depth', type=int, required=True,
                        help='FIFO depth')
    parser.add_argument('--cdc', action='store_true',
                        help='Fifo with Clock Domain Crossing')
    parser.add_argument('-rstn', '--active-low-reset', action='store_true',
                        help='Use active low reset (default is active high)')
    parser.add_argument('--rd-domain', type=str,
                        default='m_axis', help='Read clock domain name')
    parser.add_argument('--wr-domain', type=str,
                        default='s_axis', help='Write clock domain name')
    parser.add_argument('-n', '--name', type=str,
                        default=None, help='Core name')
    parser.add_argument('--prefix', type=str,
                        default='', help='Module names prefix')

    return parser.parse_args(sys_args)


def main(sys_args=None):
    from hdl_utils.amaranth_utils.generate_verilog import generate_verilog
    args = parse_args(sys_args)
    if args.cdc:
        name = args.name or 'axi_stream_fifo_cdc'
        core = AXIStreamFIFO.CreateCDC(
            data_w=args.data_width,
            user_w=args.user_width,
            depth=args.fifo_depth,
            r_domain=args.rd_domain,
            w_domain=args.wr_domain,
        )
        if args.active_low_reset:
            from hdl_utils.amaranth_utils.rstn_wrapper import RstnWrapper
            core = RstnWrapper(core=core, domain=args.rd_domain)
            core = RstnWrapper(core=core, domain=args.wr_domain)
    else:
        name = args.name or 'axi_stream_fifo'
        core = AXIStreamFIFO(
            data_w=args.data_width,
            user_w=args.user_width,
            depth=args.fifo_depth,
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
