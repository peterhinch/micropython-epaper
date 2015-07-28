# flash.py module for Embedded Artists' 2.7 inch E-paper Display. Imported by epaper.py
# Provides optional support for the flash memory chip
# Peter Hinch
# version 0.2
# 28th July 2015

# Copyright 2013 Pervasive Displays, Inc, 2015 Peter Hinch
#
# Licensed under the Apache License, Version 2.0 (the "License")
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#   http:#www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied.  See the License for the specific language
# governing permissions and limitations under the License.

# Sectors are 4096 bytes. 256*4096*8 = 8Mbit: there are 256 sectors but each page takes two

# TODO
# Use protected methods

# Terminology: a sector is 4096 bytes, the size of sector on the flash device
# a block is 512 bytes, this is defined in the block protocol

import pyb
from epd import PINS
# FLASH MX25V8005 8Mbit flash chip command set (50MHz  max clock)
FLASH_WREN = const(0x06)
FLASH_WRDI = const(0x04)
FLASH_RDID = const(0x9f)
FLASH_RDSR = const(0x05)
FLASH_WRSR = const(0x01)
FLASH_READ = const(0x03)                        # read at half frequency
FLASH_FAST_READ = const(0x0b)                   # read at full frequency
FLASH_SE = const(0x20)
FLASH_BE = const(0x52)
FLASH_CE = const(0x60)
FLASH_PP = const(0x02)
FLASH_DP = const(0xb9)
FLASH_RDP = const(0xab)
FLASH_REMS = const(0x90)
FLASH_NOP = const(0xff)

# status register bits
FLASH_WIP = const(0x01)
FLASH_WEL = const(0x02)
FLASH_BP0 = const(0x04)
FLASH_BP1 = const(0x08)
FLASH_BP2 = const(0x10)

FLASH_SECTOR_SIZE = const(4096)

# currently supported chip
FLASH_MFG = 0xef # Winbond
FLASH_ID = 0x4016 #W25Q32 memory type and capacity

def cp(source, dest):                           # Utility to copy a file e.g. to flash
    with open(source, 'rb') as infile:          # Caller should handle any OSError
        with open(dest,'wb') as outfile:        # e.g file not found
            while True:
                buf = infile.read(100)
                outfile.write(buf)
                if len(buf) < 100:
                    break

# FlashClass
# The flash and epaper deviices use different SPI modes. You must issue objFlash.flash_begin() before attempting to access
# the device, and objFlash.flash_end() afterwards
# All address method arguments are byte addresses. Hence to erase block 100, issue instance.sector_erase(100*4096)
# Sectors must be erased (to 0xff) before they can be written. Writing is done in 256 byte pages. The write method
# handles this transparently.
class FlashException(Exception):
    pass

class FlashClass(object):
    def __init__(self, intside):
        self.spi_no = PINS['SPI_BUS'][intside]
        self.pinCS = pyb.Pin(PINS['FLASH_CS'][intside], mode = pyb.Pin.OUT_PP)
        self.pinCS.high()
        self.sector0 = bytearray(FLASH_SECTOR_SIZE)
        self.current_sector = None              # Current flash sector number for writing
        self.flashsector = bytearray(FLASH_SECTOR_SIZE)
        self.verbose = False                    # I think it works now
        self.mountpoint = '/fc'
        self.begin()
        self._read(self.sector0, 0)             # Sector zero always in buffer

    def begin(self):                            # Baud rates of 50MHz supported by chip
        self.pinCS.high()
        self.spi = pyb.SPI(self.spi_no, pyb.SPI.MASTER, baudrate=21000000, polarity=1, phase=1, bits=8) # default mode 3: Polarity 1 Phase 0 MSB first
        if not self._available():
            raise FlashException("Unsupported flash device")

    def end(self):                              # Shutdown before using EPD
        self.sync()
        self.pinCS.high()
        self.spi.deinit()

    def _available(self):                       # return True if the chip is supported
        self.info()                             # initial read to reset the chip
        manufacturer, device = self.info()
        return (FLASH_MFG == manufacturer) and (FLASH_ID == device)

    def info(self):
        self.pinCS.low()
        pyb.udelay(1000)                        # FLASH wake up delay
        self.spi.send(FLASH_RDID)
        manufacturer = self.spi.send_recv(FLASH_NOP)[0]
        id_high = self.spi.send_recv(FLASH_NOP)[0]
        id_low = self.spi.send_recv(FLASH_NOP)[0]
        self.pinCS.high()
        return manufacturer, id_high << 8 | id_low

    def _read(self, buf, address, count = None):# Read data into preallocated bytearray
        self._await()
        end = len(buf) if count is None else min(count, len(buf))
        index = 0
        while index < end :
            self.pinCS.low()
            self.spi.send(FLASH_FAST_READ)
            self.spi.send((address >> 16) & 0xff)
            self.spi.send((address >> 8) & 0xff)
            self.spi.send(address & 0xff)
            self.spi.send(FLASH_NOP) # dummy byte for fast read (to 50MHz)
            while True :
                buf[index] = self.spi.send_recv(FLASH_NOP)[0]
                address += 1
                index += 1
                if index >= end or address % FLASH_SECTOR_SIZE == 0 :
                    break
            self.pinCS.high()
        self._await()

    def _await(self):                           # Wait for device not busy
        self.pinCS.low()
        self.spi.send(FLASH_RDSR)
        busy = True
        while busy:
            busy = (FLASH_WIP & self.spi.send_recv(FLASH_NOP)[0]) != 0
        self.pinCS.high()

    def _write_enable(self):
        self._await()
        self.pinCS.low()
        self.spi.send(FLASH_WREN)
        self.pinCS.high()

