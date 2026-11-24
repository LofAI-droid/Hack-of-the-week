"""Virtuele studio GenAI Kennishub — fotorealistische achtergrond in Blender (Cycles).

Gebruik:
    python3 studio_scene.py [uitvoer.png] [samples]

Assen: x = rechts, y = diepte (weg van de camera), z = omhoog. Eenheden in meter.
De camera staat stil; dit script rendert één achtergrondbeeld (1920x1080).
"""
import math
import sys

import bpy

OUT = sys.argv[1] if len(sys.argv) > 1 else "studio-achtergrond.png"
SAMPLES = int(sys.argv[2]) if len(sys.argv) > 2 else 128
# derde argument "panelen": onzichtbare panelen die alleen schaduw werpen
MET_PANELEN = len(sys.argv) > 3 and sys.argv[3] == "panelen"

# Panelen (wereldcoördinaten, meter): middelpunt x, diepte y, onderkant z, breedte, hoogte
PANEEL_Y = 2.5
PANEEL_Z0 = 0.9
PANEEL_B, PANEEL_H = 1.4, 2.0
PANEEL_X = [0.8, 2.4, 4.0]

# ---------- Huisstijl (sRGB hex) ----------
NAVY = "#003a7d"
MAGENTA = "#e4004f"
YELLOW = "#fdb028"
SKY = "#86caf6"


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_rgba(h, mix_with=None, t=0.0):
    h = h.lstrip("#")
    rgb = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    if mix_with:
        m = mix_with.lstrip("#")
        mrgb = [int(m[i : i + 2], 16) / 255 for i in (0, 2, 4)]
        rgb = [a * t + b * (1 - t) for a, b in zip(rgb, mrgb)]
    return (*[srgb_to_linear(c) for c in rgb], 1.0)


# ---------- Leeg scène ----------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


