# Test program for micropower operation.
# Requirements:
# epaper display on Y side of pyboard
# power switching hardware controlled by pin Y12
# Font loaded onto EPD flash: LiberationSerif-Regular45x44
# Displays time and temperature at 20 second intervals. Consumes 30uA when idle.
# If USB is connected does not enter standby to aid testing at the REPL

import pyb, epaper, stm
rtc = pyb.RTC()

usb_connected = pyb.Pin.board.USB_VBUS.value() == 1
if not usb_connected:
    pyb.usb_mode(None) # Save power

if stm.mem32[stm.RTC + stm.RTC_BKP1R] == 0:     # first boot
    rtc.datetime((2015, 8, 6, 4, 13, 0, 0, 0)) # Arbitrary

t = rtc.datetime()[4:7]
timestring = '{:02d}.{:02d}.{:02d}'.format(t[0],t[1],t[2])
a = epaper.Display(side = 'Y', use_flash = True, pin_pwr = 'Y12', pwr_on = 1)
s = str(a.temperature) + "C\n" + timestring
a.mountflash() # Power up
with a.font('/fc/LiberationSerif-Regular45x44'):
    a.puts(s)
a.umountflash() # Keep filesystem happy
a.show()

rtc.wakeup(20000)
stm.mem32[stm.RTC + stm.RTC_BKP1R] = 1 # indicate that we are going into standby mode
if not usb_connected:
    pyb.standby()
