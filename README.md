# micropython-epaper
A driver to enable the Pyboard to access a 2.7 inch e-paper display from
[Embedded Artists](www.embeddedartists.com/products/displays/lcd_27_epaper.php)
This can be bought from [Adafruit](www.adafruit.com) and in Europe from
[Cool Components](www.coolcomponents.co.uk).
This driver requires a Pyboard with firmware dated 28th July 2015 or later.

### Introduction

E-paper displays have high contrast and the ability to retain an image with the power
disconnected. They also have very low power consumption when in use. The Embedded
Artists model suopports monochrome only, with no grey scale: pixels are either on or off.
Further the display refresh takes time. The minimum update time defined by explicit delays
is 1.6 seconds. With the current driver it takes 3.5 S. This after some efforts at optimisation.
A time closer to 1.6 S might be achieved by writing key methods in Assembler but I have no
plans to do this. It is considerably faster than the Arduino code and as fast as the best
alternative board I have seen.

The EA rev D display includes an LM75 temperature sensor and a 4MB flash memory chip. The
driver provides access to the current temperature. The driver does not use the flash
chip: the current image is buffered in RAM. The driver has an option to mount
the flash device to enable it to be used to store data such as images and fonts. This
is the ``use_flash`` Display constructor argument. Setting this False will save over 8K of RAM.

An issue with the EA module is that the Flash memory and the display module use the
SPI bus in different, incompatible ways. The driver provides a means of arbitration between
these devices discussed below. This is transparent to the user of the Display class.

One application area for e-paper displays is in ultra low power applications. The Pyboard
in standby mode consumes about 30uA. To avoid adding to this an external circuit is required
to turn off the power to the display and any other peripherals before entering standby. the
driver provides support for such use: see Micropower Support below.

# The driver

The driver enables the display of simple graphics and/or text in any font. The graphics
capability may readily be extended by the user. This document includes instructions for
converting Windows system fonts to a form usable by the driver (using free - as in beer - software).
Such fonts may be edited prior to conversion. If anyone can point me to an open source
pure Python solution - command line would be fine - I would gladly evaluate it. My own
attempts at writing one have not been entirely successful to date.

It also supports the display of XBM format graphics files. Currently only files corresponding
to the exact size of the display (264 bits *176 lines) are supported.

# Connecting the display

The display is supplied with a 14 way ribbon cable. The easiest way to connect
it to the Pyboard is to cut this cable in half and wire one half of it (they are identical)
as follows. I fitted the Pyboard with socket headers and wired the display cable to a
14 way pin header, enabling it to be plugged in to either side of the Pyboard (the two
sides, labelled X and Y on the board, are symmetrical).

| display | signal     |  Y  |  X  | Python name   |
|:-------:|:----------:|:---:|:---:|:-------------:|
|  1      | GND        | GND | GND |               |
|  2      | 3V3        | 3V3 | 3V3 |               |
|  3      | SCK        | Y6  | X6  | (SPI bus)     |
|  4      | MOSI       | Y8  | X8  |               |
|  5      | MISO       | Y7  | X7  |               |
|  6      | SSEL       | Y5  | X5  | Pin_EPD_CS    |
|  7      | Busy       | X11 | Y11 | Pin_BUSY      |
|  8      | Border Ctl | X12 | Y12 | Pin_BORDER    |
|  9      | SCL        | X9  | Y9  | (I2C bus)     |
| 10      | SDA        | X10 | Y10 |               |
| 11      | CS Flash   | Y1  | X1  | Pin_FLASH_CS  |
| 12      | Reset      | Y2  | X2  | Pin_RESET     |
| 13      | Pwr        | Y3  | X3  | Pin_PANEL_ON  |
| 14      | Discharge  | Y4  | X4  | Pin_DISCHARGE |

Red stripe on cable is pin 1.

For information this shows the E-paper 14 way 0.1inch pitch connector as viewed looking down
on the pins with the keying cutout to the left:

|  L |  R |
|:--:|:--:|
|  1 |  2 |
|  3 |  4 |
|  5 |  6 |
|  7 |  8 |
|  9 | 10 |
| 11 | 12 |
| 13 | 14 |

