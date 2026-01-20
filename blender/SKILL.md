---
name: blender
description: Control Blender via Python. Run arbitrary Python/bpy code in a running Blender instance to inspect, create, modify scenes and objects.
---

# Blender Skill

Execute arbitrary Python code in a running Blender instance via a lightweight bridge addon.

## Usage

```bash
# Run Python code in Blender
python3 .claude/skills/blender/blender_run.py -c 'print(bpy.context.scene.name)'

# Run from file
python3 .claude/skills/blender/blender_run.py -f script.py
```

## Examples

### Inspect scene hierarchy
```bash
python3 .claude/skills/blender/blender_run.py -c '
for obj in bpy.context.scene.objects:
    print(f"{obj.name} ({obj.type})")
'
```

### Create a cube with material
```bash
python3 .claude/skills/blender/blender_run.py -c '
bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
cube = bpy.context.active_object
cube.name = "MyCube"

mat = bpy.data.materials.new("RedMaterial")
mat.use_nodes = True
mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (1, 0, 0, 1)
cube.data.materials.append(mat)

print(f"Created {cube.name}")
'
```

### Modify all mesh objects
```bash
python3 .claude/skills/blender/blender_run.py -c '
for obj in bpy.data.objects:
    if obj.type == "MESH":
        obj.scale = (2, 2, 2)
        print(f"Scaled {obj.name}")
'
```

### Render editor viewport view
```bash
python3 .claude/skills/blender/blender_run.py -c '
bpy.context.scene.render.filepath = "/tmp/render.png"
bpy.ops.render.opengl(write_still=True)
print("Rendered to /tmp/render.png")
'
```

### Render from specific camera angle
```bash
python3 .claude/skills/blender/blender_run.py -c '
import math

# Create or get camera
if "Camera" in bpy.data.objects:
    camera = bpy.data.objects["Camera"]
else:
    bpy.ops.object.camera_add()
    camera = bpy.context.active_object

# Position camera at specific angle (e.g., 45 degrees elevated, looking at origin)
camera.location = (7, -7, 5)
camera.rotation_euler = (math.radians(60), 0, math.radians(45))

# Set as active camera and render
bpy.context.scene.camera = camera
bpy.context.scene.render.filepath = "/tmp/camera_render.png"
bpy.ops.render.render(write_still=True)
print(f"Rendered from camera at {camera.location[:]} to /tmp/camera_render.png")
'
```

### Delete objects by pattern
```bash
python3 .claude/skills/blender/blender_run.py -c '
import re
count = 0
for obj in list(bpy.data.objects):
    if re.match(r"Cube\.\d+", obj.name):
        bpy.data.objects.remove(obj)
        count += 1
print(f"Deleted {count} objects")
'
```

### Get object properties
```bash
python3 .claude/skills/blender/blender_run.py -c '
obj = bpy.context.active_object
if obj:
    print(f"Name: {obj.name}")
    print(f"Type: {obj.type}")
    print(f"Location: {obj.location[:]}")
    print(f"Rotation: {obj.rotation_euler[:]}")
    print(f"Scale: {obj.scale[:]}")
else:
    print("No active object")
'
```
