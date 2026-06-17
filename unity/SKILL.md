
---
name: unity
Control Unity Editor through scripts/unity.sh
---

## run

Run an arbitrary C# script inside the Editor.
This is your super power and the most important command. The script runs in the Editor context, so it can do anything an Editor script can do — including accessing the scene, assets, Editor APIs, components, game objects, etc.

```bash
{SKILL_DIR}/scripts/unity.sh run <<'EOF'
using UnityEngine;
internal class C : IRunCommand
{
    public void Execute()
    {
        char grade = 'A';                       // single quotes inside the heredoc are fine
        Debug.Log($"grade is '{grade}'");
    }
}
EOF
```
or path to a .cs file: `{SKILL_DIR}/scripts/unity.sh run /tmp/...path_to_script.cs`

## Editor windows

Open or focus a window, or open an asset in its registered editor (`.uxml` → UI Builder). Short type names get the `UnityEditor.` prefix automatically.

```bash
{SKILL_DIR}/scripts/unity.sh editor-window-open SceneView                   # focus existing, else create
{SKILL_DIR}/scripts/unity.sh editor-window-open --new GameView              # force a new instance (--rect x,y,w,h to size)
{SKILL_DIR}/scripts/unity.sh editor-window-open --asset Assets/TitleBar.uxml
```

Capture an open window to a PNG at full retina res (writes to /tmp and prints the path):

```bash
{SKILL_DIR}/scripts/unity.sh editor-window-capture GameView                 # e.g. SceneView, GameView, InspectorWindow, ConsoleWindow
```

## Other Commands
Fetch console log entries (optional max count, default 100; `<=0` = no limit)
```bash
{SKILL_DIR}/scripts/unity.sh log get
{SKILL_DIR}/scripts/unity.sh log get 50 # (latest 50 entries)
```

Clear the Editor console.
```bash
{SKILL_DIR}/scripts/unity.sh log clear
```

Play / Pause / Stop for play-mode control

```bash
{SKILL_DIR}/scripts/unity.sh editor play
{SKILL_DIR}/scripts/unity.sh editor pause
{SKILL_DIR}/scripts/unity.sh editor stop
{SKILL_DIR}/scripts/unity.sh editor state
```

Reimport assets
```bash
{SKILL_DIR}/scripts/unity.sh asset reimport
```
IMPORTANT: use `asset reimport` before you verify changes after some assets changes.

Build players.
```bash
{SKILL_DIR}/scripts/unity.sh build --target iOS
{SKILL_DIR}/scripts/unity.sh build --target iOS --device --output /tmp/mybuild
```

## Best Practices

### Print a scene hierarchy (GameObject tree + component names)

```bash
{SKILL_DIR}/scripts/unity.sh run <<'EOF'
using System.IO;
using System.Text;
using UnityEngine;
using UnityEngine.SceneManagement;

internal class DumpHierarchy : IRunCommand
{
    public void Execute()
    {
        var sb = new StringBuilder();
        for (int i = 0; i < SceneManager.sceneCount; i++)
        {
            var scene = SceneManager.GetSceneAt(i);
            sb.AppendLine($"Scene '{scene.name}'");
            foreach (var root in scene.GetRootGameObjects())
                Dump(root.transform, 1, sb);
        }
        File.WriteAllText("/tmp/unity-hierarchy.txt", sb.ToString());
    }

    static void Dump(Transform t, int depth, StringBuilder sb)
    {
        var pad = new string(' ', depth * 2);
        var go = t.gameObject;
        sb.AppendLine($"{pad}{go.name}{(go.activeSelf ? "" : " (inactive)")}");
        foreach (var c in go.GetComponents<Component>())     // components: names only
            sb.AppendLine($"{pad}  <{(c == null ? "Missing Script" : c.GetType().Name)}>");
        for (int i = 0; i < t.childCount; i++)
            Dump(t.GetChild(i), depth + 1, sb);
    }
}
EOF
cat /tmp/unity-hierarchy.txt
```

### Preview a UXML (UI Toolkit)

After editing a `.uxml`:

```bash
{SKILL_DIR}/scripts/unity.sh asset reimport                                   # pick up the edit
{SKILL_DIR}/scripts/unity.sh editor-window-open --asset Assets/TitleBar.uxml  # opens UI Builder
{SKILL_DIR}/scripts/unity.sh editor-window-capture Unity.UI.Builder.Builder   # screenshot
```
