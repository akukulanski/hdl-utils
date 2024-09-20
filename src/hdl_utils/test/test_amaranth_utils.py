import pytest

from hdl_utils.cocotb_utils.testcases import TemplateTestbenchAmaranth


class TestbenchCoresAmaranth(TemplateTestbenchAmaranth):

    @pytest.mark.parametrize('addr_w,data_w', [(8, 32)])
    def test_axi_lite_device(self, addr_w, data_w):
        from hdl_utils.amaranth_utils.axi_lite_device import AxiLiteDevice
        registers_map = [
            ('reg_rw_1', 'rw', 0x00000000, [
                ('field_1', 32,  0),
            ]),
            ('reg_rw_2', 'rw', 0x00000004, [
                ('field_2',  1,  0),
                ('field_3', 15,  1),
                ('field_4', 16, 16),
            ]),
            ('reg_rw_3', 'rw', 0x00000008, [
                ('field_5', 32,  0),
            ]),
            ('reg_ro_1', 'ro', 0x0000000C, [
                ('field_10', 32,  0),
            ]),
            ('reg_ro_2', 'ro', 0x00000010, [
                ('field_20',  1,  0),
                ('field_30', 15,  1),
                ('field_40', 16, 16),
            ]),
            ('reg_ro_3', 'ro', 0x00000014, [
                ('field_50', 32,  0),
            ]),
        ]
        highest_addr = max([
            addr
            for _, __, addr, ___ in registers_map
        ])
        core = AxiLiteDevice(
            addr_w=addr_w,
            data_w=data_w,
            registers_map=registers_map
        )
        ports = core.get_ports()
        test_module = 'tb.tb_axi_lite_device'
        vcd_file = './axi_lite_device.py.vcd'
        env = {
            'P_ADDR_W': str(addr_w),
            'P_DATA_W': str(data_w),
            'P_HIGHEST_ADDR': str(highest_addr)
        }
        self.run_testbench(core, test_module, ports,
                           vcd_file=vcd_file, env=env)
