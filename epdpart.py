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

import pyb, gc, stm # TEST
from array import array
from uctypes import addressof
from panel import EMBEDDED_ARTISTS, getpins

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
    def __init__(self, intside, model, up_time):
        self.model = model
        self.compensate_temp = True if up_time is None else False
        self.verbose = False
        gc.collect()
        self.image_0 = bytearray(BYTES_PER_LINE * LINES_PER_DISPLAY) # 5808
        self.image_1 = bytearray(BYTES_PER_LINE * LINES_PER_DISPLAY) # 5808
        self.asm_data = array('i', [0, 0, 0, 0])
        self.image = self.image_0
        self.image_old = self.image_1
        self.line_buffer = bytearray(111) # total 11727 bytes!
        for x in range(len(self.image_old)):
            self.image_old[x] = 0
        pins = getpins(intside, model)
        self.Pin_PANEL_ON = pyb.Pin(pins['PANEL_ON'], mode = pyb.Pin.OUT_PP)
        self.Pin_BORDER = pyb.Pin(pins['BORDER'], mode = pyb.Pin.OUT_PP)
        self.Pin_DISCHARGE = pyb.Pin(pins['DISCHARGE'], mode = pyb.Pin.OUT_PP)
        self.Pin_RESET = pyb.Pin(pins['RESET'], mode = pyb.Pin.OUT_PP)
        self.Pin_BUSY = pyb.Pin(pins['BUSY'], mode = pyb.Pin.IN)
        self.Pin_EPD_CS = pyb.Pin(pins['EPD_CS'], mode = pyb.Pin.OUT_PP)    # cs for e-paper display
        self.Pin_FLASH_CS = pyb.Pin(pins['FLASH_CS'], mode = pyb.Pin.OUT_PP) # Instantiate flash CS and set high
        self.Pin_MOSI = pyb.Pin(pins['MOSI'], mode = pyb.Pin.OUT_PP)
        self.Pin_SCK = pyb.Pin(pins['SCK'], mode = pyb.Pin.OUT_PP)
        self.base_stage_time = 630 if up_time is None else up_time # ms
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
        else:
            self.adc = pyb.ADC(pins['TEMPERATURE'])

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
# See modified code at https://github.com/tvoverbeek/gratis/blob/master/PlatformWithOS/driver-common/V231_G2/epd.c
    def refresh(self):
        self.use_old = True
#        self.update_old()
#        self.frame_data_repeat(EPD_COMPENSATE)
#        self.frame_data_repeat(EPD_WHITE)
#        self.update_old()
#        self.frame_data_repeat(EPD_INVERSE)
#        self.frame_data_repeat(EPD_NORMAL)
        self.frame_data_repeat(EPD_NORMAL)


#        self.frame_data_repeat(EPD_NORMAL)      # This is where the time goes
        for x in range(len(self.image)):
            self.image_old[x] = self.image[x]   # this loop: 77ms out of 1.4s

    def exchange(self):
        self.EPD_image()

    @property
    def temperature(self):                      # return temperature as integer in Celsius
        if self.model == EMBEDDED_ARTISTS:
            return self.lm75.temperature
        else:
            return 202.5 - 0.1824 * self.adc.read()

# END OF USER INTERFACE

# self.use_old False is equivalent to passing NULL in old image
# update_old() determines which buffer to use TODO check how stage data ets to frame_fixed_repeat **********************

# clear display (anything -> white) called from clear_screen() *** works ***
    def EPD_clear(self):
        self.frame_fixed_repeat(0xff, EPD_COMPENSATE)
        self.frame_fixed_repeat(0xff, EPD_WHITE)
        self.frame_fixed_repeat(0xaa, EPD_INVERSE)
        self.frame_fixed_repeat(0xaa, EPD_NORMAL)
#        self.zero() don't alter data
#        self.update_old()
#        self.zero()

# assuming a clear (white) screen output an image called from show() *** works ***
    def EPD_image_0(self):
        self.frame_fixed_repeat(0xaa, EPD_COMPENSATE)
        self.frame_fixed_repeat(0xaa, EPD_WHITE)
        self.use_old = False
        self.frame_data_repeat(EPD_INVERSE)
        self.frame_data_repeat(EPD_NORMAL)
        self.update_old()
        self.zero()

