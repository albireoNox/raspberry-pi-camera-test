#!/usr/bin/env python

from picamera import PiCamera
import time
from argparse import ArgumentParser
import numpy as np
import png
import io

WIDTH = 128
HEIGHT = 128

def generate_debug_picture(camera, luminance_threshold):
    stream = io.BytesIO()
    
    camera.capture(stream, 'yuv')
    
    # Load the Y (luminance) data from the stream
    Y = np.fromstring(stream.getvalue(), dtype=np.uint8, count=WIDTH*HEIGHT).\
        reshape((HEIGHT, WIDTH))
    
    black_and_white = map(lambda row: map(lambda pixel: 255 if pixel > luminance_threshold else 0, row), Y)
    
    with open("black_and_white.png", 'wb') as f:
        w = png.Writer(WIDTH, HEIGHT, greyscale=True)
        w.write(f, black_and_white)
    with open("grayscale.png", 'wb') as f:
        w = png.Writer(WIDTH, HEIGHT, greyscale=True)
        w.write(f, Y)
        
        
if __name__ == '__main__':
    if (WIDTH % 32 != 0 or HEIGHT % 16 != 0):
        print("INVALID RESOLUTION")
        exit(1)

    with PiCamera() as camera:

        camera.resolution = (WIDTH, HEIGHT)
        camera.rotation = 180
        
        time.sleep(2)
    
        generate_debug_picture(camera, 30)
        
