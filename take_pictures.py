#!/usr/bin/env python

from picamera import PiCamera
import time
from argparse import ArgumentParser

parser = ArgumentParser(description="Take some pictures")

parser.add_argument("-n", "--number", type=int, help="number of pictures to take", required=True)
parser.add_argument("-w", "--wait_time", type=int, help="time to wait between pictures, in ms.", default=50)
args = parser.parse_args()

with PiCamera() as camera:

    camera.resolution = (256, 256)
    camera.rotation = 180

    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())

    time.sleep(2)

    for i in range(args.number):
        camera.capture(
            '/home/pi/Desktop/' + timestamp + '_' + str(i) + '.png', 
            format='png')
        time.sleep(args.wait_time / 1000.0)