# change from old image to new image called from exchange()
    def EPD_image(self):
        self.use_old = False
        self.frame_data_repeat(EPD_COMPENSATE)
        self.frame_data_repeat(EPD_WHITE)
        self.update_old()
        self.frame_data_repeat(EPD_INVERSE)
        self.frame_data_repeat(EPD_NORMAL)
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
        self.asm_data[0] = addressof(self.image)
        self.asm_data[1] = addressof(self.image_old)
        start = pyb.millis()
        count = 0
        while True:
            self.frame_data(stage)
            count +=1
            if pyb.elapsed_millis(start) > self.factored_stage_time:
                break
        if self.verbose:
            print('frame_data_repeat count = {}'.format(count))

    def frame_data(self, stage):
        for line in range(0, LINES_PER_DISPLAY):
            self.one_line_data(line, stage)
 
    def frame_fixed_repeat(self, fixed_value, stage):
        start = pyb.millis()
        count = 0
        while True:
            self.frame_fixed(fixed_value, stage)
            count +=1
            if pyb.elapsed_millis(start) > self.factored_stage_time:
                break
        if self.verbose:
            print('frame_fixed_repeat count = {}'.format(count))

    def frame_fixed(self, fixed_value, stage):
        for line in range(0, LINES_PER_DISPLAY):
            self.one_line_fixed(line, fixed_value, stage)

    def _nothing_frame(self):
        for line in range(LINES_PER_DISPLAY) :
            self.one_line_fixed(0x7fff, 0, EPD_COMPENSATE)

    def _dummy_line(self):
        self.one_line_fixed(0x7fff, 0, EPD_NORMAL)

# pixels on display are numbered from 1 so even is actually bits 1,3,5,...
    @micropython.viper
    def even_pixels_old(self, offset: int, data_offset: int, stage: int) -> int:
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

            p[offset] = int(setpixels(pixels, pixel_mask))
#            pixels = (pixels & pixel_mask) | ((pixel_mask ^ 0xff) & 0x55)
#            p1 = (pixels >> 6) & 0x03
#            p2 = (pixels >> 4) & 0x03
#            p3 = (pixels >> 2) & 0x03
#            p4 = pixels & 0x03
#            pixels = p1 | (p2 << 2) | (p3 << 4) | (p4 << 6)
#            p[offset] = pixels
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
    def odd_pixels_old(self, offset: int, data_offset: int, stage: int) -> int:
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
    def one_line_data(self, line, stage):
        mv_linebuf = memoryview(self.line_buffer)
        self.asm_data[2] = addressof(mv_linebuf)
        self.asm_data[3] = stage | 8 if self.use_old else stage
        spi_send_byte = self.spi.send           # send data
        self._SPI_send(b'\x70\x0a')
        self.Pin_EPD_CS.low()                   # CS low until end of line
        spi_send_byte(b'\x72\x00')              # data bytes
#        self.odd_pixels_old(0, line * BYTES_PER_LINE, stage) #note data and mask are offset by line, line buffer offset
        odd_pixels(self.asm_data, 0, line * BYTES_PER_LINE)
        offset = BYTES_PER_LINE
        offset = scan(self.line_buffer, line, offset)
        even_pixels(self.asm_data, offset, line * BYTES_PER_LINE)
        offset += BYTES_PER_LINE

##        offset = self.even_pixels_old(offset, line * BYTES_PER_LINE, stage)
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




#        for b in range(BYTES_PER_SCAN, 0, -1):  # scan line
#            if line >> 2 == b - 1: 
#                mv_linebuf[offset] = 0x03 << (2 * (line & 0x03))
#            else:
#                mv_linebuf[offset] = 0x00
#            offset += 1

