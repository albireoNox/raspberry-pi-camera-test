#!/usr/bin/env python

from __future__ import print_function

import sys
from picamera import PiCamera
import time
import numpy as np
import png
import io
import math
from gpiozero import LED
from argparse import ArgumentParser
import ConfigParser

class Config:
    def __init__(self, config_file_path):
        config = ConfigParser.SafeConfigParser()
        config.read(config_file_path)
        
        self.width = config.getint("dot", "width")
        self.height = config.getint("dot", "height")
        self.num_pixels = self.width * self.height
        self.luminance_threshold = config.getint("dot", "luminance_threshold")
        if self.luminance_threshold < 0 or self.luminance_threshold > 255:
            print("Luminance threshold must be between 0 and 255", file=sys.stderr)
            exit(1)
        self.pct_dark_low = config.getfloat("dot", "pct_dark_low")
        self.pct_dark_high = config.getfloat("dot", "pct_dark_high")
        self.max_dispersion = config.getfloat("dot", "max_dispersion")
        self.dot_region_x = config.getint("dot", "dot_region_x")
        self.dot_region_y = config.getint("dot", "dot_region_y")
        self.dot_region_radius = config.getint("dot", "dot_region_radius")
        self.dot_region_radius_squared = self.dot_region_radius * self.dot_region_radius

        self.success_pin = config.getint("pins", "success_pin")
        self.dot_found_pin = config.getint("pins", "dot_found_pin")
        self.blink_pin = config.getint("pins", "blink_pin")

class Globals:
    def __init__(self):
        self.num_dark_pixels = 0

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

def main(config):
    success_led = LED(config.success_pin, active_high=False)
    dot_anywhere_led = LED(config.dot_found_pin, active_high=False)
    blink_led = LED(config.blink_pin, active_high=False)
    _globals = Globals()

    # When capturing raw input, the camera uses a resolution whose width is a
    # factor of 32 for width and 16 for height, so we restrict the resolution to
    # satisfy that condition for the sake of simplicity.
    if (config.width % 32 != 0 or config.height % 16 != 0):
        print("INVALID RESOLUTION")
        exit(1)

    with PiCamera() as camera:

        camera.resolution = (config.width, config.height)

        # The camera requires two seconds of warm-up time for the sensor levels
        # to stabilize before we can begin capturing images.
        time.sleep(2)
        camera.start_preview()

        # We just take 50 samples as fast as we can.
        while(True):
            blink_led.on()
            with io.BytesIO() as stream: # Buffer for pixel data

                camera.capture(stream, 'yuv')
                # Load the Y (luminance) data from the stream
                Y = np.fromstring(stream.getvalue(), dtype=np.uint8, count=config.num_pixels).\
                    reshape((config.height, config.width))

                blink_led.off()
                
                _globals.num_dark_pixels = 0
                def is_dark(pixel, _globals):
                    if pixel <= config.luminance_threshold:
                        _globals.num_dark_pixels += 1
                        return True
                    else:
                        return False

                mask = [[is_dark(pixel, _globals) for pixel in row] for row in Y]

                # Percentage of dark pixels relative to all pixels
                pct_dark = (_globals.num_dark_pixels * 100.0) / config.num_pixels

                # Create a list of the dark pixels
                points = []
                for row in range(config.height):
                    for col in range(config.width):
                        if mask[row][col]:
                            points.append((col, row))

                d, center = dispersion(points)
                dst_sqrd = math.pow(center[0] - config.dot_region_x, 2) + math.pow(center[1] - config.dot_region_y, 2)
                    
                print("pct_dark:{} dsp:{} dst_sqrd:{}".format(pct_dark, d, dst_sqrd))

                # The following values were determined experimentally.
                if pct_dark > config.pct_dark_low and pct_dark < config.pct_dark_high and d < config.max_dispersion:
                    dot_anywhere_led.on()
                    if dst_sqrd < config.dot_region_radius_squared:
                        success_led.on()
                    else:
                        success_led.off()
                else:
                    dot_anywhere_led.off()
                    success_led.off()


if __name__ == '__main__':
    parser = ArgumentParser(description="Detect a dot")
    parser.add_argument("-c", "--config_file", help="File path of configuration file. Defaults to ./Config", default='./Config')
    args = parser.parse_args()
    config_file_path = args.config_file
    
    config = Config(config_file_path)
    main(config)
