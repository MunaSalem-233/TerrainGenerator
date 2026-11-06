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


# River path
def river_center(y):

    return (
        river_winding * math.sin(y * river_frequency)
        + river_winding * 0.45 * math.sin(y * river_frequency * 2.3 + 1.2))


# Terrain height
def terrain_height(x, y):
    height = fractal_noise(
        x * noise_scale,
        y * noise_scale
    ) * terrain_height
    
    # rolling hills
    height += 1.5 * math.sin(x * 0.08) * math.cos(y * 0.06)
    
    # distance from center
    distance = abs(x - river_center(y))

    # smoothing edges
    if distance < valley_width:
        t = distance / valley_width
        influence = 1.0 - smooth(t)
    else:
        influence = 0.0

    if distance < river_width:
        target_height = river_level - river_depth
    else:
        bank_t = min(
            1.0,
            (distance - river_width)
            / max(0.001, valley_width - river_width)
        )

        target_height = (
            river_level - river_depth
            + bank_t * (river_depth + 1.0)
        )

    # blending hills and river
    height = (
        height * (1.0 - influence)
        + target_height * influence
    )

    return height


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


# Water build
def create_river():
    vertices = []
    faces = []

    half_size = terrain_size / 2.0

    segments = grid_res * 2

    for i in range(segments + 1):
        y = -half_size + (
            terrain_size * i / segments
        )

        center_x = river_center(y)

        vertices.append((center_x - river_width, y, river_level))

        vertices.append((center_x + river_width, y, river_level))

    for i in range(segments):
        a = i * 2
        b = a + 1
        c = a + 2
        d = a + 3

        faces.append((a, c, d, b))

    water = create_mesh("River_Water", vertices, faces)

    cmds.polySoftEdge(water, angle=180, constructionHistory=False)

    return water


# Materials
def create_material(name, color, roughness=0.8):
    shader = cmds.shadingNode("lambert", asShader=True, name=name)

    cmds.setAttr(
        shader + ".color",
        color[0],
        color[1],
        color[2],
        type="double3"
    )

    shading_grp = cmds.sets(
        renderable=True,
        noSurfaceShader=True,
        empty=True,
        name=name + "_SG"
    )

    cmds.connectAttr(
        shader + ".outColor",
        shading_grp + ".surfaceShader",
        force=True
    )

    cmds.sets(
        shading_grp,
        edit=True,
        forceElement=True
    )

    return shading_grp


# Generate scene
def generate_terrain():
    if cmds.objExists("Procedural_Terrain"):
        cmds.delete("Procedural_Terrain")

    group = cmds.group(
        empty=True,
        name="Procedural_Terrain"
    )

    terrain = create_terrain()
    river = create_river()

    cmds.parent(terrain, group)
    cmds.parent(river, group)

    terrain_mat = create_material(
        "Terrain_G",
        (0.20, 0.34, 0.14)
    )

    water_mat = create_material(
        "River_B",
        (0.035, 0.30, 0.55),
        roughness=0.25
    )

    cmds.sets(
        terrain,
        edit=True,
        forceElement=terrain_mat
    )

    cmds.sets(
            terrain,
            edit=True,
            forceElement=water_mat
        )

    cmds.select(terrain, replace=True)

    print("Procedural Terrain Generated!")