@micropython.asm_thumb
def even_pixels(r0, r1, r2): # array, offset, data_offset, stage
    ldr(r3, [r0, 12])
    ldr(r4, [r0, 0])
    add(r4, r4, r2) # r4 = *data
    ldr(r5, [r0, 4])
    add(r5, r5, r2) # r5 = *mask
    ldr(r2, [r0, 8])
    add(r2, r2, r1) # r2 = *p
    mov(r6, 0) # r6 = b
    label(LOOP)
    push({r6, r3})
    mov(r0, r4)
    add(r0, r0, r6)
    ldr(r1, [r0, 0]) # r1 = data[b + data_offset]
    mov(r0, 0xaa)
    and_(r1, r0) # r1 = pixels = data[b + data_offset] & 0xaa
    mov(r7, 0xff) # r7 = pixel_mask
    cmp(r3, 4) # Check use_old
    blt(SKIP)
    mov(r0, r5) # EXECUTING
    add(r0, r0, r6)
    ldr(r7, [r0, 0]) # r7 = mask[b + data_offset]
    eor(r7, r1)
    mov(r0, 0xaa)
    and_(r7, r0) # r7 = pixel_mask = (mask[b + data_offset] ^ pixels) & 0xaa
    mov(r0, r7)
    mov(r6, 1)
    lsr(r0, r6)
    orr(r7, r0) # r7 = pixel_mask |= pixel_mask >> 1
    label(SKIP)
    mov(r0, 3)
    and_(r3, r0) # strip use_old bit: r3 = stage
    bne(LABEL1) # not EPD_COMPENSATE
    mov(r0, 0xaa)
    eor(r0, r1) # r0 = pixels ^ 0xaa
    mov(r6, 1)
    lsr(r0, r6) # r0 = (pixels ^ 0xaa) >> 1
    mov(r6, 0xaa)
    orr(r0, r6) # r0 = pixels = 0xaa | ((pixels ^ 0xaa) >> 1)
    b(LABEL5)
    label(LABEL1)
    cmp(r3,  EPD_WHITE)
    bne(LABEL2)
    mov(r0, 0xaa)
    eor(r0, r1)
    mov(r6, 1)
    lsr(r0, r6)
    mov(r6, 0x55)
    add(r0, r0, r6)  # r0 = pixels = 0x55 + ((pixels ^ 0xaa) >> 1)
    b(LABEL5)
    label(LABEL2)
    cmp(r3, EPD_INVERSE)
    bne(LABEL3)
    mov(r0, 0xaa)
    eor(r0, r1) # r0 = pixels ^ 0xaa
    mov(r6, 0x55)
    orr(r0, r6) # r0 = pixels = 0x55 | (pixels ^ 0xaa)
    b(LABEL5)
    label(LABEL3)
    cmp(r3, EPD_NORMAL)
    bne(LABEL4)
    mov(r0, r1) # EXECUTING
    mov(r6, 1)
    lsr(r0, r6)
    mov(r6, 0xaa)
    orr(r0, r6) # r0 = pixels = 0xaa | (pixels >> 1)
    b(LABEL5)
    label(LABEL4)
    mov(r0, r1) # r0 = pixels
    label(LABEL5)
                # r0 = pixels
    mov(r1, r7) # pixel_mask
    push({r2, r3})
    mvn(r2, r1)
    mov(r3, 0x55)
    and_(r3, r2) # r3 = (mask ^0xff) & 0x55
    and_(r0, r1)
    orr(r0, r3) # r0 = (r0 & mask) | (mask ^0xff) & 0x55
    rbit(r0, r0)
    mov(r1, 23)
    mov(r2, r0)
    lsr(r2, r1) # r2 = pixels >> 23
    mov(r1, 25)
    lsr(r0, r1) # r0 = pixels >> 25
    mov(r1, 0xaa)
    and_(r2, r1) # r2 = (pixels >> 23) & 0xaa
    mov(r1, 0x55)
    and_(r0, r1) # r0 = (pixels >> 25) & 0x55
    orr(r0, r2)
    pop({r2, r3})
                # r0 = pixels
    strb(r0, [r2, 0]) # *p = pixels
    add(r2, 1) # p++
    pop({r6, r3}) # b, loop counter
    add(r6, 1)
    cmp(r6, BYTES_PER_LINE)
    blt(LOOP)
    mov(r0, r6)