# ---------- Materialen ----------
def mat_basic(name, color, rough=0.8, spec=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = color
    b.inputs["Roughness"].default_value = rough
    b.inputs["Specular IOR Level"].default_value = spec
    return m


def mat_emission(name, color, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = color
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m


def mat_concrete(name):
    """Licht gepolijst beton: lichte kleurvariatie en wisselende glans."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 0.9
    noise.inputs["Detail"].default_value = 8.0
    noise.inputs["Roughness"].default_value = 0.55
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    # kleur
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = hex_rgba("#b9c3cf")
    ramp.color_ramp.elements[1].color = hex_rgba("#d3dae3")
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    # glans
    rr = nt.nodes.new("ShaderNodeMapRange")
    rr.inputs["To Min"].default_value = 0.04
    rr.inputs["To Max"].default_value = 0.16
    fine = nt.nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 6.0
    fine.inputs["Detail"].default_value = 4.0
    nt.links.new(tc.outputs["Object"], fine.inputs["Vector"])
    nt.links.new(fine.outputs["Fac"], rr.inputs["Value"])
    nt.links.new(rr.outputs["Result"], b.inputs["Roughness"])
    b.inputs["Specular IOR Level"].default_value = 0.55
    brick = nt.nodes.new("ShaderNodeTexBrick")
    brick.offset = 0.0
    brick.inputs["Scale"].default_value = 1.0
    brick.inputs["Mortar Size"].default_value = 0.004
    brick.inputs["Brick Width"].default_value = 2.4
    brick.inputs["Row Height"].default_value = 2.4
    brick.inputs["Color1"].default_value = (1, 1, 1, 1)
    brick.inputs["Color2"].default_value = (1, 1, 1, 1)
    brick.inputs["Mortar"].default_value = (0, 0, 0, 1)
    nt.links.new(tc.outputs["Object"], brick.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.25
    nt.links.new(brick.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


M_WALL = mat_basic("wand", hex_rgba("#e4eaf1"), rough=0.9, spec=0.3)
M_NICHE = mat_basic("nis", hex_rgba("#d5e1ee"), rough=0.9, spec=0.3)
M_SLAT = mat_basic("lamel", hex_rgba("#f6f8fb"), rough=0.55, spec=0.4)
M_COLUMN = mat_basic("zuil", hex_rgba("#f1f4f8"), rough=0.7, spec=0.35)
M_FLOOR = mat_concrete("vloer")
M_PLINT = mat_basic("plint", hex_rgba("#c9d3de"), rough=0.6)
M_LINE = mat_emission("lichtlijn", hex_rgba(MAGENTA), 2.2)
M_CIRCLE_SKY = mat_basic("cirkel-sky", hex_rgba(SKY, "#e6eef6", 0.7), rough=0.85, spec=0.2)
M_CIRCLE_YEL = mat_basic("cirkel-geel", hex_rgba(YELLOW, "#e6eef6", 0.55), rough=0.85, spec=0.2)


# ---------- Geometrie ----------
def box(name, x0, x1, y0, y1, z0, z1, mat):
    bpy.ops.mesh.primitive_cube_add(size=1)
    o = bpy.context.active_object
    o.name = name
    o.scale = (x1 - x0, y1 - y0, z1 - z0)
    o.location = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    bpy.ops.object.transform_apply(scale=True)
    bevel = o.modifiers.new("bevel", "BEVEL")
    bevel.width = 0.008
    bevel.segments = 3
    o.data.materials.append(mat)
    return o


def disc(name, x, y, z, r, depth, mat):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, vertices=128,
                                        location=(x, y, z), rotation=(math.radians(90), 0, 0))
    o = bpy.context.active_object
    o.name = name
    bevel = o.modifiers.new("bevel", "BEVEL")
    bevel.width = 0.01
    bevel.segments = 3
    bpy.ops.object.shade_smooth()
    o.data.materials.append(mat)
    return o


WALL_Y = 5.0      # voorkant achterwand
H = 5.6           # hoogte ruimte
XL, XR = -9.0, 9.0

# vloer en plafond
box("vloer", XL, XR, -9, WALL_Y + 1, -0.1, 0.0, M_FLOOR)
# geen plafond: het daglicht valt van rechtsboven binnen (buiten beeld)

# achterwand, met een opening voor de nis
NX0, NX1 = -0.45, 7.2       # nis: horizontaal
NZ0, NZ1 = 0.55, 4.3        # nis: verticaal
ND = 0.55                   # nisdiepte
box("wand-links", XL, NX0, WALL_Y, WALL_Y + ND, 0, H, M_WALL)
box("wand-rechts", NX1, XR, WALL_Y, WALL_Y + ND, 0, H, M_WALL)
box("wand-onder-nis", NX0, NX1, WALL_Y, WALL_Y + ND, 0, NZ0, M_WALL)
box("wand-boven-nis", NX0, NX1, WALL_Y, WALL_Y + ND, NZ1, H, M_WALL)
# achterkant van de nis (de wanden hierboven vormen de zijkanten)
box("nis-achter", XL, XR, WALL_Y + ND, WALL_Y + ND + 0.2, 0, H, M_NICHE)

# magenta lichtlijn langs de onderrand van de nis
box("lichtlijn", NX0, NX1, WALL_Y + 0.03, WALL_Y + 0.09, NZ0, NZ0 + 0.045, M_LINE)

# cirkelmotief in de nis, als zacht reliëf
disc("cirkel-groot", 5.6, WALL_Y + ND - 0.02, 2.75, 1.85, 0.04, M_CIRCLE_SKY)
disc("cirkel-klein", 6.6, WALL_Y + ND - 0.06, 1.65, 1.2, 0.04, M_CIRCLE_YEL)

# plint
box("plint", XL, NX0, WALL_Y - 0.02, WALL_Y, 0, 0.08, M_PLINT)
box("plint-r", NX1, XR, WALL_Y - 0.02, WALL_Y, 0, 0.08, M_PLINT)

# lamellen links
x = -6.9
while x < -3.0:
    box(f"lamel{x:.2f}", x, x + 0.16, WALL_Y - 0.16, WALL_Y, 0, H, M_SLAT)
    x += 0.42

# zuil tussen lamellen en nis
box("zuil", -2.35, -1.45, WALL_Y - 0.9, WALL_Y, 0, H, M_COLUMN)

# zijwanden
box("zijwand-l", XL - 0.1, XL, -9, WALL_Y + 1, 0, H, M_WALL)
# rechts geen zijwand: daar valt het zonlicht binnen (buiten beeld)


# ---------- Licht ----------
def area(name, loc, rot_deg, size_x, size_y, power, kelvin_rgb):
    bpy.ops.object.light_add(type="AREA", location=loc,
                             rotation=tuple(math.radians(a) for a in rot_deg))
    l = bpy.context.active_object
    l.name = name
    l.data.shape = "RECTANGLE"
    l.data.size = size_x
    l.data.size_y = size_y
    l.data.energy = power
    l.data.color = kelvin_rgb
    return l


# hoofdlicht: groot en zacht, van rechtsboven-voor (passend bij de panelen rechts)
area("hoofdlicht", (7.5, -0.5, 4.6), (62, 0, 62), 2.2, 1.4, 700, (1.0, 0.96, 0.91))
# lichtstrook in het plafond boven de nis
area("plafondstrook", (3.2, 3.6, H - 0.05), (0, 0, 0), 8.0, 0.6, 200, (0.96, 0.98, 1.0))
# zachte vullicht vanachter de camera
area("vullicht", (-2.0, -8.5, 2.6), (90, 0, 0), 8.0, 3.0, 160, (0.95, 0.97, 1.0))

# zonlicht van rechts, alsof er buiten beeld een groot raam is: geeft echte schaduwen
bpy.ops.object.light_add(type="SUN", rotation=(math.radians(55), 0, math.radians(48)))
zon = bpy.context.active_object
zon.data.energy = 4.0
zon.data.angle = math.radians(2.5)
zon.data.color = (1.0, 0.95, 0.88)

world = bpy.data.worlds.new("wereld")
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = hex_rgba("#eef3f8")
bg.inputs["Strength"].default_value = 0.22


# ---------- Camera ----------
bpy.ops.object.camera_add(location=(0.0, -7.0, 1.55), rotation=(math.radians(90), 0, 0))
cam = bpy.context.active_object
cam.data.lens = 32
cam.data.sensor_width = 36
cam.data.shift_y = -0.02
scene.camera = cam


# ---------- Panelen: enkel schaduw, onzichtbaar voor camera en spiegelingen ----------
import json
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

if MET_PANELEN:
    M_P = mat_basic("paneel", hex_rgba("#ffffff"), rough=0.6)
    for i, px in enumerate(PANEEL_X):
        o = box(f"paneel{i+1}", px - PANEEL_B / 2, px + PANEEL_B / 2, PANEEL_Y - 0.02, PANEEL_Y + 0.02,
                PANEEL_Z0, PANEEL_Z0 + PANEEL_H, M_P)
        o.visible_camera = False
        o.visible_glossy = False
        o.visible_diffuse = False

# pixelposities van de paneelhoeken, voor de HyperFrames-compositie
bpy.context.view_layer.update()
hoeken = []
for px in PANEEL_X:
    pts = []
    for (x, z) in [(px - PANEEL_B / 2, PANEEL_Z0 + PANEEL_H), (px + PANEEL_B / 2, PANEEL_Z0),
                   (px - PANEEL_B / 2, 0.0), (px + PANEEL_B / 2, 0.0)]:
        v = world_to_camera_view(scene, cam, Vector((x, PANEEL_Y, z)))
        pts.append([round(v.x * 1920, 1), round((1 - v.y) * 1080, 1)])
    hoeken.append({"links_boven": pts[0], "rechts_onder": pts[1], "vloer_links": pts[2], "vloer_rechts": pts[3]})
print("PANELEN", json.dumps(hoeken))

# ---------- Render ----------
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = SAMPLES
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 8
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.resolution_percentage = 100
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.view_settings.exposure = -0.8
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print("Klaar:", OUT)
