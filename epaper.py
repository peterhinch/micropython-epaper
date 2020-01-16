# epaper.py main module for Embedded Artists' 2.7 inch E-paper Display.
# Peter Hinch
# version 0.9
# 17 Jun 2018 Adapted for VFS mount/unmount.
# 18 Mar 2016 Adafruit module and fast (partial) updates.
# 2 Mar 2016 Power control support removed. Support for fonts as persistent byte code
# 29th Jan 2016 Monospaced fonts supported.

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

import pyb, gc, uos
from panel import NORMAL, FAST, EMBEDDED_ARTISTS, ADAFRUIT
LINES_PER_DISPLAY = const(176)  # 2.7 inch panel only!
BYTES_PER_LINE = const(33)
BITS_PER_LINE = const(264)

gc.collect()

NEWLINE = const(10)             # ord('\n')

class EPDError(OSError):
    pass

def checkstate(state, msg):
    if not state:
        raise EPDError(msg)

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
        self.bytes_horiz = 0    # No. of bytes per character row
        self.bits_horiz = 0     # Horzontal bits in character matrix
        self.bits_vert = 0      # Vertical bits in character matrix
        self.monospaced = False # Default is variable width
        self.exists = False
        self.modfont = None
        self.fontfilename = None
        self.fontfile = None

    # monospaced only applies to binary files. Since these lack an index FIXME
    # characters are saved in fixed pitch with width data, hence can be
    # rendered as fixed or variable pitch.
    # Python fonts are saved as variable or fixed pitch depending on the -f arg.
    # The monospaced flag saved with the file enables the renderer to
    # determine the correct x advance.
    def __call__(self, fontfilename, monospaced = False):
        self.fontfilename = fontfilename
        self.monospaced = monospaced
        return self

    def __enter__(self): #fopen(self, fontfile):
        if isinstance(self.fontfilename, type(uos)):  # Using a Python font
            self.fontfile = None
            f = self.fontfilename
            ok = False
            try:
                ok = f.hmap() and f.reverse()
            except AttributeError:
                pass
            if not ok:
                raise FontFileError('Font module {} is invalid'.format(f.__name__))
            self.monospaced = f.monospaced()
            self.modfont = f
            self.bits_horiz = f.max_width()
            self.bits_vert = f.height()
        else:
            self.modfont = None
            try:
                f = open(self.fontfilename, 'rb')
            except OSError as err:
                raise FontFileError(err)
            self.fontfile = f
            header = f.read(4)
            if header[0] == 0x42 and header[1] == 0xe7:
                self.bits_horiz = header[2] # font[1]
                self.bits_vert = header[3] # font[2]
            else:
                raise FontFileError('Font file {} is invalid'.format(self.fontfilename))
        self.bytes_horiz = (self.bits_horiz + 7) // 8
        self.bytes_per_ch = self.bytes_horiz * self.bits_vert
        self.exists = True
        return self

    def __exit__(self, *_):
        self.exists = False
        if self.fontfile is not None:
            self.fontfile.close()

