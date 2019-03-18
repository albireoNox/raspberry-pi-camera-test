#!/usr/bin/env python
import png

with open("test.png", 'wb') as f:
    w = png.Writer(256, 1, greyscale=True)
    w.write(f, [range(256)])