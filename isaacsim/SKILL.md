---
name: isaacsim
description: Control NVIDIA Isaac Sim via Python. Run arbitrary Python (USD/pxr, omni, isaacsim APIs, top-level await) inside a running Isaac Sim to inspect and edit scenes, simulate physics and drive robots.
---

# Isaac Sim Skill

Run Python inside a running Isaac Sim, on Kit's main thread between frames. `print()` output comes back. On error you get exit code 1, the traceback, and any Kit log errors raised during the run.

```bash
python3 ~/.claude/skills/isaacsim/isaac_run.py <<'EOF'
print(app.get_app_version(), stage.GetRootLayer().identifier)
EOF
```

One-liners as a single argument; files via `< script.py`. **Top-level `await` works**: use it whenever frames must pass. 60s timeout (`ISAAC_RUN_TIMEOUT=600`).

Globals: `stage` · `ctx` (omni.usd context) · `app` · `timeline` · `omni` `carb` `np` · `Usd UsdGeom UsdPhysics UsdShade UsdLux Sdf Gf Vt` · `await frames(n)` · `set_view(eye, target)` · `await screenshot(path=None)` · `shared` (dict kept between runs).

## Rules

- Z-up, meters (check `UsdGeom.GetStageUpAxis(stage)`, `UsdGeom.GetStageMetersPerUnit(stage)`). Quaternions `(w, x, y, z)`. USD joint limits/drive targets are **degrees**; Isaac articulation APIs are **radians**.
- Physics advances only while the timeline plays **and** frames pass: `timeline.play(); await frames(60)` ≈ 1 s. A long synchronous loop freezes the app — `await frames(1)` inside it.
- Isaac Python APIs change per version; check `app.get_app_version()` first. 6.x: `isaacsim.core.experimental.*`. 4.5–5.x: `isaacsim.core.prims` / `isaacsim.core.utils` (deprecated in 6.x). ≤4.2: `omni.isaac.core`. Discover instead of guessing: `print([n for n in dir(mod) if not n.startswith("_")])`, `help(obj.method)`. USD + `omni.usd`/`omni.timeline`/`omni.kit` are stable; prefer them for scene work.
- While simulating, read live state via physics APIs (below): USD attributes can lag (Fabric).
- `stage` is captured at run start: re-read `ctx.get_stage()` after opening/creating a stage. Physics handles die on `timeline.stop()`. Each run is a fresh namespace except `shared`.
- Raw USD edits aren't undoable; `omni.kit.commands.execute(...)` ones are (`omni.kit.undo.undo()`).

## Perceive

Overview:
```python
print(app.get_app_name(), app.get_app_version(), ctx.get_stage_url())
print(UsdGeom.GetStageUpAxis(stage), UsdGeom.GetStageMetersPerUnit(stage), timeline.is_playing(), timeline.get_current_time())
print("selected:", ctx.get_selection().get_selected_prim_paths())
```

Scene tree — type + applied schemas (`PhysicsRigidBodyAPI`, `PhysicsCollisionAPI`, `PhysicsArticulationRootAPI`…):
```python
it = iter(Usd.PrimRange(stage.GetPseudoRoot()))
for p in it:
    d = p.GetPath().pathElementCount
    if d > 4: it.PruneChildren(); continue
    print("  " * d + p.GetName(), p.GetTypeName(), p.GetAppliedSchemas() or "")
```

One prim:
```python
p = stage.GetPrimAtPath("/World/Box")
for a in p.GetAttributes():
    if a.HasAuthoredValue(): print(a.GetName(), a.Get())
print(omni.usd.get_world_transform_matrix(p).ExtractTranslation(), ctx.compute_path_world_bounding_box(str(p.GetPath())))
```

Robots and joints:
```python
for p in stage.Traverse():
    if p.HasAPI(UsdPhysics.ArticulationRootAPI): print("ARTICULATION", p.GetPath())
    elif p.IsA(UsdPhysics.Joint): print("  ", p.GetTypeName(), p.GetPath())
```

Live physics state (6.x; 4.5–5.x: `from isaacsim.core.prims import SingleArticulation` → `r = SingleArticulation(path); r.initialize(); r.get_joint_positions()`):
```python
from isaacsim.core.experimental.prims import Articulation
import isaacsim.core.experimental.utils.xform as xform_utils
timeline.play(); await frames(2)
r = Articulation("/World/franka")                         # path of the ARTICULATION root above
print(r.dof_names, r.get_dof_positions().numpy())
print([a.numpy() for a in xform_utils.get_world_pose("/World/Box")])   # position, quaternion wxyz
```

