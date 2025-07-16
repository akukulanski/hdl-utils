from __future__ import annotations
import copy
from dataclasses import dataclass, field
import numpy as np


@dataclass(kw_only=True)
class Field:
    name: str
    width: int
    offset: int
    default: int = None


@dataclass(kw_only=True)
class Register:
    name: str
    fields: list[Field]
    dir: str
    force_addr: int = field(default=None)
    default: int = None

    @classmethod
    def from_single_field(cls, field: Field, **kwargs) -> Register:
        return Register(
            name=field.name.upper(),
            fields=[field],
            **kwargs,
        )


def create_register_map_entry(
    reg: Register,
    addr: int,
) -> tuple:
    default_reg_value = None
    for f in reg.fields:
        if f.default is not None:
            if default_reg_value is None:
                    default_reg_value = 0
            def_masked = f.default & (2**f.width - 1)
            default_reg_value |= (def_masked << f.offset)
    if reg.default is not None:
        assert default_reg_value is None or default_reg_value == reg.default, (
                f'Inconsistent default value for register {reg.name}. Internal fields '
                f'default it to {hex(default_reg_value)}, != {hex(reg.default)}.'
        )
        default_reg_value = reg.default
    current_fields = [(f.name, f.width, f.offset) for f in reg.fields]
    return (reg.name, reg.dir, addr, default_reg_value, current_fields)


def calc_axi_lite_addr_width(
    registers_map: list,
    addr_jump: int
) -> int:
    assert addr_jump in (4, 8)
    highest_addr = max([
        r[2]
        for r in registers_map
    ])
    return int(np.ceil(np.log2(highest_addr + addr_jump)))


def find_field_by_name(registers_map, field_name) -> tuple:
    addr, width, offset, mask = None, None, None, None
    for r_name, r_dir, r_addr, r_default, r_fields in registers_map:
        # if reg[0] == 'CREATE_CLK_COUNTERS_SNAPSHOT':
        for f_name, f_size, f_offset in r_fields:
            if f_name == field_name:
                addr, dir, width, offset = r_addr, r_dir, f_size, f_offset
                break
    return addr, dir, width, offset


class RegisterMapFactory:

    def __init__(self, reg_width: int = 32):
        self.reg_width = reg_width
        self._reg_map = []
        self._addr_in_use = []

    @property
    def addr_jump(self) -> int:
        return self.reg_width // 8

    def find_available_addr(self, start_from: int = 0x0) -> int:
        addr = start_from
        while True:
            if addr not in self._addr_in_use:
                break
            addr += self.addr_jump
        return addr

    def add_entry(self, reg: Register, addr: int = None):
        if addr is None:
            addr = self.find_available_addr()
        assert addr not in self._addr_in_use, (
            f'Conflicting address for register {reg.name}: {hex(addr)} already in use'
        )
        entry = create_register_map_entry(reg=reg, addr=addr)
        self._reg_map.append(entry)
        self._addr_in_use.append(addr)
        return entry

    def allocate_registers(self, registers: list[Register]):
        # First allocate those with fixed addresses
        regs_forced_addr = [r for r in registers if r.force_addr is not None]
        regs_not_forced_addr = [r for r in registers if r.force_addr is None]
        for reg in regs_forced_addr:
            self.add_entry(reg=reg, addr=reg.force_addr)
        # After all registers with forced address were allocated, allocate
        # those that can select the address dynamically
        for reg in regs_not_forced_addr:
            self.add_entry(reg=reg)

    def generate_register_map(self) -> list:
        return copy.deepcopy(self._reg_map)

    def get_min_addr_width(self) -> int:
        assert self.addr_jump in (4, 8)
        highest_addr = max(self._addr_in_use)
        return int(np.ceil(np.log2(highest_addr + self.addr_jump)))
