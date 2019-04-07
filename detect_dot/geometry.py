class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        
    def __repr__(self):
        return "({}, {})".format(self.x, self.y)
    
    def __add__(self, other):
        return Point(self.x + other.x, self.y + other.y)
    
    def __sub__(self, other):
        return Point(-self.x, -self.y) + other

class Rectangle:
    # Define a rectangle between [left, right) and [top, bottom)
    def __init__(self, left, right, top, bottom):
        self.left = left
        self.right = right
        self.top = top
        self.bottom = bottom
    
    def width(self):
        return self.right - self.left
    
    def height(self):
        return self.bottom - self.top
    
    def top_left(self):
        return Point(self.left, self.top)    
    
    def points(self):
        for x in range(self.left, self.right):
            for y in range(self.top, self.bottom):
                yield Point(x, y)
                
    def points_minus_rectangle(self, other):
        for y in range(self.top, other.top):
            for x in range(self.left, self.right):
                yield Point(x, y)
        for y in range(other.top, other.bottom):
            for x in range(self.left, other.left):
                yield Point(x, y)
            for x in range(other.right, self.right):
                yield Point(x, y)
        for y in range(other.bottom, self.bottom):
            for x in range(self.left, self.right):
                yield Point(x, y)
                
    # Return point in coordinate system where top left of the rectangle is (0,0)            
    def relative_point(self, point):
        return Point(point.x - self.left, point.y - self.top)
    
    def contains_point(self, point):
        return point.x >= self.left and point.x < self.right and \
               point.y >= self.top  and point.y < self.bottom
    
    def __repr__(self):
        return "({}, {}, {}, {})".format(self.left, self.top, self.width(), self.height())

# Apply function f to pixel_data (which is a list of list), optionally cropping out anything not in the subregion
def map_pixels(pixel_data, f=None, subregion=None):
    if f is None:
        f = lambda pixel, point: pixel
    
    if subregion is None:
        subregion = Rectangle(0, len(pixel_data[0]), 0, len(pixel_data))
    
    return [[f(pixel, Point(x, y)) for x, pixel in enumerate(row[subregion.left:subregion.right])]
            for y, row in enumerate(pixel_data[subregion.top:subregion.bottom])]