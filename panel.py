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
def getpins(intside):
    if intside == 0:
        result = {'PANEL_ON': 'Y3', 'BORDER': 'X12', 'DISCHARGE': 'Y4',
        'RESET': 'Y2', 'BUSY':   'X11', 'EPD_CS': 'Y5',
        'FLASH_CS': 'Y1', 'MOSI':   'Y8',  'MISO': 'Y7',
        'SCK': 'Y6', 'SPI_BUS': 2, 'I2C_BUS': 1}
    else:
         result =  {'PANEL_ON': 'X3', 'BORDER': 'Y12', 'DISCHARGE': 'X4',
        'RESET': 'X2', 'BUSY': 'Y11', 'EPD_CS': 'X5',
        'FLASH_CS': 'X1', 'MOSI': 'X8',  'MISO': 'X7',
        'SCK': 'X6', 'SPI_BUS': 1,  'I2C_BUS': 2}
    return result
