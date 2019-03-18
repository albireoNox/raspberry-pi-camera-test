#!/usr/bin/env python

from picamera import PiCamera
import time
import numpy as np
import png
import io
import math

WIDTH = 128
HEIGHT = 128

def dispersion(points):
    if len(points) == 0:
        return float("inf")
    
    sum_x = 0
    sum_y = 0
    
    for point in points:
        sum_x += point[0]
        sum_y += point[1]
        
    mode_x = sum_x / float(len(points))
    mode_y = sum_y / float(len(points))
    
    return math.sqrt(sum(map(lambda p: math.pow(p[0]-mode_x, 2) + math.pow(p[1]-mode_y, 2), points)) / len(points)) 

num_dark_pixels = 0

def main():
    global num_dark_pixels
    if (WIDTH % 32 != 0 or HEIGHT % 16 != 0):
        print("INVALID RESOLUTION")
        exit(1)

    #stream = open('image.data', 'w+b')

    with PiCamera() as camera:

        camera.resolution = (WIDTH, HEIGHT)
        camera.rotation = 180
        
        time.sleep(2)
        
        for i in range(50):
            with io.BytesIO() as stream: 
                camera.capture(stream, 'yuv')
                
                # Load the Y (luminance) data from the stream
                Y = np.fromstring(stream.getvalue(), dtype=np.uint8, count=WIDTH*HEIGHT).\
                    reshape((HEIGHT, WIDTH))
                
                num_dark_pixels = 0
                def is_dark(pixel):
                    global num_dark_pixels
                    if pixel <= 12:
                        num_dark_pixels += 1
                        return True
                    else:
                        return False
                
                mask = map(lambda row: map(is_dark, row), Y)
                
                pct_dark = (num_dark_pixels * 100.0) / (WIDTH * HEIGHT)
                
                points = []
                for row in range(HEIGHT):
                    for col in range(WIDTH):
                        if mask[row][col]:
                            points.append((col, row))
                
                d = dispersion(points)
                
                #print("PCT: {}  DSP: {}".format(pct_dark, d))
                if pct_dark > 2 and pct_dark < 4 and d < 25:
                    print("***  n_d:{} pct_d:{} dsp:{}".format(num_dark_pixels, pct_dark, d))
                else:
                    print("-    n_d:{} pct_d:{} dsp:{}".format(num_dark_pixels, pct_dark, d))
                #if pct_dark > 2 and pct_dark < 4:
                    #print("PCT: {}".format)
                
                #x = map(lambda row: map(lambda b: 0 if b else 255, row), mask)
                
                #with open("test.png", 'wb') as f:
                    #w = png.Writer(WIDTH, HEIGHT, greyscale=True)
                    #w.write(f, x)
                    
if __name__ == '__main__':
    main()
