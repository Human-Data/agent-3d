---
name: solidworks
description: Control SolidWorks via its COM API from Python. Run arbitrary Python against a running SolidWorks (Windows) to inspect, create and modify parts, assemblies and drawings.
---

# SolidWorks Skill

Run Python against the running SolidWorks (COM via pywin32). `print()` output comes back; on error you get exit code 1 and the script traceback.

```bash
python ~/.claude/skills/solidworks/sw_run.py <<'EOF'
print(swApp.RevisionNumber(), model.GetTitle() if model else "no document open")
EOF
```

One-liners: `sw_run.py 'print(model.GetPathName())'` · files: `sw_run.py < script.py`.

Globals: `swApp` (ISldWorks) · `model` (ActiveDoc at start, `None` if nothing open) · `swconst` (every enum: `swconst.swDocPART`) · `api(q)` · `byref(v)` · `NOTHING` · `arr(seq)`.

## Rules

- Write calls exactly like the VBA API help: methods `()`, properties no `()`, **every argument required**. Look up signatures offline: `api("IModelDocExtension")` lists an interface, `api("extrusion")` searches members + enums. Interface = `I` + what you hold (`IFeature`, `IFace2`, `IComponent2`, `ISketchManager`); PartDoc/AssemblyDoc/DrawingDoc members work directly on `model`.
- **Units are SI always**: meters, radians, kg — whatever the document shows.
- ByRef/out: `e = byref(0)`, pass `e`, read `e.value`. VBA `Nothing` → `NOTHING`. Array args → `arr([x, y, z])`. Arrays come back as tuples (`None` when empty).
- Failures usually return `None`/`False`/an error code instead of raising: check returns.
- Features and edit commands act on the **selection**: `model.ClearSelection2(True)`, select, then call.
- `model` isn't refreshed: re-read `swApp.ActiveDoc` after open/new/activate. Each run is a fresh process; only SolidWorks state persists.

## Perceive

Documents:
```python
for d in swApp.GetDocuments() or (): print(d.GetType(), d.GetTitle(), d.GetPathName())   # 1 part 2 asm 3 drw
print(model.GetTitle(), model.ConfigurationManager.ActiveConfiguration.Name)
```

Feature tree + dimensions (`Name@Feature` is what `model.Parameter()` takes; folder/mate children: `f.GetFirstSubFeature()` / `s.GetNextSubFeature()`):
```python
f = model.FirstFeature()
while f:
    print(f"{f.Name} [{f.GetTypeName2()}]" + (" SUPPRESSED" if f.IsSuppressed() else ""))
    d = f.GetFirstDisplayDimension()
    while d:
        dim = d.GetDimension2(0); print(f"    {dim.Name}@{f.Name} = {dim.SystemValue}")
        d = f.GetNextDisplayDimension(d)
    f = f.GetNextFeature()
```

## Act

Edit:
```python
model.Parameter("D1@Boss-Extrude1").SystemValue = 0.03; model.EditRebuild3()
model.Extension.SelectByID2("Fillet1", "BODYFEATURE", 0, 0, 0, False, 0, NOTHING, 0); model.EditSuppress2()  # / EditUnsuppress2 / EditDelete
model.Extension.SelectByID2("", "FACE", 0.01, 0.02, 0, False, 0, NOTHING, 0)   # entity by a point on it
model.EditUndo2(1)
```
SelectByID2 types: `PLANE FACE EDGE VERTEX SKETCH SKETCHSEGMENT BODYFEATURE COMPONENT ("Part1-1@Assem1") DIMENSION DRAWINGVIEW`.