The SPI bus is not designed for driving long wires. This driver uses it at upto 21MHz so keep
them short!

# Getting started

Assuming the device is connected on the 'Y' side simply cut and paste this at the REPL.

```python
import epaper
a = epaper.Display('Y')
a.rect(20, 20, 150, 150, 3)
a.show()
```

To clear the screen and print a message (assuming we are using an SD card):

```python
a.clear_screen()
with a.font('/sd/inconsolata'):
 a.puts("Large font\ntext here")
```

# Modules

To employ the driver it is only neccessary to import the epaper module and to instantiate the
``Display`` class. The driver comprises the following modules:
 1. epaper.py The user interface to the display and flash memory
 2. epd.py Low level driver for the EPD (electrophoretic display)
 3. flash.py Low level driver for the flash memory
 4. panel.py Support for optional external power control (see below)

Note that the flash drive will need to be formatted before first use: see the flash.py doc below.

# Files and Utilities

``CfontToBinary.py`` Converts a "C" code file generated by GLC Font Creator into a binary file
usable by the driver.  
``LiberationSerif-Regular45x44`` Sample binary font files (Times Roman lookalike)  
``inconsolata`` Monospaced 24 point terminal font  
``aphrodite_2_7.xbm`` Sample full screen image files  
``cat_2_7.xbm``  
``ea_2_7.xbm``  
``saturn_2_7.xbm``  
``text_image_2_7.xbm``  
``venus_2_7.xbm``

# Module epaper.py

This is the user interface to the display, the flash memory and the temperature sensor. Display
data is buffered. The procedure for displaying text or graphics is to use the various methods
described below to write text or graphics to the buffer and then to call ``show()`` to
display the result. The ``show()`` method is the only one to access the EPD module (although
``clear_screen()`` calls ``show()``). Others affect the buffer alone.

There is support for micropower operation where the system power consumption must be minimised
for long term operation from batteries. This uses external circuitry to shut down the power to
the display before you issue ``pyb.stop()`` or ``pyb.standby``. See the appendix below.

The coodinate system has its origin at the top left corner of the display, with integer
X values from 0 to 263 and Y from 0 to 175 (inclusive).

In general the graphics code prioritises simplicity over efficiency: e-paper displays are far
from fast. But I might get round to improving the speed of font rendering which is particularly
slow when you write a string using a large font. In the meantime be patient. Or offer a patch :)

## Display class

### Methods

``Display()`` The constructor has the following arguments:
 1. ``use_flash`` Mounts the flash drive as /fc for general use. Default False.
 2. ``side`` This must be 'X' or 'Y' depending on the side of the Pyboard in use. Default 'Y'.
 3. ``pin_pwr`` Specifies a pin for optional micropower support. Default None.
 4. ``pwr_on`` Pass 1 or 0 to define the ON state of the micropower circuit. Default None.

``clear_screen()`` Clears the screen by blanking the screen buffer and calling ``show()``  
``show()`` Displays the contents of the screen buffer.  
``line()`` Draw a line. Arguments ``X0, Y0, X1, Y1, Width, Black``. Defaults: width = 1 pixel,
Black = True  
``rect()`` Draw a rectangle. Arguments ``X0, Y0, X1, Y1, Width, Black``. Defaults: width = 1 pixel,
Black = True  
``fillrect()`` Draw a filled rectangle. Arguments ``X0, Y0, X1, Y1, Black``. Defaults: Black = True  
``circle()`` Draw a circle. Arguments ``x0, y0, r, width, black``. Defaults: width = 1 pixel,
Black = True. x0, y0 are the coodinates of the centre, r is the radius.  
``fillcircle()`` Draw a filled circle. Arguments ``x0, y0, r, black``. Defaults: Black = True  
``load_xbm()`` Load a full screen image formatted as an XBM file. Argument ``sourcefile``. This is
the path to the XBM file.  
``locate()`` This sets the pixel location of the text cursor. Arguments ``x, y``.  
``puts()`` Write a text string to the buffer. Argument ``s``, the string to display. This must
be called from a ``with`` block that defines the font. For example

