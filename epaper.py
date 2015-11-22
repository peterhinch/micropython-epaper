# epaper.py main module for Embedded Artists' 2.7 inch E-paper Display.
# Peter Hinch
# version 0.5
# 23rd Sep 2015 Checks for out of date firmware on load
# 29th Aug 2015 Improved power control support
# 16th Aug 2015 Bitmap file display supports small bitmaps. Code is more generic
# 13th Aug 2015 Support for external power control hardware

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

def buildcheck(tupTarget):
    fail = True
    if 'uname' in dir(os):
        datestring = os.uname()[3]
        date = datestring.split(' on')[1]
        idate = tuple([int(x) for x in date.split('-')])
        fail = idate < tupTarget
    if fail:
        raise OSError('This driver requires a firmware build dated {:4d}-{:02d}-{:02d} or later'.format(*tupTarget))

buildcheck((2015,7,28))

NEWLINE = const(10)             # ord('\n')

# Generator parses an XBM file returning width, height, followed by data bytes
def get_xbm_data(sourcefile):
    errmsg = ''.join(("File: '", sourcefile, "' is not a valid XBM file"))
    try:
        with open(sourcefile, 'r') as f:
            phase = 0
            for line in f:
                if phase < 2:
                    if line.startswith('#define'):
                        yield int(line.split(' ')[-1])
                        phase += 1
                if phase == 2:
                    start = line.find('{')
                    if start >= 0:
                        line = line[start +1:]
                        phase += 1
                if phase == 3:
                    if not line.isspace():
                        phase += 1
                if phase == 4:
                    end = line.find('}')
                    if end >=0 :
                        line = line[:end]
                        phase += 1
                    hexnums = line.split(',')
                    if hexnums[0] != '':
                        for hexnum in [q for q in hexnums if not q.isspace()]:
                            yield int(hexnum, 16)
            if phase != 5 :
                print(errmsg)
    except OSError:
        print("Can't open " + sourcefile + " for reading")


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

    def __exit__(self, *_):
        self.exists = False
        self.fontfile.close()

class Display(object):
    FONT_HEADER_LENGTH = 4
    def __init__(self, side = 'L', use_flash = False, pwr_controller = None):
        self.flash = None                       # Assume flash is unused
        try:
            self.intside = {'x':1, 'X':1, 'y':0,'Y':0, 'l':0, 'L':0, 'r':1, 'R':1}[side]
        except KeyError:
            raise ValueError("Side must be 'L' or 'R'")
        self.pwr_controller = pwr_controller

        self.epd = EPD(self.intside, pwr_controller)
        self.font = Font()
        self.locate(0, 0)                       # Text cursor: default top left

        self.mounted = False                    # umountflash() not to sync
        if use_flash:
            self.flash = FlashClass(self.intside, pwr_controller)
            self.umountflash()                  # In case mounted by prior tests.
            if self.pwr_controller is None:     # Normal operation: flash is mounted continuously
                self.mountflash()

    def mountflash(self):
        if self.flash is None:                  # Not being used
            return
        self.flash.begin()                      # Turn on power if under control. Initialise.
        pyb.mount(self.flash, self.flash.mountpoint)
        self.mounted = True

    def umountflash(self):                      # Unmount flash and power it down
        if self.flash is None:
            return
        if self.mounted:
            self.flash.sync()
        try:
            pyb.mount(None, self.flash.mountpoint)
        except OSError:
            pass                                # Don't care if it wasn't mounted
        self.flash.end()                        # Shut down, turn off power if under control
        self.mounted = False                    # flag unmounted to prevent spurious syncs

    def show(self):
        self.umountflash()                      # sync, umount flash, shut it down and disable SPI
                                                # EPD functions which access the display electronics must be
        with self.epd as epd:                   # called from a with block to ensure proper startup & shutdown
            epd.showdata()

        if self.pwr_controller is None:         # Normal operation without power control: remount
            self.mountflash()

    @property
    def temperature(self):                      # return temperature as integer in Celsius
        return self.epd.temperature

    def clear_screen(self, show = True):
        self.locate(0, 0)                       # Reset text cursor
        self.epd.clear_data()
        if show:
            self.show()

    @micropython.native
    def setpixel(self, x, y, black):            # 41uS. Clips to borders
        if y < 0 or y >= LINES_PER_DISPLAY or x < 0 or x >= BITS_PER_LINE :
            return
        image = self.epd.image
        omask = 1 << (x & 0x07)
        index = (x >> 3) + y *BYTES_PER_LINE
        if black:
            image[index] |= omask
        else:
            image[index] &= (omask ^ 0xff)

    @micropython.viper
    def setpixelfast(self, x: int, y: int, black: int): # 27uS. Caller checks bounds
        image = ptr8(self.epd.image)
        omask = 1 << (x & 0x07)
        index = (x >> 3) + y * 33 #BYTES_PER_LINE
        if black:
            image[index] |= omask
        else:
            image[index] &= (omask ^ 0xff)

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

    def _circle(self, x0, y0, r, black = True): # Single pixel circle
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

    def load_xbm(self, sourcefile, x = 0, y = 0):
        g = get_xbm_data(sourcefile)
        width = next(g)
        height = next(g)
        self.loadgfx(g, width, height, x, y)

# Load a rectangular region with a bitmap supplied by a generator. This must supply bytes for each line in turn. These
# are displyed left to right, LSB of the 1st byte being at the top LH corner. Unused bits at the end of the line are
# ignored with a  new line starting on the next byte.

    def loadgfx(self, gen, width, height, x0, y0):
        byteoffset = x0 >> 3
        bitshift = x0 & 7   # Offset of image relative to byte boundary
        bytes_per_line = width >> 3
        if width & 7 > 0:
            bytes_per_line += 1
        for line in range(height):
            y = y0 + line
            if y >= LINES_PER_DISPLAY:
                break
            index = y * BYTES_PER_LINE + byteoffset
            bitsleft = width
            x = x0
            for byte in range(bytes_per_line):
                val = next(gen)
                bits_to_write = min(bitsleft, 8)
                x += bits_to_write
                if x <= BITS_PER_LINE:
                    if bitshift == 0 and bits_to_write == 8:
                        self.epd.image[index] = val
                        index += 1
                    else:
                        mask = ((1 << bitshift) -1) # Bits in current byte to preserve
                        bitsused = bitshift + bits_to_write
                        overflow = max(0, bitsused -8)
                        underflow = max(0, 8 -bitsused)
                        if underflow:               # Underflow in current byte
                            mask = (mask | ~((1 << bitsused) -1)) & 0xff
                        nmask = ~mask & 0xff        # Bits to overwrite
                        self.epd.image[index] = (self.epd.image[index] & mask) | ((val << bitshift) & nmask)
                        index += 1
                        if overflow :               # Bits to write to next byte
                            mask = ~((1 << overflow) -1) & 0xff    # Preserve
                            self.epd.image[index] = (self.epd.image[index] & mask) | (val >> (8 - bitshift))
                bitsleft -= bits_to_write

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
            bytenum = bit_vert >> 3
            bit = 1 << (bit_vert & 0x07)        # Faster than divmod
            for bit_horiz in range(self.font.bits_horiz): #  horizontal line
                fontbyte = fontbuf[self.font.bytes_vert * bit_horiz + bytenum +1]
                self.setpixelfast(self.char_x +bit_horiz, self.char_y +bit_vert, (fontbyte & bit) > 0)
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
