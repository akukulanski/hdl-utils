from __future__ import annotations
from abc import ABC
from dataclasses import dataclass, field


DIR_OUTPUT = "o"
DIR_INPUT = "i"
DIR_INPUT_OUTPUT = "io"
DIR_UNDEF = "-"

_flipped_dir = {
    "o": "i",
    "i": "o",
}

def flip_layout(layout) -> list:
    return [sig_info.flipped() for sig_info in layout]


@dataclass(kw_only=True)
class SignalInfo:
    name: str = field(repr=True)
    direction: str = field(repr=True, default=DIR_UNDEF)
    optional: bool = field(repr=False, default=False)
    fixed_width: int = field(repr=False, default=0)
    default_value: int = field(repr=False, default=0)

    def flipped(self):
        return SignalInfo(
            name=self.name,
            direction=_flipped_dir.get(self.direction, self.direction),
            optional=self.optional,
            fixed_width=self.fixed_width,
            default_value=self.default_value,
        )


class Bus(ABC):

    layout: list[SignalInfo]

    def __init__(self, entity, name, clock):
        self.entity = entity
        self.name = name
        self.clock = clock
        for signal_info in self.layout:
            signal_full_name = f"{name}_{signal_info.name}"
            signal = getattr(self.entity, signal_full_name, None)
            assert signal is not None or signal_info.optional, (
                f"Missing required signal: {signal_full_name}"
            )
            if signal is None:
                continue
            if signal_info.fixed_width:
                assert len(signal) == signal_info.fixed_width, f"Invalid signal width: {len(signal)} (expected {signal_info.fixed_width})"
            assert not hasattr(self, signal_info.name), f"Conflicting names: Bus.{signal_info.name} already exists"
            setattr(self, signal_info.name, signal)

    def init_signals(self):
        for signal_info in self.layout:
            if signal_info.direction == DIR_OUTPUT:
                signal = getattr(self, signal_info.name, None)
                if signal is not None:
                    # signal.setimmediatevalue(signal_info.default_value)
                    signal.value = signal_info.default_value

    @classmethod
    def flip_layout(cls) -> list:
        return flip_layout(cls.layout)

    @classmethod
    def flipped_bus(cls) -> Bus:
        class FlippedClass(cls):
            layout = [sig_info.flipped() for sig_info in cls.layout]
        return FlippedClass
