from __future__ import annotations

from amaranth import Elaboratable, Module, Signal
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out


__all__ = [
    'extract_signals_from_wiring',
    'DataStreamSignature',
    'DataStreamInterface',
    'SlaveDataStreamInterface',
    'MasterDataStreamInterface',
]


def extract_signals_from_wiring(signature: wiring.Signature):
    """
    Signature can have signals or nested signatures.
    This generator finds signals recursively.
    """
    signature_dict = getattr(signature, '__dict__', None)
    if not signature_dict:
        return
    for k in signature_dict.keys():
        if k == 'signature':
            continue
        if isinstance(signature_dict[k], Signal):
            yield signature_dict[k]
        else:
            yield from extract_signals_from_wiring(signature_dict[k])


# from: https://amaranth-lang.org/docs/amaranth/latest/stdlib/wiring.html#reusable-interfaces
class DataStreamSignature(wiring.Signature):

    def __init__(self, data_w: int):
        super().__init__({
            "data": Out(data_w),
            "valid": Out(1),
            "ready": In(1),
            "last": Out(1)
        })

    def __eq__(self, other):
        return self.members == other.members

    def create(self, *, path=None, src_loc_at=0):
        return DataStreamInterface(self, path=path, src_loc_at=1 + src_loc_at)

    @classmethod
    def create_master(cls, *, data_w: int, path=None, src_loc_at=0):
        return MasterDataStreamInterface(cls(data_w=data_w), path=path, src_loc_at=1+src_loc_at)

    @classmethod
    def create_slave(cls, *, data_w: int, path=None, src_loc_at=0):
        return SlaveDataStreamInterface(cls(data_w=data_w).flip(), path=path, src_loc_at=1+src_loc_at)

    @classmethod
    def connect_m2s(cls, *, m, master, slave):
        wiring.connect(m, master, slave)


class DataStreamInterface(wiring.PureInterface):

    @property
    def data_w(self):
        return len(self.data)

    def accepted(self):
        return self.valid & self.ready

    def extract_signals(self):
        return list(extract_signals_from_wiring(self))


class SlaveDataStreamInterface(DataStreamInterface):

    def as_master(self):
        return wiring.flipped(self)

    def connect(self, m, master):
        print(f'SlaveDataStreamInterface.connect(master={master})')
        return wiring.connect(m, master, self)


class MasterDataStreamInterface(DataStreamInterface):

    def as_slave(self):
        return wiring.flipped(self)

    def connect(self, m, slave):
        print(f'MasterDataStreamInterface.connect(slave={slave})')
        return wiring.connect(m, self, slave)
