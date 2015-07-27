# Observation of strange MicroPython behaviour

Initially a screen update took some 19 seconds and I made some efforts to reduce this. It emerged that
the overhwelming majority (98.5%) of this time was spent in the two EPD methods (``_line_fixed()`` and
``_line()``) which prepare and write to the hardware a display line. The use of the SPI bus is irreducable
beyond optimising the baud rate, buffering the data and sending it as a block. But there was scope for
improving the time spent updating the buffer.

Amongst other chnges the EPD methods ``_setbuf_data()`` and ``_setbuf_fixed()`` were implemented with
the viper decorator, eventually reducing the update time to 5.6 seconds. A figure of 3.6 seconds is
the irreducable minimum set by delays required by the hardware. Consequently the MicroPython overhead
is about two seconds.

In the course of reviewing the code I noticed that ``_setbuf_fixed()`` included a redundant line of code
```python
        image = self.image
```
I removed this. The code still worked, but update time increased to about 6.3S - an increase in the
MicroPython overhead from 2S to 2.7S: 35%.

I then wrote a script to call the method and time it. Interestingly the time was 275uS with or without
the offending line, perhaps implying that viper optimisation recognized its redundancy and issued no
code.

The effect on the MicroPython overhead is entirely repeatable and (to me) intriguing and baffling.