Available APIs and assets:
```python
import omni.client
em = app.get_extension_manager()
print(sorted(e["id"] for e in em.get_extensions() if e["enabled"] and "isaac" in e["id"]))   # enable: em.set_extension_enabled_immediate(name, True)
from isaacsim.storage.native import get_assets_root_path   # ≤4.2: omni.isaac.nucleus
root = get_assets_root_path(); print(root, [e.relative_path for e in omni.client.list(root + "/Isaac/Robots")[1]])
```

Look — then Read the PNG:
```python
set_view(eye=[2.5, 2.5, 1.8], target=[0, 0, 0.5])
print(await screenshot())   # <tmp>/isaac_view.png
```
Through a scene camera: `from omni.kit.viewport.utility import get_active_viewport; get_active_viewport().camera_path = "/World/Camera"`.

## Act

Physics scene with a falling box:
```python
UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
g = UsdGeom.Cube.Define(stage, "/World/Ground"); g.GetSizeAttr().Set(1.0)
UsdGeom.XformCommonAPI(g).SetTranslate(Gf.Vec3d(0, 0, -0.05)); UsdGeom.XformCommonAPI(g).SetScale(Gf.Vec3f(20, 20, 0.1))
UsdPhysics.CollisionAPI.Apply(g.GetPrim())                                   # collider only = static
b = UsdGeom.Cube.Define(stage, "/World/Box"); b.GetSizeAttr().Set(0.2); b.GetDisplayColorAttr().Set([(0.9, 0.2, 0.1)])
UsdGeom.XformCommonAPI(b).SetTranslate(Gf.Vec3d(0, 0, 1))
UsdPhysics.RigidBodyAPI.Apply(b.GetPrim()); UsdPhysics.CollisionAPI.Apply(b.GetPrim())
UsdLux.DistantLight.Define(stage, "/World/Sun").CreateIntensityAttr(3000)
timeline.play(); await frames(120); timeline.pause()
```

Robot (asset path from the listing above; 4.5: `/Isaac/Robots/Franka/franka.usd`, `isaacsim.core.utils.stage`):
```python
import isaacsim.core.experimental.utils.stage as stage_utils
from isaacsim.core.experimental.prims import Articulation
from isaacsim.storage.native import get_assets_root_path
stage_utils.add_reference_to_stage(get_assets_root_path() + "/Isaac/Robots/FrankaRobotics/FrankaPanda/franka.usd", "/World/franka")
timeline.play(); await frames(2)
r = Articulation("/World/franka")
r.set_dof_position_targets(np.array([[0, -0.6, 0, -2.2, 0, 1.6, 0.8, 0.04, 0.04]]))   # radians / meters
await frames(90); print(r.get_dof_positions().numpy().round(3))
```
Version-free joint drive: `UsdPhysics.DriveAPI.Get(stage.GetPrimAtPath(joint), "angular").GetTargetPositionAttr().Set(45.0)` (degrees; `"linear"` for prismatic).

Edit / files:
```python
import omni.kit.commands, omni.kit.undo
omni.kit.commands.execute("DeletePrims", paths=["/World/Box"]); omni.kit.undo.undo()
await ctx.open_stage_async("/path/scene.usd"); stage = ctx.get_stage()   # ctx.new_stage() · ctx.save_as_stage("/path/out.usd")
```

## Setup

Start the bridge inside Isaac Sim once per session (listens on 127.0.0.1:8723):
- At launch: `isaac-sim.sh --exec ~/.claude/skills/isaacsim/isaac_bridge.py` (Windows `isaac-sim.bat`; any Kit app takes `--exec`).
- Already open: Window → Script Editor → `exec(open("/abs/path/to/isaac_bridge.py").read())`.
- Autostart: add `~/.claude/skills/isaacsim/exts` to the Extension Manager search paths, then enable `claude_isaac_bridge` with Autoload (or launch with `--ext-folder <that dir> --enable claude_isaac_bridge`).
- If Isaac Sim's Python Server extension (`isaacsim.code_editor.python_server`, port 8226) is enabled, `isaac_run.py` starts the bridge through it automatically.
- Standalone `python.sh` scripts: exec the bridge after creating `SimulationApp` and keep calling `simulation_app.update()`.
- Docker: `--network=host`. Remote: `ssh -L 8723:127.0.0.1:8723 <host>`.
