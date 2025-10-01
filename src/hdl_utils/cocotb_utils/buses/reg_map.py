from __future__ import annotations

from dataclasses import dataclass


@dataclass(kw_only=True)
class Reg:
    name: str
    dir: str
    addr: int
    default: int = 0
    fields: list = None


class RegMap:
    def __init__(self, reg_map: list[Reg]):
        self.reg_map = reg_map

    @classmethod
    def from_reg_map_raw_list(cls, reg_map_raw_list: list[tuple]) -> RegMap:
        return cls([
            Reg(name=name, dir=dir, addr=addr, default=default, fields=fields)
            for name, dir, addr, default, fields in reg_map_raw_list
        ])

    def get_reg_by_name(self, name: str) -> Reg:
        for reg in self.reg_map:
            if reg.name == name:
                return reg
        return None

    def get_reg_by_addr(self, addr: int) -> Reg:
        for reg in self.reg_map:
            if reg.addr == addr:
                return reg
        return None