```python```
with a.font('/sd/LiberationSerif-Regular45x44'):
 a.puts("Large font\ntext here")
```

``setpixel()`` Set or clear a pixel. Arguments ``x, y, black``. Checks for and ignores pixels not
within the display boundary.  
``setpixelfast()`` Set or clear a pixel. Arguments ``x, y, black``. Caller must check bounds. Uses
the viper emitter for maximum speed.

The following methods are intended to support micropower operation using external power control hardware.
They should not be used in normal opertion as in this case the flash device is mounted automatically.

``mountflash()`` Power up the panel and mount the flash device.  
``umountflash()`` Unmount the flash memory and power down the panel.

### Properties

``temperature`` Returns the current temperature in degrees Celcius.

## Font class

This is a Python context manager whose purpose is to define a context for the ``Display`` ``puts()``
method described above, ensuring that the font file is closed. It has no user accessible
properties or methods. A font is instantiated for the duration of outputting one or more
strings. It must be provided with the path to a valid binary font file. See the code
sample above.

In the interests of conserving scarce RAM, fonts are stored in binary files. Individual
characters are buffered in RAM as required. This contrasts with the conventional approach of
buffering the entire font in RAM, which is faster. The EPD is not a fast device and RAM is
in short supply, hence the design decision. This is transparent to the user.

# Module epd.py

This provides the low level interface to the EPD display module. It provides two methods
and one property accesed by the ``epaper`` module:

### Methods

``showdata()`` Displays the current text buffer  
``clear_data()`` Clears the buffer without displaying it.

### Property

``temperature`` the temperature in degrees Celcius

# Module flash.py

This provides an interface to the flash memory. It supports the block protocol
enabling the flash device to be mounted on the Pyboard filesystem and used for any
purpose. There is a compromise in the design of this class between RAM usage and
flash device wear. The compromise chosen is to buffer the two most recently written
sectors: this uses 8K of RAM and substantially reduces the number of erase/write cycles,
especially for low numbered sectors, compared to a naive unbuffered approach. The
anticipated use for the flash is for storing rarely changing images and fonts so I
think the compromise is reasonable.

Buffering also improves perceived performance by reducing the number of erase/write
cycles.

## Getting Started

The flash drive must be formatted before first use. The code below will do this, and
demonstrates copying a file to the drive (assuming you have first put the file on the
SD card - modify this for any available file).

```python
import pyb, flash, os
f = flash.FlashClass(0) # If on X side pass 1
f.low_level_format()
pyb.mount(f, f.mountpoint, mkfs=True)
flash.cp('/sd/LiberationSerif-Regular45x44','/fc/LiberationSerif-Regular45x44')
os.listdir('/fc')
pyb.mount(None, '/fc')

