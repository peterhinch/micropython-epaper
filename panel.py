# panel.py base class for Embedded Artists' 2.7 inch E-paper Display.
# supports power control via external hardware driven by a single pin.
# 14th Aug 2015
# version 0.41

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

import pyb

# Pin definitions. Y skin is tuple[0], X is tuple[1]
PINS = {'PANEL_ON': ('Y3','X3'), 'BORDER': ('X12','Y12'), 'DISCHARGE': ('Y4','X4'),
        'RESET':    ('Y2','X2'), 'BUSY':   ('X11','Y11'), 'EPD_CS':    ('Y5','X5'),
        'FLASH_CS': ('Y1','X1'), 'MOSI':   ('Y8','X8'),   'MISO':      ('Y7','X7'),
        'SCK':      ('Y6','X6'), 'SPI_BUS': (2,1),        'I2C_BUS':(1,2)}

# Instantiate with a pin name and value which turns power on (0 or 1).
# If either is None power is deemed on continuously and class methods do nothing

class Panel(object):
    def __init__(self, pin_pwr, pwr_on):
        self.pwrctrl = not (pin_pwr is None or pwr_on is None)
        if self.pwrctrl:
            self.pwr_on = pwr_on
            self.pwr_off = pwr_on ^ 1
            self.pwrpin = pyb.Pin(pin_pwr, mode = pyb.Pin.OUT_PP)
            self.pwrpin.value(self.pwr_off)

    def poweron(self):
        if self.pwrctrl:
            self.pwrpin.value(self.pwr_on)
            pyb.delay(10)

    def poweroff(self):
        if self.pwrctrl:
            self.pwrpin.value(self.pwr_off)
