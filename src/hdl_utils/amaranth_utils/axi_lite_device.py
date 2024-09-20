from amaranth import Elaboratable, Module, Signal
from hdl_utils.amaranth_utils.interfaces.axi_lite import AXI4LiteSignature


class AxiLiteDevice(Elaboratable):
    def __init__(self, addr_w, data_w, registers_map, domain='sync'):
        self.addr_w = addr_w
        self.data_w = data_w
        self.registers_map = registers_map
        self.domain = domain
        self.axi_lite = AXI4LiteSignature.create_slave(
            data_w=data_w,
            addr_w=addr_w,
            path=['s_axil']
        )
        # Raw registers
        self.registers = {
            r_addr: Signal(data_w, name=f'reg_0x{r_addr:08x}')
            for _, r_dir, r_addr, r_fields in registers_map
        }
        # Register fields
        self.reg_fields = {}
        for r_name, r_dir, r_addr, r_fields in registers_map:
            for f_name, f_size, f_offset in r_fields:
                self.reg_fields[f_name] = Signal(f_size, name=f_name)

    def get_ports(self):
        ports = []
        ports += self.axi_lite.extract_signals()
        ports += list(self.reg_fields.values())
        return ports

    def elaborate(self, platform):
        m = Module()
        sync = m.d[self.domain]
        comb = m.d.comb

        # Registers
        for _, r_dir, addr, r_fields in self.registers_map:
            for name, size, offset in r_fields:
                if r_dir == 'rw':
                    comb += self.reg_fields[name].eq(
                        self.registers[addr][offset:offset+size]
                    )
                else:
                    comb += self.registers[addr][offset:offset+size].eq(
                        self.reg_fields[name]
                    )

        we = Signal()
        wr_addr = Signal(self.addr_w)
        wr_data = Signal(self.data_w)

        with m.If(self.axi_lite.aw_accepted()):
            sync += wr_addr.eq(self.axi_lite.awaddr)

        with m.If(self.axi_lite.w_accepted()):
            sync += wr_data.eq(self.axi_lite.wdata)

        for _, r_dir, r_addr, r_fields in self.registers_map:
            if r_dir == 'rw':
                with m.If((wr_addr == r_addr) & (we == 1)):
                    sync += self.registers[r_addr].eq(wr_data)

        for _, r_dir, r_addr, r_fields in self.registers_map:
            with m.If(
                self.axi_lite.ar_accepted() & (self.axi_lite.araddr == r_addr)
            ):
                sync += self.axi_lite.rdata.eq(self.registers[r_addr])

        # Axi Lite Slave Interface

        comb += self.axi_lite.rresp.eq(0)
        comb += self.axi_lite.bresp.eq(0)

        with m.FSM(domain=self.domain) as fsm_rd:
            with m.State("IDLE"):
                comb += self.axi_lite.arready.eq(1)
                comb += self.axi_lite.rvalid.eq(0)
                with m.If(self.axi_lite.ar_accepted()):
                    m.next = "READ"
            with m.State("READ"):
                comb += self.axi_lite.arready.eq(0)
                comb += self.axi_lite.rvalid.eq(1)
                with m.If(self.axi_lite.r_accepted()):
                    sync += self.axi_lite.rdata.eq(0)
                    m.next = "IDLE"

        with m.FSM(domain=self.domain) as fsm_wr:
            with m.State("IDLE"):
                comb += [self.axi_lite.awready.eq(1),
                         self.axi_lite.wready.eq(1),
                         self.axi_lite.bvalid.eq(0),
                         we.eq(0),]
                with m.If(self.axi_lite.aw_accepted() & self.axi_lite.w_accepted()):
                    m.next = "DONE"
                with m.Elif(self.axi_lite.aw_accepted()):
                    m.next = "WAITING_DATA"
                with m.Elif(self.axi_lite.w_accepted()):
                    m.next = "WAITING_ADDR"
            with m.State("WAITING_DATA"):
                comb += [self.axi_lite.awready.eq(0),
                         self.axi_lite.wready.eq(1),
                         self.axi_lite.bvalid.eq(0),
                         we.eq(0),]
                with m.If(self.axi_lite.w_accepted()):
                    m.next = "DONE"
            with m.State("WAITING_ADDR"):
                comb += [self.axi_lite.awready.eq(1),
                         self.axi_lite.wready.eq(0),
                         self.axi_lite.bvalid.eq(0),
                         we.eq(0),]
                with m.If(self.axi_lite.aw_accepted()):
                    m.next = "DONE"
            with m.State("DONE"):
                comb += [self.axi_lite.awready.eq(0),
                         self.axi_lite.wready.eq(0),
                         self.axi_lite.bvalid.eq(1),
                         we.eq(1),]
                with m.If(self.axi_lite.b_accepted()):
                    m.next = "IDLE"

        return m
