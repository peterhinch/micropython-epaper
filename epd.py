# epd.py module for Embedded Artists' 2.7 inch E-paper Display. Imported by epaper.py
# Peter Hinch
# version 0.5
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

EPD_OK = const(0) # error codes
EPD_UNSUPPORTED_COG = const(1)
EPD_PANEL_BROKEN = const(2)
EPD_DC_FAILED = const(3)

EPD_normal = const(0) # Stage
EPD_inverse = const(1)

LINES_PER_DISPLAY = const(176)
BYTES_PER_LINE = const(33)
BYTES_PER_SCAN = const(44)
BITS_PER_LINE = const(264)

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

class EPD(object):
    def __init__(self, intside, pwr_controller = None):
        gc.collect()
        from panel import getpins
        self.pwr_controller = pwr_controller
        self.image = bytearray(BYTES_PER_LINE * LINES_PER_DISPLAY)
        self.linebuf = bytearray(BYTES_PER_LINE * 2 + BYTES_PER_SCAN)
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
        self.Pin_RESET.low()
        self.Pin_PANEL_ON.low()
        self.Pin_DISCHARGE.low()
        self.Pin_BORDER.low()
        self.Pin_EPD_CS.low()
        self.Pin_FLASH_CS.high()
        self.spi_no = pins['SPI_BUS']
        self.i2c_no = pins['I2C_BUS']
        if self.pwr_controller is None:         # If we're powered up instantiate LM75 to throw
            self.lm75 = LM75(self.i2c_no)       # early error if not working

# USER INTERFACE

    def showdata(self):                         # Call from a with block
        self._frame_data_13(EPD_inverse)
        self._frame_stage2() # 1.6S
        self._frame_data_13(EPD_normal)

    def clear_data(self):
        for x in range(len(self.image)):
            self.image[x] = 0
#        self.image[:] = bytes((0 for x in range(len(self.image)))) needless RAM allocation

    @property
    def temperature(self):                      # return temperature as integer in Celsius
        if self.pwr_controller:
            self.pwr_controller.power_up()      # Apply power if controlled
            lm75 = LM75(self.i2c_no)            # Instantiate LM75 for the duration of power
            temperature = lm75.temperature
            self.pwr_controller.power_down()
            return temperature
        return self.lm75.temperature            # Permanent power

# END OF USER INTERFACE

    def __enter__(self):                        # power up sequence
        if self.pwr_controller:
            self.pwr_controller.power_up()      # Apply power if controlled
        self.status = EPD_OK
        self.Pin_RESET.low()
        self.Pin_PANEL_ON.low()
        self.Pin_DISCHARGE.low()
        self.Pin_BORDER.low()
        self.Pin_EPD_CS.low()
                                                # Baud rate: data sheet says 20MHz max. Pyboard's closest (21MHz) was unreliable
        self.spi = pyb.SPI(self.spi_no, pyb.SPI.MASTER, baudrate=10500000, polarity=1, phase=1, bits=8) # 5250000 10500000 supported by Pyboard
        self._SPI_send(b'\x00\x00')
        pyb.delay(5)
        self.Pin_PANEL_ON.high()
        pyb.delay(10)

        self.Pin_RESET.high()
        self.Pin_BORDER.high()
        self.Pin_EPD_CS.high()
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
                # output enable to disable
                self._SPI_send(b'\x70\x02')
                self._SPI_send(b'\x72\x04')
                break
        if not dc_ok:
            # output enable to disable
            self._SPI_send(b'\x70\x02')
            self._SPI_send(b'\x72\x04')

            self.status = EPD_DC_FAILED
            self._power_off()
            raise EPDException("EPD DC power failure")
