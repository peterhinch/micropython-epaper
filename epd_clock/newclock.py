# newclock.py Unusual clock display for Embedded Artists' 2.7 inch E-paper Display.

# Released under the Apache license: see LICENSE
# Copyright (c) Peter Hinch 2020

# Tested on a Pyboard 1.0
from cmath import rect, phase
from math import sin, cos, pi
from micropython import const
import gc
import epaper
from micropower import PowerController  # Only required for my hardware
import time
import arial15 as font1
import arial12 as font2

# **** BEGIN DISPLAY CONSTANTS ****
THETA = pi/3  # Intersection of arc with unit circle
PHI = pi/12  # Arc is +-30 minute segment
CRADIUS = const(70)  # Circle radius in pixels
CXOFFSET = const(17)  # Circle offset in pixels
CYOFFSET = const(17)
ST = CRADIUS + CXOFFSET
# Locations for external hours strings. Hand optimised.
TXT = ((ST + 38, CYOFFSET - 4),
       (ST + 64,  CYOFFSET + 22),
       (ST + 75,  CYOFFSET + 63),
       (ST + 64,  CYOFFSET + 101),
       (ST + 39,  CYOFFSET + 131),
       (ST - 3,  CYOFFSET + 143),
       (ST - 47,  CYOFFSET + 131),
       (ST - 73,  CYOFFSET + 101),
       (ST - 83,  CYOFFSET + 63),
       (ST - 79,  CYOFFSET + 22),
       (ST - 50,  CYOFFSET - 5),
       (ST - 7,  CYOFFSET - 17))
# Locations for internal text
TXTI = ((ST -48,  CYOFFSET + 26, ST + 50,  CYOFFSET + 75),
       (ST - 22,  CYOFFSET + 13, ST + 35,  CYOFFSET + 103),
       (ST + 2,  CYOFFSET + 10, ST + 8,  CYOFFSET + 123),
       (ST + 25,  CYOFFSET + 28, ST - 25,  CYOFFSET + 118),
       (ST + 38,  CYOFFSET + 56, ST - 45,  CYOFFSET + 105),
       (ST + 43,  CYOFFSET + 78, ST - 60,  CYOFFSET + 78),
       (ST + 32,  CYOFFSET + 105, ST - 65,  CYOFFSET + 53),
       (ST + 2,  CYOFFSET + 118, ST - 48,  CYOFFSET + 27),
       (ST - 20,  CYOFFSET + 123, ST - 20,  CYOFFSET + 8),
       (ST - 40,  CYOFFSET + 106, ST + 10,  CYOFFSET + 8),
       (ST - 55,  CYOFFSET + 76, ST + 33,  CYOFFSET + 27),
       (ST - 60,  CYOFFSET + 52, ST + 50,  CYOFFSET + 52))

# **** BEGIN DERIVED AND OTHER CONSTANTS ****

days = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday',
        'Sunday')
months = ('Jan', 'Feb', 'March', 'April', 'May', 'June', 'July',
            'Aug', 'Sept', 'Oct', 'Nov', 'Dec')

# Translation vector from unit circle to display coordinates
RADIUS = sin(THETA) / sin(PHI)
XLT = cos(THETA) - RADIUS * cos(PHI)  # Convert arc relative to [0,0] relative
RV = pi / 360  # Interpolate arc to 1 minute
TV = RV / 5  # Small increment << I minute
OR = cos(THETA) - RADIUS * cos(PHI) + 0j  # Origin of arc

# **** BEGIN DAYLIGHT SAVING ****
# This code returns the UK Time including daylight saving
# Adapted from https://forum.micropython.org/viewtopic.php?f=2&t=4034
# Winter UTC Summer (BST) is UTC+1H
# Changes happen last Sundays of March (BST) and October (UTC) at 01:00 UTC
# Ref. formulas : http://www.webexhibits.org/daylightsaving/i.html
#                 Since 1996, valid through 2099
def gbtime():
    year = time.localtime()[0]       #get current year
    HHMarch   = time.mktime((year,3 ,(31-(int(5*year/4+4))%7),1,0,0,0,0,0)) #Time of March change to BST
    HHOctober = time.mktime((year,10,(31-(int(5*year/4+1))%7),1,0,0,0,0,0)) #Time of October change to UTC
    now=time.time()
    if now < HHMarch :               # we are before last sunday of march
        cet=time.localtime(now) # UTC
    elif now < HHOctober :           # we are before last sunday of october
        cet=time.localtime(now+3600) # BST: UTC+1H
    else:                            # we are after last sunday of october
        cet=time.localtime(now) # UTC
    return(cet)

# **** BEGIN VECTOR CODE ****
# A vector is a line on the complex plane defined by a tuple of two complex
# numbers. Vectors presented for display lie in the unit circle.

# Generate vectors comprising sectors of an arc. hrs defines location of arc,
# angle its length.
# 1 <= hrs <= 12 0 <= angle < 60 in normal use
# To print full arc angle == 60
def arc(hrs, angle=60, mul=1.0):
    vs = rect(RADIUS * mul, PHI)  # Coords relative to arc origin
    ve = rect(RADIUS * mul, PHI)
    pe = PHI - angle * RV + TV
    rv = rect(1, -RV)  # Rotation vector for 1 minute (about OR)
    rot = rect(1, (3 - hrs) * pi / 6)  # hrs rotation (about [0,0])
    while phase(vs) > pe:
        ve *= rv
        # Translate to 0, 0
        yield ((vs + XLT) * rot, (ve + XLT) * rot)
        vs *= rv

