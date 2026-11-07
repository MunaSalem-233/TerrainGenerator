import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.OpenMayaUI as omui

import math
import random

from PySide6 import QtWidgets, QtCore
from shiboken6 import wrapInstance


def get_maya_window():

    pointer = omui.MQtUtil.mainWindow()

    return wrapInstance(
        int(pointer),
        QtWidgets.QWidget
    )


DEFAULTS = {
    "terrain_size": 100.0,
    "grid_res": 151,

    "terrain_height_scale": 9.0,
    "noise_scale": 0.050,
    "noise_octaves": 5,

    "river_width": 4.0,
    "valley_width": 13.0,
    "river_depth": 1.5,

    "river_winding": 13.0,
    "river_frequency": 0.075,

    "water_offset": 0.05,

    "random_seed": 42
}

SETTINGS = DEFAULTS.copy()

_noise_cache = {}


def smooth(t):

    return t * t * (3.0 - 2.0 * t)


def noise2d(x, y):

    ix = math.floor(x)
    iy = math.floor(y)

    fx = smooth(x - ix)
    fy = smooth(y - iy)

    def value(px, py):

        key = (px, py)

        if key not in _noise_cache:

            _noise_cache[key] = random.uniform(
                -1.0, 1.0
            )

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

    for octave in range(SETTINGS["noise_octaves"]):

        total += noise2d(
            x * frequency,
            y * frequency
        ) * amplitude

        amplitude_sum += amplitude

        amplitude *= 0.5
        frequency *= 2.0

    return total / amplitude_sum


def river_center(y):

    winding = SETTINGS["river_winding"]
    frequency = SETTINGS["river_frequency"]

    return (
        winding * math.sin(y * frequency)
        + winding * 0.45
        * math.sin(y * frequency * 2.3 + 1.2)
    )


def terrain_height(x, y):

    height = fractal_noise(
        x * SETTINGS["noise_scale"],
        y * SETTINGS["noise_scale"]
    ) * SETTINGS["terrain_height_scale"]

    # Rolling hills
    height += (
        1.5
        * math.sin(x * 0.08)
        * math.cos(y * 0.06)
    )

    # River settings
    river_width = SETTINGS["river_width"]
    valley_width = SETTINGS["valley_width"]

    river_depth = SETTINGS["river_depth"]

    # Distance from river
    distance = abs(x - river_center(y))

    # Valley influence
    if distance < valley_width:

        t = distance / valley_width

        influence = 1.0 - smooth(t)

    else:

        influence = 0.0

    # River bed
    if distance < river_width:

        target_height = -river_depth

    else:

        bank_t = min(
            1.0,
            (distance - river_width)
            / max(0.001, valley_width - river_width)
        )

        target_height = (
            -river_depth
            + bank_t * (river_depth + 1.0)
        )

    # Blend terrain and valley
    height = (
        height * (1.0 - influence)
        + target_height * influence
    )

    return height


def create_mesh(name, vertices, faces):

    transform = cmds.createNode(
        "transform",
        name=name
    )

    selection = om.MSelectionList()
    selection.add(transform)

    transform_obj = selection.getDependNode(0)

    points = om.MPointArray()

    for x, y, z in vertices:

        points.append(
            om.MPoint(x, y, z)
        )

    polygon_counts = om.MIntArray()
    polygon_connects = om.MIntArray()

    for face in faces:

        polygon_counts.append(len(face))

        for index in face:

            polygon_connects.append(index)

    mesh_fn = om.MFnMesh()

    u_values = om.MFloatArray()
    v_values = om.MFloatArray()

    mesh_fn.create(
        points,
        polygon_counts,
        polygon_connects,
        u_values,
        v_values,
        transform_obj
    )

    return transform


def create_terrain():

    vertices = []
    faces = []

    terrain_size = SETTINGS["terrain_size"]
    grid_res = SETTINGS["grid_res"]

    half_size = terrain_size / 2.0

    step = terrain_size / (grid_res - 1)

    for row in range(grid_res):

        y = -half_size + row * step

        for col in range(grid_res):

            x = -half_size + col * step

            z = terrain_height(x, y)

            vertices.append((x, z, y))

    # Build faces
    for row in range(grid_res - 1):

        for col in range(grid_res - 1):

            a = row * grid_res + col
            b = a + 1
            c = a + grid_res
            d = c + 1

            faces.append((a, c, d, b))

    terrain = create_mesh(
        "Terrain",
        vertices,
        faces
    )

    cmds.polySoftEdge(
        terrain,
        angle=180,
        constructionHistory=False
    )

    return terrain


