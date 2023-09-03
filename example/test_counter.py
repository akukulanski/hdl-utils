from amaranth_cocotb import run
import unittest


class TestCores(unittest.TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_counter(self):
        from counter import Counter
        core = Counter(width=8)
        ports = core.get_ports()
        test_module = 'tb_counter'
        vcd_file = './counter.vcd'
        run(core, test_module, ports=ports, vcd_file=vcd_file)
