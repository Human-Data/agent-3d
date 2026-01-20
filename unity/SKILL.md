---
name: unity
description: Control Unity Editor. Run C# code in batchmode to inspect, create, modify, or delete GameObjects, components, and properties.
---

# Unity Skill

Run arbitrary C# via `$SKILL_DIR/unity_run_cs.sh -c '<code>'` or `-f <file.cs>`.

## Examples

### Inspect scene hierarchy
```bash
$SKILL_DIR/unity_run_cs.sh -c '
var scene = UnityEngine.SceneManagement.SceneManager.GetActiveScene();
Debug.Log($"Scene: {scene.name}");
foreach (var root in scene.GetRootGameObjects()) {
    Debug.Log($"  {root.name} ({root.GetComponents<Component>().Length} components)");
    foreach (Transform child in root.transform)
        Debug.Log($"    - {child.name}");
}
'
```

### Create configured GameObject
```bash
$SKILL_DIR/unity_run_cs.sh -c '
var go = new GameObject("SpotLight");
var light = go.AddComponent<Light>();
light.type = LightType.Spot;
light.intensity = 2f;
light.range = 15f;
go.transform.position = new Vector3(0, 5, 0);
go.transform.rotation = Quaternion.Euler(90, 0, 0);
Debug.Log($"Created {go.name} at {go.transform.position}");
'
```

### Find and modify components
```bash
$SKILL_DIR/unity_run_cs.sh -c '
var cameras = Object.FindObjectsOfType<Camera>();
foreach (var cam in cameras) {
    cam.backgroundColor = Color.black;
    cam.fieldOfView = 75f;
    Debug.Log($"Updated camera: {cam.name}");
}
'
```

### Batch delete by pattern
```bash
$SKILL_DIR/unity_run_cs.sh -c '
var allObjects = Object.FindObjectsOfType<GameObject>();
int count = 0;
foreach (var go in allObjects) {
    if (go.name.StartsWith("Temp_")) {
        Object.DestroyImmediate(go);
        count++;
    }
}
Debug.Log($"Deleted {count} temporary objects");
'
```

### Inspect properties via reflection
```bash
$SKILL_DIR/unity_run_cs.sh -c '
var go = GameObject.Find("Main Camera");
if (go == null) { Debug.Log("Not found"); return; }
foreach (var comp in go.GetComponents<Component>()) {
    Debug.Log($"[{comp.GetType().Name}]");
    foreach (var prop in comp.GetType().GetProperties())
        try { Debug.Log($"  {prop.Name} = {prop.GetValue(comp)}"); } catch {}
}
'
```

### Capture Scene View screenshot
```bash
$SKILL_DIR/unity_run_cs.sh -c '
var view = UnityEditor.SceneView.lastActiveSceneView;
if (view == null) { Debug.LogError("No active Scene View"); return; }

var cam = view.camera;
var rt = RenderTexture.GetTemporary((int)view.position.width, (int)view.position.height, 24);
cam.targetTexture = rt;
cam.Render();
RenderTexture.active = rt;

var tex = new Texture2D(rt.width, rt.height, TextureFormat.RGB24, false);
tex.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
tex.Apply();

cam.targetTexture = null;
RenderTexture.active = null;
RenderTexture.ReleaseTemporary(rt);

System.IO.File.WriteAllBytes("/tmp/unity_sceneview.png", tex.EncodeToPNG());
Debug.Log("Screenshot saved: /tmp/unity_sceneview.png");
'
```

### Capture Game View screenshot
```bash
$SKILL_DIR/unity_run_cs.sh -c '
var gameViewType = typeof(UnityEditor.Editor).Assembly.GetType("UnityEditor.GameView");
var size = (Vector2)gameViewType.GetMethod("GetSizeOfMainGameView", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static).Invoke(null, null);
int width = (int)size.x, height = (int)size.y;
var rt = RenderTexture.GetTemporary(width, height, 24);
var cam = Camera.main;
var prevRT = cam.targetTexture;
cam.targetTexture = rt;
cam.Render();
RenderTexture.active = rt;
var tex = new Texture2D(width, height, TextureFormat.RGB24, false);
tex.ReadPixels(new Rect(0, 0, width, height), 0, 0);
tex.Apply();
cam.targetTexture = prevRT;
RenderTexture.ReleaseTemporary(rt);
System.IO.File.WriteAllBytes("/tmp/unity_gameview.png", tex.EncodeToPNG());
UnityEngine.Object.DestroyImmediate(tex);
return $"Saved {width}x{height}";
'
```
