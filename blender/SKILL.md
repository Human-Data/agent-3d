---
name: blender
description: Control Blender via Python. Run arbitrary Python/bpy code in a running Blender instance to inspect, create, modify scenes and objects.
---

# Blender Skill

Execute Python code in a running Blender instance. `bpy` is available; `print()` output comes back to you.

## Usage

Pipe code via stdin — heredocs are the natural way to send multi-line scripts (no shell-escaping issues):

```bash
python3 ~/.claude/skills/blender/blender_run.py <<'EOF'
for obj in bpy.context.scene.objects:
    print(f"{obj.name} ({obj.type})")
EOF
```

One-liners can be passed as a single argument:

```bash
python3 ~/.claude/skills/blender/blender_run.py 'print(bpy.context.scene.name)'
```

Files work via redirection: `blender_run.py < script.py`.

Exit code is 0 on success, 1 if the code raised (traceback is printed). Long operations (e.g. renders) can raise the 30s default timeout with `BLENDER_RUN_TIMEOUT=120`.

## Examples

### Create a cube with material
```bash
python3 ~/.claude/skills/blender/blender_run.py <<'EOF'
bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
cube = bpy.context.active_object
cube.name = "MyCube"

mat = bpy.data.materials.new("RedMaterial")
mat.use_nodes = True
mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (1, 0, 0, 1)
cube.data.materials.append(mat)

print(f"Created {cube.name}")
EOF
```

### Render viewport / camera

```bash
python3 ~/.claude/skills/blender/blender_run.py <<'EOF'
bpy.context.scene.render.filepath = "/tmp/render.png"
bpy.ops.render.opengl(write_still=True)   # viewport; use bpy.ops.render.render for camera
print("Rendered to /tmp/render.png")
EOF
```

Then Read /tmp/render.png to see the result.

## Setup (once per Blender version)

If `blender_run.py` times out, install + enable the bridge addon programmatically:

```bash
bash ~/.claude/skills/blender/install.sh
```

An already-running Blender only picks the addon up after a restart. Manual fallback: copy `blender_bridge.py` into `~/Library/Application Support/Blender/<version>/scripts/addons/`, then in Blender's Python console run `bpy.ops.preferences.addon_enable(module="blender_bridge"); bpy.ops.wm.save_userpref()`.
