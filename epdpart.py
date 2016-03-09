# epd.py module for Embedded Artists' 2.7 inch E-paper Display. Imported by epaper.py
# Peter Hinch
# version 0.8
# 8th Mar 2016 Support for Adafruit module. This file implements fast mode.
# 29th Aug 2015 Improved power control support
# 17th Aug 2015 __exit__() sequence adjusted to conform with datasheet rather than Arduino code

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

import pyb, gc
EMBEDDED_ARTISTS = const(0)
ADAFRUIT = const(1)

EPD_OK = const(0) # error codes
EPD_UNSUPPORTED_COG = const(1)
EPD_PANEL_BROKEN = const(2)
EPD_DC_FAILED = const(3)

LINES_PER_DISPLAY = const(176)
BYTES_PER_LINE = const(33)
BYTES_PER_SCAN = const(44)
BITS_PER_LINE = const(264)

BORDER_BYTE_BLACK = const(0xff)
BORDER_BYTE_WHITE = const(0xaa)
BORDER_BYTE_NULL = const(0x00)

EPD_COMPENSATE = const(0)
EPD_WHITE = const(1)
EPD_INVERSE = const(2)
EPD_NORMAL = const(3)

EPD_BORDER_BYTE_NONE = const(0)
EPD_BORDER_BYTE_ZERO = const(1)
EPD_BORDER_BYTE_SET = const(2)
# LM75 Temperature sensor

LM75_ADDR = const(0x49)                         # LM75 I2C address
LM75_TEMP_REGISTER  = const(0)                  # LM75 registers
LM75_CONF_REGISTER  = const(1)

class LM75():
    def __init__(self, bus):                    # Check existence and wake it
        self._i2c = pyb.I2C(bus, pyb.I2C.MASTER)
        devices = self._i2c.scan()
        if not LM75_ADDR in devices:
            raise OSError("No LM75 device detected")
        self.wake()

    def wake(self):
        self._i2c.mem_write(0, LM75_ADDR, LM75_CONF_REGISTER)

    def sleep(self): 
        self._i2c.mem_write(1, LM75_ADDR, LM75_CONF_REGISTER) # put sensor in shutdown mode

    @property
    def temperature(self):                      # return temperature as integer in Celsius
        temp = bytearray(2)
        self._i2c.mem_read(temp, LM75_ADDR, LM75_TEMP_REGISTER)
        temperature = int(temp[0])
        return temperature if temperature < 128 else temperature -256 # sign bit: subtract once to clear, 2nd time to add its value

class EPDException(Exception):
    pass

def temperature_to_factor_10x(temperature):
    if temperature <= -10:
        return 170
    elif temperature <= -5:
        return 120
    elif temperature <= 5:
        return 80
    elif temperature <= 10:
        return 40
    elif temperature <= 15:
        return 30
    elif temperature <= 20:
        return 20
    elif temperature <= 40:
        return 10
    return 7

