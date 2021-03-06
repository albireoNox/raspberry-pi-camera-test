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

CENTER_DOT_COLOR = [180, 50, 100, 180]
CLIP_OVERLAY_COLOR = [50, 50, 50, 180]
REFERENCE_OVERLAY_COLOR = [0, 180, 180, 60]

FOUND_DOT_COLOR = [0, 255, 0, 255]
REFERENCE_DOT_COLOR = [255, 255, 0, 255]
TARGET_DOT_COLOR = [0, 255, 0, 255]

REGION_OVERLAY_LAYER = 3
DOT_OVERLAY_LAYER = 4

class Config:
    class Dot_Params:
        def __init__(self, config, section):
            self.pct_dark_low = config.getfloat(section, "pct_dark_low")
            self.pct_dark_high = config.getfloat(section, "pct_dark_high")
            self.max_dispersion = config.getfloat(section, "max_dispersion")
            self.luminance_threshold = config.getint(section, "luminance_threshold")
            if self.luminance_threshold < 0 or self.luminance_threshold > 255:
                print("Luminance threshold must be between 0 and 255", file=sys.stderr)
                exit(1)
    
    def __init__(self, config_file_path):
        config = ConfigParser.SafeConfigParser()
        config.read(config_file_path)
        
        self.width = config.getint("dot", "width")
        self.height = config.getint("dot", "height")
        self.num_pixels = self.width * self.height

        self.dot_target_delta = Point(
            config.getint("dot_target", "reference_offset_x"),
            config.getint("dot_target", "reference_offset_y"))
        self.dot_target_radius = config.getint("dot_target", "dot_target_radius")
        self.dot_target_radius_squared = self.dot_target_radius * self.dot_target_radius

        self.dot_params = Config.Dot_Params(config, "dot")
        self.reference_dot_params = Config.Dot_Params(config, "reference_dot")

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
    def __init__(self, config):
        self.num_dark_pixels = 0
        self.config = config

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
    
    return buffer            

def get_detection_overlay(config, point, reference_point=None):
    buffer = bytearray(config.width * config.height * 4)
    if point is not None: 
        write_buf(buffer, int(point.x), int(point.y), config.width, FOUND_DOT_COLOR)
    if reference_point is not None:
        write_buf(buffer, int(reference_point.x), int(reference_point.y), config.width, REFERENCE_DOT_COLOR)
        target = config.dot_target_delta + reference_point
        
        r = config.dot_target_radius
        for dx in range (-config.dot_target_radius, config.dot_target_radius + 1):
            x = dx + target.x
            dy = round(math.sqrt(r * r - dx * dx))
            write_buf(buffer, int(target.x + dx), int(round(target.y + dy)), config.width, CENTER_DOT_COLOR)
            write_buf(buffer, int(target.x + dx), int(round(target.y - dy)), config.width, CENTER_DOT_COLOR)
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

# Return center
def find_dot(config, image, region, dot_params, exclude_region=None):
    # Shift exclude_region
    if exclude_region is not None:
        rel_top_left = region.relative_point(exclude_region.top_left())
        exclude_region = Rectangle(
            rel_top_left.x, rel_top_left.x + exclude_region.width(),
            rel_top_left.y, rel_top_left.y + exclude_region.height())
    
    def is_dark(pixel, point, dot_params, exclude_region=None):
        if exclude_region is not None and exclude_region.contains_point(point):
            return False
        if pixel <= dot_params.luminance_threshold:
            return True
        else:
            return False

    mask = map_pixels(image, lambda px, p: is_dark(px, p, dot_params, exclude_region))

    # Create a list of the dark pixels
    points = []
    for row in range(len(mask)):
        for col in range(len(mask[row])):
            if mask[row][col]:
                points.append((col, row))

    # Percentage of dark pixels relative to all pixels
    pct_dark = (len(points) * 100.0) / config.num_pixels

    d, center = dispersion(points)
    
    if pct_dark > dot_params.pct_dark_low \
            and pct_dark < dot_params.pct_dark_high \
            and d < dot_params.max_dispersion:
        
        return center + region.top_left()
    else:
        return None

def main(config):
    success_led = LED(config.success_pin, active_high=False)
    dot_anywhere_led = LED(config.dot_found_pin, active_high=False)
    blink_led = LED(config.blink_pin, active_high=False)
    debug_button = Button(config.debug_button_pin)
    _globals = Globals(config)
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
            get_detection_overlay(config, None), format='rgba', layer=DOT_OVERLAY_LAYER) 

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
                
                center = find_dot(
                    config,
                    map_pixels(Y, subregion=config.dot_region),
                    config.dot_region,
                    config.dot_params,
                    exclude_region=config.reference_region)
                reference_center = find_dot(
                    config,
                    map_pixels(Y, subregion=config.reference_region),
                    config.reference_region,
                    config.reference_dot_params)

                detection_buffer = get_detection_overlay(config, center, reference_center)
                if detection_overlay is not None:
                    camera.remove_overlay(detection_overlay)
                    detection_overlay = None                    
                detection_overlay = camera.add_overlay(
                    detection_buffer,
                    format='rgba',
                    layer=DOT_OVERLAY_LAYER)
                    
                if center is not None and reference_center is not None:                    
                    dot_target = reference_center + config.dot_target_delta
                    dst_sqrd = math.pow(center.x - dot_target.x, 2) + math.pow(center.y - dot_target.y, 2)
                    dot_anywhere_led.on()
                    if dst_sqrd < config.dot_target_radius_squared:
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
