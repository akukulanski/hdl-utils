from amaranth import (
    Elaboratable, Module, Signal, ClockDomain, ClockSignal, ResetSignal,
    DomainRenamer,
)


class RstnWrapper(Elaboratable):
    def __init__(self, core: Elaboratable, domain: str = "sync"):
        self.domain = domain
        self.xdomain = 'x' + domain
        self.wrapped_core = DomainRenamer({domain: self.xdomain})(core)
        self.clk_name = self.domain + "_clk"
        self.rstn_name = self.domain + "_rstn"
        setattr(self, self.clk_name, Signal(name=self.clk_name))
        setattr(self, self.rstn_name, Signal(name=self.rstn_name))

    @property
    def clk_signal(self):
        return getattr(self, self.clk_name)

    @property
    def rstn_signal(self):
        return getattr(self, self.rstn_name)

    def get_ports(self, *args, **kwargs):
        return [
            *self.wrapped_core.get_ports(*args, **kwargs),
            self.clk_signal, self.rstn_signal
        ]

    def elaborate(self, platform):
        m = Module()
        m.domains += ClockDomain(self.xdomain)
        m.submodules.wrapped = self.wrapped_core
        m.d.comb += [
            ClockSignal(self.xdomain).eq(self.clk_signal),
            ResetSignal(self.xdomain).eq(~self.rstn_signal),
        ]
        return m