class EPD(object):
    def __init__(self, intside, model, compensate_temp):
        self.model = model
        self.compensate_temp = compensate_temp
        self.verbose = False
        gc.collect()
        from panel import getpins
        self.image_0 = bytearray(BYTES_PER_LINE * LINES_PER_DISPLAY) # 5808
        self.image_1 = bytearray(BYTES_PER_LINE * LINES_PER_DISPLAY) # 5808
        self.image = self.image_0
        self.image_old = self.image_1
        self.line_buffer = bytearray(111) # total 11727 bytes!
        for x in range(len(self.image_old)):
            self.image_old[x] = 0
        pins = getpins(intside)
        self.Pin_PANEL_ON = pyb.Pin(pins['PANEL_ON'], mode = pyb.Pin.OUT_PP)
        self.Pin_BORDER = pyb.Pin(pins['BORDER'], mode = pyb.Pin.OUT_PP)
        self.Pin_DISCHARGE = pyb.Pin(pins['DISCHARGE'], mode = pyb.Pin.OUT_PP)
        self.Pin_RESET = pyb.Pin(pins['RESET'], mode = pyb.Pin.OUT_PP)
        self.Pin_BUSY = pyb.Pin(pins['BUSY'], mode = pyb.Pin.IN)
        self.Pin_EPD_CS = pyb.Pin(pins['EPD_CS'], mode = pyb.Pin.OUT_PP)    # cs for e-paper display
        self.Pin_FLASH_CS = pyb.Pin(pins['FLASH_CS'], mode = pyb.Pin.OUT_PP) # Instantiate flash CS and set high
        self.Pin_MOSI = pyb.Pin(pins['MOSI'], mode = pyb.Pin.OUT_PP)
        self.Pin_SCK = pyb.Pin(pins['SCK'], mode = pyb.Pin.OUT_PP)
        self.base_stage_time = 630 # ms
        self.factored_stage_time = self.base_stage_time

        self.Pin_RESET.low()
        self.Pin_PANEL_ON.low()
        self.Pin_DISCHARGE.low()
        self.Pin_BORDER.low()
        self.Pin_EPD_CS.low()
        self.Pin_FLASH_CS.high()
        self.spi_no = pins['SPI_BUS']
        if model == EMBEDDED_ARTISTS:
            self.lm75 = LM75(pins['I2C_BUS'])   # early error if not working

    def set_temperature(self):                  # Optional
        self.factored_stage_time = self.base_stage_time * temperature_to_factor_10x(self.temperature) / 10

    def enter(self):                        # power up sequence
        if self.compensate_temp:
            self.set_temperature()
        if self.verbose:
            print(self.factored_stage_time, self.compensate_temp)
        self.status = EPD_OK
        self.Pin_RESET.low()
        self.Pin_PANEL_ON.low()
        self.Pin_DISCHARGE.low()
        self.Pin_BORDER.low()
                                                # Baud rate: data sheet says 20MHz max. Pyboard's closest (21MHz) was unreliable
        self.spi = pyb.SPI(self.spi_no, pyb.SPI.MASTER, baudrate=10500000, polarity=1, phase=1, bits=8) # 5250000 10500000 supported by Pyboard
        self._SPI_send(b'\x00\x00')
        pyb.delay(5)
        self.Pin_PANEL_ON.high()
        pyb.delay(10)

        self.Pin_RESET.high()
        self.Pin_BORDER.high()
        pyb.delay(5)

        self.Pin_RESET.low()
        pyb.delay(5)

        self.Pin_RESET.high()
        pyb.delay(5)

        while self.Pin_BUSY.value() == 1:            # wait for COG to become ready
            pyb.delay(1)

        # read the COG ID 
        cog_id = self._SPI_read(b'\x71\x00') & 0x0f

        if cog_id != 2: 
            self.status = EPD_UNSUPPORTED_COG
            self._power_off()
            raise EPDException("Unsupported EPD COG device: " +str(cog_id))
        # Disable OE
        self._SPI_send(b'\x70\x02')
        self._SPI_send(b'\x72\x40')

        # check breakage
        self._SPI_send(b'\x70\x0f')
        broken_panel = self._SPI_read(b'\x73\x00') & 0x80
        if broken_panel == 0:
            self.status = EPD_PANEL_BROKEN
            self._power_off()
            raise EPDException("EPD COG device reports broken status")
        # power saving mode
        self._SPI_send(b'\x70\x0b')
        self._SPI_send(b'\x72\x02')
        # channel select
        self._SPI_send(b'\x70\x01')
        self._SPI_send(b'\x72\x00\x00\x00\x7f\xff\xfe\x00\x00') # Channel select
        # high power mode osc
        self._SPI_send(b'\x70\x07')
        self._SPI_send(b'\x72\xd1')
        # power setting
        self._SPI_send(b'\x70\x08')
        self._SPI_send(b'\x72\x02')
        # Vcom level
        self._SPI_send(b'\x70\x09')
        self._SPI_send(b'\x72\xc2')
        # power setting
        self._SPI_send(b'\x70\x04')
        self._SPI_send(b'\x72\x03')
        # driver latch on
        self._SPI_send(b'\x70\x03')
        self._SPI_send(b'\x72\x01')
        # driver latch off
        self._SPI_send(b'\x70\x03')
        self._SPI_send(b'\x72\x00')

        pyb.delay(5)
        dc_ok = False
        for i in range(4):
            # charge pump positive voltage on - VGH/VDL on
            self._SPI_send(b'\x70\x05')
            self._SPI_send(b'\x72\x01')
            pyb.delay(240)
            # charge pump negative voltage on - VGL/VDL on
            self._SPI_send(b'\x70\x05')
            self._SPI_send(b'\x72\x03')
            pyb.delay(40)
            # charge pump Vcom on - Vcom driver on
            self._SPI_send(b'\x70\x05')
            self._SPI_send(b'\x72\x0f')
            pyb.delay(40)
            # check DC/DC
            self._SPI_send(b'\x70\x0f')
            dc_state = self._SPI_read(b'\x73\x00') & 0x40
            if dc_state == 0x40:
                dc_ok = True
                break
        if not dc_ok:
            self.status = EPD_DC_FAILED
            raise EPDException("EPD DC power failure") # __exit__() will power doen
        # output enable to disable
        self._SPI_send(b'\x70\x02')
        self._SPI_send(b'\x72\x04')
        return self

    def exit(self, *_):
        self._nothing_frame()
        self._dummy_line()
        pyb.delay(25)
        self.Pin_BORDER.low()
        pyb.delay(200)
        self.Pin_BORDER.high()

        self._SPI_send(b'\x70\x0B') # Conform with datasheet
        self._SPI_send(b'\x72\x00')
        # latch reset turn on
        self._SPI_send(b'\x70\x03')
        self._SPI_send(b'\x72\x01')
        # power off charge pump Vcom
        self._SPI_send(b'\x70\x05')
        self._SPI_send(b'\x72\x03')
        # power off charge pump neg voltage
        self._SPI_send(b'\x70\x05')
        self._SPI_send(b'\x72\x01')
        pyb.delay(120)
        # discharge internal on
        self._SPI_send(b'\x70\x04')
        self._SPI_send(b'\x72\x80')
        # power off all charge pumps
        self._SPI_send(b'\x70\x05')
        self._SPI_send(b'\x72\x00')
        # turn of osc
        self._SPI_send(b'\x70\x07')
        self._SPI_send(b'\x72\x01')
        pyb.delay(50)
        self._power_off()

    def _power_off(self):                       # turn of power and all signals
        self.Pin_RESET.low()
        self.Pin_PANEL_ON.low()
        self.Pin_BORDER.low()
        self.spi.deinit()
        self.Pin_SCK.init(mode = pyb.Pin.OUT_PP)
        self.Pin_SCK.low()
        self.Pin_MOSI.init(mode = pyb.Pin.OUT_PP)
        self.Pin_MOSI.low()
        # ensure SPI MOSI and CLOCK are Low before CS Low
        self.Pin_EPD_CS.low()
        # pulse discharge pin
        self.Pin_DISCHARGE.high()
        pyb.delay(150)
        self.Pin_DISCHARGE.low()

