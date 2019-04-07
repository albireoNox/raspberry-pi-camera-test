#!/usr/bin/env python

from __future__ import print_function

import sys
from picamera import PiCamera
import time
import numpy as np
import png
import io
import math
from gpiozero import LED, Button
from argparse import ArgumentParser
import ConfigParser
from black_and_white import generate_debug_picture
from geometry import *

CENTER_DOT_COLOR = [255, 0, 0, 255]
CLIP_OVERLAY_COLOR = [50, 50, 50, 180]
REFERENCE_OVERLAY_COLOR = [0, 180, 180, 60]
FOUND_DOT_COLOR = [0, 255, 0, 255]

REGION_OVERLAY_LAYER = 3
REFERENCE_OVERLAY_LAYER = 4

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
        self.dot_region_center = Point(
            config.getint("dot", "dot_region_x"),
            config.getint("dot", "dot_region_y"))
        self.dot_region_radius = config.getint("dot", "dot_region_radius")
        self.dot_region_radius_squared = self.dot_region_radius * self.dot_region_radius

        self.dot_region = Rectangle(
            config.getint("crop", "left"),
            self.width - config.getint("crop", "right"),
            config.getint("crop", "top"),
            self.height - config.getint("crop", "bottom"))

        self.reference_region = Rectangle(
            config.getint("reference", "left"),
            config.getint("reference", "right"),
            config.getint("reference", "top"),
            config.getint("reference", "bottom"))

        self.success_pin = config.getint("pins", "success_pin")
        self.dot_found_pin = config.getint("pins", "dot_found_pin")
        self.blink_pin = config.getint("pins", "blink_pin")
        self.debug_button_pin = config.getint("pins", "debug_button_pin")
        
        self.rotation = config.getint("camera", "rotation")

class Globals:
    def __init__(self):
        self.num_dark_pixels = 0

def write_buf(buf, x, y, width, data):
    start = (y * width + x) * 4
    index = start
    for byte in data:
        buf[index] = byte
        index += 1

def get_overlay(config):
    buffer = bytearray(config.width * config.height * 4)
    image = Rectangle(0, config.width, 0, config.height)
    for point in image.points_minus_rectangle(config.dot_region):
        write_buf(buffer, point.x, point.y, config.width, CLIP_OVERLAY_COLOR)
    for point in config.reference_region.points():
        write_buf(buffer, point.x, point.y, config.width, REFERENCE_OVERLAY_COLOR)
    
    write_buf(buffer, config.dot_region_center.x, config.dot_region_center.y, config.width, CENTER_DOT_COLOR)
    
    return buffer            

def get_detection_overlay(config, point):
    buffer = bytearray(config.width * config.height * 4)
    if point is not None: 
        write_buf(buffer, int(point.x), int(point.y), config.width, FOUND_DOT_COLOR)
    return buffer            

# Given a list of pixels (as x, y pairs), calculate root mean squared deviation
# as a measure of dispersion of the points.
def dispersion(points):
    if len(points) == 0:
        return (float("inf"), Point(0, 0))
    sum_x = 0
    sum_y = 0
    for point in points:
        sum_x += point[0]
        sum_y += point[1]
    mode_x = sum_x / float(len(points))
    mode_y = sum_y / float(len(points))
    return (math.sqrt(sum(map(lambda p: math.pow(p[0]-mode_x, 2) + math.pow(p[1]-mode_y, 2), points)) / len(points)),
            Point(mode_x, mode_y))

def output_debug_image(camera, config):
    generate_debug_picture(camera, config.luminance_threshold)
    

# Needs to be a global in order to reference in the nested method below (could
# avoided in Python 3).
num_dark_pixels = 0

def main(config):
    success_led = LED(config.success_pin, active_high=False)
    dot_anywhere_led = LED(config.dot_found_pin, active_high=False)
    blink_led = LED(config.blink_pin, active_high=False)
    debug_button = Button(config.debug_button_pin)
    _globals = Globals()
    detection_overlay = None

    # When capturing raw input, the camera uses a resolution whose width is a
    # factor of 32 for width and 16 for height, so we restrict the resolution to
    # satisfy that condition for the sake of simplicity.
    if (config.width % 32 != 0 or config.height % 16 != 0):
        print("INVALID RESOLUTION")
        exit(1)

    with PiCamera() as camera:

        camera.rotation = config.rotation
        camera.resolution = (config.width, config.height)
        region_overlay_buffer = get_overlay(config)
        region_overlay = camera.add_overlay(region_overlay_buffer, format='rgba', layer=REGION_OVERLAY_LAYER)
        detection_overlay = camera.add_overlay(
            get_detection_overlay(config, None), format='rgba', layer=REFERENCE_OVERLAY_LAYER) 

        # The camera requires two seconds of warm-up time for the sensor levels
        # to stabilize before we can begin capturing images.
        time.sleep(2)
        camera.start_preview()

        num_pictures = 0
        # We just take 50 samples as fast as we can.
        while(True):

            if debug_button.is_pressed:
                output_debug_image(camera, config)
                time.sleep(2)
                continue    
            
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

                mask = map_pixels(Y, lambda p: is_dark(p, _globals), subregion=config.dot_region)
                
                # Percentage of dark pixels relative to all pixels
                pct_dark = (_globals.num_dark_pixels * 100.0) / config.num_pixels

                # Create a list of the dark pixels
                cropped_center = config.dot_region.relative_point(config.dot_region_center)
                points = []
                for row in range(len(mask)):
                    for col in range(len(mask[row])):
                        if mask[row][col]:
                            points.append((col, row))

                d, center = dispersion(points)
                dst_sqrd = math.pow(center.x - cropped_center.x, 2) + math.pow(center.y - cropped_center.y, 2)
                    
                print("pct_dark:{} dsp:{} dst_sqrd:{}".format(pct_dark, d, dst_sqrd))

                if detection_overlay is not None:
                    camera.remove_overlay(detection_overlay)
                    detection_overlay = None

                # The following values were determined experimentally.
                if pct_dark > config.pct_dark_low and pct_dark < config.pct_dark_high and d < config.max_dispersion:
                    detection_overlay = camera.add_overlay(
                        get_detection_overlay(config, center + config.dot_region.top_left()),
                        format='rgba',
                        layer=REFERENCE_OVERLAY_LAYER) 
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
