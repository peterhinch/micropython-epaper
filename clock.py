# clock.py demo for e-paper fast mode
# Simpler approach: clear data each pass.

import epaper, time, math, pyb
a = epaper.Display('L', mode = epaper.FAST)

def polar_line(origin, length, width):
    def draw(radians):
        x_end = origin[0] + length * math.sin(radians)
        y_end = origin[1] - length * math.cos(radians)
        a.line(origin[0], origin[1], x_end, y_end, width, True)
    return draw

origin = 100, 100
secs = polar_line(origin, 50, 1)
mins = polar_line(origin, 50, 2)
hours = polar_line(origin, 30, 4)

with a:
    a.clear_screen()
    while True:
        a.clear_screen(False)
        a.circle(origin[0], origin[1], 55, 1)
        t = time.localtime()
        h, m, s = t[3:6]
        hh = h + m /60
        with a.font('/sd/LiberationSerif-Regular45x44'):
            a.locate(0,0)
            a.puts('{:02d}.{:02d}.{:02d}'.format(h, m, s))
        secs(2 * math.pi * s/60)
        mins(2 * math.pi * m/60)
        hours(2 * math.pi * (h + m/60)/12)
        a.refresh()
