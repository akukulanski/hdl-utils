from amaranth import Elaboratable, Module, ResetSignal, Signal, Mux
from amaranth.lib import wiring

from hdl_utils.amaranth_utils.interfaces.axi4_stream import (
    AXI4StreamSignature,
    SlaveAXI4StreamInterface,
    MasterAXI4StreamInterface,
)


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
        m = Module()

        CREATE_BUFF_FULL_REG = True

        buff_empty = Signal(init=1)
        buff_data = Signal.like(self.sink_data)
        buff_full = Signal() if CREATE_BUFF_FULL_REG else ~buff_empty

        m.d.comb += self.sink_ready.eq(buff_empty)
        m.d.comb += self.source_valid.eq(self.sink_valid | buff_full)
        m.d.comb += self.source_data.eq(Mux(buff_full, buff_data, self.sink_data))

        with m.If((buff_empty) & self.sink_valid & ~self.source_ready):
            m.d.sync += buff_empty.eq(0)
            if CREATE_BUFF_FULL_REG:
                m.d.sync += buff_full.eq(1)
            m.d.sync += buff_data.eq(self.sink_data)
        with m.Elif(buff_full & self.source_ready):
            m.d.sync += buff_empty.eq(1)
            if CREATE_BUFF_FULL_REG:
                m.d.sync += buff_full.eq(0)

        return m


class StreamOutputReg(Elaboratable):
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
        m = Module()

        sink_valid_r = Signal()
        sink_data_r = Signal.like(self.sink_data)

        m.d.comb += self.sink_ready.eq(self.source_ready | ~sink_valid_r)
        m.d.comb += self.source_valid.eq(sink_valid_r)
        m.d.comb += self.source_data.eq(sink_data_r)

        with m.If(self.sink_valid & self.sink_ready):
            m.d.sync += sink_valid_r.eq(self.sink_valid)
            m.d.sync += sink_data_r.eq(self.sink_data)
        with m.Elif(self.source_valid & self.source_ready):
            m.d.sync += sink_valid_r.eq(0)
            # m.d.sync += sink_data_r.eq(0)

        return m


class AXISOutputReg(Elaboratable):

    def __init__(self, data_w: int, user_w: int, no_tkeep: bool = False):
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
        self.output_reg = StreamOutputReg(width=total_width)

    def get_ports(self):
        return self.sink.extract_signals() + self.source.extract_signals()

    def elaborate(self, platform):
        m = Module()
        m.submodules.output_reg = output_reg = self.output_reg
        m.d.comb += output_reg.sink_valid.eq(self.sink.tvalid)
        m.d.comb += output_reg.sink_data.eq(self.sink.flatten())
        m.d.comb += self.sink.tready.eq(output_reg.sink_ready)
        m.d.comb += self.source.tvalid.eq(output_reg.source_valid)
        m.d.comb += self.source.assign_from_flat(output_reg.source_data)
        m.d.comb += output_reg.source_ready.eq(self.source.tready)
        return m


class AXISkidBuffer(Elaboratable):

    def __init__(
        self,
        data_w: int,
        user_w: int,
        no_tkeep: bool = False,
        reg_output: bool = False,
    ):
        self.reg_output = reg_output
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
        self.output_buffer = StreamOutputReg(width=total_width) if reg_output else None

    def get_ports(self):
        return self.sink.extract_signals() + self.source.extract_signals()

    def elaborate(self, platform):
        m = Module()
        m.submodules.skid_buffer = skid_buffer = self.skid_buffer
        m.d.comb += skid_buffer.sink_valid.eq(self.sink.tvalid)
        m.d.comb += skid_buffer.sink_data.eq(self.sink.flatten())
        m.d.comb += self.sink.tready.eq(skid_buffer.sink_ready)

        if self.output_buffer is not None:
            m.submodules.output_buffer = output_buffer = self.output_buffer
            m.d.comb += output_buffer.sink_valid.eq(skid_buffer.source_valid)
            m.d.comb += output_buffer.sink_data.eq(skid_buffer.source_data)
            m.d.comb += skid_buffer.source_ready.eq(output_buffer.sink_ready)
            m.d.comb += self.source.tvalid.eq(output_buffer.source_valid)
            m.d.comb += self.source.assign_from_flat(output_buffer.source_data)
            m.d.comb += output_buffer.source_ready.eq(self.source.tready)
        else:
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
        assert isinstance(core, Elaboratable)
        assert isinstance(add_input_buffer, bool)
        assert isinstance(add_output_buffer, bool)
        assert isinstance(core_sink, (SlaveAXI4StreamInterface, type(None)))
        assert isinstance(core_source, (MasterAXI4StreamInterface, type(None)))
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
                reg_output=True,
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
                reg_output=True,
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

        if self.add_input_buffer:
            m.submodules.skid_buffer_in = self.skid_buffer_in
            wiring.connect(m, self.skid_buffer_in.source, self.core_sink)

        if self.add_output_buffer:
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
        reg_output=True,
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
