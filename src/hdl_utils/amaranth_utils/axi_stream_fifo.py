from amaranth import Elaboratable, Module, ResetSignal
from amaranth.lib.fifo import SyncFIFOBuffered, AsyncFIFO
from amaranth.lib import wiring
import math

from hdl_utils.amaranth_utils.interfaces.axi4_stream import AXI4StreamSignature
from hdl_utils.amaranth_utils.skid_buffer import AXISkidBuffer


class AXIStreamFIFO(Elaboratable):

    def __init__(
        self,
        data_w: int,
        user_w: int,
        depth: int,
        fifo_cls: Elaboratable = SyncFIFOBuffered,
        no_tkeep: bool = False,
        *args,
        **kwargs
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


class FastClkAXIStreamFIFO(Elaboratable):
    """Split AXI Stream FIFO into multiple FIFOs,
    and include Skid Buffers at the start, at the end, and between each FIFO.
    """

    def __init__(self, data_w: int, user_w: int, depth: int, max_fifo_depth: int = 4096):
        self.data_w = data_w
        self.user_w = user_w
        self.depth = depth
        self.max_fifo_depth = max_fifo_depth
        self.fifos = []
        remaining_depth = depth
        while remaining_depth > 0:
            this_fifo_depth = min(remaining_depth, max_fifo_depth)
            self.fifos.append(AXIStreamFIFO(data_w=data_w, user_w=user_w, depth=this_fifo_depth))
            remaining_depth -= this_fifo_depth
        assert len(self.fifos) == int(math.ceil(depth / max_fifo_depth)), f'{len(self.fifos)} == {int(math.ceil(depth / max_fifo_depth))}'
        assert all([f.fifo.depth == max_fifo_depth for f in self.fifos[:-1]])
        assert sum([f.fifo.depth for f in self.fifos]) == depth
        self.skid_buffers = [
            AXISkidBuffer(data_w=data_w, user_w=user_w)
            for _ in range(len(self.fifos) + 1)
        ]
        self.sink = AXI4StreamSignature.create_slave(
            data_w=data_w,
            user_w=user_w,
            path=[f's_axis'],
        )
        self.source = AXI4StreamSignature.create_master(
            data_w=data_w,
            user_w=user_w,
            path=['m_axis'],
        )

    def get_ports(self):
        ports = []
        ports += self.sink.extract_signals()
        ports += self.source.extract_signals()
        return ports

    def elaborate(self, platform):
        m = Module()
        for i in range(len(self.fifos)):
            skid_buffer_core = self.skid_buffers[i]
            fifo_core = self.fifos[i]
            m.submodules[f'skid_buffer_{i:02d}'] = skid_buffer_core
            m.submodules[f'fifo_{i:02d}'] = fifo_core
            wiring.connect(m, skid_buffer_core.source, fifo_core.sink)
            next_skid_buffer_core = self.skid_buffers[i + 1]
            wiring.connect(m, fifo_core.source, next_skid_buffer_core.sink)

        last_skid_buffer_i = len(self.skid_buffers) - 1
        m.submodules[f'skid_buffer_{last_skid_buffer_i:02d}'] = self.skid_buffers[-1]
        wiring.connect(m, self.sink.as_master(), self.skid_buffers[0].sink)
        wiring.connect(m, self.skid_buffers[-1].source, self.source.as_slave())
        return m


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