# Currently unused. Draw the unit circle in a way which may readily be
# ported to other displays.
def circle():
    segs = 60
    phi = 2 * pi / segs
    rv = rect(1, phi)
    vs = 1 + 0j
    ve = vs
    for _ in range(segs):
        ve *= rv
        yield vs, ve
        vs *= rv

# Generate vectors for the minutes ticks
def ticks(hrs, length):
    vs = rect(RADIUS, PHI)  # Coords relative to arc origin
    ve = rect(RADIUS - length, PHI)  # Short tick
    ve1 = rect(RADIUS - 1.5 * length, PHI)  # Long tick
    ve2 = rect(RADIUS - 2.0 * length, PHI)  # Extra long tick
    rv = rect(1, -5 * RV)  # Rotation vector for 5 minutes (about OR)
    rot = rect(1, (3 - hrs) * pi / 6)  # hrs rotation (about [0,0])
    for n in range(13):
        # Translate to 0, 0
        if n == 6:  # Overdrawn by hour pointer: visually cleaner if we skip
            yield
        elif n % 3 == 0:
            yield ((vs + XLT) * rot, (ve2 + XLT) * rot)  # Extra Long
        elif n % 2 == 0:
            yield ((vs + XLT) * rot, (ve1 + XLT) * rot)  # Long
        else:
            yield ((vs + XLT) * rot, (ve + XLT) * rot)  # Short
        vs *= rv
        ve *= rv
        ve1 *= rv
        ve2 *= rv

# Generate vectors for the hour chevron
def hour(hrs):
    vs = -1 + 0j
    ve = 0.96 + 0j
    rot = rect(1, (3 - hrs) * pi / 6)  # hrs rotation (about [0,0])
    yield (vs * rot, ve * rot)
    vs = 0.85 + 0.1j
    yield (vs * rot, ve * rot)
    vs = 0.85 - 0.1j
    yield (vs * rot, ve * rot)

# Draw a vector scaling it for display and converting to integer x, y
# BEWARE unconventional Y coordinate on Pervasive Displays EPD.
def draw_vec(vec, width=1):
    vs, ve = vec
    vs = vs.real - 1j * vs.imag  # Invert for weird coordinate system
    ve = ve.real - 1j * ve.imag
    vs += 1 + 1j  # Real and imag now positive
    ve += 1 + 1j
    xlat = CXOFFSET + 1j * CYOFFSET  # Translation vector
    vs = vs * CRADIUS + xlat  # Scale and shift to graphics coords
    ve = ve * CRADIUS + xlat
    e.line(round(vs.real), round(vs.imag), round(ve.real), round(ve.imag), width)

# **** BEGIN POPULATE DISPLAY ****

def populate(e, angle, hrs):
    # Draw graphics. Built-in circle method provides a slightly better visual.
    e.circle(CXOFFSET + CRADIUS, CYOFFSET + CRADIUS, CRADIUS, 1)
    # Easily portable alternative:
    #for vec in circle():
        #draw_vec(vec)
    for vec in arc(hrs):  # -30 to +30 arc
        draw_vec(vec)  # Arc
    for vec in ticks(hrs, 0.1):  # Ticks
        if vec is not None:
            draw_vec(vec)
    for vec in arc(hrs, angle, 0.99):  # Elapsed minutes arc
        draw_vec(vec, 3)  # Elapsed minutes
    for vec in hour(hrs):  # Chevron
        draw_vec(vec)
    # Draw text outside circle
    with e.font(font1):
        for n, pos in enumerate(TXT):
            e.locate(*pos)
            e.puts(str(n +1))
        e.locate(0, 0)
        e.puts('AM' if t[3] < 11 else 'PM')
    # Draw internal minutes numbers
    with e.font(font2):
        pos = TXTI[hrs - 1]  # Get locations
        e.locate(*pos[0:2])
        e.puts('-30')
        e.locate(*pos[2:4])
        e.puts('30')
    # Day/date text on RHS
    with e.font(font1):
        x = 175
        y = 0
        e.locate(x, y)
        e.puts(days[t[6]])
        y += font1.height() + 2
        e.locate(x, y)
        e.puts('{} {} {}'.format(t[2], months[t[1] - 1], t[0]))

# **** BEGIN REQUIRED FOR MY HARDWARE ****
p = PowerController(pin_active_high = 'Y12', pin_active_low = 'Y11')
p.power_up()
# **** END ****


e = epaper.Display(side = 'L', mode = epaper.FAST) #, up_time=200)
with e:
    old_mins = -1  # Invalidate
    while True:
        t = gbtime()  # Handle DST. t is tuple as per time.localtime()
        mins = t[4]
        if mins != old_mins:  # Minute has changed
            # Calculate angle: minutes before half hour are displayed to the
            # right of centre, those after are to the left.
            angle = mins + 30 if mins < 30 else mins - 30
            if old_mins == -1 or angle == 0:
                # Reset buffers to initial state and display blank screen
                e.clear_screen(True, True)
            else:
                e.clear_screen(False)  # Clear current buffer, don't display
            # Calculate hours for display.
            if old_mins == -1:  # Just started
                if mins < 30:
                    hrs = (t[3] % 12)
                    if hrs == 0:
                        hrs = 12
                else:
                    hrs = (t[3] % 12) + 1
            elif angle == 0:  # Time is at half past hour: hour shown is +1
                hrs = (t[3] % 12) + 1
            old_mins = mins
            populate(e, angle, hrs)
            e.refresh()
            gc.collect()
        time.sleep(20)