@micropython.asm_thumb
def odd_pixels(r0, r1, r2): # array, offset, data_offset, stage
    ldr(r3, [r0, 12])
    ldr(r4, [r0, 0])
    add(r4, r4, r2) # r4 = *data
    ldr(r5, [r0, 4])
    add(r5, r5, r2) # r5 = *mask
    ldr(r2, [r0, 8])
    add(r2, r2, r1) # r2 = *p
    mov(r6, BYTES_PER_LINE) # r6 = b
    label(LOOP)
    push({r6, r3})
    mov(r0, r4)
    add(r0, r0, r6)
    sub(r0, 1)
    ldr(r1, [r0, 0]) # r1 = data[b -1 + data_offset]
    mov(r0, 0x55)
    and_(r1, r0) # r1 = pixels = data[b -1 + data_offset] & 0x55
    mov(r7, 0xff) # r7 = pixel_mask
    cmp(r3, 4) # Check use_old
    blt(SKIP)
    mov(r0, r5)
    add(r0, r0, r6)
    sub(r0, 1)
    ldr(r7, [r0, 0]) # r7 = mask[b -1 + data_offset]
    eor(r7, r1)
    mov(r0, 0x55)
    and_(r7, r0) # r7 = pixel_mask = (mask[b -1 + data_offset] ^ pixels) & 0x55
    mov(r0, r7)
    mov(r6, 1)
    lsl(r0, r6)
    orr(r7, r0) # r7 = pixel_mask |= pixel_mask << 1
    label(SKIP)
    mov(r0, 3)
    and_(r3, r0) # strip use_old bit: r3 = stage
    bne(LABEL1) # not EPD_COMPENSATE
    mov(r0, 0x55)
    eor(r0, r1) # r0 = pixels ^ 0x55
    mov(r6, 0xaa)
    orr(r0, r6) # r0 = pixels = 0xaa | (pixels ^ 0x55)
    b(LABEL5)
    label(LABEL1)
    cmp(r3,  EPD_WHITE)
    bne(LABEL2)
    mov(r0, 0x55)
    eor(r0, r1)
    mov(r6, 0x55)
    add(r0, r0, r6)  # r0 = pixels = 0x55 + (pixels ^ 0x55)
    b(LABEL5)
    label(LABEL2)
    cmp(r3, EPD_INVERSE)
    bne(LABEL3)
    mov(r0, 0x55)
    eor(r0, r1) # r0 = pixels ^ 0x55
    mov(r6, 1)
    lsl(r0, r6)
    mov(r6, 0x55)
    orr(r0, r6) # r0 = pixels = 0x55 | ((pixels ^ 0x55) << 1)
    b(LABEL5)
    label(LABEL3)
    cmp(r3, EPD_NORMAL)
    bne(LABEL4)
    mov(r0, r1)
    mov(r6, 0xaa)
    orr(r0, r6) # r0 = pixels = 0xaa | pixels
    b(LABEL5)
    label(LABEL4)
    mov(r0, r1) # r0 = pixels
    label(LABEL5)
                # r0 = pixels
    mov(r1, r7) # pixel_mask
    push({r2, r3})
    mvn(r2, r1)
    mov(r3, 0x55)
    and_(r3, r2) # r3 = (mask ^0xff) & 0x55
    and_(r0, r1)
    orr(r0, r3) # r0 = (r0 & mask) | (mask ^0xff) & 0x55
    pop({r2, r3})
                # r0 = pixels
    strb(r0, [r2, 0]) # *p = pixels
    add(r2, 1) # p++
    pop({r6, r3}) # b, loop counter
    sub(r6, 1)
    bne(LOOP)

@micropython.asm_thumb
def setpixels(r0, r1): # pixels, mask
    push({r2, r3})
    mvn(r2, r1)
    mov(r3, 0x55)
    and_(r3, r2) # r3 = (mask ^0xff) & 0x55
    and_(r0, r1)
    orr(r0, r3) # r0 = (r0 & mask) | (mask ^0xff) & 0x55
    rbit(r0, r0)
    mov(r1, 23)
    mov(r2, r0)
    lsr(r2, r1) # r2 = pixels >> 23
    mov(r1, 25)
    lsr(r0, r1) # r0 = pixels >> 25
    mov(r1, 0xaa)
    and_(r2, r1) # r2 = (pixels >> 23) & 0xaa
    mov(r1, 0x55)
    and_(r0, r1) # r0 = (pixels >> 25) & 0x55
    orr(r0, r2)
    pop({r2, r3})

@micropython.asm_thumb
def scan(r0, r1, r2):
    mov(r4, BYTES_PER_SCAN) # b
    label(LOOP) # for b in range(BYTES_PER_SCAN, 0, -1):
    mov(r5, r1) # line
    mov(r6, 2)
    lsr(r5, r6)
    mov(r6, r4) # b
    sub(r6, 1)
    mov(r7, 0) # Assume not equal mv_linebuf[offset] = 0x00
    cmp(r6, r5) # if line >> 2 == b - 1:
    bne(NOTEQUAL)
    mov(r6, 3)
    and_(r6, r1)
    add(r6, r6, r6)
    mov(r7, 3)
    lsl(r7, r6) # mv_linebuf[offset] = 0x03 << (2 * (line & 0x03))
    label(NOTEQUAL)
    add(r6, r0, r2)
    strb(r7, [r6, 0])
    add(r2, 1) # offset += 1
    sub(r4, 1)
    bne(LOOP)
    mov(r0, r2)
