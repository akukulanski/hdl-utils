from hdl_utils.cocotb_utils.tb_utils import (
    width_converter_up,
    width_converter_down,
)

def test_width_converters():
    din = list(range(9))
    assert width_converter_up(
        data_in=din,
        width_in=8,
        width_out=24
    ) == [0x020100, 0x050403, 0x080706]

    assert width_converter_down(
        data_in=[0x020100, 0x050403, 0x080706],
        width_in=24,
        width_out=8
    ) == din
