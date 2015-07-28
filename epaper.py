# epaper.py Top level module for Embedded Artists' 2.7 inch E-paper Display.
# Peter Hinch
# version 0.2
# 28th July 2015

# Copyright 2015 Peter Hinch
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

# Code translated and developed from https://developer.mbed.org/users/dreschpe/code/EaEpaper/

from flash import FlashClass
from epd import EPD, LINES_PER_DISPLAY, BYTES_PER_LINE, BITS_PER_LINE
import pyb, os

NEWLINE = const(10)             # ord('\n')

class FontFileError(Exception):
    pass

class Font(object):
    def __init__(self):
        self.bytes_per_ch = 0   # Number of bytes to define a character
        self.bytes_vert = 0     # No. of bytes per character column
        self.bits_horiz = 0     # Horzontal bits in character matrix
        self.bits_vert = 0      # Vertical bits in character matrix
        self.exists = False

    def __call__(self, fontfilename):
        self.fontfilename = fontfilename
        return self

    def __enter__(self): #fopen(self, fontfile):
        try:
            f = open(self.fontfilename, 'rb')
        except OSError as err:
            raise FontFileError(err)
        self.fontfile = f
        header = f.read(4)
        if header[0] == 0x3f and header[1] == 0xe7:
            self.bits_horiz = header[2] # font[1]
            self.bits_vert = header[3] # font[2]
            div, mod = divmod(self.bits_vert, 8)
            self.bytes_vert = div if mod == 0 else div +1 # font[3]
            self.bytes_per_ch = self.bytes_vert * self.bits_horiz +1 # font[0]
        else:
             raise FontFileError("Font file is invalid")
        self.exists = True
        return self

    def __exit__(self, *_): #fclose(self)
        self.exists = False
        self.fontfile.close()

class Display(object):
    FONT_HEADER_LENGTH = 4
    def __init__(self, testing = False, use_flash = False, side = 'Y'):
        self.testing = testing
        self.flash_used = use_flash
        try:
            self.intside = {'x':1, 'X':1, 'y':0,'Y':0}[side]
        except KeyError:
            raise ValueError("Side must be 'X' or 'Y'")
        self.epd = EPD(self.intside)

        self.font = Font()
        self.char_x = 0                         # Text cursor: default top left
        self.char_y = 0
        if self.flash_used:
            self.flash = FlashClass(self.intside)
            try:
                pyb.mount(None, self.flash.mountpoint)
            except OSError:
                pass                            # Ignore if not mounted
            pyb.mount(self.flash, self.flash.mountpoint)

    def show(self):
        if self.flash_used:
            self.flash.sync()
            pyb.mount(None, self.flash.mountpoint)
            self.flash.end()                    # sync and disable SPI
                                                # EPD functions which access the display electronics must be
        with self.epd as epd:                   # called from a with block to ensure proper startup & shutdown
            time = epd.showdata()
            if self.testing:
                print("Elapsed time:", time/1000)

        if self.flash_used:
            self.flash.begin()                  # Re-enable flash
            pyb.mount(self.flash, self.flash.mountpoint)

    @property
    def temperature(self):                      # return temperature as integer in Celsius
        return self.epd.lm75.temperature

    def clear_screen(self):
        self.epd.clear_data()
        self.show()

    def setpixel(self, x, y, black = True):
        if y < 0 or y >= LINES_PER_DISPLAY or x < 0 or x >= BITS_PER_LINE :
            return
        byte, bit = divmod(x, 8)
        omask = 1 << bit
        index = byte + y *BYTES_PER_LINE
        if black:
            self.epd.image[index] |= omask
        else:
            self.epd.image[index] &= (omask ^ 0xff)

