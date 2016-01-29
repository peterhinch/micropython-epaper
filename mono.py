import pyb, epaper
from micropower import PowerController
p = PowerController(pin_active_high = 'Y12', pin_active_low = 'Y11')
p.power_up()
a = epaper.Display(side = 'L')

with a.font('/sd/Courier_New19x11$isDegs', monospaced = True):
    a.puts('Test of alignment 12.34\n')
    a.puts('mmmmmmmmmmmmmmmmm 12.34\n')
a.show()
p.power_down()
