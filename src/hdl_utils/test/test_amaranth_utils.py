import pytest

from hdl_utils.cocotb_utils.testcases import TemplateTestbenchAmaranth


class TestbenchCoresAmaranth(TemplateTestbenchAmaranth):

    @pytest.mark.parametrize('data_w,user_w', [(8, 4)])
    def test_axi_stream_interface_a(
        self,
        data_w: int,
        user_w: int,
    ):
        from amaranth import Elaboratable, Module, Signal
        from amaranth.lib import wiring
        from hdl_utils.amaranth_utils.interfaces.axi4_stream import (
            AXI4StreamSignature)
        m_axis = AXI4StreamSignature.create_master(data_w=data_w, user_w=user_w)
        s_axis = AXI4StreamSignature.create_slave(data_w=data_w, user_w=user_w)
        for iface in (m_axis, s_axis):
            assert len(iface.tdata) == data_w
            assert len(iface.tuser) == user_w
            assert len(iface.tkeep) == data_w // 8
            assert len(iface.tvalid) == 1
            assert len(iface.tready) == 1
            assert len(iface.tlast) == 1

        m = Module()
        wiring.connect(m, s_axis.as_master(), m_axis.as_slave())
        m.d.sync += Signal().eq(~Signal())

        class Dummy(Elaboratable):
            def elaborate(self, platform):
                return m

        core = Dummy()
        ports = m_axis.extract_signals() + s_axis.extract_signals()
        test_module = 'tb.tb_axi_stream'
        vcd_file = None
        env = {
            'P_DATA_W': str(data_w),
            'P_USER_W': str(user_w),
        }
        self.run_testbench(core, test_module, ports,
                           vcd_file=vcd_file, env=env)

    @pytest.mark.parametrize('data_w,user_w', [(8, 4)])
    def test_axi_stream_interface_b(
        self,
        data_w: int,
        user_w: int,
    ):
        from amaranth import Elaboratable, Module, Signal
        from hdl_utils.amaranth_utils.interfaces.axi4_stream import (
            AXI4StreamSignature)
        m_axis = AXI4StreamSignature.create_master(data_w=data_w, user_w=user_w)
        s_axis = AXI4StreamSignature.create_slave(data_w=data_w, user_w=user_w)

        m = Module()
        packed = Signal(data_w + user_w + data_w // 8 + 1)
        m.d.comb += packed.eq(s_axis.flatten())
        m.d.comb += m_axis.assign_from_flat(packed)
        m.d.comb += [
            m_axis.tvalid.eq(s_axis.tvalid),
            s_axis.tready.eq(m_axis.tready),
        ]
        m.d.sync += Signal().eq(~Signal())

        class Dummy(Elaboratable):
            def elaborate(self, platform):
                return m

        core = Dummy()
        ports = m_axis.extract_signals() + s_axis.extract_signals()
        test_module = 'tb.tb_axi_stream'
        vcd_file = None
        env = {
            'P_DATA_W': str(data_w),
            'P_USER_W': str(user_w),
        }
        self.run_testbench(core, test_module, ports,
                           vcd_file=vcd_file, env=env)

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

    @pytest.mark.skip(reason='Testbench Not Implemented')
    @pytest.mark.parametrize('data_w,user_w,depth', [(8, 2, 16)])
    def test_axi_stream_fifo(self, data_w: int, user_w: int, depth: int):
        from hdl_utils.amaranth_utils.axi_stream_fifo import AXIStreamFIFO

        core = AXIStreamFIFO(
            data_w=data_w,
            user_w=user_w,
            depth=depth,
        )
        ports = core.get_ports()
        test_module = 'tb.tb_axi_stream_fifo'
        vcd_file = f'./tb_axi_stream_fifo_{data_w}_{user_w}_{depth}.vcd'
        env = {
            'P_DATA_W': str(data_w),
            'P_USER_W': str(user_w),
            'P_DEPTH': str(depth)
        }
        self.run_testbench(core, test_module, ports,
                           vcd_file=vcd_file, env=env)

    @pytest.mark.parametrize('data_w,user_w,depth', [(8, 2, 8)])
    def test_axi_stream_fifo_cdc(self, data_w: int, user_w: int, depth: int):
        from hdl_utils.amaranth_utils.axi_stream_fifo import AXIStreamFIFO

        core = AXIStreamFIFO.CreateCDC(
            data_w=data_w,
            user_w=user_w,
            depth=depth,
            r_domain='rd_domain',
            w_domain='wr_domain',
            # fifo_cls: Elaboratable = AsyncFIFO,
            # fifo_cls: Elaboratable = AsyncFIFOBuffered,
        )
        ports = core.get_ports()
        test_module = 'tb.tb_axi_stream_fifo_cdc'
        vcd_file = f'./tb_axi_stream_fifo_cdc_{data_w}_{user_w}_{depth}.vcd'
        env = {
            'P_DATA_W': str(data_w),
            'P_USER_W': str(user_w),
            'P_DEPTH': str(depth)
        }
        self.run_testbench(core, test_module, ports,
                           vcd_file=vcd_file, env=env)
