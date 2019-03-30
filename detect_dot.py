#!/usr/bin/env python

from picamera import PiCamera
import time
import numpy as np
import png
import io
import math
from gpiozero import LED

WIDTH = 128
HEIGHT = 128

# Given a list of pixels (as x, y pairs), calculate root mean squared deviation
# as a measure of dispersion of the points.
def dispersion(points):
    if len(points) == 0:
        return (float("inf"), (0, 0))
    sum_x = 0
    sum_y = 0
    for point in points:
        sum_x += point[0]
        sum_y += point[1]
    mode_x = sum_x / float(len(points))
    mode_y = sum_y / float(len(points))
    return (math.sqrt(sum(map(lambda p: math.pow(p[0]-mode_x, 2) + math.pow(p[1]-mode_y, 2), points)) / len(points)),
            (mode_x, mode_y))

# Needs to be a global in order to reference in the nested method below (could
# avoided in Python 3).
num_dark_pixels = 0

def main():
    led = LED(2)
    global num_dark_pixels

    # When capturing raw input, the camera uses a resolution whose width is a
    # factor of 32 for width and 16 for height, so we restrict the resolution to
    # satisfy that condition for the sake of simplicity.
    if (WIDTH % 32 != 0 or HEIGHT % 16 != 0):
        print("INVALID RESOLUTION")
        exit(1)

    with PiCamera() as camera:

        camera.resolution = (WIDTH, HEIGHT)

        # The camera requires two seconds of warm-up time for the sensor levels
        # to stabilize before we can begin capturing images.
        time.sleep(2)
        camera.start_preview()

        # We just take 50 samples as fast as we can.
        for i in range(500):

            with io.BytesIO() as stream: # Buffer for pixel data

                camera.capture(stream, 'yuv')
                # Load the Y (luminance) data from the stream
                Y = np.fromstring(stream.getvalue(), dtype=np.uint8, count=WIDTH*HEIGHT).\
                    reshape((HEIGHT, WIDTH))

                num_dark_pixels = 0
                def is_dark(pixel):
                    global num_dark_pixels
                    # Define 12 as an arbitrary luminance cutoff for "dark" pixels.
                    if pixel <= 12:
                        num_dark_pixels += 1
                        return True
                    else:
                        return False

                mask = map(lambda row: map(is_dark, row), Y)

                # Percentage of dark pixels relative to all pixels
                pct_dark = (num_dark_pixels * 100.0) / (WIDTH * HEIGHT)

                # Create a list of the dark pixels
                points = []
                for row in range(HEIGHT):
                    for col in range(WIDTH):
                        if mask[row][col]:
                            points.append((col, row))

                d, center = dispersion(points)
                dst = math.pow(center[0] - 64, 2) + math.pow(center[1] - 64, 2)

                # The following values were determined experimentally.
                if pct_dark > 0.14 and pct_dark < 4 and d < 25 and dst < 10:
                    # We detected the dot
                    led.on()
                    print("***  n_d:{} pct_d:{} dsp:{}, dst:{}".format(num_dark_pixels, pct_dark, d, dst))
                else:
                    # We did not detect the dot
                    led.off()
                    print("-    n_d:{} pct_d:{} dsp:{}, dst:{}".format(num_dark_pixels, pct_dark, d, dst))

if __name__ == '__main__':
    main()
