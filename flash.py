# flash.py module for Embedded Artists' 2.7 inch E-paper Display. Imported by epaper.py
# Provides optional support for the flash memory chip
# Peter Hinch
# version 0.7
# 17 June 2018 Block protocol replaced with IOCTL
# 2 Mar 2016 Power control support removed

# Copyright 2013 Pervasive Displays, Inc, 2015 Peter Hinch
#
# Licensed under the Apache License, Version 2.0 (the "License")
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied.  See the License for the specific language
# governing permissions and limitations under the License.

# Rev D of the Pervasive Displays module uses a Winbond W25Q32 chip: an 8 MB Flash chip
# Sectors are 4096 bytes. 1024*4096*8 = 32Mbit: there are 1024 sectors

# Terminology:
# a sector is 4096 bytes, the size of data unit on the flash device for erasure
# a page is 256 bytes and is the minimum data unit which may be written to the device
# a block is 512 bytes, this is defined in the block protocol for FAT

import pyb 

# Winbond W25Q32 command set
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
FLASH_SECTOR_MASK = const(0xfff)

# currently supported chip
FLASH_MFG = 0xef # Winbond
FLASH_ID = 0x4016 #W25Q32 memory type and capacity

# Dumb file copy utility to help with managing flash contents at the REPL.
def cp(source, dest):
    if dest.endswith('/'):                      # minimal way to allow
        dest = ''.join((dest, source.split('/')[-1]))  # cp /sd/file /fc/
    with open(source, 'rb') as infile:          # Caller should handle any OSError
        with open(dest,'wb') as outfile:        # e.g file not found
            while True:
                buf = infile.read(100)
                outfile.write(buf)
                if len(buf) < 100:
                    break

# FlashClass
# The flash and epaper deviices use different SPI modes. You must issue objFlash.begin() before attempting to access
# the device, and objFlash.end() afterwards
# All address method arguments are byte addresses. Hence to erase block 100, issue objFlash.sector_erase(100*4096)
# Sectors must be erased (to 0xff) before they can be written. Writing is done in 256 byte pages. The _write() method
# handles paging transparently but does assume target pages are erased.
class FlashException(Exception):
    pass

BUFFER = const(0)                               # Indices into sector descriptor
DIRTY = const(1)

class FlashClass(object):
    def __init__(self, intside):
        from panel import getpins
        pins = getpins(intside)
        self.spi_no = pins['SPI_BUS']
        self.pinCS = pyb.Pin(pins['FLASH_CS'], mode = pyb.Pin.OUT_PP)
        self.buff0 = bytearray(FLASH_SECTOR_SIZE)
        self.buff1 = bytearray(FLASH_SECTOR_SIZE)
        self.current_sector = None              # Current flash sector number for writing
        self.prev_sector = None
        self.buffered_sectors = dict()          # sector : sector descriptor which is [buffer, dirty]
        self.mountpoint = '/fc'
        self.begin()

    def begin(self):                            # Baud rates of 50MHz supported by chip
        self.pinCS.high()
        self.spi = pyb.SPI(self.spi_no, pyb.SPI.MASTER, baudrate = 21000000, polarity = 1, phase = 1, bits = 8)
        if not self._available():               # Includes 1mS wakeup delay
            raise FlashException("Unsupported flash device")

    def end(self):                              # Shutdown before using EPD
        self.synchronise()
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
                if index >= end or address & FLASH_SECTOR_MASK == 0 :
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