# USER INTERFACE
# clear_screen() calls clear_data() and, if show, EPD_clear()
# Clear screen, show image, called from show()
    def showdata(self):
        self.EPD_clear()
        self.EPD_image_0()

    def clear_data(self):
        for x in range(len(self.image)):
            self.image[x] = 0

# EPD_partial_image() - fast update of current image
    def refresh(self):
        self.use_old = True
        self.frame_data_repeat(EPD_NORMAL)      # This is where the time goes
        for x in range(len(self.image)):
            self.image_old[x] = self.image[x]   # this loop: 77ms out of 1.4s

    def exchange(self):
        self.EPD_image()

    @property
    def temperature(self):                      # return temperature as integer in Celsius
        if self.model == EMBEDDED_ARTISTS:
            return self.lm75.temperature
        else:
            return 25

# END OF USER INTERFACE

# clear display (anything -> white) called from clear_screen() *** works ***
    def EPD_clear(self):
        self.frame_fixed_repeat(0xff)
        self.frame_fixed_repeat(0xff)           # Some ghosting if you don't repeat
        self.frame_fixed_repeat(0xaa)
        self.frame_fixed_repeat(0xaa)
        self.zero()
        self.update_old()
        self.zero()

# assuming a clear (white) screen output an image called from show() *** works ***
    def EPD_image_0(self):
        self.frame_fixed_repeat(0xaa)
