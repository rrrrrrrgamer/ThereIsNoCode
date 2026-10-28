# Module docstring: a bare string at the top of the file that documents the whole program (lines inside a string can't carry comments)
"""
KARELS BARREL OF TERRORS  (puzzles + Escape Karel maze in ONE file)
-------------------------------------------------------------------
PART 1: the PyQt puzzle console (password -> three Karel puzzles).
PART 2: the "Escape Karel" maze game (pygame).

After the 3rd puzzle is solved the screen glitches, turns black, and then cuts straight
into the maze. Both parts live in this one file, so there is no second script to launch.
"""

import sys  # system access: command-line args, platform name, and sys.exit()
import math  # math functions (sin, hypot, pi, exp) used for animation and distances
import array  # compact typed arrays, used to build raw audio sample buffers
import random  # random numbers for mazes, glitches, and effects
import base64  # decodes the embedded base64 dog image
import io  # in-memory byte streams (lets pygame load an image from bytes)
import os  # file paths and directory listing
import traceback  # prints full error details if the maze crashes
from collections import deque  # fast double-ended queue, used for breadth-first search
import pygame  # game library used for the maze, sound, and drawing
from PyQt5.QtWidgets import QMainWindow, QApplication, QTextEdit, QPushButton, QWidget, QTabWidget, QGraphicsView, \
    QGraphicsScene, QGraphicsPixmapItem  # PyQt window/widget classes (the backslash continues the import onto the next line)
from PyQt5.QtGui import QBrush, QPen, QColor, QPixmap, QFont, QPainter, QRadialGradient, QFontMetrics  # PyQt drawing helpers: fills, outlines, colors, images, fonts, painter, gradients, text measuring
from PyQt5.QtTest import QTest  # QTest.qWait lets us pause without freezing the window
from PyQt5.QtCore import QTimer, Qt, QElapsedTimer  # timers and Qt constants (key codes, alignment, window flags)
from io import StringIO  # in-memory text buffer used to capture print() output
import contextlib  # provides redirect_stdout to capture printed text

# Hand-off flags between the puzzle half and the maze half of this file
LAUNCH_MAZE = False  # set to True when the 3rd puzzle is solved and the transition is done
BLACK_WIN = None  # the black full-screen window shown during the transition


"""
QMainWindow: Makes the window
QApplication: The whole thing
QTextEdit: Allows me to edit texts and titles and add text boxes and output boxes
QPushButton: Makes the push of Buttons do something
QWidget: Manages console features like tabs, boxes, and buttons.
QTabWidget: Manager for tabs
QGraphicsView: Puts all graphics created on the screen
QGraphicsScene: Creates all graphics
QGraphicsPixmapItem: Can take files and make graphics from them, like karel PNG.
QBrush: Colors graphics items
QPen: Paints lines on the scene with a selected color
Qcolor: picks a color for QBrush or QPen
QPixmap: take the files for QGraphicsPixmap item to turn into a graphics
QPainter / QRadialGradient: draw the "Orion Studios" power-on intro by hand
QElapsedTimer: keeps the intro animation timing accurate
"""


"""
This class is to handle other errors now forseen in Karel's World
"""


class KarelError(Exception):  # custom exception type for Karel mistakes (crashing, no ball, stop pressed)
    pass  # no extra behavior needed; it just needs to exist as its own error type


class CodeEdit(QTextEdit):  # a text editor that auto-indents like a code editor
    def keyPressEvent(self, event):  # Qt calls this every time a key is pressed in the editor
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):  # only do special handling for the Enter keys
            line = self.textCursor().block().text()  # get the full text of the line the cursor is on
            indent = line[:len(line) - len(line.lstrip(" "))]  # copy the leading spaces of that line
            if line.rstrip().endswith(":"):  # a line ending in ":" starts a new Python block
                indent += "    "  # so add 4 more spaces of indentation
            super().keyPressEvent(event)  # let the normal Enter key press happen (makes the new line)
            self.insertPlainText(indent)  # type the computed indentation onto the new line
        else:  # any other key
            super().keyPressEvent(event)  # behave normally


# -------------------- Orion Studios power-on intro --------------------
def make_power_on_sound(zap_time):  # builds the intro sound; zap_time is when the white flash happens
    """Synthesised power-up: a rising whine, a soft click, and a zap at the flash."""  # function docstring
    try:  # audio can fail on some machines, so guard everything
        if not pygame.mixer.get_init():  # if the sound system isn't started yet
            pygame.mixer.init(frequency=48000, size=-16, channels=2, buffer=1024)  # start it: 48kHz, 16-bit signed, stereo
        init = pygame.mixer.get_init()  # read back the actual settings (frequency, format, channels)
        if not init or init[1] != -16:  # bail out if audio failed or isn't 16-bit signed
            return None  # no sound will be played
        freq, _, channels = init  # unpack sample rate and channel count (format is ignored)
        n = int(freq * (zap_time + 1.0))  # total number of samples: zap time plus 1 second of tail
        buf = array.array("h")  # empty array of signed 16-bit integers to hold samples
        phase = 0.0  # current angle of the sine wave
        for i in range(n):  # generate one sample at a time
            t = i / freq  # time in seconds of this sample
            k = min(t / zap_time, 1.0)  # progress toward the zap, capped at 1
            f = 40 + 1400 * k ** 2  # frequency rises from 40 Hz upward (rising whine)
            phase += 2 * math.pi * f / freq  # advance the wave angle by this sample's step
            amp = 0.4 * k ** 1.5 if t < zap_time else 0.4 * math.exp(-(t - zap_time) * 4)  # volume swells before the zap, then decays
            v = amp * math.sin(phase) + 0.15 * amp * math.sin(phase * 2.01)  # main tone plus a quiet overtone
            if t < 0.05:  # click as the dot appears
                v += 0.5 * (1 - t / 0.05) * random.uniform(-1, 1)  # add a burst of fading noise
            if zap_time <= t < zap_time + 0.12:  # zap at the white flash
                v += 0.5 * (1 - (t - zap_time) / 0.12) * random.uniform(-1, 1)  # add another burst of fading noise
            sample = max(-32767, min(32767, int(v * 32767 * 0.8)))  # scale to 16-bit range and clamp to avoid overflow
            for _ in range(channels):  # write the same sample to every channel
                buf.append(sample)  # store the sample
        return pygame.mixer.Sound(buffer=buf.tobytes())  # turn the raw bytes into a playable Sound object
    except Exception as err:  # anything went wrong while building the sound
        print("Could not build power-on sound:", err)  # report it
        return None  # continue without sound