#    def _write_disable(self): # Unused function
#        self._await()
#        self.pinCS.low()
#        self.spi.send(FLASH_WRDI)
#        self.pinCS.high()

    def _write(self, buf, address):             # Write data in 256 byte pages
        end = len(buf)
        index = 0
        while index < end :
            self._write_enable()                # Wait for any previous write to complete (upto 3mS) and set enable bit
            self.pinCS.low()
            self.spi.send(FLASH_PP)             # Page program 256 bytes max
            self.spi.send((address >> 16) & 0xff)
            self.spi.send((address >> 8) & 0xff)
            self.spi.send(address & 0xff)
            while True:
                self.spi.send(buf[index])
                address += 1
                index += 1
                if index >= end or address & 0xff == 0 :
                    break
            self.pinCS.high()                   # Kick off the write
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
        sector = blocknum // 8                  # Flash sector: 8 blocks per sector
        if sector in self.buffered_sectors:     # It is cached: read from cache
            cache = self.buffered_sectors[sector][BUFFER]
            index = (blocknum << 9) & FLASH_SECTOR_MASK # Byte index into current sector
            buf[:] = cache[index : index + 512]
        else:
            self._read(buf, blocknum << 9)

    def _writesector(self, sector):             # Erase and write a cached sector if neccessary.
        if self.buffered_sectors[sector][DIRTY]:# Caller ensures it is actually cached
            self.buffered_sectors[sector][DIRTY] = False # cache will be clean
            address = sector * FLASH_SECTOR_SIZE
            self._sector_erase(address)
            cache = self.buffered_sectors[sector][BUFFER]
            self._write(cache, address)

    def _writeblock(self, blocknum, buf):       # Write a single 512 byte block
        sector = blocknum // 8                  # Flash sector: 8 blocks per sector
        index = (blocknum << 9) & FLASH_SECTOR_MASK # Byte index into current sector
        if sector in self.buffered_sectors:     # It is cached: update cache and return
            cache = self.buffered_sectors[sector][BUFFER]
            self.buffered_sectors[sector][DIRTY] = True
            cache[index : index + 512] = buf
            return
        cache = None
        if self.current_sector is None :        # Program start: No sector is cached
            self.current_sector = sector
            cache = self.buff0                  # allocate buff0
        elif self.prev_sector is None:          # one sector was cached
            self.prev_sector = self.current_sector
            self.current_sector = sector
            cache = self.buff1                  # allocate buf1
        if cache is not None:                   # A new buffer was allocated
            self._read(cache, sector * FLASH_SECTOR_SIZE) # Read new sector
            self.buffered_sectors[sector] = [cache, True] # put in dict marked dirty
            cache[index : index + 512] = buf    # apply mods
            return
                                                # Normal running: two sectors already cached. new sector
        self._writesector(self.prev_sector)     # needs to be cached. Write out old sector and 
        cache = self.buffered_sectors.pop(self.prev_sector)[BUFFER] # remove from dict retrieving its buffer
        self.buffered_sectors[sector] = [cache, True]   # Assign its buffer to new sector, mark dirty
        self.prev_sector = self.current_sector
        self.current_sector = sector
        self._read(cache, sector * FLASH_SECTOR_SIZE) # Read new sector
        cache[index : index + 512] = buf        # and update

# ******* THE IOCTL PROTOCOL *******
# In practice MicroPython currently only reads and writes single blocks but the protocol calls
# for multiple blocks so these functions aim to provide that capability
    def readblocks(self, blocknum, buf):
        buflen = len(buf)
        if buflen == 512:                       # skip creating the blockbuf
            return self._readblock(blocknum, buf)
        start = 0
        blockbuf = bytearray[512]
        while buflen - start  > 0:
            self._readblock(blocknum, blockbuf)
            buf[start : start +512] = blockbuf
            start += 512
            blocknum += 1

    def writeblocks(self, blocknum, buf):
        buflen = len(buf)
        start = 0
        while buflen - start  > 0 :
            self._writeblock(blocknum, buf[start : start + 512])
            start += 512
            blocknum += 1

    def synchronise(self):  # Renamed: ioctl protocol doesn't like count() so may not like sync()
        for sector in self.buffered_sectors:
            self._writesector(sector)           # Only if dirty

    def ioctl(self, op, arg):
        if op == 3:
            self.synchronise()
        if op == 4: # get number of blocks
            return 8192
        if op == 5: # get block size
            return 512
