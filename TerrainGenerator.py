import maya.cmds as cmds
import maya.api.OpenMaya as om
import math
import random

# Prodecural Terrain that generates a river running through it.
# Breakdown structure:
#   Terrain:
#       -Plane: Fixed size? How big do we want the landscape to be? Height?
#       -Roughness: Noise slider. Subdivisions. (Math equations...)
#   River:
#       -Width and depth: Range values.
#       -Carving logic to generate river: Motion path.
#       -Water mesh surface

# Artists would be given variations to height, depth, width, and roughness of terrain.

terrain_size = 100.0
grid_res = 151

terrain_height = 9.0
noise_scale = 0.050
noise_octaves = 5

river_width = 4.0
valley_width = 13.0
river_level = 0.0
river_depth = 1.5

river_winding = 13.0
river_frequency = 0.075

random_seed = 42

# Noise generation
random.seed(random_seed)

_noise_cache = {}


def smooth(t):
    return t * t * (3.0 - 2.0 * t)


def noise2d(x, y):
    ix = math.floor(x)
    iy = math.floor(y)

    fx = x - ix
    fy = y - iy

    fx = smooth(fx)
    fy = smooth(fy)

    def value(px, py):
        key = (px, py)

        if key not in _noise_cache:
            _noise_cache[key] = random.uniform(-1.0, 1.0)

        return _noise_cache[key]
    a = value(ix, iy)
    b = value(ix + 1, iy)
    c = value(ix, iy + 1)
    d = value(ix + 1, iy + 1)

    bottom = a + (b - a) * fx
    top = c + (d - c) * fx

    return bottom + (top - bottom) * fy


def fractal_noise(x, y):

    total = 0.0
    amplitude = 1.0
    frequency = 1.0
    amplitude_sum = 0.0

    for octave in range(noise_octaves):
        total += noise2d(x * frequency, y * frequency) * amplitude

        amplitude_sum += amplitude
        amplitude *= 0.5
        frequency *= 2.0

    return total / amplitude_sum


# Mesh creation
def create_mesh(name, vertices, faces):
    points = om.MPointArray()

    for x, y, z in vertices:
        points.append(om.MPoint(x, y, z))

    polygon_counts = om.MIntArray()
    polygon_connects = om.MIntArray()

    for face in faces:
        polygon_counts.append(len(face))

        for index in face:
            polygon_connects.append(index)

    mesh_fn = om.MFnMesh()

    mesh_obj = mesh_fn.create(points, polygon_counts, polygon_connects)

    transform = om.MfnDagNode(mesh_obj).parent(0)
    transform_fn = om.MFnDagNode(transform)
    transform_fn.setName(name)

    return transform_fn.fullPathName()


# Terrain building
def create_terrain():
    vertices = []
    faces = []

    half_size = terrain_size / 2.0
    step = terrain_size / (grid_res - 1)

    for row in range(grid_res):
        y = -half_size + row * step

        for col in range(grid_res):
            x = -half_size + col * step
            z = terrain_height(x, y)

            vertices.append((x, y, z))

    for row in range(grid_res - 1):
        for col in range(grid_res - 1):
            a = row * grid_res + col
            b = a + 1
            c = a + grid_res
            d = c + 1

            faces.append((a, c, d, b))

    terrain = create_mesh("Terrain", vertices, faces)

    cmds.polySoftEdge(terrain, angle=180, constructionHistory=False)

    return terrain