class PowerOnOverlay(QWidget):  # full-window widget that plays the "Orion Studios" intro
    """Black screen -> 'Orion Studios' -> old-TV power-on that reveals the window underneath."""  # class docstring
    BLACK_LEAD = 0.6  # black before the text appears
    FADE_IN = 1.0  # text fades in
    HOLD = 1.4  # text stays
    FADE_OUT = 0.8  # text fades out
    BLACK_GAP = 0.5  # black pause before power-on
    DOT = 0.6  # dot glows
    LINE = 0.35  # dot stretches into a line
    EXPAND = 0.45  # line opens up into the full screen
    FLASH = 0.8  # white flash fades away

    def __init__(self, parent, on_done):  # parent window, and a function to call when the intro ends
        super().__init__(parent)  # initialize the QWidget base class
        self.on_done = on_done  # remember the finish callback
        self.setFocusPolicy(Qt.StrongFocus)  # let this widget take keyboard focus

        self.t0 = self.BLACK_LEAD  # time when the title starts fading in
        self.t1 = self.t0 + self.FADE_IN  # time when the title is fully visible
        self.t2 = self.t1 + self.HOLD  # time when the title starts fading out
        self.t3 = self.t2 + self.FADE_OUT  # time when the title is gone
        self.t4 = self.t3 + self.BLACK_GAP  # power-on starts here
        self.t5 = self.t4 + self.DOT  # end of the glowing dot phase
        self.t6 = self.t5 + self.LINE  # end of the dot-to-line phase
        self.t7 = self.t6 + self.EXPAND  # end of the line-opens-up phase
        self.t8 = self.t7 + self.FLASH  # end of the white flash (intro is over)

        self.title_family = "Georgia"  # serif; falls back to any serif font if missing

        self.t = 0.0  # current time in seconds since the intro began
        self.sound = make_power_on_sound(self.t7 - self.t4)  # build the sound; zap lands when the screen opens
        self.sound_played = False  # tracks whether the sound has started yet

        self.clock = QElapsedTimer()  # precise stopwatch for animation timing
        self.timer = QTimer(self)  # repeating timer that drives each animation frame
        self.timer.setInterval(16)  # fire about every 16 ms (~60 frames per second)
        self.timer.timeout.connect(self.tick)  # call self.tick on every timer fire

    def start(self):  # begins the animation
        self.clock.start()  # start the stopwatch
        self.timer.start()  # start the frame timer
        self.setFocus()  # grab keyboard focus

    def tick(self):  # runs every frame
        self.t = self.clock.elapsed() / 1000.0  # convert elapsed milliseconds to seconds
        if self.t >= self.t4 and not self.sound_played:  # time for the power-on sound and it hasn't played yet
            self.sound_played = True  # mark it as played so it only plays once
            if self.sound:  # only if the sound was built successfully
                self.sound.play()  # play it
        if self.t >= self.t8:  # the whole intro has finished
            self.timer.stop()  # stop the frame timer
            self.hide()  # hide this overlay
            self.on_done()  # tell the main window the intro finished
            self.deleteLater()  # schedule this widget for deletion
            return  # skip the repaint below
        self.update()  # request a repaint (calls paintEvent)

    def paintEvent(self, event):  # Qt calls this to draw the widget
        p = QPainter(self)  # painter that draws onto this widget
        w, h = self.width(), self.height()  # widget size
        cx, cy = w // 2, h // 2  # center point
        t = self.t  # shorthand for the current time
        black = QColor(0, 0, 0)  # reusable black color

        if t < self.t4:  # phase 1: the title card
            # ---- Title card ----
            p.fillRect(0, 0, w, h, black)  # fill the whole widget with black
            if t < self.t0:  # still in the initial black pause
                a = 0.0  # fully transparent text
            elif t < self.t1:  # fading in
                a = (t - self.t0) / self.FADE_IN  # opacity rises from 0 to 1
            elif t < self.t2:  # holding
                a = 1.0  # fully visible
            else:  # fading out
                a = max(0.0, 1.0 - (t - self.t2) / self.FADE_OUT)  # opacity falls from 1 to 0
            if a > 0:  # only draw text if it's visible
                font = QFont(self.title_family, max(18, h // 14))  # font sized relative to window height (min 18)
                font.setStyleHint(QFont.Serif)  # prefer a serif font if Georgia is missing
                font.setLetterSpacing(QFont.AbsoluteSpacing, 6)  # add 6 pixels between letters
                p.setFont(font)  # use this font
                p.setPen(QColor(235, 235, 235, int(255 * a)))  # off-white text with the current opacity
                p.drawText(self.rect(), Qt.AlignCenter, "Orion Studios")  # draw the title centered

        elif t < self.t5:  # phase 2: a dot glows in the middle
            # ---- A dot glows in the middle ----
            k = (t - self.t4) / self.DOT  # progress through this phase, 0 to 1
            p.fillRect(0, 0, w, h, black)  # black background
            r = 46  # glow radius in pixels
            grad = QRadialGradient(cx, cy, r)  # circular gradient centered on the screen
            grad.setColorAt(0.0, QColor(255, 255, 255, int(200 * k)))  # bright white in the center, growing with k
            grad.setColorAt(1.0, QColor(255, 255, 255, 0))  # fully transparent at the edge
            p.setPen(Qt.NoPen)  # no outline
            p.setBrush(QBrush(grad))  # fill using the gradient
            p.drawEllipse(cx - r, cy - r, r * 2, r * 2)  # draw the soft glow
            dot = max(1, int(4 * k))  # dot radius grows up to 4 pixels
            p.setBrush(QColor(255, 255, 255))  # solid white fill
            p.drawEllipse(cx - dot, cy - dot, dot * 2, dot * 2)  # draw the bright dot

        elif t < self.t6:  # phase 3: the dot stretches into a line
            # ---- The dot stretches sideways into a line ----
            k = (t - self.t5) / self.LINE  # progress through this phase
            p.fillRect(0, 0, w, h, black)  # black background
            lw = max(6, int(w * k ** 2))  # line width grows quickly toward the full width
            p.setPen(Qt.NoPen)  # no outline
            p.setBrush(QColor(255, 255, 255, 70))  # faint translucent white for the glow
            p.drawRect(cx - lw // 2, cy - 5, lw, 10)  # soft glow rectangle
            p.setBrush(QColor(255, 255, 255))  # solid white
            p.drawRect(cx - lw // 2, cy - 1, lw, 3)  # bright core line

        elif t < self.t7:  # phase 4: the line opens to reveal the window
            # ---- The line opens up and reveals the window ----
            k = (t - self.t6) / self.EXPAND  # progress through this phase
            hh = max(3, int(h * k ** 3))  # height of the open band, growing faster over time
            top = cy - hh // 2  # top edge of the open band
            p.fillRect(0, 0, w, top, black)  # black cover above the band
            p.fillRect(0, top + hh, w, h - top - hh, black)  # black cover below the band
            p.fillRect(0, top, w, hh, QColor(255, 255, 255, int(60 + 190 * (1 - k))))  # white tint over the band that fades as it opens

        else:  # phase 5: the white flash
            # ---- White flash fades away ----
            f = t - self.t7  # time since the flash began
            a = 255 if f < 0.12 else int(255 * max(0.0, 1 - (f - 0.12) / (self.FLASH - 0.12)))  # solid white briefly, then fade out
            p.fillRect(0, 0, w, h, QColor(255, 255, 255, a))  # draw the white layer with that opacity

        p.end()  # finish painting


# -------------------- Final transition overlay: red/black glitching + binary --------------------
class GlitchOverlay(QWidget):  # full-screen glitch effect shown after the 3rd puzzle
    """Full-screen glitch: blood-red binary, red/black tiles, screen tears. Can then turn pure black."""  # class docstring
    TILE = 90  # size of the red/black glitch tiles (pixels)
    SOUL = "karel is coming for your soul"  # the message that gets shown in binary

    def __init__(self, duration):  # duration is the glitch length in milliseconds
        super().__init__()  # initialize the QWidget base class (no parent)
        self.duration = duration  # remember the duration
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)  # no title bar and always on top
        self.setCursor(Qt.BlankCursor)  # hide the mouse cursor

        screen = QApplication.primaryScreen()  # the main monitor
        size = screen.size()  # its size
        self.sw, self.sh = size.width(), size.height()  # store screen width and height

        # Freeze what is on screen right now so the glitches tear and eat *that* picture
        grab = screen.grabWindow(0)  # take a screenshot of the whole screen
        if grab.isNull():  # screenshot failed
            grab = QPixmap(self.sw, self.sh)  # make a blank image instead
            grab.fill(QColor(0, 0, 0))  # fill it with black
        self.snap = grab.scaled(self.sw, self.sh)  # scale the screenshot to exactly the screen size
        self.snap.setDevicePixelRatio(1.0)  # treat it as 1:1 pixels (avoids high-DPI scaling issues)

        self.black = False  # when True the overlay just paints solid black
        self.t = 0.0  # seconds since the glitch started
        self.dead = set()  # tiles that have gone black for good
        self.bursts = []  # random binary text bursts
        self.next_burst = 0.0  # time when the next burst set should be generated

        self.font = QFont("Consolas", 14, QFont.Bold)  # bold monospace font for the binary
        self.font.setStyleHint(QFont.Monospace)  # fall back to any monospace font
        metrics = QFontMetrics(self.font)  # tool for measuring text with that font
        self.line_h = metrics.height()  # height of one line of text

        # The scrolling "karel is coming for your soul" binary rows (same as in the maze)
        binary = " ".join(format(ord(ch), "08b") for ch in self.SOUL)  # convert each letter to 8-bit binary, separated by spaces
        self.unit = binary + "      "  # one repeating unit: the message plus a gap
        self.unit_w = max(1, metrics.horizontalAdvance(self.unit))  # pixel width of one unit (at least 1)
        self.rows = []  # list of scrolling rows
        y = 30  # y position of the first row
        while y < self.sh - 10:  # keep adding rows until the screen is full
            self.rows.append({"y": y, "dir": random.choice((-1, 1)), "speed": random.uniform(50, 230),
                              "seed": random.uniform(0, self.unit_w), "order": random.random()})  # each row gets a random direction, speed, start offset, and appearance order
            y += self.line_h  # move down one line

        self.clock = QElapsedTimer()  # stopwatch for timing
        self.timer = QTimer(self)  # frame timer
        self.timer.setInterval(16)  # about 60 frames per second
        self.timer.timeout.connect(self.tick)  # run tick on each timer fire

    def start(self):  # begins the glitch
        self.showFullScreen()  # display the overlay across the whole screen
        self.clock.start()  # start the stopwatch
        self.timer.start()  # start the frame timer

    def go_black(self):  # switch to the solid-black phase
        self.black = True  # paintEvent will now draw only black
        self.timer.stop()  # no more animation needed
        self.update()  # repaint once to show the black

    def tick(self):  # runs every frame during the glitch
        self.t = self.clock.elapsed() / 1000.0  # elapsed seconds
        k = min(1.0, self.t / (self.duration / 1000.0))  # progress through the glitch, 0 to 1
        cols = -(-self.sw // self.TILE)  # number of tile columns (ceiling division)
        rows_ = -(-self.sh // self.TILE)  # number of tile rows (ceiling division)
        target = int(cols * rows_ * 0.45 * k ** 1.2)  # how many tiles should be dead by now (up to 45%)
        while len(self.dead) < target:  # add dead tiles until we reach the target
            self.dead.add((random.randrange(cols), random.randrange(rows_)))  # kill a random tile
        self.update()  # repaint

    def paintEvent(self, event):  # draws the glitch each frame
        p = QPainter(self)  # painter for this widget
        w, h = self.sw, self.sh  # screen dimensions
        if self.black:  # black phase
            p.fillRect(0, 0, w, h, QColor(0, 0, 0))  # fill everything black
            p.end()  # finish painting
            return  # nothing else to draw

        t = self.t  # current time
        k = min(1.0, t / (self.duration / 1000.0))  # intensity from 0 to 1
        S = self.TILE  # tile size shorthand
        cols = -(-w // S)  # tile columns
        rows_ = -(-h // S)  # tile rows

        # The frozen screen, torn sideways in random strips (more tears as time goes on)
        p.drawPixmap(0, 0, self.snap)  # draw the screenshot as the base
        for _ in range(random.randint(1, 2 + int(6 * k))):  # more tears the further along we are
            sy = random.randint(0, h - 30)  # random strip top
            sh = random.randint(4, 24 + int(40 * k))  # random strip height (taller over time)
            offset = random.randint(-25, 25) * (1 + int(2 * k))  # random sideways shift (bigger over time)
            p.drawPixmap(offset, sy, self.snap, 0, sy, w, sh)  # redraw that strip of the screenshot shifted sideways

        # Red wash that gets stronger
        p.fillRect(0, 0, w, h, QColor(140, 0, 10, int(20 + 70 * k)))  # translucent red layer that gets stronger

        # Red/black tiles: some are dead (black), the rest flicker red/black every frame
        for (tx, ty) in self.dead:  # every permanently dead tile
            col = QColor(60, 0, 5) if random.random() < 0.03 else QColor(0, 0, 0)  # almost always black, rarely dark red
            p.fillRect(tx * S, ty * S, S, S, col)  # paint the tile
        palette = ((0, 0, 0), (0, 0, 0), (90, 0, 8), (170, 0, 15), (220, 20, 30))  # possible flicker colors (black twice for weighting)
        for _ in range(int(cols * rows_ * 0.35 * k ** 1.4)):  # number of flickering tiles grows over time
            x0 = random.randrange(cols) * S  # random tile x position
            y0 = random.randrange(rows_) * S  # random tile y position
            r, g, b = random.choice(palette)  # pick a color
            p.fillRect(x0, y0, S, S, QColor(r, g, b))  # fill the tile with it
            for _ in range(random.randint(1, 3)):  # add 1-3 horizontal stripes to the tile
                sy = y0 + random.randint(0, S - 8)  # stripe top inside the tile
                sh = min(random.randint(3, 16), y0 + S - sy)  # stripe height, kept inside the tile
                stripe = QColor(0, 0, 0) if random.random() < 0.5 else QColor(200, 0, 20)  # black or bright red
                p.fillRect(x0, sy, S, sh, stripe)  # draw the stripe

        p.setFont(self.font)  # use the monospace font for the text below

        # Scrolling "karel is coming for your soul" binary rows
        alpha = int(70 + 150 * k)  # text opacity grows over time
        for row in self.rows:  # each scrolling row
            if row["order"] > 0.15 + 0.7 * k:  # rows appear gradually based on their random order
                continue  # not yet visible
            if random.random() < 0.15:  # 15% chance per frame
                continue  # skip drawing for a flicker effect
            offset = (row["seed"] + t * row["speed"]) % self.unit_w  # scroll position, wrapping every unit width
            x = int(offset - self.unit_w if row["dir"] > 0 else -offset) + random.randint(-3, 3)  # start x depends on direction, plus small jitter
            while x < w:  # repeat the unit across the screen width
                p.setPen(QColor(90, 0, 8, alpha // 2))  # dark red, half-opacity for the ghost shadow
                p.drawText(x + random.choice((-3, 3)), row["y"] + 2, self.unit)  # draw the ghost slightly offset
                p.setPen(QColor(200, 0, 20, alpha))  # bright blood red for the main text
                p.drawText(x, row["y"], self.unit)  # draw the main text
                x += self.unit_w  # move right by one unit

        # Random bursts of binary that re-randomize every frame
        if t >= self.next_burst:  # time to make new bursts
            self.next_burst = t + random.uniform(0.08, 0.3)  # schedule the next one shortly
            self.bursts = [{"x": random.randint(0, max(1, w - 400)), "y": random.randint(40, h - 40),
                            "len": random.randint(8, 40)} for _ in range(random.randint(3, 6 + int(25 * k)))]  # create a random number of bursts, each with a random spot and length
        for item in self.bursts:  # draw each burst
            text = "".join(random.choice("01") for _ in range(item["len"]))  # fresh random string of 0s and 1s
            jx = item["x"] + random.randint(-6, 6)  # horizontal jitter
            jy = item["y"] + random.randint(-3, 3)  # vertical jitter
            p.setPen(QColor(90, 0, 8))  # dark red for the ghost
            p.drawText(jx + random.choice((-3, 3)), jy + 2, text)  # draw the ghost
            p.setPen(QColor(200, 0, 20))  # bright red for the main text
            p.drawText(jx, jy, text)  # draw the main text

        p.end()  # finish painting


# A bare-string block comment describing the TabbedConsole class (no runtime effect)
"""
Tabbed Console is everything that you see in the console except for Karel's 
output box, it is assigned the import that makes the window, so everything in 
this class will directly affect the window you see.
"""


class TabbedConsole(QMainWindow):  # the main window: password screen, then three puzzle tabs
    # initializes the program
    def __init__(self):  # constructor, runs when the window object is created
        super().__init__()  # initialize the QMainWindow base class

        # Assigns a varaible for the tabs manager
        self.tabs = QTabWidget()  # container that will hold the three puzzle tabs
        # self.count will keeptrack of the milestones the player has passed so the code can determine what happens next
        self.count = 0  # progress milestone counter (0 = password stage)
        self.tries = 0  # how many wrong password attempts so far
        self.voices = 0  # (unused) counter for voicelines
        self.put = False  # True once the put_ball puzzle is solved
        self.take = False  # True once the take_ball puzzle is solved
        self.right = False  # True once the turn_right puzzle is solved
        # Call the function that makes the window
        self.intro = PowerOnOverlay(self, self.introFinished)  # create the intro overlay, calling introFinished when done
        self.makeWindow()  # build the password screen widgets

        # Power-on intro that covers the window until it "boots"

    # starts the "Orion Studios" intro (called after the window is shown)
    def startIntro(self):  # begins showing the intro
        self.intro.setGeometry(self.rect())  # make the overlay cover the whole window
        self.intro.raise_()  # bring it in front of everything
        self.intro.show()  # make it visible
        self.intro.start()  # start its animation

    # runs when the intro is done and the window is fully revealed
    def introFinished(self):  # callback from the overlay
        self.intro = None  # drop the reference since the overlay deletes itself
        self.textBox.setFocus()  # put the typing cursor in the code box
        if self.count == 0:  # still on the password screen
            QTimer.singleShot(1000, lambda: self.playVoiceline(r'VA Files\uh huh.wav'))  # after 1s, play the first voiceline
        if self.count == 0:  # (same check again)
            QTimer.singleShot(2000, lambda: self.playVoiceline(r'VA Files\hey what are u doing here.wav'))  # after 2s, play the second voiceline
        if self.count == 0:  # (same check again)
            QTimer.singleShot(5000, lambda: self.playVoiceline(r'VA Files\no matter.wav'))  # after 5s, play the third voiceline

    # keeps the intro covering the whole window if it is resized
    def resizeEvent(self, event):  # Qt calls this whenever the window size changes
        super().resizeEvent(event)  # run the normal resize handling
        if getattr(self, "intro", None) is not None:  # only if the intro still exists
            self.intro.setGeometry(self.rect())  # resize the overlay to match

    # This function makes the window
    def makeWindow(self):  # builds the password-screen layout
        # Takes the user's screen's width and height
        screen = QApplication.primaryScreen()  # the main monitor
        self.width = screen.size().width()  # store its width (this shadows QWidget.width, but works here)
        self.height = screen.size().height()  # store its height

        # Set the size of the screen. It should be adaptable to all screen sizes
        self.setGeometry(int(self.width / -500), 0, self.width, self.height)  # position/size the window to fill the screen (tiny negative x offset)
        # Names the window
        self.setWindowTitle("Kind-hearted Assistant of Resources and Environmental Life-style")  # title bar text (spells KARREL-ish acronym)

        # Makes the text box the user types in on the password screen.
        self.textBox = CodeEdit(self)  # code editor where the player types Python
        # sets the size and location of the text box. Should be adaptable to all screen sizes
        self.textBox.setGeometry(int(self.width / 20), int(self.height / 20), int((self.width * 9) / 20),
                                 int((self.height * 18) / 20))  # left half of the screen, with margins
        self.textBox.setFont(QFont("Consolas", 12))  # monospace font, size 12
        # sets the original visible text the player can see in the text box, I left a commented hint there.
        self.textBox.setPlainText('""" \nThe password is a four digit number code! \nREMEMBER: This is a Python only program\n""" \n')  # starting hint text shown to the player
        self.textBox.setTabStopDistance(self.textBox.fontMetrics().horizontalAdvance(" ") * 4)  # make a Tab character 4 spaces wide
        # Makes the output box the in the first window in which the user has to type the password to gain access
        self.outputBox = QTextEdit(self)  # box that shows the program output
        # sets the size adn location of the output box. Should be adaptable to all screen sizes
        self.outputBox.setGeometry(int((self.width * 11) / 20), int(self.height / 20), int((self.width * 9) / 20),
                                   int((self.height * 18) / 20))  # right half of the screen
        # makes a button with the word "Run" in it
        self.runButton = QPushButton("Run", self)  # the Run button
        # sets the size and location of the Run button. Should be adaptable to all screen sizes
        self.runButton.setGeometry(int((self.width * 11) / 20), int(self.height / 40), int(self.width / 20),
                                   int(self.height / 50))  # small button above the output box
        # Makes that the "Run" button run the run_code function whenever it is pressed.
        self.runButton.clicked.connect(self.run_code)  # clicking calls run_code

    # Makes 3 well-defined tabs when the player correctly guesses teh password
    def makeTabs(self):  # builds the three puzzle tabs
        # Initializes each of the tabs
        self.put_ball = QWidget()  # blank page for tab 1
        self.take_ball = QWidget()  # blank page for tab 2
        self.turn_right = QWidget()  # blank page for tab 3

        # Add each of the tabs to widget manager
        self.tabs.addTab(self.put_ball, "put_ball()")  # add tab 1 with its label
        self.tabs.addTab(self.take_ball, "take_ball()")  # add tab 2 with its label
        self.tabs.addTab(self.turn_right, "turn_right()")  # add tab 3 with its label

        # Section label for tab 1 (bare string, no runtime effect)
        """ TAB 1: """
        # Creates the widgets for the first tab
        # makes the text box
        self.put_ball.textBox = CodeEdit(self.put_ball)  # code editor for tab 1
        # sets its size and position
        self.put_ball.textBox.setGeometry(int(self.width / 20), int(self.height / 20), int((self.width * 9) / 20),
                                          int((self.height * 18) / 20))  # same left-half layout as the password screen
        self.put_ball.textBox.setFont(QFont("Consolas", 12))  # monospace font
        # sets initial text in it.
        self.put_ball.textBox.setPlainText(
            '"""\nBuild 3 towers using put_ball() commands\nEach tower should be 3 balls tall\n"""\n')  # instructions for puzzle 1
        self.put_ball.textBox.setTabStopDistance(self.textBox.fontMetrics().horizontalAdvance(" ") * 4)  # Tab = 4 spaces
        # makes the "output box" based on Karel's world using KarelWorld class
        self.put_ball.worldView = KarelWorld(self.put_ball)  # create the grid world for tab 1
        self.put_ball.worldView.drawWorld(0, 720)  # draw the grid with Karel at the bottom-left
        # Sets the output box position
        self.put_ball.worldView.move(int((self.width * 11) / 20), int(self.height / 20))  # place it on the right half
        # sets the output box size
        self.put_ball.worldView.resize(800, 800)  # 800x800 pixels

        # creates the balls that cannot be erased by resetWorld
        self.put_ball.worldView.addMandatoryBall(160, 720)  # ball at the base of tower 1
        self.put_ball.worldView.addMandatoryBall(400, 720)  # ball at the base of tower 2
        self.put_ball.worldView.addMandatoryBall(640, 720)  # ball at the base of tower 3

        # Makes the run button
        self.put_ball.runButton = QPushButton("Run", self.put_ball)  # Run button for tab 1
        # sets the run button's size and positon
        self.put_ball.runButton.setGeometry(int((self.width * 11) / 20), int(self.height / 40), int(self.width / 20),
                                            int(self.height / 50))  # position above the world view
        # run run_code once the button is pressed
        self.put_ball.runButton.clicked.connect(self.run_karelWorld)  # clicking runs the player's Karel code
        self.put_ball.stopButton = QPushButton("Stop", self.put_ball)  # Stop button for tab 1
        self.put_ball.stopButton.setGeometry(int((self.width * 12) / 20), int(self.height / 40), int(self.width / 20),
                                             int(self.height / 50))  # placed to the right of Run
        self.put_ball.stopButton.clicked.connect(self.put_ball.worldView.stop)  # clicking requests the program to stop

        # Section label for tab 2
        """ TAB 2: """
        # Creates the widgets for the second tab
        # makes the text box
        self.take_ball.textBox = CodeEdit(self.take_ball)  # code editor for tab 2
        # sets its size and position
        self.take_ball.textBox.setGeometry(int(self.width / 20), int(self.height / 20), int((self.width * 9) / 20),
                                           int((self.height * 18) / 20))  # left-half layout
        self.take_ball.textBox.setFont(QFont("Consolas", 12))  # monospace font
        # sets initial text on the text box
        self.take_ball.textBox.setPlainText(
            '"""\nToo many balls are around here,\nClean up this field using take_ball()\n"""\n')  # instructions for puzzle 2
        self.take_ball.textBox.setTabStopDistance(self.textBox.fontMetrics().horizontalAdvance(" ") * 4)  # Tab = 4 spaces
        # makes the "output box" for Karel's World based on the KarelWorld class
        self.take_ball.worldView = KarelWorld(self.take_ball)  # create the grid world for tab 2
        # tells the class to make the map and gives Karel's initial position
        self.take_ball.worldView.drawWorld(0, 720)  # draw the grid with Karel at the bottom-left
        # sets the output box position
        self.take_ball.worldView.move(int((self.width * 11) / 20), int(self.height / 20))  # right half
        # sets the output box size
        self.take_ball.worldView.resize(800, 800)  # 800x800 pixels

        # Creates the balls that cannot be erased from the world
        for c, r in random.sample([(c, r) for c in range(1, 10) for r in range(1, 10)], 15):  # pick 15 unique random grid squares
            self.take_ball.worldView.addMandatoryBall(c * 80, r * 80)  # place a ball there (each square is 80 px)

        # makes the run button
        self.take_ball.runButton = QPushButton("Run", self.take_ball)  # Run button for tab 2
        # sets the size and position of the run button
        self.take_ball.runButton.setGeometry(int((self.width * 11) / 20), int(self.height / 40), int(self.width / 20),
                                             int(self.height / 50))  # position above the world view
        # run run_code when the button is pressed
        self.take_ball.runButton.clicked.connect(self.run_karelWorld)  # clicking runs the player's Karel code
        self.take_ball.stopButton = QPushButton("Stop", self.take_ball)  # Stop button for tab 2
        self.take_ball.stopButton.setGeometry(int((self.width * 12) / 20), int(self.height / 40), int(self.width / 20),
                                              int(self.height / 50))  # placed to the right of Run
        self.take_ball.stopButton.clicked.connect(self.take_ball.worldView.stop)  # clicking requests the program to stop

        # Section label for tab 3
        """ TAB 3: """
        # Creates the widgets for the third tab
        # makes the text box
        self.turn_right.textBox = CodeEdit(self.turn_right)  # code editor for tab 3
        # sets the size and position of the text box
        self.turn_right.textBox.setGeometry(int(self.width / 20), int(self.height / 20), int((self.width * 9) / 20),
                                            int((self.height * 18) / 20))  # left-half layout
        self.turn_right.textBox.setFont(QFont("Consolas", 12))  # monospace font
        # sets the initial text for the text box
        self.turn_right.textBox.setPlainText(
            '"""\nKarel help karel get the ball\nAvoid the hurdles using turn_right()\n"""\n')  # instructions for puzzle 3
        self.turn_right.textBox.setTabStopDistance(self.textBox.fontMetrics().horizontalAdvance(" ") * 4)  # Tab = 4 spaces
        # makes the output box for Karel's world using the KarelWorld class
        self.turn_right.worldView = KarelWorld(self.turn_right)  # create the grid world for tab 3
        self.turn_right.worldView.drawWorld(0, 720)  # draw the grid with Karel at the bottom-left
        # sets the position of the output box
        self.turn_right.worldView.move(int((self.width * 11) / 20), int(self.height / 20))  # right half
        # sets the size of the output box
        self.turn_right.worldView.resize(800, 800)  # 800x800 pixels

        # Creates teh balls that cannot be erased from the world
        self.turn_right.worldView.addMandatoryBall(720, 720)  # the ball Karel must fetch (bottom-right corner)

        self.turn_right.worldView.addWall(4, 11, "up")  # red wall segment (hurdle) 1
        self.turn_right.worldView.addWall(6, 11, "up")  # red wall segment (hurdle) 2
        self.turn_right.worldView.addWall(8, 11, "up")  # red wall segment (hurdle) 3

        # makes the run button
        self.turn_right.runButton = QPushButton("Run", self.turn_right)  # Run button for tab 3
        # sets the size and position of the button
        self.turn_right.runButton.setGeometry(int((self.width * 11) / 20), int(self.height / 40), int(self.width / 20),
                                              int(self.height / 50))  # position above the world view
        # runs run_code once the button is pressed
        self.turn_right.runButton.clicked.connect(self.run_karelWorld)  # clicking runs the player's Karel code
        self.turn_right.stopButton = QPushButton("Stop", self.turn_right)  # Stop button for tab 3
        self.turn_right.stopButton.setGeometry(int((self.width * 12) / 20), int(self.height / 40), int(self.width / 20),
                                               int(self.height / 50))  # placed to the right of Run
        self.turn_right.stopButton.clicked.connect(self.turn_right.worldView.stop)  # clicking requests the program to stop

        # makes the tabs the main window from now on.
        self.put_ball.worldView.resetWorld()  # place the mandatory balls in world 1
        self.take_ball.worldView.resetWorld()  # place the mandatory balls in world 2
        self.turn_right.worldView.resetWorld()  # place the mandatory ball in world 3
        self.setCentralWidget(self.tabs)  # replace the password screen with the tab widget

    # plays the music and audio files, the music shifts depending on the milestone (self.count) and the Audio is scripted
    def playMusic(self):  # starts/changes/stops background music based on progress
        try:  # audio errors are caught at the bottom
            # Initialize the sound device explicitly before loading the soundtrack.
            if not pygame.mixer.get_init():  # if audio isn't started
                pygame.mixer.init(frequency=48000, size=-16, channels=2, buffer=1024)  # start it with these settings
            pygame.mixer.set_num_channels(8)  # allow 8 sounds to play at once

            # finds the current directory that the player is playing from
            path = os.getcwd()  # current working directory
            # Load and play the background music natively using Pygame (loops indefinitely)
            # Plays the music for the first milestone (after the player correctly guesses the password
            if self.count == 1:  # password solved
                # names the music that it is supposed to play at the moment
                music = r'\kurosity killed the dog.wav'  # filename (Windows-style path separator)
                if os.path.exists(path + music):  # only if the file exists
                    # combines the name of the path and the name of the music and finds the file
                    pygame.mixer.music.load(path + music)  # plays the music
                    pygame.mixer.music.play(-1)  # -1 means loop forever

            # Plays the music for the second milestone (after two puzzles are solved)
            elif self.count == 3:  # two puzzles solved
                # names the music that it is supposed to play at the moment
                music = r'\everythings fine.wav'  # filename for this stage
                if os.path.exists(path + music):  # only if the file exists
                    # combines the name of the path and the name of the music and finds the file
                    pygame.mixer.music.load(path + music)  # plays the music
                    pygame.mixer.music.play(-1)  # loops forever
                # raises an error message
                else:  # file wasn't found
                    print(path + music)  # print the missing path to help debugging

            elif self.count > 3:  # all puzzles solved
                pygame.mixer.music.stop()  # stop the music

        except pygame.error as exc:  # audio problem
            AUDIO_ERROR = str(exc)  # convert the error to text
            print("AUDIO ERROR: Pygame could not initialize audio:", AUDIO_ERROR)  # report it
            print("Check your computer's output device/volume and restart the game.")  # give the player advice

    def playVoiceline(self, name):  # plays a voice audio file located next to this script
        try:  # catch audio errors
            if not pygame.mixer.get_init():  # if audio isn't started
                pygame.mixer.init(frequency=48000, size=-16, channels=2, buffer=1024)  # start it
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)  # full path to the file next to this script
            if os.path.exists(path):  # only if the file exists
                if getattr(self, "voice", None) is not None:  # if a previous voiceline exists
                    self.voice.stop()  # stop it so voicelines don't overlap

                self.voice = pygame.mixer.Sound(path)  # load the new voiceline
                self.voice.play()  # play it

            else:  # file wasn't found
                print("Voiceline not found:", path)  # tell the developer which one is missing
        except pygame.error as exc:  # audio problem
            print("VOICELINE ERROR:". exc)  # NOTE: typo in the original: "." should be "," (this line would itself raise an error if reached)

    # run when the run buttons are clicked and print the resulting output in the output box (first window only)
    def run_code(self):  # runs the password-screen code
        # checks to see if the first milestone has not been passed yet
        if self.count == 0:  # still on the password stage
            # takes the code from the window's text box and puts it in a variable
            code = self.textBox.toPlainText()  # the player's typed code as a string

            # Creates an in-memory system for the output instead of a disk file
            output_stream = StringIO()  # in-memory text buffer

            # directs output to memory
            with contextlib.redirect_stdout(output_stream):  # while inside, print() writes into the buffer
                # Attempts to run the code and catch errors if possible
                try:  # guard against errors in the player's code
                    exec(code)  # run the player's code

                except Exception as e:  # the player's code crashed
                    print(e)  # show the error message in the output instead

            # takes the output from the memory created
            output = output_stream.getvalue()  # everything that was printed

            # Assigns and displays the text in the output box.
            self.outputBox.setPlainText(output)  # show it to the player

            # A bare-string block comment (no runtime effect)
            """
            SPOILER ALERT:
                Before you just look at the answer in this code, 
                try to solve the first puzzle by yourself for a better
                experience. 
            """
            # Checks to see if in the displayed code the correct password was in it
            if "7245" in self.outputBox.toPlainText() and self.count == 0:  # correct password was printed
                # calls the function that makes the tabs and substitutes the current window
                self.makeTabs()  # build the puzzle tabs
                # increases self.count by 1 to symbolize the first milestone has been passed.
                self.count += 1  # progress to milestone 1
                # calls teh play music function to play the audio.
                self.playMusic()  # start milestone 1 music
                QTimer.singleShot(10, lambda: self.playVoiceline(r'VA Files\welcome.wav'))  # play the welcome line almost immediately
                QTimer.singleShot(19000, lambda: self.playVoiceline(r'VA Files\Your new.wav'))  # play another line 19 seconds later

            elif self.tries == 0:  # first wrong attempt
                QTimer.singleShot(10, lambda: self.playVoiceline(r'VA Files\i knew it.wav'))  # taunting voiceline
                self.tries += 1  # count the attempt

            elif self.tries == 3:  # fourth wrong attempt
                QTimer.singleShot(10, lambda: self.playVoiceline(r'VA Files\you didnt.wav'))  # another taunt
                self.tries += 1  # count the attempt

            else:  # any other wrong attempt
                self.tries += 1  # just count it

    def run_karelWorld(self):  # runs the player's Karel code in the current puzzle tab
        # takes the current tab in which the user is in
        currentTab = self.tabs.currentWidget()  # whichever tab is showing
        currentTab.runButton.setEnabled(False)  # disable Run so it can't be clicked twice
        # hides the error boxes from previous runs
        currentTab.errorBox.hide()  # hide any old message
        # resets the world from previous runs.
        currentTab.worldView.resetWorld()  # put Karel and the balls back to the start
        currentTab.worldView.stopRequested = False  # clear any previous stop request
        # takes the code/text in the text box.
        code = currentTab.textBox.toPlainText()  # the player's code

        # makes an in-memory system for the output
        outputStream = StringIO()  # in-memory text buffer

        # directs output to memory
        with contextlib.redirect_stdout(outputStream):  # capture anything printed
            try:  # guard against errors in the player's code
                # makes a list of commands that the player can use in the code.
                commands = {
                    "move": self.slow(currentTab.worldView.moveKarel, currentTab),  # move() steps forward (slowed so you can watch)
                    "turn_right": self.slow(currentTab.worldView.turnRight, currentTab),  # turn_right() turns clockwise
                    "turn_left": self.slow(currentTab.worldView.turnLeft, currentTab),  # turn_left() turns counter-clockwise
                    "put_ball": self.slow(currentTab.worldView.putBall, currentTab),  # put_ball() drops a ball
                    "take_ball": self.slow(currentTab.worldView.takeBall, currentTab),  # take_ball() picks a ball up
                    "front_is_clear": currentTab.worldView.isBlocked,  # front_is_clear() checks for walls ahead (instant)
                    "balls_present": currentTab.worldView.ballsPresent  # balls_present() checks for a ball here (instant)
                }  # end of the allowed commands dictionary
                exec(code, commands)  # run the player's code using only these commands as its globals

            # prints the error
            except KarelError:  # a Karel-specific error (message already shown)
                pass  # nothing more to do
            except Exception as e:  # any other error in the player's code
                currentTab.worldView.showError(str(e), "red")  # show it in a red box

            else:  # the code finished with no errors
                self.solved()  # check whether the puzzles are solved

            finally:  # always runs
                currentTab.runButton.setEnabled(True)  # re-enable the Run button

        if self.put:  # puzzle 1 is solved
            self.put_ball.worldView.showError("Congratulations! \nBug Fixed!", "green")  # show a green success box

        if self.take:  # puzzle 2 is solved
            self.take_ball.worldView.showError("Congratulations! \nBug Fixed!", "green")  # show a green success box

        if self.right:  # puzzle 3 is solved
            self.turn_right.worldView.showError("Congratulations! \nBug Fixed!", "green")  # show a green success box

    def solved(self):  # checks each puzzle's goal and advances the story

        cells = {(b.x(), b.y()) for b in self.put_ball.worldView.balls}  # set of all ball positions in world 1
        self.put = all((x, y) in cells for x in (160, 400, 640) for y in (720, 640, 560))  # true if all 3 towers have balls at 3 heights

        self.take = len(self.take_ball.worldView.balls) == 0  # true if every ball in world 2 was removed

        self.right = len(self.turn_right.worldView.balls) == 0  # true if the ball in world 3 was picked up

        if self.put and self.take and self.right:  # all three puzzles solved
            if self.count != 4:  # only trigger this once
                self.count = 4  # final milestone
                QTimer.singleShot(100, lambda: self.playVoiceline(r'VA Files\excellent.wav'))  # play the "excellent" line
                self.playMusic()  # stops the music (count > 3)
                QTimer.singleShot(8000, lambda: self.glitchTransition())  # after 8 seconds, start the glitch transition
        elif (self.put and self.take) or (self.put and self.right) or (self.take and self.right):  # exactly two solved
            if self.count != 3:  # only trigger once
                self.count = 3  # milestone 3
                self.playMusic()  # switch to the milestone-3 music
                QTimer.singleShot(100, lambda: self.playVoiceline(r'VA Files\excellent job.wav'))  # praise voiceline
                QTimer.singleShot(20000, lambda: self.playVoiceline(r'VA Files\seems the code.wav'))  # follow-up voiceline 20 seconds later

        elif self.put or self.take or self.right:  # exactly one solved
            self.count = 2  # milestone 2
            QTimer.singleShot(100, lambda: self.playVoiceline(r'VA Files\great.wav'))  # encouragement voiceline


    def slow(self, fn, tab=None, delay=300):  # wraps a Karel command so it pauses afterward and can be stopped
        def wrapper(*args, **kwargs):  # the replacement function the player's code will actually call
            result = fn(*args, **kwargs)  # run the real command
            QTest.qWait(delay)  # wait 300 ms (keeps the window responsive) so the animation is visible
            if tab is not None and tab.worldView.stopRequested:  # the player pressed Stop
                raise KarelError()  # abort the player's program
            return result  # pass the command's return value back
        return wrapper  # hand back the wrapped function

    # ------------------------------------------------------------------
    # Final transition (after the 3rd puzzle):  red/black glitching + binary -> black -> maze
    # ------------------------------------------------------------------
    GLITCH_TIME = 3500  # ms of glitching (it gets more and more intense)
    BLACK_TIME = 1500  # ms the screen stays pure black before the maze appears

    def glitchTransition(self):  # starts the final glitch effect
        global BLACK_WIN  # we need to assign the module-level variable
        # one full-screen overlay does the glitching AND becomes the black screen afterwards
        self.playVoiceline(r'VA Files\Real bad.wav')  # play the ominous voiceline
        BLACK_WIN = GlitchOverlay(self.GLITCH_TIME)  # create the glitch overlay
        BLACK_WIN.start()  # show it and start animating
        QTimer.singleShot(self.GLITCH_TIME, self.showBlackScreen)  # after the glitch time, switch to black
        QTimer.singleShot(self.GLITCH_TIME + self.BLACK_TIME, self.finishTransition)  # after the black time, finish

    def showBlackScreen(self):  # turns the overlay solid black
        BLACK_WIN.go_black()  # tell the overlay to go black
        # the puzzle music cuts out as the screen goes black
        try:  # music might not be playing
            pygame.mixer.music.stop()  # stop it
        except pygame.error:  # audio not initialized
            pass  # ignore

    def finishTransition(self):  # ends the puzzle part and hands off to the maze
        global LAUNCH_MAZE  # we need to assign the module-level flag
        LAUNCH_MAZE = True  # tells the bottom of this file to start the maze
        self.close()  # close the puzzle window
        # ends app.exec() below; the black screen stays up until the maze window is ready
        QApplication.instance().quit()  # stop the Qt event loop


class KarelWorld(QGraphicsView):  # the 10x10 grid where Karel moves, drawn as a Qt graphics view
    def __init__(self, parent=None):  # parent is the tab page it lives on
        super().__init__(parent)  # initialize the QGraphicsView base class

        screen = QApplication.primaryScreen()  # the main monitor
        self.width = screen.size().width()  # store screen width
        self.height = screen.size().height()  # store screen height

        self.tab = parent  # remember which tab this world belongs to
        self.tab.errorBox = QTextEdit(self.tab)  # create the message box for this tab
        self.tab.errorBox.hide()  # start hidden

        self.balls = []  # ball graphics currently in the world
        self.walls = []  # wall graphics
        self.orien = []  # orientation ("up"/"right") of each wall, in the same order
        self.mandatory = []  # positions of balls that always return on reset

        self.karel = QPixmap(os.path.join(os.path.dirname(__file__), "karel.png"))  # load karel.png from beside this script
        self.karelSprite = QGraphicsPixmapItem(self.karel)  # graphics item that displays Karel
        self.facing = "right"  # Karel starts facing right

        self.stopRequested = False  # becomes True when Stop is pressed

        self.scene = QGraphicsScene(self)  # the canvas that holds all graphics items
        self.setScene(self.scene)  # attach the canvas to this view

    def drawWorld(self, x=0, y=0):  # draws the grid and places Karel at pixel (x, y)
        cols = 10  # number of grid columns
        rows = 10  # number of grid rows
        self.karelx = x  # Karel's current x pixel position
        self.karely = y  # Karel's current y pixel position

        for x in range(cols):  # for each column
            for y in range(rows):  # for each row
                self.scene.addRect(80 * x, 80 * y, 80, 80)  # draw an 80x80 square

        self.karelSprite.setPixmap(self.karel.scaled(80, 80))  # shrink Karel's image to one square
        self.karelSprite.setPos(self.karelx, self.karely)  # put him at the starting position
        self.karelSprite.setZValue(2)  # draw above balls and the grid
        self.scene.addItem(self.karelSprite)  # add him to the canvas

    def putBall(self):  # drops a ball on Karel's square
        tempFace = self.facing  # remember the current direction
        while self.facing != "right":  # rotate until facing right (resets the rotation offset)
            self.turnLeft()  # turn left once
        ball = self.scene.addEllipse(0, 0, 80, 80)  # create an 80x80 circle
        ball.setPos(self.karelx, self.karely)  # put it where Karel is
        ball.setBrush(QBrush(QColor("yellow")))  # fill it yellow
        ball.setZValue(1)  # draw above the grid but below Karel
        self.balls.append(ball)  # record it

        while self.facing != tempFace:  # rotate back to the original direction
            self.turnLeft()  # turn left once

    def takeBall(self):  # picks up a ball on Karel's square
        try:  # any failure is reported to the player
            found = False  # whether a ball was found
            tempFace = self.facing  # remember the current direction
            while self.facing != "right":  # rotate until facing right
                self.turnLeft()  # turn left once
            for ball in self.balls:  # check each ball
                if self.karelSprite.x() == ball.x() and self.karelSprite.y() == ball.y():  # ball is on Karel's square
                    self.scene.removeItem(ball)  # remove it from the canvas
                    self.balls.remove(ball)  # remove it from the list
                    found = True  # note that we found one
                    break  # only pick up one

            while self.facing != tempFace:  # rotate back to the original direction
                self.turnLeft()  # turn left once
            if not found:  # nothing was on this square
                raise KarelError("No balls present in your current position")  # trigger the error handling below

        except:  # catches the KarelError above (and anything else)
            self.showError("No balls present in your current position", "red")  # show a red error box
            raise KarelError()  # stop the player's program

    def turnRight(self):  # rotates Karel 90 degrees clockwise
        if self.facing == "right":  # facing right
            self.facing = "down"  # now facing down
            self.karelx += 80  # shift position to compensate for the rotation pivot
            self.karelSprite.setRotation(90)  # rotate the sprite 90 degrees

        elif self.facing == "up":  # facing up
            self.facing = "right"  # now facing right
            self.karely -= 80  # compensate for the rotation pivot
            self.karelSprite.setRotation(0)  # no rotation

        elif self.facing == "left":  # facing left
            self.facing = "up"  # now facing up
            self.karelx -= 80  # compensate for the rotation pivot
            self.karelSprite.setRotation(270)  # rotate 270 degrees

        else:  # facing down
            self.facing = "left"  # now facing left
            self.karely += 80  # compensate for the rotation pivot
            self.karelSprite.setRotation(180)  # rotate 180 degrees

        self.karelSprite.setPos(self.karelx, self.karely)  # apply the new position

    def turnLeft(self):  # rotates Karel 90 degrees counter-clockwise
        if self.facing == "right":  # facing right
            self.facing = "up"  # now facing up
            self.karely += 80  # compensate for the rotation pivot
            self.karelSprite.setRotation(270)  # rotate 270 degrees

        elif self.facing == "up":  # facing up
            self.facing = "left"  # now facing left
            self.karelx += 80  # compensate for the rotation pivot
            self.karelSprite.setRotation(180)  # rotate 180 degrees

        elif self.facing == "left":  # facing left
            self.facing = "down"  # now facing down
            self.karely -= 80  # compensate for the rotation pivot
            self.karelSprite.setRotation(90)  # rotate 90 degrees

        else:  # facing down
            self.facing = "right"  # now facing right
            self.karelx -= 80  # compensate for the rotation pivot
            self.karelSprite.setRotation(0)  # no rotation

        self.karelSprite.setPos(self.karelx, self.karely)  # apply the new position

    def moveKarel(self):  # moves Karel one square forward
        try:  # any failure is reported
            if not self.isBlocked():  # isBlocked actually returns "front is clear", so this means a wall is ahead
                raise KarelError("Oops! Karel crashed into a wall!")  # crash

            elif self.facing == "right":  # facing right
                self.karelx += 80  # move one square right

            elif self.facing == "up":  # facing up
                self.karely -= 80  # move one square up

            elif self.facing == "left":  # facing left
                self.karelx -= 80  # move one square left

            else:  # facing down
                self.karely += 80  # move one square down

            self.karelSprite.setPos(self.karelx, self.karely)  # apply the new position

        except:  # catches the crash error
            self.showError("Oops! Karel crashed into a wall!", "red")  # show a red error box
            raise KarelError()  # stop the player's program

    def addWall(self, col, row, side):  # adds a red wall segment at a grid position
        pen = QPen(QColor("red"), 4)  # red line, 4 pixels thick
        keepGoing = True  # becomes False if the orientation is invalid
        if side == "right":  # horizontal wall
            wall = self.scene.addLine(0, 0, 80, 0, pen)  # line 80 px wide
            wall.setPos((col * 80) - 80, (row * 80) - 80)  # position by 1-based column/row

        elif side == "up":  # vertical wall
            wall = self.scene.addLine(0, 0, 0, -80, pen)  # line 80 px tall going upward
            wall.setPos((col * 80) - 80, (row * 80) - 80)  # position by 1-based column/row

        else:  # unknown orientation
            self.showError("Give a valid wall orientation", "red")  # tell the developer
            keepGoing = False  # don't register the wall

        if keepGoing:  # a wall was created
            wall.setZValue(3)  # draw above everything else
            self.walls.append(wall)  # record the wall
            self.orien.append(side)  # record its orientation

    def isBlocked(self):  # returns True if the square in front of Karel is clear (name is inverted)
        tempFace = self.facing  # remember the current direction
        while self.facing != "right":  # rotate to the standard orientation
            self.turnLeft()  # turn left once

        frontIsClear = True  # assume it's clear until a wall is found
        for wall in self.walls:  # check every wall
            if tempFace == "right":  # facing right
                if self.karelx + 80 == wall.x() and self.karely + 80 == wall.y() and self.orien[
                    self.walls.index(wall)] == "up":  # a vertical wall sits on the right edge of Karel's square
                    frontIsClear = False  # blocked

            elif tempFace == "up":  # facing up
                if self.karelx == wall.x() and self.karely == wall.y() and self.orien[
                    self.walls.index(wall)] == "right":  # a horizontal wall sits on the top edge
                    frontIsClear = False  # blocked

            elif tempFace == "left":  # facing left
                if self.karelx == wall.x() and self.karely + 80 == wall.y() and self.orien[
                    self.walls.index(wall)] == "up":  # a vertical wall sits on the left edge
                    frontIsClear = False  # blocked

            else:  # facing down
                if self.karelx == wall.x() and self.karely + 80 == wall.y() and self.orien[
                    self.walls.index(wall)] == "right":  # a horizontal wall sits on the bottom edge
                    frontIsClear = False  # blocked

        if self.karelx + 80 > 799 and tempFace == "right":  # at the right edge of the world
            frontIsClear = False  # blocked by the border

        elif self.karely - 80 < 0 and tempFace == "up":  # at the top edge
            frontIsClear = False  # blocked by the border

        elif self.karelx - 80 < 0 and tempFace == "left":  # at the left edge
            frontIsClear = False  # blocked by the border

        elif self.karely + 80 > 799 and tempFace == "down":  # at the bottom edge
            frontIsClear = False  # blocked by the border

        while self.facing != tempFace:  # rotate back to the original direction
            self.turnLeft()  # turn left once

        return frontIsClear  # True if nothing is in the way

    def ballsPresent(self):  # returns True if there is a ball on Karel's square
        found = False  # assume none
        tempFace = self.facing  # remember the current direction
        while self.facing != "right":  # rotate to the standard orientation
            self.turnLeft()  # turn left once
        for ball in self.balls:  # check each ball
            if self.karelSprite.x() == ball.x() and self.karelSprite.y() == ball.y():  # ball is on Karel's square
                found = True  # found one
                break  # no need to keep looking

        while self.facing != tempFace:  # rotate back to the original direction
            self.turnLeft()  # turn left once

        return found  # True or False

    def showError(self, message, color):  # shows a colored message box over the world
        self.tab.errorBox.setPlainText(("///Error:/// \n" if color == "red" else "") + message)  # prefix errors with a header, then the message
        self.tab.errorBox.setGeometry(int(self.width * 11 / 20), int(self.height / 20), 800, 400)  # place the box over the world view
        self.tab.errorBox.setStyleSheet("background-color: " + color + "; color: black")  # color the box and use black text
        self.tab.errorBox.show()  # make it visible

    def addMandatoryBall(self, x, y):  # registers a ball that always reappears on reset
        self.mandatory.append((x, y))  # store its pixel position

    def stop(self):  # called by the Stop button
        self.stopRequested = True  # the next slowed command will abort the program

    def resetWorld(self):  # puts the world back to its starting state
        for ball in self.balls:  # for every existing ball
            self.scene.removeItem(ball)  # remove it from the canvas

        self.balls.clear()  # empty the list
        self.facing = "right"  # Karel faces right
        self.karelSprite.setRotation(0)  # no rotation
        self.karelSprite.setPos(0, 720)  # bottom-left square
        self.karelx = 0  # reset x position
        self.karely = 720  # reset y position
        for tuple in self.mandatory:  # for each mandatory ball position (note: "tuple" shadows the built-in name)
            ball = self.scene.addEllipse(0, 0, 80, 80)  # create a circle
            ball.setPos(tuple[0], tuple[1])  # move it to the saved position
            ball.setBrush(QBrush(QColor("yellow")))  # fill yellow
            ball.setZValue(1)  # draw above the grid
            self.balls.append(ball)  # record it


# ======================================================================
# PART 1 RUNS HERE: the puzzle console.  When the window closes, the
# program only continues into PART 2 (the maze) if the 3rd puzzle was solved.
# ======================================================================
app = QApplication(sys.argv)  # create the Qt application (must exist before any windows)
ide = TabbedConsole()  # create the main puzzle window
ide.show()  # display it
# plays the "Orion Studios" power-on intro over the window
ide.startIntro()  # start the intro animation
# starts loop to wait for inputs (returns when the window closes or the transition ends)
app.exec()  # run the Qt event loop until quit() or the window closes

if not LAUNCH_MAZE:  # the player closed the window without finishing the puzzles
    sys.exit(0)  # exit the program, skipping the maze

# ======================================================================
# PART 2: ESCAPE KAREL (the maze)
# ======================================================================
elapsed = 0.0  # module-level starting value for the maze timer (also silences the "unresolved reference" warning)
# Docstring-style string describing the maze game and its rules (no runtime effect)
"""
ESCAPE KAREL
------------
Find the green exit before time runs out, and before Karel catches you.

Difficulty ramps up as time passes:
  * Your light (field of view) keeps shrinking.
  * Karel starts slow, then speeds up twice (48 seconds in, and again at 83 seconds).
  * Each time Karel speeds up, the screen floods with blood-red binary that spells out
    "karel is coming for your soul" (8-bit ASCII).
  * Blood-red binary glitches also flicker across the screen at random.
  * Background music loops while you play (and restarts when you press R).
  * In the final minutes, yellow balls start spawning at random. Touching one slows you down.
  * Touching the green exit drops you into a long corridor where Karel chases you.
    He gets faster and faster while tiles of the screen glitch red/black and disappear.
    Reaching the end of the corridor shows "YOU ESCAPED!" for a few seconds, then triggers
    a white flash and a computer shutting off.

Controls: WASD / Arrow keys to move, R to restart after the game ends, ESC to quit.
"""

try:  # the whole maze game is wrapped so any crash prints a readable error (see the except at the very bottom)

    # -------------------- Settings --------------------
    # On Windows, stop display scaling from shrinking the reported screen size
    # (otherwise a 1920x1080 screen at 150% zoom would report as 1280x720).
    if sys.platform == "win32":  # only needed on Windows
        try:  # this call may not exist or may fail
            import ctypes  # lets Python call Windows system functions

            ctypes.windll.user32.SetProcessDPIAware()  # tell Windows not to scale this program's pixels
        except Exception:  # anything went wrong
            pass  # ignore and continue

    pygame.init()  # start all pygame modules
# Detect the biggest size the main monitor supports and use it for everything.
    try:  # get_desktop_sizes only exists in pygame 2+
        SCREEN_W, SCREEN_H = pygame.display.get_desktop_sizes()[0]  # width/height of the first monitor
    except Exception:  # older pygame
        info = pygame.display.Info()  # query display info the old way
        SCREEN_W, SCREEN_H = info.current_w, info.current_h  # use the current display size

    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.FULLSCREEN)  # open a fullscreen window; this is the surface everything draws on

    # Cover the screen in black right away, then remove the black window left over from the
    # puzzle transition, so the player goes straight from black to the maze.
    screen.fill((0, 0, 0))  # paint everything black
    pygame.display.flip()  # show the black frame
    try:  # closing the old window may fail
        if BLACK_WIN is not None:  # the Qt black overlay still exists
            BLACK_WIN.close()  # close it
            app.processEvents()  # let Qt process the close right now
    except Exception:  # anything went wrong
        pass  # ignore
    FPS = 60  # target frames per second

    CELL = 64  # size of one maze cell in pixels (corridor width)
    COLS, ROWS = 44, 44  # maze size in cells (was 30 x 30)
    LOOP_CHANCE = 0.03  # chance to open extra passages so the maze has loops
    # (kept low: loops create shortcuts, which shorten the route)
    WALL_DRAW = 5  # white wall thickness (pixels)
    WALL_COLLIDE = 6  # wall thickness used for collisions (pixels)

    TIME_LIMIT = 258  # seconds (4 minutes 18 seconds)

    # Maze length guarantee. Every new maze is re-rolled until the SHORTEST route from the
    # start to the exit is at least this many cells long. A 30x30 maze averaged ~100 cells;
    # 200 cells is ~2x longer, which puts a normal (exploring, backtracking) run at about
    # 2.5 minutes. Raise it for a longer game, lower it for a shorter one.
    MIN_PATH_CELLS = 200  # minimum shortest-path length, in cells
    MAZE_TRIES = 80  # how many mazes to try before settling for the longest found

    PLAYER_SPEED = 185.0  # pixels per second
    PLAYER_RADIUS = 10  # player's collision circle size in pixels

    # Karel: starts slow, then speeds up TWICE (at 48 s and again at 83 s into the maze)
    KAREL_BASE_SPEED = 70.0  # 70.0
    KAREL_SPEEDUP_TIME = 48.0  # seconds into the maze when he speeds up
    KAREL_SPEEDUP_FACTOR = 2.5  # his speed is multiplied by this at that moment
    CATCH_DISTANCE = 24  # if Karel gets this close (pixels), you're caught

    KAREL_SPEEDUP_TIME_2 = 83.0  # seconds into the maze when he speeds up a 2nd time
    KAREL_SPEEDUP_FACTOR_2 = 1.15  # his speed is multiplied by this AGAIN at that moment

    # The binary flood that plays on every Karel speed-up
    SOUL_MESSAGE = "karel is coming for your soul" # Oooh Spooky
    SOUL_DURATION = 5  # seconds the flood lasts (builds up, holds, then fades)
    SOUL_WASH_ALPHA = 14  # red tint over the screen (was ~55-75)
    SOUL_TEXT_ALPHA = 105  # how see-through the binary is (255 = solid)
    SOUL_ROW_FRACTION = 0.35  # at most this fraction of rows ever show (1.0 = full screen)

    # Screen shake that plays on Karel's 2nd speed-up only
    SHAKE_DURATION = 4.5  # seconds the shake lasts (it fades out toward the end)
    SHAKE_STRENGTH = 50  # biggest sideways/up-down jolt, in pixels

    # Field of view: shrinks every minute
    START_RADIUS = 320  # light radius at the start (pixels)
    MIN_RADIUS = 65  # light never gets smfaller than this
    FOV_SHRINK_PER_MIN = 0.75  # radius is multiplied by this every minute (smooth)

    # Yellow balls: spawn at random during the last BALL_PHASE seconds
    BALL_PHASE = 120  # last 2 minutes
    BALL_START_TIME = TIME_LIMIT - BALL_PHASE  # the moment (in seconds) balls start appearing
    BALL_INTERVAL = (0.8, 2.2)  # seconds between spawns (random)
    BALL_MAX = 30  # most balls alive at once
    BALL_RADIUS = 25  # T
    BALL_SPAWN_RANGE = 8  # balls appear within this many cells of you (the maze is big now,
    # so spawning them maze-wide would almost never put one in your way)
    BALL_SLOW_FACTOR = 0.45  # your speed while slowed (set to 1.0 to make balls harmless)
    BALL_SLOW_TIME = 2.5  # seconds of slowdown after touching a ball

    BEACON_RANGE = 520  # exit glows through the darkness within this distance (pixels)

    # Final chase corridor (triggered when you touch the green exit square)
    CHASE_LEN = 12000  # corridor length in pixels (was 7000, ~64 s of running)
    CHASE_H = 96  # corridor height in pixels
    CHASE_START_X = 100  # where the player starts in the corridor
    CHASE_EXIT_X = CHASE_LEN - 100  # where the exit sits (100 px from the end)
    CHASE_GAP = 600  # how far behind you Karel starts (was 600)
    CHASE_FINAL_GAP = 65  # he is still this far back at the exit if you never stop (was 55)
    # (catch happens at 24, so a long stumble is needed to get caught)
    CHASE_KAREL_V0 = 80.0  # Karel's starting speed in the chase (was 90)
    CHASE_LIGHT = 260  # your light radius during the chase
    CHASE_TILE = 90  # size of the glitch tiles (pixels)
    CHASE_TILE_MAX_FRAC = 0.4  # at most this fraction of the screen glitches at once
    ESCAPE_TEXT_TIME = 3.0  # seconds "YOU ESCAPED!" is shown before the computer shuts off

    # Background music (looping). The first path is tried first, then the same filename
    # next to this script, then the current folder.
    MUSIC_FILE = "Karels Barrel of Terribles (1).wav" # This is the audio file as a wav file
    MUSIC_PATHS = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), MUSIC_FILE),  # same folder as this script
        os.path.join(os.getcwd(), MUSIC_FILE),  # current working directory
    ]  # end of the list of places to look for the music
    print([f for f in os.listdir(os.path.dirname(os.path.abspath(__file__))) if f.lower().endswith((".wav", "mp3", ".ogg"))])  # debug: list audio files found next to the script
    MUSIC_VOLUME = 1  # Sets the volume to 100% You can edit this in the settings to your liking

    EXIT_COLOR = (70, 235, 110) #RGB value for exit color
    BALL_COLOR = (255, 225, 30) #RGB value for ball color
    WALL_COLOR = (70, 70, 70) #RGB value for wall color
    FLOOR_COLOR = (14, 13, 20) #RGB value for floor color

    # Karel's sprite: a brown dog with a black collar (embedded, so no extra files needed)
    DOG_PNG_B64 = (  # Karel Source Code Sprite from online
        "iVBORw0KGgoAAAANSUhEUgAAADQAAAA4CAYAAACyutuQAAARrklEQVR42tVae3xU5Zl+3u9c5pKZXCa3mcmF3AwgNwViBdQgCC6X"  # base64 image data (part of the dog PNG)
        "Fq1N10WplhZr7f62blu3ttvukN0W7bay21+72rq0bttVu01b7QpVQdQgoEDkIpcEwi0kkJBM7slk5pzzfe/+kQlFi5VALNvz+53f"  # base64 image data
        "/DFnznzP977v8z7vcw5wZQ+tvLz8mYceeigMQF+2bFnRokWLvqbrOv7SDgIAZtYCGYHO/IJxTxIRysvL/iE/L+9tIQQAaJdyY3GF"  # base64 image data
        "gelelx435OCqebfcck9ra/uSgYFBl5RSA6D+YsLDzAQAkcceC5QUhjsf+dwCzsvO4MxULxeFc9SiRbeVV1VVaZFIZNQbfkWSdfXq"  # base64 image data
        "1QSA3ZaV3tUb83vcBk8pyZYA843XlBg/39o05fDBPUeSGaRHIhFVXV2t/t+m3KFDhwgA9u3bFyCwISXj5hkl+uFTnVrvwBB3Rdu+"  # base64 image data
        "XHX77fOY2dCEcC4WzBUD1N7eTgCwfefOXK9J8HtdHMr04zNLZwiPy6AUis9a/9LLm/1pgXcKi8q+e+edd36EmUUkEhEj6fon2eZK"  # base64 image data
        "kIEgcoJ5xWuK0uXXvvjXs52+wYTuNnUQAEcqdbIlikOnO8XBY+1o7YwhIyv78WPHj38huWYBgCorK1FbW6sAcPK8YiynNF1HX1/X"  # base64 image data
        "3GlluSAQEQDLdpCwHSiwKB6fJz4xa4L69v0LralXBzna1Tv3ueeeKmJm0zB0KYic2tpaJ8mGPELzf/YIRSIRUV1drT5Wddf4vVs3"  # base64 image data
        "7n94+fW61+MiqfjcYpgIxa8fQLjhDNw+N37oc/P3Gk5TisuTMFzu0/GEtT8nmFuflpH1Tm4wULdp/fomIrKuVMrpzJDZoYK/ryj2"  # base64 image data
        "PrZyyXSndyChC0EgZjimjrSWTlT+ZDMy71wEua8Rh5tO4Tf3zOOO1i7q7IthYMhG72AC3QMJtHXHbEXmyZLiwnV1dXWPXQnaZpfL"  # base64 image data
        "4IwM+fFppblwJNPItjIRNFtiICcNR2eUIvHqW7AIOPVX01GaF6Crg+ksNMEAWDFzPOFQd3/M2Fx39KqNu/Z/Z+L48aXanzNKkUhE"  # base64 image data
        "1NbWqrs++8W8s8f3P7pkVpmG4fp51xpYCLRPzEdLaQ5OzihBX0EWOGYh4UhKWA4lLEdYthTMECluk+dMK+JoV596u6G5YuRGGgD5"  # base64 image data
        "Z9Bvgpm1rNzw00UZ9ImvLL9JDsYtTdAf7ykxQ+kaSDFIKTBdeN+VUnC7DBw5FcXaX+1MCGZ2J8GIDztauq7L0pKSF7o62j6Rl5Um"  # base64 image data
        "DV3TpOQL5yURyFEA8/uCYR4+iaDcpsZer+eECIfDO2bOnHmfaRgj9DfWVE5lZWUuAGL+/Pk3tp89uxBg59iZLq27P4Y0nwvMDMX8"  # base64 image data
        "vl1y5LthAAwGQERsGpr0p7gcr8twtu8/Rbo75SCl+ny2Uo6eGsj9xenmk/cTUQyo0oCaMU1Bt8uFwvz8/z3ZdHIpEcmE7eg5GT7c"  # base64 image data
        "MXcS5kwdBwAYSjgQRDg/IMyAx6XDcpTUBbEQgGVLzbIdGhiy0BIdwJsHW3DgRLSjvLz8dvL5fC2rlkwN7Ws8K95u6t/5wH2fWfro"  # base64 image data
        "o4903HRTpZ5sXJfTb8DMYnpFxYrGxhMLBnp7PglIIYjINHQkLAcMxpTSID45bwrKC7MQT9iwHAVNEJRieNwGNu5oxMadR5Du88Dj"  # base64 image data
        "dkMyICE6FJmH2nsHt4eC43Z/fNnCrdXV1W2UlRN6ccXNJbfOryizfrlxr2tLfWdjbvnMpXWbnz8yHTDeBpwRWXGhdIpEInTo0CGq"  # base64 image data
        "qal5b6I7bpcLucHw8/H+zmXXT8pDMOBHtDeG13cfR2dfDB7TgGJGwnZgaBpuqSjF0jkTkJWegv5YAh7TQOOpDvXPP9tCmdlZbxG0"  # base64 image data
        "PYHsnHqvN7WuYNbchg2Pr+lRjnN+ugrKDhZ9atZVKT9bvmCyAgQfa4lqv912tC3K6Z9urt/7UvLi9/YrvhArEgGCBDRdQyJh+YtK"  # base64 image data
        "J6yJ95z52298qtLKy00TCUvquibQ2tmPn7xQh31HW2HqOgQRpFKwpUQg1Ysls8dj7rXFSPGYcvVPXtX6lXddd/TsqkQiAanUe8W1"  # base64 image data
        "qKqq4pqaGgWA6b4vRbK2PL/uwJerKnKIBDxuQyUsW9vw1nHe0xJfs+xzX177g6/e3+U4w+vXBIGEBiKBRx//j8D2zW/k79u7Lxht"  # base64 image data
        "PxvypfrGWVYiUyetUNqxmeke5K9YOFWV5meJ/lgCggjMDJepQwhCzasH8Ls3DkGQgKkLMADbkVDMKA4FVLrPRUfbYqfWrv3eR1at"  # base64 image data
        "WtUBQKusrOScnJxzAP54UwnIyA4/sqwi9PCS2eOdzt6Ybho6uw0Nuxvb6NdbGlsdzf1aTmZGfVtHd5/pcpf093QVCnZK3KZeoGsU"  # base64 image data
        "IHbgNjT4vS4EUt0IZfowLpiO4lBAgUgkLAdC0PkTKwCCz2virQOn8NP1b6N3MA63oUMN0zAStpQAa3nh0K6W02dmEZH6E6n/7mZ3"  # base64 image data
        "34MP5q5/9umGBz8+3ZcfTMdgzBIkCD6PKc929mtP/X43Gps7UV6YjfGFmQhn+hFI9cDrNuA2dbhNQ7kMXWm6gCYEwCBLSopbjgBz"  # base64 image data
        "Ukv/8SEVw+81cSbajyd/txMNTR0wdR0Ag4hYSYUUn2/o+z/4QeE999zTycxERPxBgDQiyNLyyfer/rYnvv6pG22XaRhxywEBcJk6"  # base64 image data
        "s2IZ7R1EMMsPQ9cgJZNUkqRkUsykFA/3CPC5PSTC+wJ5Lyi3qYMVo+a1/XhhWwM0EtA04Ugp9VA4vLm5pWUBDd/sAydXbWSW6O/r"  # base64 image data
        "2sW6b/yuA8emXT+5wE7xmJrtKCiliAHh87pEwnLEUMIRtiOFlIqU+oOyGAFw/nlRIzMRHKnAACom5iM/Nx0HTpzluGWzLyWFPjJr"  # base64 image data
        "1t133XVXc5IAPjDlRlSBsm1H64y23ts5JF5evW6zcSbaZ6d6XTxCibYjQUTQBCWb37sb4OUcI1qubzCBigl5yPC5JQlNLyop+scN"  # base64 image data
        "Gza8ORqtKc6jYUVEdk939DZp+n/9L0+9buysb0aGzyuV4ove8Uu3tgDT0HAm2ifPdg3ohYUFv61vOPwIM+uj8ejEe3oLiCje291Z"  # base64 image data
        "FS4o/vrjz+92Xth6SPN7TcaHfChmeFy6eudoq6Z7fIdfeaVmpW3Z4rwR+5JcHwZA8XhCHDlS/8jixYtm/+bNpu2/3LyfDF0wf0iw"  # base64 image data
        "GIChC+4biGPbwdbExMnT7iwtndmbJK1ROaj0ASakw8yGOyX15ANLp4Svm1TIg0MWnd9Txio6fq/L+dFzO/TdJ/qfGejrvEtKpWNY"  # base64 image data
        "do2Ntx2JRBQAbeXKBwoyUsz0UJafbUeNeS0pZnhdBurqm/H6niZUzJj8upSKKisrL41g3u+L6upq0jQhX3x5/cOlQZ+3OJwpLdsZ"  # base64 image data
        "e25gQAjClr0noek6ioqKY6OpmYsClHQn5cNffLCgp6vz7pkTwuxIpX0Y9SMEIW45aOscgCYIsVj8sgbMC/6YiDQCUPPiy3+T7tU8"  # base64 image data
        "U0pDMm7ZY147I0UsJcN2JJgZ/f09POaAAChd19F6unXxpOJsTvO56f1m/7HjOUBJhe7uHowpoOQzGfXL/3kqxMqZPq0sSI5UH55l"  # base64 image data
        "TIDi4RMAbNsaW0AjjzrWrl03PsNn+ssLslTCci6YbswMpfiy4kIgSKmS0gqwLDn8R7W1YwOopqaGCMChhsMTi3L9yEhLUY5UF6Rb"  # base64 image data
        "09CQ4jGHddOlAEvOPraUw4AAxGIxCQC1Y1lDQhNwe9zXXV2UfcG+M9I7Wtr7sH1/E0xdY5/XZE6OA6ORFEQE21Zwkj2uqKAgGwAu"  # base64 image data
        "tQ9dyNuWRBpc5EwoCWfAsuW7MClmuAwdze29+M5/16JnIM4TCxtp8ezxmFIa5FSfS9oOk+045Eh+t1465/mOKPVh0ZuwHdhSQtMN"  # base64 image data
        "aLqefllm5gVYlBcvftB/+mhNWW7AB8t2xPmIBBGUUvjRczvRMxCHxzToZMdQfN2LB/Vw4Lh+TVmuXp4fQDDTB7/HpVwuXQFEUili"  # base64 image data
        "ZkjFpBTTSBoTAZYj4chh36Wjs1MNl1Dt5QOKRCJUXV3NR1p3TJ4UzMhyGRoPxv9ACFIy0v1uPLNpH060dqlP3jyZag+09qz63Ofn"  # base64 image data
        "ZGdnW489/mTulmNDFW82Hr/JJOe6jBQjP+AzRVaaB5lpXnhdOrweE163Cxl+NxQPb9DgkIXUFBdS3Cbao1E1ZhGqrq4WAFTP6aZp"  # base64 image data
        "hTcVQmhCjlyjFMPrMdDQ1IHnag/ivmUVqiA3Xd92fOiH3/rWt+qTtzhGhO1CaN9f8+Pf+Nd9/9vXNja1zTFFbHZP99GQz+vOGRgY"  # base64 image data
        "DIYzPMY/fWYeg5k0IdA3mEBxOAOGpuFUr8wQSZNxLEiBhdAQSHXdEgp44UgGUdLwFgTHUfj3X23HDVOL1OLry7XX9p1uL56z8N+S"  # base64 image data
        "3pgGQGOGLqXUvvrZ2/ob9+/a0tPW8khXR9tHlZOY2dHRcdWEydMWC123lVLDNUVA3LKRmeqFaWgQmpZ1OYJRvFeFfPabj3vdQt6Q"  # base64 image data
        "meY9Vz9KMVJTXPiv3++GoQl8ZfkNauOu43S8k9ZsfeaJbgCipqZGJsdkJ/lJVVVVmmLWLcvWLMsWRJS4bvqt2w1D7+fhvVIYtqzg"  # base64 image data
        "97rgNnW0t52+DGl6HqCqqioBAK/86om56V4tN8XtklKxUEmracfBZmzZcwL/eM9cdaqtW3+xrrnhROOBJ5L3uNC8z0mQ5wAyg157"  # base64 image data
        "c0OQAL8YVghEIFiWA4/bIEEE0/TkJd/1UZcFqKamBoahoyfadm844IWmCTAzdE2gP2bhR8/txKeXzkBhMA0/33gA5M39ihh+UEsX"  # base64 image data
        "I/erqqpABE5LSSkxdc3QhFAjA2bclmDFYFYwTSPVsm263AgRAPnoo98JJGIDC/NzUmE7SjADKR4TP35+J8ryM3HH3EnyhTfqxdGz"  # base64 image data
        "sVeO1df9nocJ46LcmJGXLbq7OgMMBgnBIz1qcMhC/5BFsYQN23Gy01L9DEBVVlbqlwpIAMAvnn12iqkhLRjwqYTtULrPjc11x3C0"  # base64 image data
        "OYoH7rgePYNxfnnHUXhc3lbTNDiZTqMSrqbHPDf3j4Q2bjlojfaLG6YVK5kYKPb6M55+5503MpKPc/RRA6qsrBzu21JMyErzIN3v"  # base64 image data
        "UUIQ2roG8PTLe/HppTPgdRtIWI4+Z9o47uw4c2duqOCJSCQSTnrOF50ivtRAr2JASUlINumE5eDwqQ5MLQuKb9+3QAVTnOWz53x0"  # base64 image data
        "57x5CxcIQaPaNDHSlQnA2WhHVnaaF6apw9Q11Ly6H/1DCZTkZcJlaBBEuGPuZP7uAwu1wjR1/9q1a9+uuPbaGz9onAeAnJwcBoCB"  # base64 image data
        "3sH2wSGLLalomBgYoSw/BuMWNmw/jKuLc8Q37p0nP3Z9YdmuHds2Tp486UtiuN4uCpT2Bz1Kihm3TxqXMeua8pCKxW0RyvTjdLQP"  # base64 image data
        "67c1QNc0uE0dfQNDZGgatXcPoOFkhy811b+1PRrdU1lZqTU1Nb0vMyXHEh4/ZYLZ2tz8hVlX5+kel8mWLWlqWQhKMX77+kHEEjbS"  # base64 image data
        "U9zimqvCzsFjLeLwibZbV6y4u2bv3r3tF2MH6+eEPAkwy4JQph8AwXYk8nPS8LUVlXh20zv46fo6+L0eGQrlnB5KyNaBWOJo5dzK"  # base64 image data
        "lzZu3PgMEdFFPL5kAPjYggXdq7du6+4dTOQGs/w8OGSTUozlC69BaV4A//lCHTZsa4A/xaO7Pd7OcDCnNh6Pt18sm9LIhcysZ2Zm"  # base64 image data
        "19+74KrSWVOKHEeyGHmBIMPv5ci6TeLA6cFtvV3R+abpspRyIOWoPUBmZld6RtaxmyYG8m67eYqMx21yuXQWRMhMTUFjS1R+48lN"  # base64 image data
        "Rk4wf+03v/mvaz7/+eVdjjMKe27kNciVK1dOzs3JlVnpPi7Ny+KKCfm8ZNZ4XnHrNfx3VbN4RnmIc3KCZ5jZSC5OT8qdUYFiZpo4"  # base64 image data
        "ceJWv8/HWel+zs7wczgrjYtDAS4JZ3JBTjoH0tN5/vz5FcnfGKMhnXMReuihh/xdZ89O3Fq3Jygd+2rLluWObZd193QFlCODRGyW"  # base64 image data
        "jCt86WB9/d1E5OAyXnJdu3Zt6NixY0WbNr3qZVYFknlcd3evAShOTU2P54dzdm/dunXz6tWrnerqah6NT/d/1bFXJ7dwlloAAAAA"  # base64 image data
        "SUVORK5CYII="  # final base64 chunk (the "=" is padding) that completes the PNG data
    )  # end of the parenthesized string; Python joins all the pieces above into one long string

    # -------------------- Maze generation --------------------
    # Thin-wall maze. grid[y][x] is a bitmask of the open passages out of that cell.
    N, E, S, W = 1, 2, 4, 8  # one bit per direction: north=1, east=2, south=4, west=8
    DIRS = {N: (0, -1, S), E: (1, 0, W), S: (0, 1, N), W: (-1, 0, E)}  # direction -> (x step, y step, opposite direction bit)


    def make_maze(cols, rows):  # builds a random maze with depth-first search
        grid = [[0] * cols for _ in range(rows)]  # every cell starts with all walls closed (0 = no openings)
        visited = [[False] * cols for _ in range(rows)]  # tracks which cells the algorithm has reached
        visited[0][0] = True  # start carving from the top-left cell
        stack = [(0, 0)]  # stack of cells to backtrack through
        while stack:  # repeat until every reachable cell is done
            x, y = stack[-1]  # current cell is the top of the stack
            options = []  # unvisited neighbors we could move to
            for bit, (dx, dy, opposite) in DIRS.items():  # check all four directions
                nx, ny = x + dx, y + dy  # neighbor coordinates
                if 0 <= nx < cols and 0 <= ny < rows and not visited[ny][nx]:  # neighbor is inside the grid and unvisited
                    options.append((bit, nx, ny, opposite))  # remember it as a candidate
            if options:  # at least one unvisited neighbor
                bit, nx, ny, opposite = random.choice(options)  # pick one at random
                grid[y][x] |= bit  # open a passage from this cell toward it
                grid[ny][nx] |= opposite  # open the matching passage back
                visited[ny][nx] = True  # mark the neighbor visited
                stack.append((nx, ny))  # move into the neighbor
            else:  # dead end
                stack.pop()  # backtrack to the previous cell

        # Open a few extra passages to create loops (fewer dead-end traps)
        for y in range(rows):  # every row
            for x in range(cols):  # every column
                for bit in (E, S):  # only check east and south so each wall is considered once
                    dx, dy, opposite = DIRS[bit]  # step and opposite for this direction
                    nx, ny = x + dx, y + dy  # the neighbor in that direction
                    if 0 <= nx < cols and 0 <= ny < rows and not grid[y][x] & bit:  # neighbor exists and a wall is still there
                        if random.random() < LOOP_CHANCE:  # small random chance
                            grid[y][x] |= bit  # knock down the wall on this side
                            grid[ny][nx] |= opposite  # and on the neighbor's side
        return grid  # the finished maze


    def make_long_maze(cols, rows):  # keeps generating mazes until one has a long enough solution
        """Re-roll mazes until the shortest start-to-exit route is at least MIN_PATH_CELLS long."""  # docstring
        best, best_len = None, -1  # remember the best maze seen so far
        for _ in range(MAZE_TRIES):  # try up to MAZE_TRIES times
            grid = make_maze(cols, rows)  # generate a candidate
            length = bfs_distances(grid, (0, 0))[rows - 1][cols - 1]  # shortest path length from start to the exit corner
            if length >= MIN_PATH_CELLS:  # long enough
                return grid  # use it
            if length > best_len:  # otherwise remember it if it's the longest so far
                best, best_len = grid, length  # save it
        return best  # fall back to the longest found


    def build_walls(grid):  # converts the maze grid into collision rectangles
        """Collision rectangles (x0, y0, x1, y1), bucketed by the cell that owns them."""  # docstring
        rows, cols = len(grid), len(grid[0])  # grid dimensions
        h = WALL_COLLIDE / 2  # half the wall thickness
        buckets = {}  # maps (cell x, cell y) -> list of wall rectangles

        def add(cx, cy, rect):  # helper that stores a rectangle in a cell's bucket
            buckets.setdefault((cx, cy), []).append(rect)  # create the list if needed, then add

        for y in range(rows):  # every row
            for x in range(cols):  # every column
                px, py = x * CELL, y * CELL  # top-left pixel of this cell
                if not grid[y][x] & N:  # no opening to the north, so there's a wall
                    add(x, y, (px - h, py - h, px + CELL + h, py + h))  # thin rectangle along the top edge
                if not grid[y][x] & W:  # no opening to the west, so there's a wall
                    add(x, y, (px - h, py - h, px + h, py + CELL + h))  # thin rectangle along the left edge
                if y == rows - 1:  # bottom row needs a border wall
                    add(x, y, (px - h, py + CELL - h, px + CELL + h, py + CELL + h))  # rectangle along the bottom edge
                if x == cols - 1:  # rightmost column needs a border wall
                    add(x, y, (px + CELL - h, py - h, px + CELL + h, py + CELL + h))  # rectangle along the right edge
        return buckets  # the collision data


    def cell_center(cell):  # pixel position of the middle of a cell
        return cell[0] * CELL + CELL / 2, cell[1] * CELL + CELL / 2  # (x, y) center


    def pixel_to_cell(x, y):  # converts a pixel position into the cell it's inside
        return (max(0, min(COLS - 1, int(x // CELL))), max(0, min(ROWS - 1, int(y // CELL))))  # divide by cell size and clamp to the grid


    def bfs_distances(grid, source):  # breadth-first search for step counts from one cell to all others
        """Number of cell steps from `source` to every cell, following open passages."""  # docstring
        rows, cols = len(grid), len(grid[0])  # grid dimensions
        dist = [[-1] * cols for _ in range(rows)]  # -1 means "not reached yet"
        sx, sy = source  # source coordinates
        dist[sy][sx] = 0  # the source is 0 steps from itself
        queue = deque([source])  # queue of cells to expand
        while queue:  # until nothing is left
            x, y = queue.popleft()  # take the oldest cell
            for bit, (dx, dy, _) in DIRS.items():  # check each direction
                if grid[y][x] & bit:  # there's an open passage that way
                    nx, ny = x + dx, y + dy  # neighbor coordinates
                    if dist[ny][nx] == -1:  # not reached before
                        dist[ny][nx] = dist[y][x] + 1  # one step farther than the current cell
                        queue.append((nx, ny))  # explore it later
        return dist  # grid of distances


    def pick_karel_cell(grid, player_cell, exit_cell):  # chooses where Karel starts
        """Place Karel a good distance from the player, roughly mid-maze."""  # docstring
        dist = bfs_distances(grid, player_cell)  # distances from the player's cell
        max_d = dist[exit_cell[1]][exit_cell[0]]  # distance from the player to the exit
        lo, hi = int(max_d * 0.35), int(max_d * 0.55)  # Karel must be 35%-55% of the way to the exit
        candidates = [  # all cells within that distance range
            (x, y)  # the cell coordinates
            for y in range(len(grid))  # loop over rows
            for x in range(len(grid[0]))  # loop over columns
            if lo <= dist[y][x] <= hi  # keep only cells in range
        ]  # end of the list
        return random.choice(candidates) if candidates else exit_cell  # random valid cell, or the exit if none exist


    # -------------------- Collision --------------------
    def hits_wall(walls, x, y, r):  # True if a circle at (x, y) with radius r overlaps any wall
        cx, cy = int(x // CELL), int(y // CELL)  # the cell the circle is in
        for gy in range(cy - 1, cy + 2):  # check the cell above, same, and below
            for gx in range(cx - 1, cx + 2):  # and left, same, and right
                for x0, y0, x1, y1 in walls.get((gx, gy), ()):  # every wall rectangle in that cell
                    nx = min(max(x, x0), x1)  # closest x on the rectangle to the circle center
                    ny = min(max(y, y0), y1)  # closest y on the rectangle to the circle center
                    if (x - nx) ** 2 + (y - ny) ** 2 < r * r:  # closest point is inside the circle
                        return True  # collision
        return False  # no collisions found


    # -------------------- Difficulty scaling --------------------
    def fov_radius(elapsed):  # light radius at a given time
        r = START_RADIUS * (FOV_SHRINK_PER_MIN ** (elapsed / 60.0))  # shrink exponentially, 25% per minute
        return max(MIN_RADIUS, r)  # never go below the minimum


    def karel_speed_multiplier(elapsed):  # how much faster than base speed Karel is
        multiplier = 1.0  # start at normal speed
        if elapsed >= KAREL_SPEEDUP_TIME:  # past the first speed-up time
            multiplier *= KAREL_SPEEDUP_FACTOR  # 1st speed-up
        if elapsed >= KAREL_SPEEDUP_TIME_2:  # past the second speed-up time
            multiplier *= KAREL_SPEEDUP_FACTOR_2  # 2nd speed-up (stacks on the 1st)
        return multiplier  # the combined multiplier


    def karel_speed(elapsed):  # Karel's actual speed in pixels per second
        return KAREL_BASE_SPEED * karel_speed_multiplier(elapsed)  # base speed times the multiplier


    # -------------------- Setup --------------------
    pygame.init()  # make sure pygame is initialized (harmless to call again)


    def start_music():  # starts the looping soundtrack
        # Docstring below (a multi-line string, so it can't hold per-line comments): explains that this loops music and restarts it if called again
        """Loop the soundtrack in the background (does not block the game).
        Calling this again reloads the file and starts it from the beginning."""
        try:  # initializing audio may fail
            if not pygame.mixer.get_init():  # audio not started yet
                pygame.mixer.init()  # start it with default settings
        except pygame.error as err:  # no audio device
            print("Audio unavailable:", err)  # report it
            return  # give up on music
        for path in MUSIC_PATHS:  # try each possible file location
            if os.path.isfile(path):  # the file exists here
                try:  # loading may fail
                    pygame.mixer.music.load(open(path, "rb"), "wav")  # load the file as WAV
                    pygame.mixer.music.set_volume(MUSIC_VOLUME)  # apply the volume setting
                    pygame.mixer.music.play(-1)  # -1 = loop forever
                    return  # success, stop searching
                except pygame.error as err:  # loading failed
                    print("Could not play", path, "-", err)  # report it and try the next path
        print("Music file not found. Tried:", [(p, os.path.isfile(p)) for p in MUSIC_PATHS])  # nothing worked: list each path and whether it exists


    start_music()  # begin the maze music
    pygame.display.set_caption("Escape Karel")  # window title
    clock = pygame.time.Clock()  # used to limit and measure frame time

    font = pygame.font.SysFont("arial", 24, bold=True)  # medium bold font for the HUD
    small_font = pygame.font.SysFont("arial", 16)  # small font for hints
    big_font = pygame.font.SysFont("arial", 56, bold=True)  # large font for end screens
    binary_font = pygame.font.SysFont("consolas,couriernew,monospace", 20, bold=True)  # monospace font for the binary text

    dog_right = pygame.image.load(io.BytesIO(base64.b64decode(DOG_PNG_B64)), "karel.png").convert_alpha()  # decode the embedded base64 PNG into an image with transparency
    dog_left = pygame.transform.flip(dog_right, True, False)  # mirrored copy for when Karel faces left

    exit_cell = (COLS - 1, ROWS - 1)  # the exit is the bottom-right cell
    exit_x, exit_y = cell_center(exit_cell)  # pixel position of the exit

    # Reusable full-screen surfaces (avoids reallocating every frame)
    dark_surface = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)  # transparent layer used for darkness
    flash_surface = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)  # transparent layer for color flashes
    hud_surface = pygame.Surface((SCREEN_W, 44), pygame.SRCALPHA)  # top bar background
    hud_surface.fill((0, 0, 0, 215))  # mostly opaque black
    end_panel = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)  # dimming layer for end screens
    end_panel.fill((0, 0, 0, 205))  # mostly opaque black

    # -------------------- "Karel is coming for your soul" binary flood --------------------
    # The message as 8-bit ASCII, one byte per letter, e.g. "01101011 01100001 ..."
    SOUL_BINARY = " ".join(format(ord(ch), "08b") for ch in SOUL_MESSAGE)  # convert each character to 8 binary digits, joined by spaces


    def build_soul_strips():  # pre-renders the binary text images
        """Pre-render one long strip of the message (repeated) so each frame is only a few blits."""  # docstring
        unit = SOUL_BINARY + "      "  # the message plus a gap
        unit_w = binary_font.size(unit)[0]  # pixel width of one unit
        copies = SCREEN_W // unit_w + 2  # enough to always cover the screen while scrolling
        text = unit * copies  # repeat the unit
        main = binary_font.render(text, True, (200, 0, 20))  # bright red text image
        ghost = binary_font.render(text, True, (90, 0, 8))  # darker red shadow image
        return main, ghost, unit_w  # the two images and the unit width


    soul_main, soul_ghost, soul_unit_w = build_soul_strips()  # build them once at startup


    def build_soul_rows():  # creates one scrolling row per line of text
        """One scrolling row of binary every line of text height, each with its own speed/direction."""  # docstring
        row_h = binary_font.get_linesize()  # height of one text line
        rows = []  # list of row settings
        y = 46  # start just below the HUD
        while y < SCREEN_H - 24:  # until near the bottom of the screen
            rows.append({  # add a row
                "y": y,  # vertical position
                "dir": random.choice((-1, 1)),  # scroll left or right
                "speed": random.uniform(50, 230),  # random scroll speed
                "seed": random.uniform(0, soul_unit_w),  # random starting offset
                "order": random.random(),  # rows appear in random order as the flood builds
            })  # end of this row's settings
            y += row_h  # move to the next line
        return rows  # all rows


    soul_rows = build_soul_rows()  # build the rows once
    soul_state = {"start": 0.0, "until": 0.0}  # when the current flood began and when it ends


    def trigger_soul(elapsed):  # starts a binary flood
        soul_state["start"] = elapsed  # record when it began
        soul_state["until"] = elapsed + SOUL_DURATION  # record when it ends


    def draw_soul_binary(elapsed):  # draws the flood if one is active
        """Blood-red binary that spells 'karel is coming for your soul' (kept light so you can still see)."""  # docstring
        if elapsed >= soul_state["until"]:  # no flood active
            return  # nothing to draw
        t = elapsed - soul_state["start"]  # seconds since the flood began
        fade_in, fade_out = 0.9, 1.3  # fade durations in seconds
        if t < fade_in:  # still fading in
            k = t / fade_in  # intensity rises 0 to 1
        elif t > SOUL_DURATION - fade_out:  # fading out
            k = (SOUL_DURATION - t) / fade_out  # intensity falls 1 to 0
        else:  # in the middle
            k = 1.0  # full intensity
        k = max(0.0, min(1.0, k))  # clamp to 0-1

        # Very light red wash
        flash_surface.fill((140, 0, 10, int(SOUL_WASH_ALPHA * k)))  # fill the layer with a faint red
        screen.blit(flash_surface, (0, 0))  # draw it over the screen

        alpha = int(SOUL_TEXT_ALPHA * k)  # text opacity for this moment
        soul_main.set_alpha(alpha)  # apply it to the main text
        soul_ghost.set_alpha(alpha // 2)  # half as opaque for the shadow
        for row in soul_rows:  # each scrolling row
            if row["order"] > k * SOUL_ROW_FRACTION:  # this row hasn't "appeared" yet
                continue  # only a fraction of the rows ever appear
            if random.random() < 0.15:  # 15% chance
                continue  # random flicker
            offset = (row["seed"] + t * row["speed"]) % soul_unit_w  # scrolled distance, wrapping each unit
            x = offset - soul_unit_w if row["dir"] > 0 else -offset  # x position depends on scroll direction
            x += random.randint(-3, 3)  # small horizontal jitter
            screen.blit(soul_ghost, (x + random.choice((-3, 3)), row["y"] + 2))  # draw the shadow slightly offset
            screen.blit(soul_main, (x, row["y"]))  # draw the main text


    # -------------------- Screen shake --------------------
    shake_state = {"start": 0.0, "until": 0.0}  # when the shake began and ends


    def trigger_shake(elapsed):  # starts a screen shake
        shake_state["start"] = elapsed  # record start
        shake_state["until"] = elapsed + SHAKE_DURATION  # record end


    def apply_screen_shake(elapsed):  # shifts the finished frame by a random amount
        """Jolt the whole finished frame by a random offset that fades out over time."""  # docstring
        if elapsed >= shake_state["until"]:  # no shake active
            return  # nothing to do
        t = (elapsed - shake_state["start"]) / SHAKE_DURATION  # 0 -> 1
        strength = SHAKE_STRENGTH * (1.0 - t) ** 0.7  # strong at first, then eases off
        ox = int(random.uniform(-strength, strength))  # random horizontal offset
        oy = int(random.uniform(-strength, strength))  # random vertical offset
        frame = screen.copy()  # copy the current picture
        screen.fill((0, 0, 0))  # clear the screen to black
        screen.blit(frame, (ox, oy))  # draw the picture back shifted


    # -------------------- Drawing --------------------
    def draw_maze(camera_x, camera_y, grid):  # draws the visible part of the maze
        screen.fill(FLOOR_COLOR)  # paint the floor color
        x0 = max(0, int(camera_x // CELL))  # first visible column
        y0 = max(0, int(camera_y // CELL))  # first visible row
        x1 = min(COLS, int((camera_x + SCREEN_W) // CELL) + 2)  # one past the last visible column
        y1 = min(ROWS, int((camera_y + SCREEN_H) // CELL) + 2)  # one past the last visible row
        t = WALL_DRAW  # wall thickness
        o = t // 2  # half thickness, used to center walls on cell edges
        for gy in range(y0, y1):  # each visible row
            for gx in range(x0, x1):  # each visible column
                px = int(gx * CELL - camera_x)  # cell's on-screen x
                py = int(gy * CELL - camera_y)  # cell's on-screen y
                g = grid[gy][gx]  # the cell's passage bitmask
                if not g & N:  # no north opening
                    pygame.draw.rect(screen, WALL_COLOR, (px - o, py - o, CELL + t, t))  # draw the top wall
                if not g & W:  # no west opening
                    pygame.draw.rect(screen, WALL_COLOR, (px - o, py - o, t, CELL + t))  # draw the left wall
                if gy == ROWS - 1:  # bottom row
                    pygame.draw.rect(screen, WALL_COLOR, (px - o, py + CELL - o, CELL + t, t))  # draw the bottom border
                if gx == COLS - 1:  # rightmost column
                    pygame.draw.rect(screen, WALL_COLOR, (px + CELL - o, py - o, t, CELL + t))  # draw the right border


    def draw_character(x, y, camera_x, camera_y, is_karel):  # draws either Karel or the player
        sx, sy = int(x - camera_x), int(y - camera_y)  # world position to screen position
        if is_karel:  # drawing Karel
            sprite = dog_right if karel_facing >= 0 else dog_left  # pick the sprite facing the right way
            pygame.draw.ellipse(screen, (0, 0, 0), (sx - 18, sy + 18, 36, 10))  # shadow
            screen.blit(sprite, sprite.get_rect(center=(sx, sy)))  # draw the dog centered on his position
        else:  # drawing the player
            pygame.draw.circle(screen, (0, 0, 0), (sx, sy), PLAYER_RADIUS + 2)  # black outline
            pygame.draw.circle(screen, (255, 215, 0), (sx, sy), PLAYER_RADIUS)  # gold body
            pygame.draw.circle(screen, (255, 250, 190), (sx - 3, sy - 3), 3)  # small highlight


    _glow_cache = {}  # stores glow images so they're built only once


    def get_glow(radius, color):  # returns a soft circular glow image
        key = (radius, color)  # cache key
        if key not in _glow_cache:  # not built yet
            surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)  # transparent square
            for r in range(radius, 0, -2):  # draw circles from big to small
                alpha = int(150 * (1 - r / radius) ** 1.6)  # more opaque toward the center
                pygame.draw.circle(surf, (*color, alpha), (radius, radius), r)  # draw one ring
            _glow_cache[key] = surf  # save it
        return _glow_cache[key]  # return the cached image


    def draw_balls(camera_x, camera_y, elapsed):  # draws every yellow ball
        for ball in balls:  # each ball
            sx, sy = int(ball["x"] - camera_x), int(ball["y"] - camera_y)  # screen position
            if sx < -40 or sx > SCREEN_W + 40 or sy < -40 or sy > SCREEN_H + 40:  # off-screen
                continue  # skip drawing it
            grow = min(1.0, (elapsed - ball["born"]) / 0.4)  # pop in when spawning
            pulse = 1 + 0.12 * math.sin(elapsed * 6 + ball["phase"])  # gentle pulsing size
            r = max(2, int(BALL_RADIUS * grow * pulse))  # current radius
            glow = get_glow(22, BALL_COLOR)  # glow image
            screen.blit(glow, glow.get_rect(center=(sx, sy)))  # draw the glow
            pygame.draw.circle(screen, (150, 110, 0), (sx, sy), r + 1)  # dark outline
            pygame.draw.circle(screen, BALL_COLOR, (sx, sy), r)  # yellow body
            pygame.draw.circle(screen, (255, 250, 200), (sx - r // 3, sy - r // 3), max(1, r // 3))  # highlight


    _light_cache = {}  # stores light masks by radius


    def get_light_mask(radius):  # returns a circular "hole" mask for the darkness
        radius = max(8, int(radius // 4 * 4))  # quantize so the cache stays small
        if radius not in _light_cache:  # not built yet
            size = radius * 2  # width and height
            mask = pygame.Surface((size, size), pygame.SRCALPHA)  # transparent square
            mask.fill((0, 0, 0, 252))  # start almost fully dark
            for r in range(radius, 0, -2):  # draw circles from big to small
                alpha = int(252 * (r / radius) ** 1.8)  # darkness fades to clear at the center
                pygame.draw.circle(mask, (0, 0, 0, alpha), (radius, radius), r)  # draw one ring
            _light_cache[radius] = mask  # save it
        return _light_cache[radius]  # return the cached mask


    def draw_lighting(px, py, elapsed, radius=None):  # darkens everything except around the player
        flicker = 1 + 0.03 * math.sin(elapsed * 9) + 0.015 * math.sin(elapsed * 23)  # slight light flicker
        base = radius if radius is not None else fov_radius(elapsed)  # use the given radius or the shrinking default
        mask = get_light_mask(base * flicker)  # get the mask for that radius
        r = mask.get_width() // 2  # mask radius
        dark_surface.fill((0, 0, 0, 252))  # fill the darkness layer
        dark_surface.blit(mask, (int(px) - r, int(py) - r), special_flags=pygame.BLEND_RGBA_MIN)  # cut a soft hole at the player using min-alpha blending
        screen.blit(dark_surface, (0, 0))  # draw the darkness over the scene


    def draw_exit_beacon(camera_x, camera_y, elapsed):  # draws the glowing exit when close
        """Pulsing green glow that cuts through the darkness when the exit is fairly close."""  # docstring
        dist = math.hypot(player_x - exit_x, player_y - exit_y)  # distance from the player to the exit
        if dist > BEACON_RANGE:  # too far
            return  # no beacon
        closeness = 1 - dist / BEACON_RANGE  # 0 far, 1 at the exit
        pulse = 0.65 + 0.35 * math.sin(elapsed * 4)  # pulsing brightness
        glow = get_glow(46, EXIT_COLOR)  # green glow image
        glow.set_alpha(int(255 * min(1.0, 0.35 + closeness) * pulse))  # brighter when closer
        sx, sy = int(exit_x - camera_x), int(exit_y - camera_y)  # exit's screen position
        screen.blit(glow, glow.get_rect(center=(sx, sy)))  # draw the glow
        pygame.draw.rect(screen, EXIT_COLOR, (sx - 13, sy - 13, 26, 26), border_radius=4)  # draw the green square
        pygame.draw.rect(screen, (220, 255, 225), (sx - 13, sy - 13, 26, 26), 2, border_radius=4)  # light outline


    def draw_blood_glitch(elapsed, g):  # random red glitch bursts during play
        """Random bursts of blood-red binary text, jitter, ghosting and screen tears."""  # docstring
        if elapsed >= g["next_at"] and elapsed > g["until"]:  # time for a new burst
            g["until"] = elapsed + random.uniform(0.15, 0.7)  # burst lasts a short random time
            g["next_at"] = g["until"] + random.uniform(1.2, 6.0)  # next burst after a random pause
            g["items"] = [  # create the text pieces for this burst
                {
                    "x": random.randint(0, SCREEN_W - 250),  # random x
                    "y": random.randint(50, SCREEN_H - 60),  # random y
                    "len": random.randint(8, 40),  # random number of digits
                }  # end of one item
                for _ in range(random.randint(3, 10))  # 3 to 10 items
            ]  # end of the items list

        if elapsed >= g["until"]:  # no burst active
            return  # nothing to draw

        # Red flash tint
        flash_surface.fill((150, 0, 10, random.randint(10, 45)))  # faint random-strength red
        screen.blit(flash_surface, (0, 0))  # draw it

        # Binary text that re-randomizes and jitters every frame
        for item in g["items"]:  # each text piece
            text = "".join(random.choice("01") for _ in range(item["len"]))  # fresh random 0s and 1s
            jx = item["x"] + random.randint(-6, 6)  # horizontal jitter
            jy = item["y"] + random.randint(-3, 3)  # vertical jitter
            ghost = binary_font.render(text, True, (90, 0, 8))  # dark shadow text
            main = binary_font.render(text, True, (200, 0, 20))  # bright text
            screen.blit(ghost, (jx + random.choice((-3, 3)), jy + 2))  # draw the shadow offset
            screen.blit(main, (jx, jy))  # draw the main text

        # Horizontal tear: shift random strips of the screen sideways
        for _ in range(random.randint(1, 4)):  # 1 to 4 tears
            sy = random.randint(0, SCREEN_H - 30)  # random strip top
            sh = random.randint(4, 24)  # random strip height
            offset = random.randint(-25, 25)  # random sideways shift
            strip = screen.subsurface((0, sy, SCREEN_W, sh)).copy()  # copy that strip of the screen
            screen.blit(strip, (offset, sy))  # draw it back shifted


    def centered_text(message, y, color=(240, 240, 240), font_obj=None):  # draws text centered horizontally
        chosen_font = font_obj or font  # use the given font or the default
        image = chosen_font.render(message, True, color)  # render the text to an image
        screen.blit(image, image.get_rect(center=(SCREEN_W // 2, y)))  # draw it centered at the given y


    # -------------------- Movement --------------------
    def move_player(dx, dy, dt, elapsed):  # moves the player with wall collisions
        global player_x, player_y  # we modify these module-level variables
        if dx == 0 and dy == 0:  # no keys pressed
            return  # nothing to do
        speed = PLAYER_SPEED * (BALL_SLOW_FACTOR if elapsed < slow_until else 1.0)  # slower while affected by a ball
        length = math.hypot(dx, dy)  # length of the direction vector
        mx, my = dx / length * speed * dt, dy / length * speed * dt  # normalized movement this frame (so diagonals aren't faster)
        if not hits_wall(walls, player_x + mx, player_y, PLAYER_RADIUS):  # horizontal move is free
            player_x += mx  # apply it
        if not hits_wall(walls, player_x, player_y + my, PLAYER_RADIUS):  # vertical move is free
            player_y += my  # apply it (separate checks let you slide along walls)


    def move_karel(dt, elapsed):  # moves Karel one frame toward the player
        """Karel chases the player along the shortest path through the maze."""  # docstring
        global karel_x, karel_y, karel_facing  # we modify these module-level variables
        kcx, kcy = pixel_to_cell(karel_x, karel_y)  # Karel's current cell
        ccx, ccy = cell_center((kcx, kcy))  # that cell's center in pixels

        # Pick the open neighbouring cell closest to the player
        best, best_d = None, dist_field[kcy][kcx]  # start with "no better cell" at the current distance
        for bit, (ddx, ddy, _) in DIRS.items():  # each direction
            if maze[kcy][kcx] & bit:  # passage is open
                nx, ny = kcx + ddx, kcy + ddy  # neighbor cell
                d = dist_field[ny][nx]  # its distance to the player
                if d != -1 and d < best_d:  # reachable and closer than anything so far
                    best, best_d = (nx, ny, ddx, ddy), d  # remember it

        speed = karel_speed(elapsed) * dt  # distance Karel can move this frame
        if best is None:  # no closer neighbor
            # Same cell as the player: home in directly
            tx, ty = player_x, player_y  # head straight to the player
        else:  # there's a better neighbor
            nx, ny, ddx, ddy = best  # unpack it
            aligned = abs(karel_y - ccy) < 2 if ddx != 0 else abs(karel_x - ccx) < 2  # is Karel lined up with the corridor he's entering
            tx, ty = cell_center((nx, ny)) if aligned else (ccx, ccy)  # go to the next cell, or first to the current cell's center to line up

        vx, vy = tx - karel_x, ty - karel_y  # vector toward the target
        if abs(vx) > 0.5:  # moving noticeably sideways
            karel_facing = 1 if vx > 0 else -1  # face right or left
        dist = math.hypot(vx, vy)  # distance to the target
        if dist <= speed or dist == 0:  # close enough to arrive this frame
            karel_x, karel_y = tx, ty  # snap to the target
        else:  # still travelling
            karel_x += vx / dist * speed  # step toward it in x
            karel_y += vy / dist * speed  # step toward it in y


    # -------------------- Yellow balls --------------------
    def spawn_ball(elapsed):  # tries to create one ball near the player
        taken = {pixel_to_cell(b["x"], b["y"]) for b in balls}  # cells that already have a ball
        pcx, pcy = pixel_to_cell(player_x, player_y)  # the player's cell
        for _ in range(40):  # try up to 40 random spots
            # Pick a cell near the player so balls actually matter in the big maze
            cell = (  # the candidate cell
                max(0, min(COLS - 1, pcx + random.randint(-BALL_SPAWN_RANGE, BALL_SPAWN_RANGE))),  # random column near the player, clamped
                max(0, min(ROWS - 1, pcy + random.randint(-BALL_SPAWN_RANGE, BALL_SPAWN_RANGE))),  # random row near the player, clamped
            )  # end of the cell tuple
            if cell == exit_cell or cell in taken:  # the exit or an occupied cell
                continue  # try another
            bx, by = cell_center(cell)  # the cell center
            bx += random.randint(-16, 16)  # small random x offset
            by += random.randint(-16, 16)  # small random y offset
            if math.hypot(bx - player_x, by - player_y) < 160:  # too close to the player
                continue  # never spawn right on top of you
            balls.append({"x": bx, "y": by, "born": elapsed, "phase": random.uniform(0, 6.28)})  # create the ball with a random pulse phase
            return  # done, only one ball per call


    # -------------------- Final chase --------------------
    CHASE_MID_Y = SCREEN_H // 2  # vertical center of the screen, where the corridor sits
    chase = {"active": False, "t": 0.0, "T": 1.0, "v1": 0.0, "speed": 0.0, "tiles": {}, "acc": 0.0,
             "snap": None, "shut_t": 0.0, "text_t": 0.0, "sound": None}  # one dictionary holding all chase/ending state (active flag, timers, Karel speed, glitch tiles, screenshot, sound)


    def start_chase():  # begins the final corridor chase
        """Called when you touch the exit: drop into a long corridor with Karel behind you."""  # docstring
        global state, player_x, player_y, karel_x, karel_y, karel_facing, balls, slow_until  # variables we change
        state = "chase"  # switch the game mode
        balls = []  # remove all balls
        slow_until = 0.0  # clear any slowdown
        player_x, player_y = float(CHASE_START_X), float(CHASE_MID_Y)  # put the player at the corridor start
        karel_x, karel_y = player_x - CHASE_GAP, float(CHASE_MID_Y)  # put Karel behind the player
        karel_facing = 1  # Karel faces right
        # Karel's speed ramps up as v0 + (v1 - v0) * progress^2. v1 is solved so that if you
        # run flat out the whole way, Karel is exactly CHASE_FINAL_GAP behind you at the exit.
        run_dist = CHASE_EXIT_X - 26 - CHASE_START_X  # distance the player must run
        T = run_dist / PLAYER_SPEED  # time to run it at full speed
        v0 = CHASE_KAREL_V0  # Karel's starting speed
        v1 = v0 + 3.0 * (CHASE_GAP + run_dist - v0 * T - CHASE_FINAL_GAP) / T  # final speed solved from the integral of the quadratic ramp
        chase.update(active=True, t=0.0, T=T, v1=v1, speed=v0, tiles={}, acc=0.0)  # store the chase settings and reset timers


    def chase_cam_x():  # camera's x position in the corridor
        return int(max(0, min(CHASE_LEN - SCREEN_W, player_x - SCREEN_W / 2)))  # follow the player, clamped to the corridor


    def update_chase_tiles(dt, progress):  # manages the glitching/disappearing screen tiles
        tiles = chase["tiles"]  # the active tiles
        for key in list(tiles):  # each tile (copy of keys so we can delete)
            t = tiles[key]  # the tile's data
            t["age"] += dt  # age it
            if t["age"] > t["glitch"] + t["gone"] + t["back"]:  # lifecycle finished
                del tiles[key]  # remove it

        cols = math.ceil(SCREEN_W / CHASE_TILE)  # tile columns on screen
        rows_ = math.ceil(SCREEN_H / CHASE_TILE)  # tile rows on screen
        cap = int(cols * rows_ * CHASE_TILE_MAX_FRAC)  # maximum tiles allowed at once
        chase["acc"] += (1.5 + 20.0 * progress ** 1.5) * dt  # more tiles break as you near the exit
        psx, psy = player_x - chase_cam_x(), player_y  # player's screen position
        while chase["acc"] >= 1.0:  # each whole unit = one new tile to create
            chase["acc"] -= 1.0  # use up one unit
            if len(tiles) >= cap:  # too many already
                continue  # skip
            for _ in range(10):  # try up to 10 random tiles
                key = (random.randrange(cols), random.randrange(rows_))  # random tile position
                cx = key[0] * CHASE_TILE + CHASE_TILE / 2  # tile center x
                cy = key[1] * CHASE_TILE + CHASE_TILE / 2  # tile center y
                if key in tiles or math.hypot(cx - psx, cy - psy) < 110:  # already glitching or too close to the player
                    continue  # never hide yourself
                tiles[key] = {  # create the tile
                    "age": 0.0,  # starts new
                    "glitch": random.uniform(0.3, 0.9),  # red/black flicker
                    "gone": random.uniform(2.0, 5.0),  # then it disappears (black)
                    "back": random.uniform(0.2, 0.5),  # flickers again as it returns
                }  # end of the tile
                break  # done for this unit


    def draw_chase_tiles():  # draws all glitch tiles
        S = CHASE_TILE  # tile size
        for (tx, ty), t in chase["tiles"].items():  # each tile
            x0, y0 = tx * S, ty * S  # its pixel position
            a = t["age"]  # its age
            if t["glitch"] <= a <= t["glitch"] + t["gone"]:  # in the "gone" phase
                col = (60, 0, 5) if random.random() < 0.03 else (0, 0, 0)  # black, with rare dark-red flickers
                pygame.draw.rect(screen, col, (x0, y0, S, S))  # fill the tile
            else:  # in a flicker phase
                base = random.choice(((0, 0, 0), (0, 0, 0), (90, 0, 8), (170, 0, 15), (220, 20, 30)))  # random red/black color
                pygame.draw.rect(screen, base, (x0, y0, S, S))  # fill the tile
                for _ in range(random.randint(1, 3)):  # 1-3 stripes
                    sy = y0 + random.randint(0, S - 8)  # stripe top
                    sh = min(random.randint(3, 16), y0 + S - sy)  # stripe height, kept inside the tile
                    stripe = random.choice(((0, 0, 0), (200, 0, 20)))  # black or bright red
                    pygame.draw.rect(screen, stripe, (x0, sy, S, sh))  # draw the stripe


    def update_chase(dt):  # one frame of game logic during the chase
        global player_x, player_y, karel_x, state  # variables we change
        chase["t"] += dt  # advance the chase timer
        keys = pygame.key.get_pressed()  # which keys are held
        dx = int(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - int(keys[pygame.K_a] or keys[pygame.K_LEFT])  # +1 right, -1 left, 0 neither
        dy = int(keys[pygame.K_s] or keys[pygame.K_DOWN]) - int(keys[pygame.K_w] or keys[pygame.K_UP])  # +1 down, -1 up, 0 neither
        player_x = max(PLAYER_RADIUS + 4, min(CHASE_LEN - PLAYER_RADIUS - 4, player_x + dx * PLAYER_SPEED * dt))  # move horizontally, staying inside the corridor
        lim = CHASE_H / 2 - PLAYER_RADIUS - 3  # how far from the center line the player may go vertically
        player_y = max(CHASE_MID_Y - lim, min(CHASE_MID_Y + lim, player_y + dy * PLAYER_SPEED * dt))  # move vertically within the corridor walls

        k = min(1.0, chase["t"] / chase["T"])  # progress through the chase, 0 to 1
        chase["speed"] = CHASE_KAREL_V0 + (chase["v1"] - CHASE_KAREL_V0) * k * k  # Karel's speed ramps up quadratically
        karel_x += chase["speed"] * dt  # Karel runs forward
        update_chase_tiles(dt, k)  # update the glitch tiles

        if player_x >= CHASE_EXIT_X - 26:  # player reached the exit
            start_escape_text()  # show "YOU ESCAPED!" first; the shutdown comes after
        elif karel_x >= player_x - CATCH_DISTANCE:  # Karel caught up
            state = "caught"  # game over


    def draw_chase_frame():  # draws the corridor scene
        cam_x = chase_cam_x()  # camera position
        top = CHASE_MID_Y - CHASE_H // 2  # top edge of the corridor
        screen.fill((0, 0, 0))  # black background
        pygame.draw.rect(screen, FLOOR_COLOR, (0, top, SCREEN_W, CHASE_H))  # corridor floor
        for wx in range(-(cam_x % 128), SCREEN_W, 128):  # vertical lines every 128 px, scrolling with the camera
            pygame.draw.rect(screen, (30, 28, 40), (wx, top, 3, CHASE_H))  # floor marks so you feel the speed
        pygame.draw.rect(screen, WALL_COLOR, (0, top - WALL_DRAW, SCREEN_W, WALL_DRAW))  # top wall
        pygame.draw.rect(screen, WALL_COLOR, (0, top + CHASE_H, SCREEN_W, WALL_DRAW))  # bottom wall

        ex = int(CHASE_EXIT_X - cam_x)  # exit's screen x
        ey = CHASE_MID_Y  # exit's screen y
        pygame.draw.rect(screen, EXIT_COLOR, (ex - 13, ey - 13, 26, 26), border_radius=4)  # green exit square
        pygame.draw.rect(screen, (220, 255, 225), (ex - 13, ey - 13, 26, 26), 2, border_radius=4)  # light outline

        draw_character(karel_x, karel_y, cam_x, 0, True)  # draw Karel
        draw_character(player_x, player_y, cam_x, 0, False)  # draw the player
        draw_lighting(player_x - cam_x, player_y, chase["t"], CHASE_LIGHT)  # darkness with a light around the player

        # Exit beacon cutting through the dark
        dist = CHASE_EXIT_X - player_x  # distance to the exit
        if 0 < dist < 900:  # exit is ahead and fairly near
            closeness = 1 - dist / 900  # 0 far, 1 at the exit
            pulse = 0.65 + 0.35 * math.sin(chase["t"] * 4)  # pulsing brightness
            glow = get_glow(46, EXIT_COLOR)  # green glow image
            glow.set_alpha(int(255 * min(1.0, 0.35 + closeness) * pulse))  # brighter when closer
            screen.blit(glow, glow.get_rect(center=(ex, ey)))  # draw the glow
            pygame.draw.rect(screen, EXIT_COLOR, (ex - 13, ey - 13, 26, 26), border_radius=4)  # redraw the exit square above the darkness

        draw_chase_tiles()  # draw the glitch tiles on top

        # HUD
        screen.blit(hud_surface, (0, 0))  # top bar background
        screen.blit(font.render("ESCAPE KAREL", True, (240, 240, 240)), (16, 9))  # game title at the left
        run_img = font.render("RUN!", True, (255, 60, 60))  # red "RUN!" text
        screen.blit(run_img, (SCREEN_W - run_img.get_width() - 18, 9))  # draw it at the right
        info = small_font.render(  # build the status text
            f"Karel speed: x{chase['speed'] / KAREL_BASE_SPEED:.2f}   |   "  # Karel's speed as a multiple of his base speed
            f"Exit: {max(0, int(CHASE_EXIT_X - player_x))} px", True, (220, 110, 110))  # remaining distance in pixels
        screen.blit(info, (SCREEN_W // 2 - info.get_width() // 2, 14))  # draw it centered in the bar


    def draw_end_overlay():  # draws the "caught" screen in the corridor
        """End panel for the 'caught' screen (the escape ending has its own screens)."""  # docstring
        screen.blit(end_panel, (0, 0))  # dim the scene
        if state == "caught":  # only the caught ending uses this
            centered_text("KAREL CAUGHT YOU", SCREEN_H // 2 - 35, (255, 90, 90), big_font)  # big red title
            centered_text("Karel reached you in the corridor.", SCREEN_H // 2 + 15)  # subtitle
        centered_text("Press R to restart  |  ESC to quit", SCREEN_H // 2 + 65, (220, 220, 220), small_font)  # instructions


    # -------------------- Exit: flash of light + computer shutting off --------------------
    SHUT_FLASH = 0.8  # white flash (holds, then fades)
    SHUT_SQUASH = 0.4  # picture collapses into a horizontal line
    SHUT_LINE = 0.3  # line shrinks into a dot
    SHUT_DOT = 0.5  # dot fades out
    SHUT_TOTAL = 2.8  # total time before the end screen appears (rest is black)


    def make_shutdown_sound():  # builds the power-down sound
        """Synthesised power-down: a zap, a falling whine and a final click (no extra files)."""  # docstring
        try:  # audio can fail
            init = pygame.mixer.get_init()  # current audio settings
            if not init or init[1] != -16:  # audio missing or wrong format
                return None  # no sound
            freq, _, channels = init  # sample rate and channel count
            n = int(freq * 1.7)  # 1.7 seconds of samples
            buf = array.array("h")  # buffer of 16-bit samples
            phase = 0.0  # wave angle
            for i in range(n):  # each sample
                t = i / freq  # time in seconds
                f = 40 + 1400 * max(0.0, 1 - t / 1.4) ** 2  # falling whine
                phase += 2 * math.pi * f / freq  # advance the wave
                amp = 0.45 * math.exp(-t * 1.8)  # volume decays over time
                v = amp * math.sin(phase) + 0.15 * amp * math.sin(phase * 2.01)  # tone plus overtone
                if t < 0.12:  # zap at the flash
                    v += 0.5 * (1 - t / 0.12) * random.uniform(-1, 1)  # fading noise burst
                if 1.5 <= t < 1.56:  # click as the dot dies
                    v += 0.7 * (1 - (t - 1.5) / 0.06) * random.uniform(-1, 1)  # short noise click
                sample = max(-32767, min(32767, int(v * 32767 * 0.8)))  # scale and clamp to 16-bit
                for _ in range(channels):  # same sample on every channel
                    buf.append(sample)  # store it
            return pygame.mixer.Sound(buffer=buf.tobytes())  # make a playable sound
        except Exception as err:  # something failed
            print("Could not build shutdown sound:", err)  # report it
            return None  # no sound


    def draw_escape_text_frame():  # draws the "YOU ESCAPED!" screen
        """The frozen corridor with 'YOU ESCAPED!' over it."""  # docstring
        draw_chase_frame()  # draw the corridor scene
        screen.blit(end_panel, (0, 0))  # dim it
        centered_text("YOU ESCAPED!", SCREEN_H // 2 - 35, EXIT_COLOR, big_font)  # big green title
        centered_text("You made it out of the maze.", SCREEN_H // 2 + 15)  # subtitle


    def start_escape_text():  # begins the escape text phase
        """You touched the exit: show 'YOU ESCAPED!' first, the shutdown comes after."""  # docstring
        global state  # we change the game state
        chase["text_t"] = 0.0  # reset the text timer
        state = "escape_text"  # switch mode


    def update_escape_text(dt):  # advances the escape text timer
        chase["text_t"] += dt  # add elapsed time
        if chase["text_t"] >= ESCAPE_TEXT_TIME:  # shown long enough
            start_shutdown()  # move on to the shutdown animation


    def start_shutdown():  # begins the computer-shutdown animation
        """The escape text has been shown: flash white, then switch the 'computer' off."""  # docstring
        global state  # we change the game state
        draw_escape_text_frame()  # draw the final frame so we can copy it
        chase["snap"] = screen.copy()  # save that picture for the shutdown animation
        chase["shut_t"] = 0.0  # reset the shutdown timer
        state = "shutdown"  # switch mode
        try:  # music might not be playing
            pygame.mixer.music.fadeout(1200)  # fade music out over 1.2 seconds
        except pygame.error:  # audio problem
            pass  # ignore
        if chase["sound"] is None:  # sound not built yet
            chase["sound"] = make_shutdown_sound()  # build it once
        if chase["sound"]:  # sound exists
            chase["sound"].play()  # play it


    def update_shutdown(dt):  # advances the shutdown timer
        global state  # we change the game state
        chase["shut_t"] += dt  # add elapsed time
        if chase["shut_t"] >= SHUT_TOTAL:  # animation finished
            state = "escaped"  # show the final black screen


    def draw_shutdown_frame():  # draws one frame of the old-TV shutdown effect
        t = chase["shut_t"]  # time since the shutdown began
        cx, cy = SCREEN_W // 2, SCREEN_H // 2  # screen center
        snap = chase["snap"]  # the saved picture
        t1 = SHUT_FLASH  # end of the flash phase
        t2 = t1 + SHUT_SQUASH  # end of the squash phase
        t3 = t2 + SHUT_LINE  # end of the line phase
        t4 = t3 + SHUT_DOT  # end of the dot phase
        if t < t1:  # phase 1: flash
            # Blinding white flash over the frozen scene, then it fades back
            screen.blit(snap, (0, 0))  # draw the saved picture
            a = 255 if t < 0.12 else int(255 * max(0.0, 1 - (t - 0.12) / (t1 - 0.12)))  # solid white briefly, then fade
            flash_surface.fill((255, 255, 255, a))  # white layer with that opacity
            screen.blit(flash_surface, (0, 0))  # draw it
        elif t < t2:  # phase 2: squash into a line
            # Old-TV collapse: the picture squashes into a bright horizontal line
            p = (t - t1) / SHUT_SQUASH  # progress 0 to 1
            h = max(3, int(SCREEN_H * (1 - p) ** 3))  # shrinking picture height
            screen.fill((0, 0, 0))  # black background
            squashed = pygame.transform.scale(snap, (SCREEN_W, h))  # squash the picture vertically
            screen.blit(squashed, (0, cy - h // 2))  # draw it centered
            bright = pygame.Surface((SCREEN_W, h), pygame.SRCALPHA)  # white tint layer
            bright.fill((255, 255, 255, int(60 + 190 * p)))  # gets brighter as it shrinks
            screen.blit(bright, (0, cy - h // 2))  # draw the tint
        elif t < t3:  # phase 3: line shrinks to a dot
            # The line shrinks sideways into a dot
            p = (t - t2) / SHUT_LINE  # progress 0 to 1
            w = max(2, int(SCREEN_W * (1 - p) ** 2))  # shrinking line width
            screen.fill((0, 0, 0))  # black background
            pygame.draw.rect(screen, (255, 255, 255), (cx - w // 2, cy - 1, w, 3))  # the white line
            glow = get_glow(46, (255, 255, 255))  # white glow image
            glow.set_alpha(int(120 + 100 * p))  # glow brightens
            screen.blit(glow, glow.get_rect(center=(cx, cy)))  # draw it at the center
        elif t < t4:  # phase 4: dot fades
            # The dot glows for a moment and dies
            p = (t - t3) / SHUT_DOT  # progress 0 to 1
            screen.fill((0, 0, 0))  # black background
            glow = get_glow(46, (255, 255, 255))  # white glow image
            glow.set_alpha(int(255 * (1 - p)))  # glow fades out
            screen.blit(glow, glow.get_rect(center=(cx, cy)))  # draw it
            pygame.draw.circle(screen, (255, 255, 255), (cx, cy), max(1, int(4 * (1 - p))))  # small shrinking white dot
        else:  # after the animation
            screen.fill((0, 0, 0))  # pure black


    # -------------------- Game state --------------------
    def new_glitch_state():  # creates fresh settings for the random glitch bursts
        return {"next_at": random.uniform(3.0, 9.0), "until": 0.0, "items": []}  # first burst in 3-9 seconds, none active yet


    def reset_game():  # starts (or restarts) a maze run
        global maze, walls, player_x, player_y, karel_x, karel_y, elapsed, state  # variables we create/change
        global glitch_state, dist_field, last_player_cell, karel_sped_up, karel_sped_up_2, karel_facing  # more variables
        global balls, ball_next, balls_started, slow_until  # and the ball variables
        maze = make_long_maze(COLS, ROWS)  # generate a new maze
        walls = build_walls(maze)  # build its collision data
        player_x, player_y = cell_center((0, 0))  # player starts in the top-left cell
        karel_x, karel_y = cell_center(pick_karel_cell(maze, (0, 0), exit_cell))  # Karel starts mid-maze
        elapsed = 0.0  # reset the timer
        state = "playing"  # normal gameplay mode
        glitch_state = new_glitch_state()  # fresh glitch schedule
        soul_state["start"] = 0.0  # clear any binary flood
        soul_state["until"] = 0.0  # (end time too)
        shake_state["start"] = 0.0  # clear any shake
        shake_state["until"] = 0.0  # (end time too)
        last_player_cell = pixel_to_cell(player_x, player_y)  # the player's cell
        dist_field = bfs_distances(maze, last_player_cell)  # distances from the player, used by Karel to path-find
        karel_sped_up = False  # first speed-up hasn't happened
        karel_sped_up_2 = False  # second speed-up hasn't happened
        karel_facing = 1  # Karel faces right
        balls = []  # no balls
        ball_next = 0.0  # next spawn time
        balls_started = False  # balls haven't started spawning
        slow_until = 0.0  # not slowed
        chase.update(active=False, t=0.0, tiles={}, acc=0.0, snap=None, shut_t=0.0, text_t=0.0)  # reset the chase/ending state


    # -------------------- Main game loop --------------------
    reset_game()  # set up the first run
    running = True  # loop flag

    while running:  # one iteration per frame
        dt = min(clock.tick(FPS) / 1000.0, 0.04)  # seconds since last frame, capped at 0.04 to avoid huge jumps

        for event in pygame.event.get():  # process all pending events
            if event.type == pygame.QUIT:  # window close request
                running = False  # stop the loop
            elif event.type == pygame.KEYDOWN:  # a key was pressed
                if event.key == pygame.K_ESCAPE:  # Escape key
                    running = False  # quit
                elif state not in ("playing", "chase", "escape_text", "shutdown") and event.key == pygame.K_r:  # R pressed on an end screen
                    start_music()  # reload + play(-1) restarts the track from the beginning
                    reset_game()  # start a new run

        if state == "playing":  # normal maze gameplay
            elapsed += dt  # advance the game clock
            keys = pygame.key.get_pressed()  # held keys
            dx = int(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - int(keys[pygame.K_a] or keys[pygame.K_LEFT])  # horizontal input
            dy = int(keys[pygame.K_s] or keys[pygame.K_DOWN]) - int(keys[pygame.K_w] or keys[pygame.K_UP])  # vertical input
            move_player(dx, dy, dt, elapsed)  # move the player

            # Refresh Karel's path map only when the player enters a new cell
            pc = pixel_to_cell(player_x, player_y)  # the player's current cell
            if pc != last_player_cell:  # changed cells
                last_player_cell = pc  # remember it
                dist_field = bfs_distances(maze, pc)  # recompute distances from the new cell
            move_karel(dt, elapsed)  # move Karel

            # Each time Karel speeds up, flood the screen with the binary message as a warning
            if not karel_sped_up and elapsed >= KAREL_SPEEDUP_TIME:  # first speed-up moment
                karel_sped_up = True  # only once
                glitch_state["next_at"] = elapsed  # trigger a glitch burst now
                trigger_soul(elapsed)  # start the binary flood
            if not karel_sped_up_2 and elapsed >= KAREL_SPEEDUP_TIME_2:  # second speed-up moment
                karel_sped_up_2 = True  # only once
                glitch_state["next_at"] = elapsed  # trigger a glitch burst now
                trigger_soul(elapsed)  # start the binary flood
                trigger_shake(elapsed)  # also shake the screen

            # Yellow balls start spawning in the final minutes
            if elapsed >= BALL_START_TIME:  # ball phase has begun
                if not balls_started:  # first time here
                    balls_started = True  # remember
                    ball_next = elapsed  # spawn immediately
                    glitch_state["next_at"] = elapsed  # glitch burst as the balls begin
                if elapsed >= ball_next and len(balls) < BALL_MAX:  # time to spawn and room for more
                    spawn_ball(elapsed)  # create a ball
                    ball_next = elapsed + random.uniform(*BALL_INTERVAL)  # schedule the next one randomly
            for ball in balls[:]:  # each ball (iterating a copy since we may remove)
                if math.hypot(player_x - ball["x"], player_y - ball["y"]) < PLAYER_RADIUS + BALL_RADIUS:  # player touches the ball
                    balls.remove(ball)  # the ball disappears
                    slow_until = elapsed + BALL_SLOW_TIME  # start the slowdown

            if math.hypot(player_x - exit_x, player_y - exit_y) < CELL * 0.4:  # player reached the exit
                start_chase()  # touching the exit now starts the final chase
            elif math.hypot(player_x - karel_x, player_y - karel_y) < CATCH_DISTANCE:  # Karel touched the player
                state = "caught"  # game over
            elif elapsed >= TIME_LIMIT:  # out of time
                state = "time_up"  # game over

        elif state == "chase":  # corridor chase
            update_chase(dt)  # run its logic

        elif state == "escape_text":  # showing "YOU ESCAPED!"
            update_escape_text(dt)  # run its timer

        elif state == "shutdown":  # shutdown animation
            update_shutdown(dt)  # run its timer

        # The chase corridor has its own drawing; skip the maze drawing below.
        if chase["active"]:  # we're in the chase/ending sequence
            if state == "shutdown":  # shutdown animation
                draw_shutdown_frame()  # draw it
            elif state == "escape_text":  # escape text
                draw_escape_text_frame()  # draw it
            elif state == "escaped":  # final screen
                screen.fill((0, 0, 0))  # the "computer" is off
                centered_text("Press R to restart  |  ESC to quit",
                              SCREEN_H // 2, (220, 220, 220), small_font)  # show restart/quit instructions on black
            else:  # chase or caught
                draw_chase_frame()  # draw the corridor
                if state != "chase":  # the chase ended in being caught
                    draw_end_overlay()  # draw the caught panel
            pygame.display.flip()  # show the finished frame
            continue  # skip the maze drawing below

        # Camera follows the player and stays inside the maze boundaries.
        camera_x = int(max(0, min(COLS * CELL - SCREEN_W, player_x - SCREEN_W / 2)))  # camera x centered on the player, clamped
        camera_y = int(max(0, min(ROWS * CELL - SCREEN_H, player_y - SCREEN_H / 2)))  # camera y centered on the player, clamped
        draw_maze(camera_x, camera_y, maze)  # draw floor and walls

        ex, ey = int(exit_x - camera_x), int(exit_y - camera_y)  # exit's screen position
        pygame.draw.rect(screen, EXIT_COLOR, (ex - 13, ey - 13, 26, 26), border_radius=4)  # green exit square
        pygame.draw.rect(screen, (220, 255, 225), (ex - 13, ey - 13, 26, 26), 2, border_radius=4)  # light outline

        draw_balls(camera_x, camera_y, elapsed)  # yellow balls
        draw_character(karel_x, karel_y, camera_x, camera_y, True)  # Karel
        draw_character(player_x, player_y, camera_x, camera_y, False)  # the player

        player_sx, player_sy = player_x - camera_x, player_y - camera_y  # player's screen position
        draw_lighting(player_sx, player_sy, elapsed)  # darkness with a light around the player
        draw_exit_beacon(camera_x, camera_y, elapsed)  # glowing exit if close
        if state == "playing":  # only during live play
            draw_blood_glitch(elapsed, glitch_state)  # random glitch bursts
            draw_soul_binary(elapsed)  # the binary flood if active

        remaining = max(0, int(TIME_LIMIT - elapsed))  # whole seconds left
        timer_text = f"{remaining // 60:02d}:{remaining % 60:02d}"  # format as MM:SS
        screen.blit(hud_surface, (0, 0))  # top bar background
        screen.blit(font.render("ESCAPE KAREL", True, (240, 240, 240)), (16, 9))  # title at the left
        timer_color = (255, 90, 90) if remaining <= 45 else (245, 245, 245)  # red when 45 seconds or less remain
        timer_img = font.render(timer_text, True, timer_color)  # render the timer
        screen.blit(timer_img, (SCREEN_W - timer_img.get_width() - 18, 9))  # draw it at the right
        karel_info = small_font.render(  # build the speed text
            f"Karel speed: x{karel_speed_multiplier(elapsed):.2f}", True, (220, 110, 110)  # Karel's current speed multiplier
        )  # end of the render call
        screen.blit(karel_info, (SCREEN_W // 2 - karel_info.get_width() // 2, 14))  # draw it centered in the bar
        if balls_started and state == "playing":  # during the ball phase
            warn = "SLOWED!" if elapsed < slow_until else "Yellow balls slow you down - avoid them"  # message depends on slowdown
            warn_img = small_font.render(warn, True, BALL_COLOR)  # render it in yellow
            screen.blit(warn_img, (16, 52))  # draw below the bar
        screen.blit(  # draw the controls hint
            small_font.render("Move: WASD / Arrow Keys   |   R: Restart after end   |   ESC: Quit", True,
                              (180, 190, 205)),  # the rendered hint text in light gray-blue
            (16, SCREEN_H - 25),  # at the bottom-left
        )  # end of the blit

        if state != "playing":  # the run has ended
            screen.blit(end_panel, (0, 0))  # dim the scene
            if state == "escaped":  # (rarely used here)
                centered_text("YOU ESCAPED!", SCREEN_H // 2 - 35, EXIT_COLOR, big_font)  # green title
                centered_text("You made it out of the maze.", SCREEN_H // 2 + 15)  # subtitle
            elif state == "caught":  # Karel got you
                centered_text("KAREL CAUGHT YOU", SCREEN_H // 2 - 35, (255, 90, 90), big_font)  # red title
                centered_text("Karel reached you in the maze.", SCREEN_H // 2 + 15)  # subtitle
            else:  # time ran out
                centered_text("TIME'S UP", SCREEN_H // 2 - 35, (255, 90, 90), big_font)  # red title
                centered_text("You ran out of time.", SCREEN_H // 2 + 15)  # subtitle
            centered_text("Press R to restart  |  ESC to quit", SCREEN_H // 2 + 65, (220, 220, 220), small_font)  # instructions

        if state == "playing":  # only while playing
            apply_screen_shake(elapsed)  # shake the finished frame if a shake is active

        pygame.display.flip()  # show the finished frame on the monitor

    pygame.quit()  # shut down pygame after the loop ends
    sys.exit()  # exit the program

except Exception:  # any unexpected error in the maze code
    print("\nKarel Maze Escape encountered an error:")  # headline for the error
    traceback.print_exc()  # print the full error details
    if BLACK_WIN is not None: BLACK_WIN.close(); app.processEvents()  # close the leftover black overlay so the console is visible
    try:  # waiting for input may fail
        input("\nPress Enter to close this window...")  # keep the window open so the player can read the error
    except EOFError:  # no console input available
        pass  # ignore
    try:  # cleanup
        import pygame  # re-import in case the name was lost

        pygame.quit()  # shut pygame down
    except Exception:  # anything went wrong
        pass  # ignore


"""
Special thanks to:
    - Luke Starr [ Tester ] 
    - Caleb Ffrench [ Tester ] 
    - Arsalan Raza [ Tester ] 
    - Kavin Karuppuswamy [ Tester ] 
    - Adrian Alverez [ Tester ] 
    - Mathew Hernandez [ Narrator ] 
    - Matthew Lavoy [ Tester ] 
    - Kevin Wang [ Tester ] 
    - Malachi Geldner [ Music Reviewer ] 
    - Karel [ Agreed To take part in event (Main Villan) ]
    - Codehs [ Giving us Karel ]  
    - Rafeal Correa [ Game Developer, (Created the first part of the game) ] 
"""