#        self.frame_fixed_repeat(0xaa)
        self.use_old = False
        self.frame_data_repeat(EPD_INVERSE)
        self.frame_data_repeat(EPD_NORMAL)
        self.update_old()
        self.zero()

# change from old image to new image called from exchange()
    def EPD_image(self):
        self.use_old = True
        self.frame_data_repeat(EPD_COMPENSATE)
        self.frame_data_repeat(EPD_WHITE)
        self.use_old = False
        self.frame_data_repeat(EPD_INVERSE)
        self.frame_data_repeat(EPD_NORMAL)
        self.update_old()
        self.zero()

    def update_old(self):
        i = self.image_old
        self.image_old = self.image
        self.image = i

    def zero(self):
        im = memoryview(self.image) # marginal speedup
        length = len(im)
        for x in range(length):
            im[x] = 0

    def frame_data_repeat(self, stage):
        start = pyb.millis()
        count = 0
        while True:
            self.frame_data(stage)
            count +=1
            if pyb.elapsed_millis(start) > self.factored_stage_time:
                break
        if self.verbose:
            print('frame_data_repeat count = {}'.format(count))

    def frame_fixed_repeat(self, fixed_value):
        start = pyb.millis()
        count = 0
        while True:
            self.frame_fixed(fixed_value)
            count +=1
            if pyb.elapsed_millis(start) > self.factored_stage_time:
                break
        if self.verbose:
            print('frame_fixed_repeat count = {}'.format(count))

    def _nothing_frame(self):
        for line in range(LINES_PER_DISPLAY) :
            self.one_line_fixed(0x7fff, 0, EPD_COMPENSATE)

    def _dummy_line(self):
        self.one_line_fixed(0x7fff, 0, EPD_NORMAL)

    def frame_fixed(self, fixed_value):
        for line in range(0, LINES_PER_DISPLAY):
            self.one_line_fixed(line, fixed_value, 0)

    def frame_data(self, stage):
        for line in range(0, LINES_PER_DISPLAY):
            n = line * BYTES_PER_LINE
            self.one_line_data(line, n, stage)
 
# pixels on display are numbered from 1 so even is actually bits 1,3,5,...
# could be speeded up: test data, have two loops one for fixed, one for data
    @micropython.viper
    def even_pixels(self, offset: int, data_offset: int, stage: int) -> int:
        p = ptr8(self.line_buffer)
        data = ptr8(self.image)
        mask = ptr8(self.image_old)
        for b in range(0, BYTES_PER_LINE): 
            pixels = data[b + data_offset] & 0xaa
            pixel_mask = 0xff
            if self.use_old:
                pixel_mask = (mask[b + data_offset] ^ pixels) & 0xaa
                pixel_mask |= pixel_mask >> 1

            if stage == EPD_COMPENSATE:         # B -> W, W -> B (Current Image)
                pixels = 0xaa | ((pixels ^ 0xaa) >> 1)
            elif stage == EPD_WHITE:            # B -> N, W -> W (Current Image)
                pixels = 0x55 + ((pixels ^ 0xaa) >> 1)
            elif stage == EPD_INVERSE:          # B -> N, W -> B (New Image)
                pixels = 0x55 | (pixels ^ 0xaa)
            elif stage == EPD_NORMAL:           # B -> B, W -> W (New Image)
                pixels = 0xaa | (pixels >> 1)

            pixels = (pixels & pixel_mask) | ((pixel_mask ^ 0xff) & 0x55)
            p1 = (pixels >> 6) & 0x03
            p2 = (pixels >> 4) & 0x03
            p3 = (pixels >> 2) & 0x03
            p4 = pixels & 0x03
            pixels = p1 | (p2 << 2) | (p3 << 4) | (p4 << 6)
            p[offset] = pixels
            p[offset] = pixels
            offset += 1
        return offset

    @micropython.viper
    def even_pixels_fixed(self, offset: int, fixed_value: int) -> int:
        p = ptr8(self.line_buffer)
        for b in range(0, BYTES_PER_LINE): 
            p[offset] = fixed_value
            offset +=1
        return offset

