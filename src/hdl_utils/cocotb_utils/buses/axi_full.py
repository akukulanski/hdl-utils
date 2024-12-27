# Copyright (c) 2014 Potential Ventures Ltd
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of Potential Ventures Ltd,
#       SolarFlare Communications Inc nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL POTENTIAL VENTURES LTD BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""Drivers for Advanced Microcontroller Bus Architecture."""

import sys
import cocotb
from cocotb.triggers import RisingEdge, ReadOnly, Lock
from cocotb_bus.drivers import BusDriver
from cocotb.binary import BinaryValue

import array


class AXIProtocolError(Exception):
    pass


class AXI4Slave(BusDriver):
    '''
    AXI4 Slave

    Monitors an internal memory and handles read and write requests.
    '''
    _signals = [
        "ARREADY", "ARVALID", "ARADDR",
        "ARLEN",   "ARSIZE",  "ARBURST", "ARPROT",
        "RREADY",  "RVALID",  "RDATA",   "RLAST",
        "AWREADY", "AWADDR",  "AWVALID",
        "AWPROT",  "AWSIZE",  "AWBURST", "AWLEN",
        "WREADY",  "WVALID",  "WDATA",
    ]

    _optional_signals = [
        "WLAST",   "WSTRB",
        "BVALID",  "BREADY",  "BRESP",   "RRESP",
        "RCOUNT",  "WCOUNT",  "RACOUNT", "WACOUNT",
        "ARLOCK",  "AWLOCK",  "ARCACHE", "AWCACHE",
        "ARQOS",   "AWQOS",   "ARID",    "AWID",
        "BID",     "RID",     "WID"
    ]

    def __init__(self, entity, name, clock, memory, baseaddr=0, read_callback=None,
                 big_endian=False, **kwargs):

        super().__init__(entity, name, clock, **kwargs)
        self.clock = clock

        self.big_endian = big_endian
        self.bus.ARREADY.setimmediatevalue(1)
        self.bus.RVALID.setimmediatevalue(0)
        self.bus.RLAST.setimmediatevalue(0)
        self.bus.AWREADY.setimmediatevalue(1)
        self.baseaddr = baseaddr
        self._memory = memory

        cocotb.fork(self._read_data())
        cocotb.fork(self._write_data())

    def _size_to_bytes_in_beat(self, AxSIZE):
        if AxSIZE <= 7:
            return 2 ** AxSIZE
        return None

    async def reset(self):
        self.bus.AWPROT = 0
        self.bus.ARPROT = 0
        rst = getattr(self.entity, self.bus._name + "_ARESETN")
        await RisingEdge(self.clock)
        rst.value = 0
        await RisingEdge(self.clock)
        rst.value = 1

    async def _write_data(self):
        while True:
            self.bus.BRESP.value = 0
            self.bus.WREADY.value = 0
            self.bus.BVALID.value = 0
            self.bus.AWREADY.value = 1
            await RisingEdge(self.clock)
            while not self.bus.AWVALID.value:
                await RisingEdge(self.clock)
            _awaddr = int(self.bus.AWADDR)
            _awlen = int(self.bus.AWLEN)
            _awsize = int(self.bus.AWSIZE)
            self.bus.AWREADY.value = 0

            burst_length = _awlen + 1
            bytes_in_beat = self._size_to_bytes_in_beat(_awsize)

            burst_count = burst_length

            for b in range(burst_length):
                self.bus.WREADY.value = 1
                await RisingEdge(self.clock)
                while not self.bus.WVALID.value:
                    await RisingEdge(self.clock)
                word = self.bus.WDATA.value
                word.big_endian = self.big_endian
                _burst_diff = burst_length - burst_count
                start_addr = _awaddr + b * bytes_in_beat
                end_addr = start_addr + bytes_in_beat
                self._memory[start_addr:end_addr] = array.array('B', word.buff)

            if not self.bus.WLAST.value:
                raise AXIProtocolError('WLAST != 1 when BURST Finished')

            self.bus.WREADY.value = 0
            self.bus.BVALID.value = 1
            self.bus.BRESP.value = 0
            while not self.bus.BREADY.value:
                await RisingEdge(self.clock)

            self.bus.BVALID.value = 0

    async def _read_data(self):
        self.bus.RDATA.value = 0
        self.bus.RRESP.value = 0

        while True:
            self.bus.ARREADY.value = 0
            while True:
                if self.bus.ARVALID.value:
                    self.bus.ARREADY.value = 1
                    break
                await RisingEdge(self.clock)

            await ReadOnly()
            _araddr = int(self.bus.ARADDR)
            _arlen = int(self.bus.ARLEN)
            _arsize = int(self.bus.ARSIZE)
            _arburst = int(self.bus.ARBURST)
            _arprot = int(self.bus.ARPROT)

            burst_length = _arlen + 1
            bytes_in_beat = self._size_to_bytes_in_beat(_arsize)

            word = BinaryValue(n_bits=bytes_in_beat*8, bigEndian=self.big_endian)

            if __debug__:
                self.log.debug(
                    "ARADDR  %d\n" % _araddr +
                    "ARLEN   %d\n" % _arlen +
                    "ARSIZE  %d\n" % _arsize +
                    "ARBURST %d\n" % _arburst +
                    "BURST_LENGTH %d\n" % burst_length +
                    "Bytes in beat %d\n" % bytes_in_beat)

            burst_count = burst_length

            await RisingEdge(self.clock)
            self.bus.ARREADY.value = 0

            while True:
                self.bus.RVALID.value = 1

                if self.bus.RREADY.value or (burst_count == burst_length):
                    _burst_diff = burst_length - burst_count
                    _st = _araddr - self.baseaddr + \
                        (_burst_diff * bytes_in_beat)
                    _end = _araddr - self.baseaddr + \
                        ((_burst_diff + 1) * bytes_in_beat)
                    word = self._memory[_st:_end]
                    word = ''.join(["{:02x}".format(x) for x in word[::-1]])

                    self.bus.RDATA.value = int(word, 16)

                    burst_count -= 1
                    if burst_count == 0:
                        burst_count = burst_length
                        self.bus.RLAST.value = 1
                        break
                await RisingEdge(self.clock)
            await RisingEdge(self.clock)
            while not self.bus.RREADY.value:
                await RisingEdge(self.clock)

            self.bus.RVALID.value = 0
            self.bus.RLAST.value = 0
            self.bus.RDATA.value = 0