def create_river():

    vertices = []
    faces = []

    terrain_size = SETTINGS["terrain_size"]
    river_width = SETTINGS["river_width"]

    half_size = terrain_size / 2.0

    segments = SETTINGS["grid_res"] * 2

    for i in range(segments + 1):

        y = -half_size + (
            terrain_size * i / segments
        )

        center_x = river_center(y)

        # Calculate water height along river center
        center_height = terrain_height(
            center_x,
            y
        )

        water_height = (
            center_height
            + SETTINGS["water_offset"]
        )

        # Create river edges
        left_x = center_x - river_width
        right_x = center_x + river_width

        vertices.append((
            left_x,
            water_height,
            y
        ))

        vertices.append((
            right_x,
            water_height,
            y
        ))

    # Create water faces
    for i in range(segments):

        a = i * 2
        b = a + 1
        c = a + 2
        d = a + 3

        faces.append((a, c, d, b))

    water = create_mesh(
        "River_Water",
        vertices,
        faces
    )

    cmds.polySoftEdge(
        water,
        angle=180,
        constructionHistory=False
    )

    return water


def create_material(name, color):

    shader = cmds.shadingNode(
        "lambert",
        asShader=True,
        name=name
    )

    cmds.setAttr(
        shader + ".color",
        color[0],
        color[1],
        color[2],
        type="double3"
    )

    shading_group = cmds.sets(
        renderable=True,
        noSurfaceShader=True,
        empty=True,
        name=name + "_SG"
    )

    cmds.connectAttr(
        shader + ".outColor",
        shading_group + ".surfaceShader",
        force=True
    )

    return shader, shading_group


def delete_old_material(name):

    shading_group = name + "_SG"

    if cmds.objExists(shading_group):

        cmds.delete(shading_group)

    if cmds.objExists(name):

        cmds.delete(name)


def assign_material(obj, shading_group):

    cmds.sets(
        obj,
        edit=True,
        forceElement=shading_group
    )


def setup_viewport():

    panels = cmds.getPanel(
        type="modelPanel"
    )

    for panel in panels:

        cmds.modelEditor(
            panel,
            edit=True,
            displayAppearance="smoothShaded",
            wireframeOnShaded=False,
            displayTextures=True
        )


def generate_terrain():

    global _noise_cache

    print("Generating landscape...")

    # Remove previous landscape
    if cmds.objExists("Procedural_Landscape"):

        cmds.delete("Procedural_Landscape")

    # Remove previous materials
    delete_old_material("Terrain_G")
    delete_old_material("River_B")

    # Reset random noise
    _noise_cache = {}

    random.seed(
        SETTINGS["random_seed"]
    )

    # Create group
    group = cmds.group(
        empty=True,
        name="Procedural_Landscape"
    )

    # Generate terrain
    terrain = create_terrain()

    terrain = cmds.parent(
        terrain,
        group
    )[0]

    print("Terrain created!")

    # Generate river
    river = create_river()

    river = cmds.parent(
        river,
        group
    )[0]

    print("River created!")

    # Create materials
    terrain_shader, terrain_mat = create_material(
        "Terrain_G",
        (0.20, 0.34, 0.14)
    )

    water_shader, water_mat = create_material(
        "River_B",
        (0.035, 0.30, 0.55)
    )

    # Assign materials
    assign_material(
        terrain,
        terrain_mat
    )

    assign_material(
        river,
        water_mat
    )

    # Viewport
    setup_viewport()

    cmds.select(clear=True)

    print("Procedural Landscape Generated!")