# Set temperature factor
        # stage1: repeat, step, block
        # stage2: repeat, t1, t2
        # stage3: repeat, step, block
        if self.pwr_controller:                 # powered up, no LM75 instance, must not power down
            lm75 = LM75(self.i2c_no)            # Instantiate LM75
            temperature = lm75.temperature
        else:
            temperature = self.lm75.temperature
        if temperature < 10 :
            self.compensation = {'stage1_repeat':2, 'stage1_step':8, 'stage1_block':64,
                                 'stage2_repeat':4, 'stage2_t1':392, 'stage2_t2':392,
                                 'stage3_repeat':2, 'stage3_step':8, 'stage3_block':64}#  0 ... 10 Celcius
        elif temperature < 40:
            self.compensation = {'stage1_repeat':2, 'stage1_step':4, 'stage1_block':32,
                                 'stage2_repeat':4, 'stage2_t1':196, 'stage2_t2':196,
                                 'stage3_repeat':2, 'stage3_step':4, 'stage3_block':32} # 10 ... 40 Celcius
        else: 
            self.compensation = {'stage1_repeat':4, 'stage1_step':8, 'stage1_block':64,
                                 'stage2_repeat':4, 'stage2_t1':196, 'stage2_t2':196,
                                 'stage3_repeat':4, 'stage3_step':8, 'stage3_block':64}# 40 ... 50 Celcius
        return self

    def __exit__(self, *_):
        self._nothing_frame()
        self._dummy_line()

        self.Pin_BORDER.low()
        pyb.delay(200)
        self.Pin_BORDER.high()

        # check DC/DC
        self._SPI_send(b'\x70\x0f')
        dc_state = self._SPI_read(b'\x73\x00') & 0x40
        if dc_state != 0x40:
            self.status = EPD_DC_FAILED
            self._power_off()
            raise EPDException("EPD DC power failure")
        self._SPI_send(b'\x70\x0B') # Conform with datasheet
        self._SPI_send(b'\x72\x00')
        # latch reset turn on
        self._SPI_send(b'\x70\x03')
        self._SPI_send(b'\x72\x01')
        # output enable off
#        self._SPI_send(b'\x70\x02') Conform with datasheet
#        self._SPI_send(b'\x72\x05')
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
        self.Pin_PANEL_ON.low()
#        self._SPI_send(b'\x00\x00')
        self.spi.deinit()
        self.Pin_SCK.init(mode = pyb.Pin.OUT_PP)
        self.Pin_SCK.low()
        self.Pin_MOSI.init(mode = pyb.Pin.OUT_PP)
        self.Pin_MOSI.low()
        self.Pin_BORDER.low()
        # ensure SPI MOSI and CLOCK are Low before CS Low
        if (self.pwr_controller) and (self.pwr_controller.single_ended == True):
            self.pwr_controller.power_down()    # Turn off device power if +ve supply only is controlled
            pyb.delay(10)                       # No point waggling pins if there's no gnd...
        self.Pin_RESET.low()
        self.Pin_EPD_CS.low()
        # pulse discharge pin
        self.Pin_DISCHARGE.high()
        pyb.delay(150)
        self.Pin_DISCHARGE.low()
        if (self.pwr_controller) and (self.pwr_controller.single_ended == False):
            self.pwr_controller.power_down()    # Turn off device power now if both supplies are controlled

# One frame of data is the number of lines * rows. For example:
# The 2.7” frame of data is 176 lines * 264 dots.

    def _frame_fixed_timed(self, fixed_value, stage_time):
        t_start = pyb.millis()
        t_elapsed = -1
        while t_elapsed < stage_time: 
            for line in range(LINES_PER_DISPLAY -1, -1, -1): 
                self._line_fixed(line, fixed_value, set_voltage_limit = False)
            t_elapsed = pyb.elapsed_millis(t_start)

    def _nothing_frame(self):
        for line in range(LINES_PER_DISPLAY) :
            self._line_fixed(line, 0, set_voltage_limit = True)

    def _dummy_line(self):
        line = 0x7fff
        self._line_fixed(line, 0, set_voltage_limit = True)

    def _frame_stage2(self):
        for i in range(self.compensation['stage2_repeat']): # 4
            self._frame_fixed_timed(0xff, self.compensation['stage2_t1']) # 196mS
            self._frame_fixed_timed(0xaa, self.compensation['stage2_t2']) # 196mS

    def _frame_data_13(self, stage):
        if stage == EPD_inverse :   # stage 1
            self.pixelmask = 0xff
            repeat = self.compensation['stage1_repeat']
            step = self.compensation['stage1_step']
            block = self.compensation['stage1_block']
        else:                      # stage 3
            self.pixelmask = 0
            repeat = self.compensation['stage3_repeat']
            step = self.compensation['stage3_step']
            block = self.compensation['stage3_block']

        for n in range(repeat):
            block_begin = 0
            block_end = 0
            while block_begin < LINES_PER_DISPLAY:
                block_end += step
                block_begin = max(block_end - block, 0)
                if block_begin >= LINES_PER_DISPLAY:
                    break

                full_block = (block_end - block_begin == block)
                for line in range(block_begin, block_end):
                    if (line >= LINES_PER_DISPLAY):
                        break
                    if (full_block and (line < (block_begin + step))):
                        self._line_fixed(line, 0, set_voltage_limit = False)
                    else:
                        self._line(line, line * BYTES_PER_LINE)

