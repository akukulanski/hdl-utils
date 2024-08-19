from amaranth import Elaboratable, Module, Signal
from amaranth.lib import wiring

from hdl_utils.amaranth_utils.interfaces import DataStreamSignature


class DataStreamInverter(Elaboratable):

    def __init__(self, width):
        self.sink = DataStreamSignature.create_slave(data_w=width)
        self.source = DataStreamSignature.create_master(data_w=width)

    def get_ports(self):
        return self.sink.extract_signals() + self.source.extract_signals()

    def elaborate(self, elaboratable):
        m = Module()
        x = Signal()
        m.d.sync += x.eq(~x)
        m.d.comb += [
            self.source.valid.eq(self.sink.valid),
            self.source.last.eq(self.sink.last),
            self.source.data.eq(~self.sink.data),
            self.sink.ready.eq(self.source.ready),
        ]
        # wiring.connect(m, wiring.flipped(self.sink), wiring.flipped(self.source)))
        # wiring.connect(m, self.sink.as_master(), self.source.as_slave()))
        return m
