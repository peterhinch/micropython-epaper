# panel.py pin definition for Embedded Artists' 2.7 inch E-paper Display.
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

# Pin definitions. Y skin is tuple[0], X is tuple[1]
PINS = {'PANEL_ON': ('Y3','X3'), 'BORDER': ('X12','Y12'), 'DISCHARGE': ('Y4','X4'),
        'RESET':    ('Y2','X2'), 'BUSY':   ('X11','Y11'), 'EPD_CS':    ('Y5','X5'),
        'FLASH_CS': ('Y1','X1'), 'MOSI':   ('Y8','X8'),   'MISO':      ('Y7','X7'),
        'SCK':      ('Y6','X6'), 'SPI_BUS': (2,1),        'I2C_BUS':(1,2)}