class Display(object):
    FONT_HEADER_LENGTH = 4
    def __init__(self, side='L',*, mode=NORMAL, model=EMBEDDED_ARTISTS, use_flash=False, up_time=None):
        self.flash = None                       # Assume flash is unused
        self.in_context = False
        try:
            intside = {'l':0, 'r':1}[side.lower()]
        except (KeyError, AttributeError):
            raise ValueError("Side must be 'L' or 'R'")
        if model not in (EMBEDDED_ARTISTS, ADAFRUIT):
            raise ValueError('Unsupported model')
        if mode == FAST and use_flash:
            raise ValueError('Flash memory unavailable in fast mode')
        if mode == NORMAL and up_time is not None:
            raise ValueError('Cannot set up_time in normal mode')
        if mode == NORMAL:
            from epd import EPD
            self.epd = EPD(intside, model)
        elif mode == FAST:
            from epdpart import EPD
            self.epd = EPD(intside, model, up_time)
        else:
            raise ValueError('Unsupported mode {}'.format(mode))
        self.mode = mode
        self.font = Font()
        gc.collect()
        self.locate(0, 0)                       # Text cursor: default top left

        self.mounted = False                    # umountflash() not to sync
        if use_flash:
            from flash import FlashClass
            gc.collect()
            self.flash = FlashClass(intside)
            self.umountflash()                  # In case mounted by prior tests.
            self.mountflash()
        gc.collect()

    def checkcm(self):
        if not (self.mode == NORMAL or self.in_context):
            raise EPDError('Fast mode must be run using a context manager')

    def __enter__(self):                        # Power up
        checkstate(self.mode == FAST, "In normal mode, can't use context manager")
        self.in_context = True
        self.epd.enter()
        return self

    def __exit__(self, *_):                     # shut down
        self.in_context = False
        self.epd.exit()
        pass

    def mountflash(self):
        if self.flash is None:                  # Not being used
            return
        self.flash.begin()                      # Initialise.
        vfs = uos.VfsFat(self.flash)  # Instantiate FAT filesystem
        uos.mount(vfs, self.flash.mountpoint)
        self.mounted = True

    def umountflash(self):                      # Unmount flash
        if self.flash is None:
            return
        if self.mounted:
            self.flash.synchronise()
        try:
            uos.umount(self.flash.mountpoint)
        except OSError:
            pass                                # Don't care if it wasn't mounted
        self.flash.end()                        # Shut down
        self.mounted = False                    # flag unmounted to prevent spurious syncs

    def show(self):
        self.checkcm()
        self.umountflash()                      # sync, umount flash, shut it down and disable SPI
        if self.mode == NORMAL:                 # EPD functions which access the display electronics must be
            with self.epd as epd:               # called from a with block to ensure proper startup & shutdown
                epd.showdata()
        else:                                   # Fast mode: already in context manager
            self.epd.showdata()
        self.mountflash()

    def clear_screen(self, show=True, both=False):
        self.checkcm()
        self.locate(0, 0)                       # Reset text cursor
        self.epd.clear_data(both)
        if show:
            if self.mode == NORMAL:
                self.show()
            else:
                self.epd.EPD_clear()

    def refresh(self, fast =True):              # Fast mode only functions
        checkstate(self.mode == FAST, 'refresh() invalid in normal mode')
        self.checkcm()
        self.epd.refresh(fast)

    def exchange(self, clear_data):
        checkstate(self.mode == FAST, 'exchange() invalid in normal mode')
        self.checkcm()
        self.epd.exchange(clear_data)

    @property
    def temperature(self):                      # return temperature as integer in Celsius
        return self.epd.temperature

    @property
    def location(self):
        return self.char_x, self.char_y

    @micropython.native
    def setpixel(self, x, y, black):            # 41uS. Clips to borders. x, y must be integer
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
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
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
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
        x0, x1 = (x0, x1) if x1 > x0 else (x1, x0) # x0, y0 is top left, x1, y1 is bottom right
        y0, y1 = (y0, y1) if y1 > y0 else (y1, y0)
        for w in range(width):
            self._rect(x0 +w, y0 +w, x1 -w, y1 -w, black)

    def fillrect(self, x0, y0, x1, y1, black = True): # Draw filled rectangle
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
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
        x0, y0, r = int(x0), int(y0), int(r)
        for r in range(r, r -width, -1):
            self._circle(x0, y0, r, black)

    def fillcircle(self, x0, y0, r, black = True): # Draw filled circle
        x0, y0, r = int(x0), int(y0), int(r)
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

# Load a rectangular region with a bitmap supplied by a generator.

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

# font.bytes_horiz
# In cse of font file it's the pysical width of every character as stored in file
# In case of Python font it's the value of max_width converted to bytes
    def _character(self, c, usefile):
        font = self.font                        # Cache for speed
        bits_vert = font.bits_vert
        if usefile:
            ff = font.fontfile
            ff.seek(self.FONT_HEADER_LENGTH + (c -32) * (font.bytes_per_ch + 1))
            buf = ff.read(font.bytes_per_ch + 1)
            # Characters are stored as constant width.
            bytes_horiz = font.bytes_horiz      # No. of bytes before next row
            # Advance = bits_horiz if variable pitch else font.bits_horiz
            bits_horiz = buf[0]
            offset = 1
        else:
            modfont = font.modfont
            buf, height, bits_horiz = modfont.get_ch(chr(c))
            # Width varies between characters
            bytes_horiz = (bits_horiz + 7) // 8
            offset = 0
        # Sanity checks: prevent index errors. Wrapping should be done at string/word level.
        if (self.char_x + bytes_horiz * 8) > BITS_PER_LINE :
            self.char_x = 0
            self.char_y += bits_vert
        if self.char_y >= (LINES_PER_DISPLAY - bits_vert):
            self.char_y = 0

        image = self.epd.image
        y = self.char_y                         # x, y are pixel coordinates
        for bit_vert in range(bits_vert):       # for each vertical line
            x = self.char_x
            for byte_horiz in range(bytes_horiz):
                fontbyte = buf[bit_vert * bytes_horiz + byte_horiz + offset]
                index = (x >> 3) + y * BYTES_PER_LINE
                nbits = x & 0x07
                if nbits == 0:
                    image[index] = fontbyte
                else:
                    image[index] &= (0xff >> (8 - nbits))
                    image[index] |= (fontbyte << nbits)
                    image[index + 1] &= (0xff << nbits)
                    image[index + 1] |= (fontbyte >> (8 - nbits))
                x += 8
            y += 1
        self.char_x += font.bits_horiz if font.monospaced else bits_horiz

    def _putc(self, value, usefile):            # print char
        if (value == NEWLINE):
            self.char_x = 0
            self.char_y += self.font.bits_vert
            if (self.char_y >= LINES_PER_DISPLAY - self.font.bits_vert):
                self.char_y = 0
        else:
            self._character(value, usefile)
        return value

    def puts(self, s):                          # Output a string at cursor
        if self.font.exists:
            if self.font.modfont is None:       # No font module: using binary file
                for char in s:
                    c = ord(char)
                    if (c > 31 and c < 127) or c == NEWLINE:
                        self._putc(c, True)
            else:                               # Python font file is self-checking
                for char in s:
                    self._putc(ord(char), False)
        else:
             raise FontFileError("There is no current font")
