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

Look — then Read the PNG:
```python
set_view(eye=[2.5, 2.5, 1.8], target=[0, 0, 0.5])
print(await screenshot())   # <tmp>/isaac_view.png
```
Through a scene camera: `from omni.kit.viewport.utility import get_active_viewport; get_active_viewport().camera_path = "/World/Camera"`.

## Act

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
