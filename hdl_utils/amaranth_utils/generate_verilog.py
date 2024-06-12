from amaranth.hdl.ir import Fragment
from amaranth.back import verilog
from amaranth import Elaboratable

import re


def generate_verilog(core: Elaboratable,
                     name: str = None,
                     ports: list = None,
                     prefix: str = ''):
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

    output = re.sub(r'\*\)', '*/', re.sub(r'\(\*', '/*', output))
    output = output.replace('__', '_')
    output = re.sub(f'module (?!{name})', f'module {prefix}_', output)

    return output
