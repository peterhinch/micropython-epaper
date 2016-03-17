# clock.py demo for e-paper fast mode

import epaper, time, math, pyb
a = epaper.Display('L', mode = epaper.FAST)

# closure creates line which can be rotated, erasing old line
def polar_line(origin, length, width):
    x_end, y_end = None, None
    x_origin, y_origin = origin
    def draw(radians):
        nonlocal x_end, y_end, x_origin, y_origin
        if x_end is not None:
            a.line(x_origin, y_origin, x_end, y_end, width, False) # erase
        x_end = x_origin + length * math.sin(radians)
        y_end = y_origin - length * math.cos(radians)
        a.line(x_origin, y_origin, x_end, y_end, width, True)
    return draw

origin = 100, 100
secs = polar_line(origin, 50, 1)
mins = polar_line(origin, 50, 2)
hours = polar_line(origin, 30, 4)

with a:
    a.clear_screen()
    while True:
        a.circle(origin[0], origin[1], 55, 1)
        t = time.localtime()
        h, m, s = t[3:6]
        hh = h + m /60
        with a.font('/sd/LiberationSerif-Regular45x44'):
            a.locate(0,0)
            a.puts('{:02d}.{:02d}.{:02d} '.format(h, m, s)) # trailing space allows for varying character width
            secs(2 * math.pi * s/60)
            mins(2 * math.pi * m/60)
            hours(2 * math.pi * (h + m/60)/12)
            a.refresh()
