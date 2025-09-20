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
            assert iface.tkeep.init == 2**(data_w // 8) - 1

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

    @pytest.mark.parametrize('data_w,user_w,depth', [(8, 2, 16)])
    def test_axi_stream_fifo(self, data_w: int, user_w: int, depth: int):
        from hdl_utils.amaranth_utils.axi_stream_fifo import AXIStreamFIFO

        core = AXIStreamFIFO(
            data_w=data_w,
            user_w=user_w,
            depth=depth,
        )
        ports = core.get_ports()
        test_module = 'tb.tb_axi_stream_pass_through'
        vcd_file = f'./tb_axi_stream_fifo_{data_w}_{user_w}_{depth}.vcd'
        env = {
            'P_DATA_W': str(data_w),
            'P_USER_W': str(user_w),
            'P_DEPTH': str(depth),
            'P_HAS_TKEEP': str(int(bool(hasattr(core.sink, 'tkeep')))),
            'P_TEST_LENGTH': str(32 * depth),
        }
        self.run_testbench(core, test_module, ports,
                           vcd_file=vcd_file, env=env)

    @pytest.mark.parametrize('data_w,user_w,depth,max_fifo_depth', [
        (8, 2, 16, 8),
        (8, 2, 16, 7),
    ])
    def test_fast_clk_axi_stream_fifo(self, data_w: int, user_w: int, depth: int, max_fifo_depth: int):
        from hdl_utils.amaranth_utils.axi_stream_fifo import FastClkAXIStreamFIFO

        core = FastClkAXIStreamFIFO(
            data_w=data_w,
            user_w=user_w,
            depth=depth,
            max_fifo_depth=max_fifo_depth,
        )
        ports = core.get_ports()
        test_module = 'tb.tb_axi_stream_pass_through'
        vcd_file = f'./tb_fast_clk_axi_stream_fifo_{data_w}_{user_w}_{depth}_{max_fifo_depth}.vcd'
        env = {
            'P_DATA_W': str(data_w),
            'P_USER_W': str(user_w),
            'P_DEPTH': str(depth),
            'P_MAX_FIFO_DEPTH': str(max_fifo_depth),
            'P_HAS_TKEEP': str(int(bool(hasattr(core.sink, 'tkeep')))),
            'P_TEST_LENGTH': str(32 * depth),
        }
        self.run_testbench(core, test_module, ports, vcd_file=vcd_file, env=env)

    @pytest.mark.parametrize('data_w,user_w,depth,low_reset', [
        (8, 2, 8, False),
        (8, 2, 8, True),
    ])
    def test_axi_stream_fifo_cdc(
        self,
        data_w: int,
        user_w: int,
        depth: int,
        low_reset: bool
    ):
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
        if low_reset:
            from hdl_utils.amaranth_utils.rstn_wrapper import RstnWrapper
            core = RstnWrapper(core=core, domain="rd_domain")
            core = RstnWrapper(core=core, domain="wr_domain")
            pfx = '_rstn'
        else:
            pfx = ''
        ports = core.get_ports()
        test_module = 'tb.tb_axi_stream_fifo_cdc'
        vcd_file = f'./tb_axi_stream_fifo_cdc_{data_w}_{user_w}_{depth}{pfx}.vcd'
        env = {
            'P_DATA_W': str(data_w),
            'P_USER_W': str(user_w),
            'P_DEPTH': str(depth)
        }
        self.run_testbench(core, test_module, ports,
                           vcd_file=vcd_file, env=env)

    @pytest.mark.parametrize('data_w,user_w', [(8, 2)])
    def test_axi_stream_skid_buffer(self, data_w: int, user_w: int):
        from hdl_utils.amaranth_utils.skid_buffer import AXISkidBuffer

        core = AXISkidBuffer(
            data_w=data_w,
            user_w=user_w,
        )
        ports = core.get_ports()
        test_module = 'tb.tb_axi_stream_pass_through'
        vcd_file = f'./tb_axi_stream_skid_buffer_{data_w}_{user_w}.vcd'
        env = {
            'P_DATA_W': str(data_w),
            'P_USER_W': str(user_w),
            'P_HAS_TKEEP': str(int(bool(hasattr(core.sink, 'tkeep')))),
            'P_TEST_LENGTH': str(32),
        }
        self.run_testbench(core, test_module, ports, vcd_file=vcd_file, env=env)

    @pytest.mark.parametrize(
        'DWI,DWO,UWI',
        [
            (24, 8, 3),
            (48, 24, 4),
        ]
    )
    def test_width_converter_down(self, DWI, DWO, UWI):
        from hdl_utils.amaranth_utils.axi_stream_width_converter import \
            AXIStreamWidthConverterDown

        core = AXIStreamWidthConverterDown(
            data_w_i=DWI,
            data_w_o=DWO,
            user_w_i=UWI,
        )
        ports = core.get_ports()
        test_module = 'tb.tb_axi_stream_width_converter_down'
        vcd_file = f'./tb_axi_stream_width_converter_down_{DWI}_{DWO}_{UWI}.vcd'
        env = {
            'P_DWI': str(DWI),
            'P_DWO': str(DWO),
            'P_UWI': str(UWI),
        }
        self.run_testbench(core, test_module, ports,
                           vcd_file=vcd_file, env=env)

    @pytest.mark.parametrize(
        'DWI,DWO,UWI',
        [
            (16, 8, 0),  # EXPECT FAIL: zero user width
            (24, 48, 4),  # EXPECT FAIL: 24 <= 48
            (40, 24, 4),  # EXPECT FAIL: 40 % 24 == 16
        ]
    )
    def test_width_converter_down_bad(self, DWI, DWO, UWI):
        from hdl_utils.amaranth_utils.axi_stream_width_converter import \
            AXIStreamWidthConverterDown

        with pytest.raises(AssertionError):
            AXIStreamWidthConverterDown(
                data_w_i=DWI,
                data_w_o=DWO,
                user_w_i=UWI,
            )

    @pytest.mark.parametrize(
        'DWI,DWO,UWI',
        [
            (8, 24, 1),
            (24, 48, 2),
        ]
    )
    def test_width_converter_up(self, DWI, DWO, UWI):
        from hdl_utils.amaranth_utils.axi_stream_width_converter import \
            AXIStreamWidthConverterUp

        core = AXIStreamWidthConverterUp(
            data_w_i=DWI,
            data_w_o=DWO,
            user_w_i=UWI,
        )
        ports = core.get_ports()
        test_module = 'tb.tb_axi_stream_width_converter_up'
        vcd_file = f'./tb_axi_stream_width_converter_up_{DWI}_{DWO}_{UWI}.vcd'
        env = {
            'P_DWI': str(DWI),
            'P_DWO': str(DWO),
            'P_UWI': str(UWI),
        }

        self.run_testbench(core, test_module, ports,
                           vcd_file=vcd_file, env=env)

    @pytest.mark.parametrize(
        'DWI,DWO,UWI',
        [
            (8, 16, 0),  # EXPECT FAIL: zero user width
            (48, 24, 2),  # EXPECT FAIL: 48 >= 24
            (24, 40, 2),  # EXPECT FAIL: 40 % 24 == 16
        ]
    )
    def test_width_converter_up_bad(self, DWI, DWO, UWI):
        from hdl_utils.amaranth_utils.axi_stream_width_converter import \
            AXIStreamWidthConverterUp

        with pytest.raises(AssertionError):
            AXIStreamWidthConverterUp(
                data_w_i=DWI,
                data_w_o=DWO,
                user_w_i=UWI,
            )

    @pytest.mark.parametrize('addr_w,data_w,user_w', [(32, 128, 0)])
    def test_axi_stream_to_full(self, addr_w, data_w, user_w):
        from hdl_utils.amaranth_utils.axi_stream_to_full import AxiStreamToFull
        core = AxiStreamToFull(
            addr_w=addr_w,
            data_w=data_w,
            user_w=user_w,
        )
        ports = core.get_ports()
        test_module = 'tb.tb_axi_stream_to_full'
        vcd_file = './tb_axi_stream_to_full.py.vcd'
        env = {
            'P_ADDR_W': str(addr_w),
            'P_DATA_W': str(data_w),
            'P_USER_W': str(user_w),
        }
        self.run_testbench(core, test_module, ports, vcd_file=vcd_file, env=env)

    @pytest.mark.parametrize('addr_w,data_w,user_w,burst_len', [(32, 128, 0, 8)])
    def test_axi_dma(self, addr_w, data_w, user_w, burst_len):
        from hdl_utils.amaranth_utils.axi_dma import AxiDma
        core = AxiDma(
            addr_w=addr_w,
            data_w=data_w,
            user_w=user_w,
            burst_len=burst_len,
        )
        ports = core.get_ports()
        test_module = 'tb.tb_axi_dma'
        vcd_file = './tb_axi_dma.py.vcd'
        env = {
            'P_ADDR_W': str(addr_w),
            'P_DATA_W': str(data_w),
            'P_USER_W': str(user_w),
            'P_BURST_LEN': str(burst_len),
        }
        self.run_testbench(core, test_module, ports, vcd_file=vcd_file, env=env)

    @pytest.mark.parametrize('addr_w,data_w,user_w,burst_len,ignore_rd_size_signal', [
        (32, 128, 0, 8, False),
        (32, 128, 0, 8, True),
    ])
    def test_axi_dma_triple_buffer(self, addr_w, data_w, user_w, burst_len, ignore_rd_size_signal):
        from hdl_utils.amaranth_utils.axi_dma_triple_buffer import AXIDmaTripleBuffer
        init_rd_size = 8
        core = AXIDmaTripleBuffer(
            addr_w=addr_w,
            data_w=data_w,
            user_w=user_w,
            burst_len=burst_len,
            ignore_rd_size_signal=ignore_rd_size_signal,
            init_rd_size=init_rd_size,
        )
        ports = core.get_ports()
        test_module = 'tb.tb_axi_dma_triple_buffer'
        vcd_file = './tb_axi_dma_triple_buffer.py.vcd'
        env = {
            'P_ADDR_W': str(addr_w),
            'P_DATA_W': str(data_w),
            'P_USER_W': str(user_w),
            'P_BURST_LEN': str(burst_len),
            'P_INIT_RD_SIZE': str(init_rd_size),
            'P_IGNORE_RD_SIZE_SIGNAL': str(int(bool(ignore_rd_size_signal))),
        }
        self.run_testbench(core, test_module, ports, vcd_file=vcd_file, env=env)

    @pytest.mark.parametrize(
        'data_w,user_w,no_tkeep,n_split',
        [
            (8, 1, True, 2),
            (8, 1, True, 3),
            (8, 1, True, 1),
            (16, 1, False, 2),
            (16, 2, False, 2),
        ]
    )
    def test_axis_splitter(
        self,
        data_w: int,
        user_w: int,
        no_tkeep: bool,
        n_split: int,
    ):
        from hdl_utils.amaranth_utils.axi_stream_splitter import \
            AXIStreamSplitter

        core = AXIStreamSplitter(
            data_w=data_w,
            user_w=user_w,
            no_tkeep=no_tkeep,
            n_split=n_split,
        )
        ports = core.get_ports()
        test_module = 'tb.tb_axi_stream_splitter'
        vcd_file = f'./tb_axi_stream_splitter_{data_w}_{user_w}_{no_tkeep}_{n_split}.vcd'
        env = {
            'P_DATA_W': str(data_w),
            'P_USER_W': str(user_w),
            'P_NO_TKEEP': str(int(no_tkeep)),
            'P_N_SPLIT': str(n_split),
        }
        self.run_testbench(core, test_module, ports,
                           vcd_file=vcd_file, env=env)