# ****** Simple graphics support ******

    def _line(self, x0, y0, x1, y1, black = True): # Sinle pixel line
        dx = x1 -x0
        dy = y1 -y0
        dx_sym = 1 if dx > 0 else -1
        dy_sym = 1 if dy > 0 else -1

        dx = dx_sym*dx
        dy = dy_sym*dy
        dx_x2 = dx*2
        dy_x2 = dy*2
        if (dx >= dy):
            di = dy_x2 - dx
            while (x0 != x1):
                self.setpixel(x0, y0, black)
                x0 += dx_sym
                if (di<0):
                    di += dy_x2
                else :
                    di += dy_x2 - dx_x2
                    y0 += dy_sym
            self.setpixel(x0, y0, black)
        else:
            di = dx_x2 - dy
            while (y0 != y1):
                self.setpixel(x0, y0, black)
                y0 += dy_sym
                if (di < 0):
                    di += dx_x2
                else:
                    di += dx_x2 - dy_x2
                    x0 += dx_sym
            self.setpixel(x0, y0, black)

    def line(self, x0, y0, x1, y1, width =1, black = True): # Draw line
        if abs(x1 - x0) > abs(y1 - y0): # < 45 degrees
            for w in range(-width//2 +1, width//2 +1):
                self._line(x0, y0 +w, x1, y1 +w, black)
        else:
            for w in range(-width//2 +1, width//2 +1):
                self._line(x0 +w, y0, x1 +w, y1, black)

    def _rect(self, x0, y0, x1, y1, black): # Draw rectangle
        self.line(x0, y0, x1, y0, 1, black)
        self.line(x0, y0, x0, y1, 1, black)
        self.line(x0, y1, x1, y1, 1, black)
        self.line(x1, y0, x1, y1, 1, black)

    def rect(self, x0, y0, x1, y1, width =1, black = True): # Draw rectangle
        x0, x1 = (x0, x1) if x1 > x0 else (x1, x0) # x0, y0 is top left, x1, y1 is bottom right
        y0, y1 = (y0, y1) if y1 > y0 else (y1, y0)
        for w in range(width):
            self._rect(x0 +w, y0 +w, x1 -w, y1 -w, black)

    def fillrect(self, x0, y0, x1, y1, black = True): # Draw filled rectangle
        x0, x1 = (x0, x1) if x1 > x0 else (x1, x0)
        y0, y1 = (y0, y1) if y1 > y0 else (y1, y0)
        for x in range(x0, x1):
            for y in range(y0, y1):
                self.setpixel(x, y, black)

    def _circle(self, x0, y0, r, black = True): # Sinle pixel circle
        x = -r
        y = 0
        err = 2 -2*r
        while x <= 0:
            self.setpixel(x0 -x, y0 +y, black)
            self.setpixel(x0 +x, y0 +y, black)
            self.setpixel(x0 +x, y0 -y, black)
            self.setpixel(x0 -x, y0 -y, black)
            e2 = err
            if (e2 <= y):
                y += 1
                err += y*2 +1
                if (-x == y and e2 <= x):
                    e2 = 0
            if (e2 > x):
                x += 1
                err += x*2 +1

    def circle(self, x0, y0, r, width =1, black = True): # Draw circle
        for r in range(r, r -width, -1):
            self._circle(x0, y0, r, black)

    def fillcircle(self, x0, y0, r, black = True): # Draw filled circle
        x = -r
        y = 0
        err = 2 -2*r
        while x <= 0:
            self._line(x0 -x, y0 -y, x0 -x, y0 +y, black)
            self._line(x0 +x, y0 -y, x0 +x, y0 +y, black)
            e2 = err
            if (e2 <= y):
                y +=1
                err += y*2 +1
                if (-x == y and e2 <= x):
                    e2 = 0
            if (e2 > x):
                x += 1
                err += x*2 +1

# ****** Image display ******

    def load_xbm(self, sourcefile):
        '''
        Load an xBM image file for display.
        '''
        errmsg = ''.join(("File: '", sourcefile, "' is either not a valid XBM file or is not the correct size (", 
                          str(LINES_PER_DISPLAY), " lines of ", str(BYTES_PER_LINE), " bytes per line)"))
        try:
            with open(sourcefile, 'r') as f:
                started = False
                finished = False
                while not started:
                    line = f.readline()
                    start = line.find('{')
                    if start >= 0:
                        line = line[start +1:]
                        started = True
                        if line.isspace():
                            line = f.readline()
                if started:
                    index = 0
                    while not finished:
                        end = line.find('}')
                        if end >=0 :
                            line = line[:end]
                            finished = True
                        hexnums = line.split(',')
                        if hexnums[0] != '':
                            for hexnum in [x for x in hexnums if not x.isspace()]:
                                self.epd.image[index] = int(hexnum, 16)
                                index += 1
                        line = f.readline()
                if not started or not finished or index != BYTES_PER_LINE * LINES_PER_DISPLAY:
                    print(errmsg)
        except OSError:
            print("Can't open " + sourcefile + " for reading")
        except IndexError:
            print(errmsg)

# ****** Text support ******

    def locate(self, x, y):                     # set cursor position
        self.char_x = x                         # Text input cursor to (x, y)
        self.char_y = y

    def _character(self, c):
        if (self.char_x + self.font.bits_horiz) > BITS_PER_LINE :
            self.char_x = 0
            self.char_y += self.font.bits_vert
            if self.char_y >= (LINES_PER_DISPLAY - self.font.bits_vert):
                self.char_y = 0
        self.font.fontfile.seek(self.FONT_HEADER_LENGTH + (c -32) * self.font.bytes_per_ch)
        fontbuf = self.font.fontfile.read(self.font.bytes_per_ch)
                                                # write out the character
        for bit_vert in range(self.font.bits_vert):   # for each vertical line
            for bit_horiz in range(self.font.bits_horiz): #  horizontal line
                bytenum, bitnum = divmod(bit_vert, 8)
                fontbyte = fontbuf[self.font.bytes_vert * bit_horiz + bytenum +1]
                bit = 1 << bitnum
                self.setpixel(self.char_x +bit_horiz, self.char_y +bit_vert, (fontbyte & bit) > 0)
        self.char_x += fontbuf[0]               # width of current char

    def _putc(self, value):                     # print char
        if (value == NEWLINE):
            self.char_x = 0
            self.char_y += self.font.bits_vert
            if (self.char_y >= LINES_PER_DISPLAY - self.font.bits_vert):
                self.char_y = 0
        else: 
            self._character(value)
        return value

    def puts(self, s):                          # Output a string at cursor
        if self.font.exists:
            for char in s:
                c = ord(char)
                if (c > 31 and c < 128) or c == NEWLINE:
                    self._putc(c)
        else:
             raise FontFileError("There is no current font")