# Optimisation: display refresh code spends 98.5% of its time running _line() [97.8% after optimisation]
    @micropython.native
    def _line_fixed(self, line, fixed_value, set_voltage_limit):
        spi_send_byte = self.spi.send       # Optimisation: save function in local namespace
        if set_voltage_limit:               # charge pump voltage level reduce voltage shift
            self._SPI_send(b'\x70\x04\x72\x00') # voltage level 0 for 2.7 inch panel
        self._SPI_send(b'\x70\x0a')
        self.Pin_EPD_CS.low()                    # CS low: stays low until end of line
        spi_send_byte(b'\x72\x00')
        self._setbuf_fixed(line, fixed_value)
        spi_send_byte(self.linebuf)
        self.Pin_EPD_CS.high()
        # output data to panel
        self._SPI_send(b'\x70\x02\x72\x07')

    @micropython.native
    def _line(self, line, offset):
        spi_send_byte = self.spi.send       # Optimisation: save function in local namespace
        self._SPI_send(b'\x70\x0a')
        self.Pin_EPD_CS.low()                    # CS low: stays low until end of line
        spi_send_byte(b'\x72\x00')
        self._setbuf_data(line, offset)
        spi_send_byte(self.linebuf)
        self.Pin_EPD_CS.high()
        # output data to panel
        self._SPI_send(b'\x70\x02\x72\x07')

    @micropython.viper
    def _setbuf_fixed(self, line: int, fixed_value: int):
        index = 0                           # odd pixels
        buf = ptr8(self.linebuf)
        for b in range(BYTES_PER_LINE, 0, -1): # Optimisation: replacing for .. in range made trivial gains.
            buf[index] = fixed_value # Optimisation: buffer SPI data
            index += 1
                                            # scan line
        scan_pos = (LINES_PER_DISPLAY - line - 1) >> 2
        scan_shift = (line & 3) << 1 
        for b in range(BYTES_PER_SCAN):
            if scan_pos == b:
                buf[index] = 3 << scan_shift
            else:
                buf[index] = 0
            index += 1
        for b in range(BYTES_PER_LINE):     # Even pixels
            buf[index] = fixed_value
            index += 1

    @micropython.viper
    def _setbuf_data(self, line: int, offset: int): # 5.85S
        pixelmask = int(self.pixelmask)
        buf = ptr8(self.linebuf)                # Optimisation: use local namespace
        image = ptr8(self.image)
        index = 0                           # odd pixels
        for b in range(BYTES_PER_LINE, 0, -1):
            buf[index] = int(image[offset + b - 1])  ^ pixelmask | 0xaa
            index += 1
                                            # scan line
        scan_pos = (LINES_PER_DISPLAY - line -1) >> 2
        scan_shift = (line & 3) << 1
        for b in range(BYTES_PER_SCAN):
            buf[index] = 3 << scan_shift if scan_pos == b else 0
            index += 1
        for b in range(BYTES_PER_LINE): # Even pixels
            pixels = ((int(image[offset + b])  ^ pixelmask) >> 1) | 0xaa
            pixels = (((pixels & 0xc0) >> 6)
                | ((pixels & 0x30) >> 2)
                | ((pixels & 0x0c) << 2)
                | ((pixels & 0x03) << 6))
            buf[index] = pixels
            index += 1
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

