---
name: unity
description: Control Unity Editor. Run C# code in batchmode to inspect, create, modify, or delete GameObjects, components, and properties.
---


## First-Time Setup (one time)

Copy `$SKILL_DIR/CodeExecutor.cs` to your Unity project's `Assets/Editor/` folder. Unity will auto-compile it.

```bash
cp $SKILL_DIR/CodeExecutor.cs <your-project>/Assets/Editor/
```

# Unity Skill

Run arbitrary C# via:
- **Heredoc (preferred)**: `$SKILL_DIR/unity_run_cs.sh <<'EOF' ... EOF` - Zero escaping issues!
- **File**: `$SKILL_DIR/unity_run_cs.sh -f <file.cs>`

The CodeExecutor:
- Watches `~/.unity_code_executor/input.cs` for code to execute
- Logs are captured directly from Unity's Editor.log at `~/Library/Logs/Unity/Editor.log`

## Screenshot Editor Tabs
```bash
$SKILL_DIR/unity_screenshot_tab.sh <tab> [output_path]
```
Tabs: `hierarchy`, `inspector`, `project`, `console`, `scene`, `game`, `animation`, `animator`, `profiler`

## Examples

### Inspect scene hierarchy
```bash
$SKILL_DIR/unity_run_cs.sh <<'EOF'
var scene = UnityEngine.SceneManagement.SceneManager.GetActiveScene();
Debug.Log($"Scene: {scene.name}");
foreach (var root in scene.GetRootGameObjects()) {
    Debug.Log($"  {root.name} ({root.GetComponents<Component>().Length} components)");
    foreach (Transform child in root.transform)
        Debug.Log($"    - {child.name}");
}
EOF
```

### Create configured GameObject
```bash
$SKILL_DIR/unity_run_cs.sh <<'EOF'
var go = new GameObject("SpotLight");
var light = go.AddComponent<Light>();
light.type = LightType.Spot;
light.intensity = 2f;
light.range = 15f;
go.transform.position = new Vector3(0, 5, 0);
go.transform.rotation = Quaternion.Euler(90, 0, 0);
Debug.Log($"Created {go.name} at {go.transform.position}");
EOF
```

### Find and modify components
```bash
$SKILL_DIR/unity_run_cs.sh <<'EOF'
var cameras = Object.FindObjectsOfType<Camera>();
foreach (var cam in cameras) {
    cam.backgroundColor = Color.black;
    cam.fieldOfView = 75f;
    Debug.Log($"Updated camera: {cam.name}");
}
EOF
```

### Batch delete by pattern
```bash
$SKILL_DIR/unity_run_cs.sh <<'EOF'
var allObjects = Object.FindObjectsOfType<GameObject>();
int count = 0;
foreach (var go in allObjects) {
    if (go.name.StartsWith("Temp_")) {
        Object.DestroyImmediate(go);
        count++;
    }
}
Debug.Log($"Deleted {count} temporary objects");
EOF
```

### Inspect properties via reflection
```bash
$SKILL_DIR/unity_run_cs.sh <<'EOF'
var go = GameObject.Find("Main Camera");
if (go == null) { Debug.Log("Not found"); return; }
foreach (var comp in go.GetComponents<Component>()) {
    Debug.Log($"[{comp.GetType().Name}]");
    foreach (var prop in comp.GetType().GetProperties())
        try { Debug.Log($"  {prop.Name} = {prop.GetValue(comp)}"); } catch {}
}
EOF
```


### Capture Game View screenshot
```bash
$SKILL_DIR/unity_screenshot_tab.sh game /tmp/unity_gameview.png
```
