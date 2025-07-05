from abc import ABC
from dataclasses import dataclass, field


DIR_OUTPUT = "o"
DIR_INPUT = "i"
DIR_INPUT_OUTPUT = "io"
DIR_UNDEF = "-"


@dataclass(kw_only=True)
class SignalInfo:
    name: str = field(repr=True)
    direction: str = field(repr=True, default=DIR_UNDEF)
    optional: bool = field(repr=False, default=False)
    fixed_width: int = field(repr=False, default=0)
    default_value: int = field(repr=False, default=0)


class Bus(ABC):

    layout: list[SignalInfo]

    def __init__(self, dut, name, clock):
        self.dut = dut
        self.name = name
        for signal_info in self.layout:
            signal_full_name = f"{name}_{signal_info.name}"
            signal = getattr(self.dut, signal_full_name, None)
            assert signal is not None or signal_info.optional, (
                f"Missing required signal: {signal_full_name}"
            )
            if signal is None:
                continue
            if signal_info.fixed_width:
                assert len(signal) == signal_info.fixed_width, f"Invalid signal width: {len(signal)} (expected {signal_info.fixed_width})"
            assert not hasattr(self, signal_info.name), f"Conflicting names: Bus.{signal_info.name} already exists"
            setattr(self, signal_info.name, signal)