```

## File copy

A ``cp(source, dest)`` function is provided as a generic file copy routine. Arguments are
full pathnames to source and destination files. If an OSError is thrown (e.g. by the
source file not existing) it is up to the caller to handle it.

## FlashClass

### Methods providing the block protocol

For the protocol definition see
[the pyb documentation](http://docs.micropython.org/en/latest/library/pyb.html)

``readblocks()``  
``writeblocks()``  
``sync()``  
``count()``  

### Other methods

The following methods are available for general use.
``available()`` Returns True if the device is detected and is supported.  
``info()`` Returns manufacturer and device ID as integers.  
``begin()`` Set up the bus and device. Throws a FlashException if device cannot be validated.  
``end()`` Sync the device then shut down the bus.  
``low_level_format()`` Erases the filesystem! Currently (this may change) the pyb module doesn't
provide a means of forcing a drive format. Issuing a ``low_level_format()`` followed by
``pyb.mount()`` with ``mkfs-True`` will format the drive deleting all files.

Other than for debugging there is no need to call ``available()``: the constructor will throw
a ``FlashException`` if it fails to communicate with and correctly identify the chip.

### SPI bus arbitration

This is provided for information for those wishing to modify the code. The Embedded Artists device
has a flash memory chip (Winbond  W25Q32 32Mbit chip) which shares the SPI bus with the display
device (Pervasive Displays EM027BS013). These use the bus in different incompatible ways,
consequently to use the display with the flash device mounted requires arbitration. This is
done in the Display class ``show()`` method. Firstly it disables the Flash memory's use of the bus
with ``self.flash.end()``. The EPD class is a Python context manager and its appearance in a
``with`` statement performs hardware initialisation including setting up the bus.

On completion of the ``with`` block the display hardware is shut down in an orderly fashion and
the bus de-initilased. The flash device is then re-initilased and re-mounted.

# Module panel.py

This provides the base class for the ``EPD`` and ``FlashClass`` classes. Its purpose is to support optional
external hardware for micropower operation. Its methods do nothing unless the Display object
was instantiated with ``pin_pwr`` and ``pwr_on`` arguments. It also provides the Pyboard pin definitions
for use by the panel.

### Methods

``poweron()`` Turns the power control hardware on, delays 10mS.  
``poweroff()`` Turns the power control hardware off.

# Fonts

As explained above, the driver requires fonts to be provided in a specific binary file format. This
section describes how to produce these. Alas this needs a Windows program available
[here](http://www.mikroe.com/glcd-font-creator/) but it is free (as in beer).

To convert a system font to a usable format follow these steps.  
Start the Font Creator. Select File - New Font - Import an Existing System Font and select a font.
Accept the defaults. Assuming you have no desire to modify it click on the button "Export for GLCD".
Select the microC tab and press Save, following the usual file creation routine.

On a PC with Python 3 installed issue (to convert a file trebuchet.c to binary trebuchet)
```
$ ./CfontToBinary.py -i trebuchet.c -o trebuchet
```
The latter file can then be copied to the Pyboard and used by the driver.

This assumes Linux but CfontToBinary.py is plain Python3 and should run on other platforms. 

Although small fonts are displayed accurately they can be hard to read! Note that fonts
can be subject to copyright restrictions. The provided font samples are released under open licences.

# Micropower Support

This enables the display panel to be turned off to conserve power in applications where power consumption
is critical and assumes external hardware to ahieve this. Hardware issues are discussed [here](micropower/micropower.md)

Given a hardware controller capable of switching the power to the display (it uses about 10mA
during transitions) your code should instantiate the ``Display`` object with the pin ID that
operates your controller and its sense (the bit value required to turn the display on). Then use
the display (and temperature sensor) as normal. The ``Display`` object will use the hardware to turn
the display on and off as necessary.

In this mode usage of the LM75 is supported: the ``Display.temperature`` property powers up the LM75
for the duration of the reading. Use of flash is also supported, but to take advantage of the hardware the flash
is not permanently mounted as this would require the hardware to be powered up. Accordingly
the device should be mounted using the ``Display`` class ``mountflash()`` method prior to use and
unmounted using the ``umountflash()`` method. Power will be applied for the duration of the mount.

To achieve minimum power consumption use the processor flash memory for code storage rather than an
SD card because this draws power even when the Pyboard is in standby. Current consumption using ``pyb.standby()``
with a suitable hardware switch should be about 30uA offering the potential of months of operation
from a CR2032 button cell depending on the frequency and duration of power up events. Use of the panel's
flash memory will add minimal power as the hardware powers off the entire panel in standby.

# Legalities

This software is based on C code released under the Apache licence. Accordingly I have released this
code under the same licence and included the original copyright headers in the source. If the
copyright owner has any issues with this I will be happy to accommodate any requests for changes.

# References

This code is derived from that at [Embedded Artists](https://github.com/embeddedartists/gratis)
with graphics code derived from [ARM mbed](https://developer.mbed.org/users/dreschpe/code/EaEpaper/)

Further sources of information:  
[device data and interface timing](http://www.pervasivedisplays.com/products/27)  
[COG interface timing](http://www.pervasivedisplays.com/_literature_220873/COG_Driver_Interface_Timing_for_small_size_G2_V231)  
[Flash device data](http://www.elinux.org/images/f/f5/Winbond-w25q32.pdf)  
[RePaper](http://repaper.org/doc/cog_driving.html)