#    def _write_disable(self):
#        self._await()
#        self.pinCS.low()
#        self.spi.send(FLASH_WRDI)
#        self.pinCS.high()

    def _write(self, buf, address):             # Write data in 256 byte blocks
        end = len(buf)
        index = 0
        while index < end :
            self._write_enable()                # Wait for any previous write to complete (upto 3mS) and set enable bit
            self.pinCS.low()
            self.spi.send(FLASH_PP) # Page program 256 bytes max
            self.spi.send((address >> 16) & 0xff)
            self.spi.send((address >> 8) & 0xff)
            self.spi.send(address & 0xff)
            while True:
                self.spi.send(buf[index])
                address += 1
                index += 1
                if index >= end or address & 0xff == 0 :
                    break
            self.pinCS.high() # Kick off the write
        self._await()

    def _sector_erase(self, address):
        self._write_enable()
        self.pinCS.low()
        self.spi.send(FLASH_SE)
        self.spi.send((address >> 16) & 0xff)
        self.spi.send((address >> 8) & 0xff)
        self.spi.send(address & 0xff)
        self.pinCS.high()
        self._await()

    def _readblock(self, blocknum, buf):
        sector = blocknum // 8
        index = (blocknum << 9) % FLASH_SECTOR_SIZE # Byte index into current sector
        if sector == 0:                         # Sector zero always read from cache
            buf[0 : 512] = self.sector0[index : index +512]
            return 0
        self._write_cached_data()               # Ensure flash is up to date
        self._read(buf, blocknum << 9)
        return 0

    def _writeblock(self, blocknum, buf):       # Write a single 512 byte block
        sector = blocknum // 8                  # Flash sector: 8 blocks per sector
        index = (blocknum << 9) % FLASH_SECTOR_SIZE # Byte index into current sector
        if sector == 0:                         # Update the cache
            self.sector0[index : index + 512] = buf
            return 0
        if self.current_sector is None :        # No sector is cached
            self.current_sector = sector
            self._read(self.flashsector, sector * FLASH_SECTOR_SIZE) # Read new sector
        elif sector != self.current_sector:     # We are going to write to a new sector
            self._write_cached_data()           # Write out the old sector
            self.current_sector = sector        # New one is current
            self._read(self.flashsector, sector * FLASH_SECTOR_SIZE) # Read new sector
        self.flashsector[index : index + 512] = buf # Update cached data
        return 0

    def _write_cached_data(self):               # Write out the current cached sector
        if self.current_sector is not None :    # A sector is cached
            address = self.current_sector * FLASH_SECTOR_SIZE
            assert address > 0, "Address is zero"
            self._sector_erase(address)
            self._write(self.flashsector, address)
            if self.verbose:
                print("Write flash sector ", self.current_sector)
            self.current_sector = None          # No sector is cached
        else:
            if self.verbose:
                print("write_cached_data: nothing to do")

# ******* THE BLOCK PROTOCOL *******
# In practice MicroPython currently only reads and writes single blocks but the protocol calls
# for multiple blocks so these functions aim to provide that capability
    def readblocks(self, blocknum, buf):
        buflen = len(buf)
        if buflen == 512:
            return self._readblock(blocknum, buf)
        start = 0
        blockbuf = bytearray[512]
        while buflen - start  > 0:
            self._readblock(blocknum, blockbuf)
            buf[start : start +512] = blockbuf
            start += 512
            blocknum += 1
        return 0

    def writeblocks(self, blocknum, buf):
        buflen = len(buf)
        if buflen == 512:
            return self._writeblock(blocknum, buf)
        start = 0
        while buflen - start  > 0 :
            self._writeblock(blocknum, buf[start : start + 512])
            start += 512
            blocknum += 1
        return 0

    def sync(self):
        if self.verbose:
            print("Sync called")
        self._write_cached_data()
        self._read(self.flashsector, 0)         # Read a copy of sector zero
        try:
            next(z for z in zip(self.flashsector, self.sector0) if z[0] != z[1])
            self._sector_erase(0)               # Cache differs from copy in device
            self._write(self.sector0, 0)        # write it out
            if self.verbose:
                print("Sector zero updated")
        except StopIteration:
            pass                                # Sector zero is up to date
        return 0

    def count(self):
        return 2048 # 2048*512 = 1MByte
