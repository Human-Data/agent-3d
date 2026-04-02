---
name: solidworks
description: Control SolidWorks via its COM API from Python. Run arbitrary Python against a running SolidWorks (Windows) to inspect, create and modify parts, assemblies and drawings.
---

# SolidWorks Skill

Run Python against the running SolidWorks (COM via pywin32). `print()` output comes back; on error you get exit code 1, the script traceback and a `hint:`.

```bash
python ~/.claude/skills/solidworks/sw_run.py <<'EOF'
print(swApp.RevisionNumber(), model.GetTitle() if model else "no document open")
EOF
```

One-liners: `sw_run.py 'print(model.GetPathName())'` · files: `sw_run.py < script.py` · 60s timeout, `SW_RUN_TIMEOUT=600` for big opens/rebuilds.

Globals: `swApp` (ISldWorks) · `model` (ActiveDoc at start, `None` if nothing open) · `swconst` (every enum: `swconst.swDocPART`) · `api(q)` · `byref(v)` · `NOTHING` · `arr(seq)`.

## Rules

- Write calls exactly like the VBA API help: methods `()`, properties no `()`, **every argument required**. Look up signatures offline: `api("IModelDocExtension")` lists an interface, `api("extrusion")` searches members + enums. Interface = `I` + what you hold (`IFeature`, `IFace2`, `IComponent2`, `ISketchManager`); PartDoc/AssemblyDoc/DrawingDoc members work directly on `model`.
- **Units are SI always**: meters, radians, kg — whatever the document shows.
- ByRef/out: `e = byref(0)`, pass `e`, read `e.value`. VBA `Nothing` → `NOTHING`. Array args → `arr([x, y, z])`. Arrays come back as tuples (`None` when empty).
- Failures usually return `None`/`False`/an error code instead of raising: check returns.
- Features and edit commands act on the **selection**: `model.ClearSelection2(True)`, select, then call.
- `model` isn't refreshed: re-read `swApp.ActiveDoc` after open/new/activate. Each run is a fresh process; only SolidWorks state persists.
- A modal dialog in SolidWorks blocks every call until the timeout — ask the user to close it.

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

Geometry:
```python
mp = model.Extension.CreateMassProperty()
print(mp.Mass, mp.Volume, mp.SurfaceArea, mp.CenterOfMass)                  # kg, m3, m2, m
print(model.GetPartBox(True) if model.GetType() == 1 else model.GetBox(0))  # x1,y1,z1,x2,y2,z2
for b in model.GetBodies2(swconst.swSolidBody, True) or (): print(b.Name, len(b.GetFaces()), "faces")
```

Assembly components (`False` = all levels; translation in m):
```python
for c in model.GetComponents(False) or ():
    t = c.Transform2
    print(c.Name2, c.ReferencedConfiguration, c.IsSuppressed(), t.ArrayData[9:12] if t else None, c.GetPathName())
```

What the user selected:
```python
sm = model.SelectionManager
for i in range(1, sm.GetSelectedObjectCount2(-1) + 1):
    print(sm.GetSelectedObjectType3(i, -1), sm.GetSelectionPoint2(i, -1))   # decode: api("swSelectType_e")
obj = sm.GetSelectedObject6(1, -1)                                           # IFace2 / IEdge / IFeature / IComponent2 ...
```

Custom properties: `cpm = model.Extension.CustomPropertyManager("")` (`""` = file, or a config name) → `cpm.GetNames()`, `cpm.Get(name)`.

Look — render the view, then Read the PNG (works for drawings too):
```python
import os; p = os.path.join(os.environ["TEMP"], "sw_view.png")
model.ShowNamedView2("*Isometric", 7); model.ViewZoomtofit2()
e, w = byref(0), byref(0)
print(model.Extension.SaveAs(p, 0, 3, NOTHING, e, w), e.value, p)   # 3 = silent|copy
```

## Act

New part → sketch → extrude:
```python
m = swApp.NewDocument(swApp.GetUserPreferenceStringValue(swconst.swDefaultTemplatePart), 0, 0, 0)
m.Extension.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, NOTHING, 0)
sk = m.SketchManager; sk.AddToDB = True              # no snapping to nearby geometry
sk.InsertSketch(True)                                # open a sketch on the selected plane
sk.CreateCenterRectangle(0, 0, 0, 0.05, 0.025, 0)    # center, corner
sk.CreateCircleByRadius(0, 0, 0, 0.01)
sk.InsertSketch(True)                                # close it
m.ClearSelection2(True); m.FeatureByPositionReverse(0).Select2(False, 0)   # select the new sketch
f = m.FeatureManager.FeatureExtrusion2(True, False, False, swconst.swEndCondBlind, 0, 0.02, 0, False, False,
        False, False, 0, 0, False, False, False, False, True, True, True, 0, 0, False)
print(f.Name if f else "extrude failed")
```

Edit:
```python
model.Parameter("D1@Boss-Extrude1").SystemValue = 0.03; model.EditRebuild3()
model.Extension.SelectByID2("Fillet1", "BODYFEATURE", 0, 0, 0, False, 0, NOTHING, 0); model.EditSuppress2()  # / EditUnsuppress2 / EditDelete
model.Extension.SelectByID2("", "FACE", 0.01, 0.02, 0, False, 0, NOTHING, 0)   # entity by a point on it
model.EditUndo2(1)
```
SelectByID2 types: `PLANE FACE EDGE VERTEX SKETCH SKETCHSEGMENT BODYFEATURE COMPONENT ("Part1-1@Assem1") DIMENSION DRAWINGVIEW`.

Files:
```python
e, w = byref(0), byref(0)
m = swApp.OpenDoc6(r"C:\p\part.SLDPRT", swconst.swDocPART, swconst.swOpenDocOptions_Silent, "", e, w)   # None → e.value
model.Save3(swconst.swSaveAsOptions_Silent, e, w)
model.Extension.SaveAs(r"C:\p\part.step", 0, 3, NOTHING, e, w)    # format from extension: step stl x_t pdf dxf png
swApp.CloseDoc(model.GetTitle())
```

Assemblies: `AddComponent5` (open the file first), mates via `AddMate5` on the selected pair. Drawings: `CreateDrawViewFromModelView3`. Signatures: `api(...)`.

## Setup

Windows only: native Windows Python (not WSL) + `python -m pip install pywin32`. Start SolidWorks first; `sw_run.py` attaches to the running instance and never launches one. The first run indexes SolidWorks' type library into `%TEMP%\sw_run_cache` (a few seconds). That index is what makes `()`, `swconst` and `api()` work.
