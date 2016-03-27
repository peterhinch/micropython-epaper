# Ghosting test: Version of e-paper clock running on Raspberry Pi
import sys, time, math
from PIL import Image
from PIL import ImageDraw, ImageFont
from EPD import EPD

WHITE = 1
BLACK = 0

class polar_line():
    def __init__(self, origin, length, width):
        self.width = width
        self.length = length
        self.x_end, self.y_end = None, None
        self.x_origin, self.y_origin = origin

    def draw_polar(self, radians):
        self.x_end = self.x_origin + self.length * math.sin(radians)
        self.y_end = self.y_origin - self.length * math.cos(radians)
        draw.line([(self.x_origin, self.y_origin), (self.x_end, self.y_end)], fill = BLACK, width = self.width)


origin = 100, 100
secs = polar_line(origin, 50, 1)
mins = polar_line(origin, 50, 2)
hours = polar_line(origin, 30, 4)


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
    secs.draw_polar(2 * math.pi * s/60)
    mins.draw_polar(2 * math.pi * m/60)
    hours.draw_polar(2 * math.pi * (h + m/60)/12)
    epd.display(image)
    epd.partial_update()

