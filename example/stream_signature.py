from amaranth import Elaboratable, Module, Signal
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out


def extract_signals(signature: wiring.Signature):
    """
    Signature can have signals or nested signatures.
    This generator finds signals recursively.
    """
    signature_dict = signature.__dict__
    for k in signature_dict.keys():
        if k == 'signature':
            continue
        if isinstance(signature_dict[k], Signal):
            yield signature_dict[k]
        else:
            yield from extract_signals(signature_dict[k])


# from: https://amaranth-lang.org/docs/amaranth/latest/stdlib/wiring.html#reusable-interfaces
class SimpleStreamSignature(wiring.Signature):
    def __init__(self, data_shape):
        super().__init__({
            "data": Out(data_shape),
            "valid": Out(1),
            "ready": In(1),
            "last": Out(1)
        })

    def __eq__(self, other):
        return self.members == other.members


class DataStreamInv(wiring.Component):

    # source and sink defined here
    # TO DO: check if there is any difference about inheriting wiring.Component
    # and elaboratable.
    source: Out(SimpleStreamSignature(8))
    # sink: Out(SimpleStreamSignature(8).flip())
    sink: In(SimpleStreamSignature(8))  # In also flips!

    def get_ports(self):
        ports = []
        ports += [self.sink[f] for f in self.sink.fields]
        ports += [self.source[f] for f in self.source.fields]
        return ports

    def elaborate(self, platform):
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


# Option 1: Elaboratable, and create signatures in __init__
# Why? To be able to parametrize widths
class BaseAsElaboratable(Elaboratable):

    def __init__(self, width=8):
        self.sink = SimpleStreamSignature(width).flip().create()
        self.source = SimpleStreamSignature(width).create()


# Option 2: declare the signatures in the class
class BaseAsComponent(wiring.Component):
    # sink: Out(SimpleStreamSignature(8).flip())
    sink: In(SimpleStreamSignature(8))  # In flips!
    source: Out(SimpleStreamSignature(8))


class TripleInverterRTL:

    def get_ports(self):
        ports = []
        ports += list(extract_signals(self.sink))
        ports += list(extract_signals(self.source))
        return ports

    def elaborate(self, platform):
        m = Module()
        m.submodules.first_inv = first_inv = DataStreamInv()
        m.submodules.second_inv = second_inv = DataStreamInv()
        m.submodules.third_inv = third_inv = DataStreamInv()
        wiring.connect(m, wiring.flipped(self.sink), first_inv.sink)
        wiring.connect(m, first_inv.source, second_inv.sink)
        wiring.connect(m, second_inv.source, third_inv.sink)
        wiring.connect(m, third_inv.source, wiring.flipped(self.source))
        return m


class TripleInverter_A(TripleInverterRTL, BaseAsElaboratable): ...
class TripleInverter_B(TripleInverterRTL, BaseAsComponent): ...


if __name__ == '__main__':
    from hdl_utils.amaranth_utils.generate_verilog import generate_verilog
    output = generate_verilog(TripleInverter_A())
    print(output)
