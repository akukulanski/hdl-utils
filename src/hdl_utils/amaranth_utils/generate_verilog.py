from amaranth.hdl.ir import Fragment
from amaranth.back import verilog
from amaranth import Elaboratable

import re


def generate_verilog(core: Elaboratable,
                     name: str = None,
                     ports: list = None,
                     prefix: str = '',
                     remove_duplicate_underscores: bool = True,
                     remove_comments: bool = True,
                     remove_empty_lines: bool = True,
                     timescale: str = '`timescale 1ns/1ps',
                     ):
    """
    Generate Verilog of a core described by an Elaboratable object.

    parameters:
        core: Elaboratable
            The core to generate the verilog.

        name: str
            The name of the core.

        ports: list
            The ports of the core. If not specified, the elaboratable should have
            a method called "get_ports()".

        prefix: str
            A prefix for all the submodules in the file to be generated, to avoid
            collision with other files of a project.
    """

    if name is None:
        name = 'top_level'

    if ports is None:
        ports = core.get_ports()

    fragment = Fragment.get(core, None)
    output = verilog.convert(fragment, name=name, ports=ports)

    if timescale:
        output = f'{timescale}\n\n{output}'

    # Reformat the verilog output
    output = re.sub(r'\*\)', '*/', re.sub(r'\(\*', '/*', output))
    # Fix duplicate underscores
    if remove_duplicate_underscores:
        output = output.replace('__', '_')
    # Remove comments
    if remove_comments:
        regex = r'/\* .* \*/\s*'
        output = re.sub(regex, '', output)
    # Remove empty lines
    if remove_empty_lines:
        regex = r'^\s*$\n'
        output = re.sub(regex, '', output)
    # Add prefix to the modules to avoid conflicts between cores that have
    # submodules with repeating names
    # EDIT: Disabled. Now generation already uses module names "name.submodule"
    # output = re.sub(f'module (?!{name})', f'module {prefix}_', output)

    return output