# pixels on display are numbered from 1 so odd is actually bits 0,2,4,...
    @micropython.viper
    def odd_pixels(self, offset: int, data_offset: int, stage: int) -> int:
        p = ptr8(self.line_buffer)
        data = ptr8(self.image)
        mask = ptr8(self.image_old)
        for b in range(BYTES_PER_LINE, 0, -1):
            pixels = data[b - 1 + data_offset] & 0x55
            pixel_mask = 0xff
            if self.use_old:
                pixel_mask = (mask[b - 1 + data_offset] ^ pixels) & 0x55
                pixel_mask |= pixel_mask << 1
            if stage == EPD_COMPENSATE:         # B -> W, W -> B (Current Image)
                pixels = 0xaa | (pixels ^ 0x55)
            elif stage == EPD_WHITE:            # B -> N, W -> W (Current Image)
                pixels = 0x55 + (pixels ^ 0x55)
            elif stage == EPD_INVERSE:          # B -> N, W -> B (New Image)
                pixels = 0x55 | ((pixels ^ 0x55) << 1)
            elif stage == EPD_NORMAL:           # B -> B, W -> W (New Image)
                pixels = 0xaa | pixels
            pixels = (pixels & pixel_mask) | ((pixel_mask ^ 0xff) & 0x55)
            p[offset] = pixels
            offset += 1
        return offset

    @micropython.viper
    def odd_pixels_fixed(self, offset: int, fixed_value: int) -> int:
        p = ptr8(self.line_buffer)
        for b in range(BYTES_PER_LINE, 0, -1):
            p[offset] = fixed_value
            offset +=1
        return offset

# output one line of scan and data bytes to the display
    @micropython.native
    def one_line_data(self, line, data_offset, stage):
        spi_send_byte = self.spi.send           # send data
        self._SPI_send(b'\x70\x0a')
        self.Pin_EPD_CS.low()                   # CS low until end of line
        spi_send_byte(b'\x72\x00')              # data bytes
        mv_linebuf = memoryview(self.line_buffer)
        offset = self.odd_pixels(0, data_offset, stage) #note data and mask are offset by line, line buffer offset 
        for b in range(BYTES_PER_SCAN, 0, -1):  # scan line
            if line // 4 == b - 1: 
                mv_linebuf[offset] = 0x03 << (2 * (line & 0x03))
            else:
                mv_linebuf[offset] = 0x00
            offset += 1
        offset = self.even_pixels(offset, data_offset, stage)
        spi_send_byte(mv_linebuf[:offset])      # send the accumulated line buffer
        self.Pin_EPD_CS.high()
        self._SPI_send(b'\x70\x02\x72\x07')     # output data to panel

    @micropython.native
    def one_line_fixed(self, line, fixed_value, stage):
        spi_send_byte = self.spi.send           # send data
        self._SPI_send(b'\x70\x0a')
        self.Pin_EPD_CS.low()                   # CS low until end of line
        spi_send_byte(b'\x72\x00')              # data bytes
        mv_linebuf = memoryview(self.line_buffer)
        offset = self.odd_pixels_fixed(0, fixed_value)
        for b in range(BYTES_PER_SCAN, 0, -1):  # scan line
            if line // 4 == b - 1: 
                mv_linebuf[offset] = 0x03 << (2 * (line & 0x03))
            else:
                mv_linebuf[offset] = 0x00
            offset += 1
        offset = self.even_pixels_fixed(offset, fixed_value)
        spi_send_byte(mv_linebuf[:offset])      # send the accumulated line buffer
        self.Pin_EPD_CS.high()
        self._SPI_send(b'\x70\x02\x72\x07')     # output data to panel

    @micropython.native
    def _SPI_send(self, buf):
        self.Pin_EPD_CS.low()
        self.spi.send(buf)
        self.Pin_EPD_CS.high()

    @micropython.native
    def _SPI_read(self, buf):
        self.Pin_EPD_CS.low()
        for x in range(len(buf)):
            result = self.spi.send_recv(buf[x])[0]
        self.Pin_EPD_CS.high()
        return result

