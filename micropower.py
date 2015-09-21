# micropower.py Support for hardware capable of switching off the power for Pyboard peripherals
# 28th Aug 2015
# version 0.45

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

class PowerController(object):
    def __init__(self, pin_active_high, pin_active_low):
        self.upcount = 0
        if pin_active_low is not None:          # Start with power down
            self.al = pyb.Pin(pin_active_low, mode = pyb.Pin.OUT_PP)
            self.al.high()
        else:
            self.al = None
        if pin_active_high is not None:         # and pullups disabled
            self.ah = pyb.Pin(pin_active_high, mode = pyb.Pin.OUT_PP)
            self.ah.low()
        else:
            self.ah = None

    def __enter__(self):                        # Optional use as context manager
        self.power_up()
        return self

    def __exit__(self, *_):
        self.power_down()

    def power_up(self):
        self.upcount += 1                       # Cope with nested calls
        if self.upcount == 1:
            if self.ah is not None:
                self.ah.high()                  # Enable I2C pullups
            if self.al is not None:
                self.al.low()                   # Power up
            pyb.delay(10)                       # Nominal time for device to settle

    def power_down(self):
        if self.upcount > 1:
            self.upcount -= 1
        elif self.upcount == 1:
            self.upcount = 0
            if self.al is not None:
                self.al.high()                  # Power off
            pyb.delay(10)                       # Avoid glitches on switched
            if self.ah is not None:             # I2C bus while power decays
                self.ah.low()                   # Disable I2C pullups
        for bus in (pyb.SPI(1), pyb.SPI(2), pyb.I2C(1), pyb.I2C(2)):
            bus.deinit()                        # I2C drivers seem to need this

    @property
    def single_ended(self):
        return (self.ah is not None) and (self.al is not None)

