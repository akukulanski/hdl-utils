from amaranth import Elaboratable, Module, Signal

from hdl_utils.amaranth_utils.interfaces import (DataStreamSlave,
                                                 DataStreamMaster)


class DataStreamInv(Elaboratable):

    def __init__(self, width):
        self.sink = DataStreamSlave(data_w=width, name='sink')
        self.source = DataStreamMaster(data_w=width, name='source')

    def get_ports(self):
        ports = []
        ports += [self.sink[f] for f in self.sink.fields]
        ports += [self.source[f] for f in self.source.fields]
        return ports

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
        return m
