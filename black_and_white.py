#!/usr/bin/env python

from picamera import PiCamera
import time
from argparse import ArgumentParser
import numpy as np
import png
import io

WIDTH = 256
HEIGHT = 256

if (WIDTH % 32 != 0 or HEIGHT % 16 != 0):
    print("INVALID RESOLUTION")
    exit(1)

#stream = open('image.data', 'w+b')
stream = io.BytesIO()

with PiCamera() as camera:

    camera.resolution = (WIDTH, HEIGHT)
    camera.rotation = 180
    
    time.sleep(2)
    
    camera.capture(stream, 'yuv')
    
    # Load the Y (luminance) data from the stream
    Y = np.fromstring(stream.getvalue(), dtype=np.uint8, count=WIDTH*HEIGHT).\
        reshape((HEIGHT, WIDTH))
    
    avg = sum(map(sum, Y)) / float(sum(map(len, Y))) 
    
    x = map(lambda row: map(lambda pixel: 255 if pixel > avg else 0, row), Y)
    
    with open("test.png", 'wb') as f:
        w = png.Writer(WIDTH, HEIGHT, greyscale=True)
        w.write(f, x)