class TerrainGeneratorUI(QtWidgets.QDialog):

    def __init__(self, parent=get_maya_window()):

        super(TerrainGeneratorUI, self).__init__(parent)

        # Unique name used to identify this window
        self.setObjectName("ProceduralTerrainGenerator")

        self.setWindowTitle(
            "Procedural Terrain Generator"
        )

        self.setMinimumWidth(350)

        self.setWindowFlags(
            self.windowFlags()
            | QtCore.Qt.Window
        )

        self.controls = {}

        self.create_interface()

    def create_interface(self):

        main_layout = QtWidgets.QVBoxLayout(self)

        # Title
        title = QtWidgets.QLabel(
            "Procedural Terrain Generator"
        )

        title.setStyleSheet(
            "font-size: 16px; font-weight: bold;"
        )

        main_layout.addWidget(title)

        description = QtWidgets.QLabel(
            "Generate customizable terrain and rivers."
        )

        description.setStyleSheet(
            "color: gray;"
        )

        main_layout.addWidget(description)

        # Scroll area
        scroll = QtWidgets.QScrollArea()

        scroll.setWidgetResizable(True)

        scroll_widget = QtWidgets.QWidget()

        scroll_layout = QtWidgets.QVBoxLayout(
            scroll_widget
        )

        # Terrain settings
        terrain_group = QtWidgets.QGroupBox(
            "Terrain Settings"
        )

        terrain_layout = QtWidgets.QFormLayout(
            terrain_group
        )

        self.add_setting(
            terrain_layout,
            "terrain_size",
            "Terrain Size",
            10, 500, 1
        )

        self.add_setting(
            terrain_layout,
            "grid_res",
            "Grid Resolution",
            20, 301, 1,
            integer=True
        )

        self.add_setting(
            terrain_layout,
            "terrain_height_scale",
            "Terrain Height",
            0, 30, 0.5
        )

        self.add_setting(
            terrain_layout,
            "noise_scale",
            "Noise Scale",
            0.001, 0.2, 0.005
        )

        self.add_setting(
            terrain_layout,
            "noise_octaves",
            "Noise Octaves",
            1, 8, 1,
            integer=True
        )

        scroll_layout.addWidget(terrain_group)

        # River settings
        river_group = QtWidgets.QGroupBox(
            "River Settings"
        )

        river_layout = QtWidgets.QFormLayout(
            river_group
        )

        self.add_setting(
            river_layout,
            "river_width",
            "River Width",
            1, 15, 0.5
        )

        self.add_setting(
            river_layout,
            "valley_width",
            "Valley Width",
            2, 40, 0.5
        )

        self.add_setting(
            river_layout,
            "river_depth",
            "River Depth",
            0.1, 10, 0.1
        )

        self.add_setting(
            river_layout,
            "river_winding",
            "River Winding",
            0, 30, 0.5
        )

        self.add_setting(
            river_layout,
            "river_frequency",
            "River Frequency",
            0.001, 0.2, 0.005
        )

        self.add_setting(
            river_layout,
            "water_offset",
            "Water Offset",
            0.001, 0.5, 0.01
        )

        scroll_layout.addWidget(river_group)

        # Random seed
        seed_group = QtWidgets.QGroupBox(
            "Random Seed"
        )

        seed_layout = QtWidgets.QHBoxLayout(
            seed_group
        )

        self.add_setting(
            seed_layout,
            "random_seed",
            "Seed",
            0, 999999, 1,
            integer=True
        )

        random_button = QtWidgets.QPushButton(
            "Randomize"
        )

        random_button.clicked.connect(
            self.randomize_seed
        )

        seed_layout.addWidget(random_button)

        scroll_layout.addWidget(seed_group)

        scroll_layout.addStretch()

        scroll.setWidget(scroll_widget)

        main_layout.addWidget(scroll)

        # Generate button
        generate_button = QtWidgets.QPushButton(
            "GENERATE TERRAIN"
        )

        generate_button.setMinimumHeight(40)

        generate_button.setStyleSheet("""
            QPushButton {
                background-color: #39784b;
                color: white;
                font-weight: bold;
                border-radius: 5px;
            }

            QPushButton:hover {
                background-color: #4b9660;
            }
        """)

        generate_button.clicked.connect(
            self.generate
        )

        main_layout.addWidget(generate_button)

        # Reset button
        reset_button = QtWidgets.QPushButton(
            "Reset Settings"
        )

        reset_button.clicked.connect(
            self.reset_settings
        )

        main_layout.addWidget(reset_button)

        self.status_label = QtWidgets.QLabel(
            "Ready to generate."
        )

        self.status_label.setStyleSheet(
            "color: gray;"
        )

        main_layout.addWidget(self.status_label)

    def add_setting(self, layout, key, label, minimum, maximum,
                    step, integer=False):

        if integer:

            control = QtWidgets.QSpinBox()

            control.setRange(
                int(minimum),
                int(maximum)
            )

            control.setSingleStep(int(step))

        else:

            control = QtWidgets.QDoubleSpinBox()

            control.setRange(
                minimum,
                maximum
            )

            control.setSingleStep(step)

            control.setDecimals(3)

        control.setValue(SETTINGS[key])

    # Support both QFormLayout and QHBoxLayout
        if isinstance(layout, QtWidgets.QFormLayout):

            layout.addRow(label, control)

        else:

            label_widget = QtWidgets.QLabel(label)

            layout.addWidget(label_widget)
            layout.addWidget(control)

        self.controls[key] = control

    def read_settings(self):

        for key, control in self.controls.items():

            SETTINGS[key] = control.value()

        # Ensure the valley is wider than the river
        SETTINGS["valley_width"] = max(
            SETTINGS["valley_width"],
            SETTINGS["river_width"] + 0.5
        )

    def generate(self):

        self.read_settings()

        self.status_label.setText(
            "Generating landscape..."
        )

        QtWidgets.QApplication.processEvents()

        try:

            generate_terrain()

            self.status_label.setText(
                "Landscape generated successfully!"
            )

        except Exception as error:

            self.status_label.setText(
                "Generation failed. See Script Editor."
            )

            cmds.warning(str(error))

            raise

    def randomize_seed(self):

        seed = random.randint(
            0,
            999999
        )

        self.controls["random_seed"].setValue(
            seed
        )

    def reset_settings(self):

        for key, control in self.controls.items():

            control.setValue(
                DEFAULTS[key]
            )

        self.status_label.setText(
            "Settings reset."
        )


for widget in QtWidgets.QApplication.topLevelWidgets():

    if widget.objectName() == "ProceduralTerrainGenerator":

        widget.close()
        widget.deleteLater()


# Create and display the new window

terrain_generator_window = TerrainGeneratorUI()

terrain_generator_window.show()