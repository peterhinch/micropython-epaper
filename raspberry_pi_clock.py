# Ghosting test: Version of e-paper clock running on Raspberry Pi
import sys, time, math
from PIL import Image
from PIL import ImageDraw, ImageFont
from EPD import EPD

WHITE = 1
BLACK = 0
origin = 100, 100 # of clock face

def polar_line(radians, length, width):
    x_end = origin[0] + length * math.sin(radians)
    y_end = origin[1] - length * math.cos(radians)
    draw.line([(origin[0], origin[1]), (x_end, y_end)], fill = BLACK, width = width)

epd = EPD()

print('panel = {p:s} {w:d} x {h:d}  version={v:s} COG={g:d} FILM={f:d}'.format(p=epd.panel, w=epd.width, h=epd.height, v=epd.version, g=epd.cog, f=epd.film))

epd.clear()

# initially set all white background
image = Image.new('1', epd.size, WHITE)
width, height = image.size
# prepare for drawing
draw = ImageDraw.Draw(image)
font = ImageFont.truetype("LiberationSerif-Regular.ttf", 36)
while True:
    draw.rectangle((0, 0, width, height), fill=WHITE, outline=WHITE)
    draw.ellipse((origin[0] -55, origin[1] -55, origin[0] +55, origin[1] +55), fill=WHITE, outline=BLACK)

    t = time.localtime()
    h, m, s = t[3:6]
    hh = h + m /60
    draw.text((0,0), '{:02d}.{:02d}.{:02d} '.format(h, m, s), font=font)
    polar_line(2 * math.pi * s/60, 50, 1)
    polar_line(2 * math.pi * m/60, 50, 2)
    polar_line(2 * math.pi * (h + m/60)/12, 30, 4)
    epd.display(image)
    epd.partial_update()

