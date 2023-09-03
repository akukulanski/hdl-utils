from amaranth import Elaboratable, Signal, Module


class Counter(Elaboratable):
    def __init__(self, width):
        self.count = Signal(width)

    def get_ports(self):
        return [self.count]

    def elaborate(self, platform):
        m = Module()
        m.d.sync += self.count.eq(self.count + 1)
        return m


if __name__ == '__main__':
    from hdl_utils.amaranth_utils.generate_verilog import generate_verilog
    import sys
    assert len(sys.argv) == 2, f'Usage: {sys.argv[0]} WIDTH'
    width = int(sys.argv[1])
    output = generate_verilog(Counter(width))
    print(output)
