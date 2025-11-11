import os
import pytest

from hdl_utils.cocotb_utils.testcases import TemplateTestbenchAmaranth


this_dir = os.path.dirname(__file__)
waveforms_dir = os.path.join(this_dir, '..', '..', '..', 'output', 'waveforms')

in_waveform_dir = lambda x: os.path.join(waveforms_dir, x)


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
        from hdl_utils.test.example_reg_map import get_example_reg_map_factory
        reg_map_factory = get_example_reg_map_factory(data_w)
        registers_map = reg_map_factory.generate_register_map()
        highest_addr = max([
            addr
            for name, dir, addr, default, fields in registers_map
        ])
        core = AxiLiteDevice(
            addr_w=addr_w,
            data_w=data_w,
            registers_map=registers_map
        )
        ports = core.get_ports()
        test_module = 'tb.tb_axi_lite_device'
        vcd_file = in_waveform_dir('axi_lite_device.py.vcd')
        env = {
            'P_ADDR_W': str(addr_w),
            'P_DATA_W': str(data_w),
            'P_HIGHEST_ADDR': str(highest_addr)
        }
        self.run_testbench(core, test_module, ports,
                           vcd_file=vcd_file, env=env)

    @pytest.mark.parametrize('data_w,user_w,depth,packet_mode', [
        (8, 2, 16, False),
        (8, 2, 16, True),
    ])
    def test_axi_stream_fifo(self, data_w: int, user_w: int, depth: int, packet_mode: bool):
        from hdl_utils.amaranth_utils.axi_stream_fifo import AXIStreamFIFO

        core = AXIStreamFIFO(
            data_w=data_w,
            user_w=user_w,
            depth=depth,
            packet_mode=packet_mode,
        )
        ports = core.get_ports()
        test_module = 'tb.tb_axi_stream_pass_through'
        base_name = f'tb_axi_stream_fifo_{data_w}_{user_w}_{depth}'
        if packet_mode:
            base_name += '_packet'
        vcd_file = in_waveform_dir(f'{base_name}.vcd')
        env = {
            'P_DATA_W': str(data_w),
            'P_USER_W': str(user_w),
            'P_DEPTH': str(depth),
            'P_HAS_TKEEP': str(int(bool(hasattr(core.sink, 'tkeep')))),
            'P_PACKET_MODE': str(int(bool(packet_mode))),
            'P_TEST_LENGTH': str(32 * depth),
        }
        self.run_testbench(core, test_module, ports, vcd_file=vcd_file, env=env)

        # If packet mode, run extra testbench specific for that mode
        if packet_mode:
            test_module = 'tb.tb_axi_stream_fifo_packet_mode'
            base_name = f'tb_axi_stream_fifo_packet_mode_{data_w}_{user_w}_{depth}'
            vcd_file = in_waveform_dir(f'{base_name}.vcd')
            self.run_testbench(core, test_module, ports, vcd_file=vcd_file, env=env)

    @pytest.mark.parametrize('data_w,user_w,depth,max_fifo_depth', [
        (8, 2, 16, 8),
        (8, 2, 16, 7),
    ])
    def test_fast_clk_axi_stream_fifo(self, data_w: int, user_w: int, depth: int, max_fifo_depth: int):
        from hdl_utils.amaranth_utils.axi_stream_fifo import FastClkAXIStreamFIFO
        from hdl_utils.amaranth_utils.skid_buffer import AXISkidBuffer
        import math
        n_fifos = int(math.ceil(depth / max_fifo_depth))
        core = FastClkAXIStreamFIFO(
            data_w=data_w,
            user_w=user_w,
            depth=depth,
            max_fifo_depth=max_fifo_depth,
        )
        assert len(core.fifos) == n_fifos
        for i in range(n_fifos - 1):
            assert isinstance(core.fifos[i].skid_buffer_in, AXISkidBuffer)
            assert getattr(core.fifos[i], 'skid_buffer_out') is None
        assert isinstance(core.fifos[-1].skid_buffer_in, AXISkidBuffer)
        assert isinstance(core.fifos[-1].skid_buffer_out, AXISkidBuffer)
        assert core.sink is core.fifos[0].skid_buffer_in.sink
        assert core.source is core.fifos[-1].skid_buffer_out.source
        ports = core.get_ports()
        test_module = 'tb.tb_axi_stream_pass_through'
        vcd_file = in_waveform_dir(f'tb_fast_clk_axi_stream_fifo_{data_w}_{user_w}_{depth}_{max_fifo_depth}.vcd')
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
        vcd_file = in_waveform_dir(f'tb_axi_stream_fifo_cdc_{data_w}_{user_w}_{depth}{pfx}.vcd')
        env = {
            'P_DATA_W': str(data_w),
            'P_USER_W': str(user_w),
            'P_DEPTH': str(depth)
        }
        self.run_testbench(core, test_module, ports,
                           vcd_file=vcd_file, env=env)

    @pytest.mark.parametrize('data_w,user_w,reg_output', [(8, 2, False), (8, 2, True)])
    def test_axi_stream_skid_buffer(self, data_w: int, user_w: int, reg_output: bool):
        from hdl_utils.amaranth_utils.skid_buffer import AXISkidBuffer

        core = AXISkidBuffer(
            data_w=data_w,
            user_w=user_w,
            reg_output=reg_output,
        )
        ports = core.get_ports()
        test_module = 'tb.tb_axi_stream_pass_through'
        postfix = f'_r' if reg_output else ''
        vcd_file = in_waveform_dir(f'tb_axi_stream_skid_buffer_{data_w}_{user_w}{postfix}.vcd')
        env = {
            'P_DATA_W': str(data_w),
            'P_USER_W': str(user_w),
            'P_HAS_TKEEP': str(int(bool(hasattr(core.sink, 'tkeep')))),
            'P_REG_OUTPUT': str(int(reg_output)),
            'P_TEST_LENGTH': str(32),
        }
        self.run_testbench(core, test_module, ports, vcd_file=vcd_file, env=env)

    @pytest.mark.parametrize('data_w,user_w', [(8, 2)])
    def test_axi_stream_output_reg(self, data_w: int, user_w: int):
        from hdl_utils.amaranth_utils.skid_buffer import AXISOutputReg

        core = AXISOutputReg(
            data_w=data_w,
            user_w=user_w,
        )
        ports = core.get_ports()
        test_module = 'tb.tb_axi_stream_pass_through'
        vcd_file = in_waveform_dir(f'tb_axi_stream_xx_{data_w}_{user_w}.vcd')
        env = {
            'P_DATA_W': str(data_w),
            'P_USER_W': str(user_w),
            'P_HAS_TKEEP': str(int(bool(hasattr(core.sink, 'tkeep')))),
            'P_TEST_LENGTH': str(32),
        }
        self.run_testbench(core, test_module, ports, vcd_file=vcd_file, env=env)

    @pytest.mark.parametrize('data_w,user_w,no_tkeep,add_input_buffer,add_output_buffer', [
        (8, 2, False, False, False),
        (8, 2, False, False, True),
        (8, 2, False, True, False),
        (8, 2, False, True, True),
        (8, 2, True, False, False),
        (8, 2, True, False, True),
        (8, 2, True, True, False),
        (8, 2, True, True, True),
    ])
    def test_axi_stream_skid_buffer_wrapper(self, data_w: int, user_w: int,
                                            no_tkeep: bool,
                                            add_input_buffer: bool,
                                            add_output_buffer: bool):
        from hdl_utils.amaranth_utils.skid_buffer import AXISkidBuffer
        from hdl_utils.amaranth_utils.axi_stream_fifo import AXIStreamFIFO

        depth = 4
        fifo_core = AXIStreamFIFO(data_w=data_w, user_w=user_w, no_tkeep=no_tkeep, depth=depth)
        core = AXISkidBuffer.wrap_core(
            core=fifo_core,
            core_sink=fifo_core.sink,
            core_source=fifo_core.source,
            add_input_buffer=add_input_buffer,
            add_output_buffer=add_output_buffer,
        )
        ports = core.get_ports()
        test_module = 'tb.tb_axi_stream_pass_through'
        vcd_file = in_waveform_dir(f'tb_skid_buffer_wrapper_{data_w}_{user_w}_{add_input_buffer}_{add_output_buffer}.vcd')
        env = {
            'P_DATA_W': str(data_w),
            'P_USER_W': str(user_w),
            'P_HAS_TKEEP': str(int(bool(not no_tkeep))),
            'P_TEST_LENGTH': str(4 * 32),
            'P_ADD_INPUT_BUFFER': str(int(bool(add_input_buffer))),
            'P_ADD_INPUT_BUFFER': str(int(bool(add_output_buffer))),
        }
        self.run_testbench(core, test_module, ports, vcd_file=vcd_file, env=env)

    @pytest.mark.parametrize(
        'DWI,DWO,UWI,add_skid_buffers',
        [
            (24, 8, 3, False),
            (48, 24, 4, False),
            (24, 8, 3, True),

            (8, 24, 1, False),
            (24, 48, 2, False),
            (24, 48, 2, True),

            (8, 8, 1, True),
        ]
    )
    def test_width_converter(self, DWI, DWO, UWI, add_skid_buffers):
        from hdl_utils.amaranth_utils.axi_stream_width_converter import \
            AXIStreamWidthConverter

        core = AXIStreamWidthConverter(
            data_w_i=DWI,
            data_w_o=DWO,
            user_w_i=UWI,
        )
        ports = core.get_ports()
        base_name = f'tb_axi_stream_width_converter_{DWI}_{DWO}_{UWI}'

        if DWO > DWI:
            test_module = 'tb.tb_axi_stream_width_converter_up'
        else:
            test_module = 'tb.tb_axi_stream_width_converter_down'

        if add_skid_buffers:
            from hdl_utils.amaranth_utils.skid_buffer import AXISkidBuffer
            core = AXISkidBuffer.wrap_core(
                core=core,
                add_input_buffer=True,
                add_output_buffer=True,
                core_sink=core.sink,
                core_source=core.source,
            )
            ports = core.get_ports()
            base_name += '_sb'

        vcd_file = in_waveform_dir(f'{base_name}.vcd')
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
            # (16, 8, 0),  # EXPECT FAIL: zero user width
            (40, 24, 4),  # EXPECT FAIL: 40 % 24 == 16

            # (8, 16, 0),  # EXPECT FAIL: zero user width
            (24, 40, 2),  # EXPECT FAIL: 40 % 24 == 16
        ]
    )
    def test_width_converter_bad(self, DWI, DWO, UWI):
        from hdl_utils.amaranth_utils.axi_stream_width_converter import \
            AXIStreamWidthConverter

        with pytest.raises(AssertionError):
            AXIStreamWidthConverter(
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
        vcd_file = in_waveform_dir('tb_axi_stream_to_full.py.vcd')
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
        vcd_file = in_waveform_dir('tb_axi_dma.py.vcd')
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
        vcd_file = in_waveform_dir('tb_axi_dma_triple_buffer.py.vcd')
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
        vcd_file = in_waveform_dir(f'tb_axi_stream_splitter_{data_w}_{user_w}_{no_tkeep}_{n_split}.vcd')
        env = {
            'P_DATA_W': str(data_w),
            'P_USER_W': str(user_w),
            'P_NO_TKEEP': str(int(no_tkeep)),
            'P_N_SPLIT': str(n_split),
        }
        self.run_testbench(core, test_module, ports,
                           vcd_file=vcd_file, env=env)

    @pytest.mark.parametrize('data_w,user_w', [(8, 2)])
    def test_axi_stream_packet_rate_limiter(self, data_w: int, user_w: int):
        from hdl_utils.amaranth_utils.axi_stream_packet_rate_limiter import AXISPacketRateLimiter

        core = AXISPacketRateLimiter(
            data_w=data_w,
            user_w=user_w,
        )
        ports = core.get_ports()
        env = {
            'P_DATA_W': str(data_w),
            'P_USER_W': str(user_w),
            'P_HAS_TKEEP': str(int(bool(hasattr(core.sink, 'tkeep')))),
            'P_TEST_LENGTH': str(32),
        }

        # Test pass through
        test_module = 'tb.tb_axi_stream_pass_through'
        base_name = f'tb_axi_stream_packet_rate_limiter_pass_through_{data_w}_{user_w}'
        vcd_file = in_waveform_dir(f'{base_name}.vcd')
        self.run_testbench(core, test_module, ports, vcd_file=vcd_file, env=env)

        # Test limiter
        test_module = 'tb.tb_axi_stream_packet_rate_limiter'
        base_name = f'tb_axi_stream_packet_rate_limiter_{data_w}_{user_w}'
        vcd_file = in_waveform_dir(f'{base_name}.vcd')
        self.run_testbench(core, test_module, ports, vcd_file=vcd_file, env=env)
