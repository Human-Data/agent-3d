cmd_editor-window-capture() {
    local win="${1:-UnityEditor.SceneView}"
    [[ "$win" == *.* ]] || win="UnityEditor.$win"
    local short="${win##*.}"                          # UnityEditor.SceneView -> SceneView
    local rand; printf -v rand '%04x%04x' "$RANDOM" "$RANDOM"
    local out="/tmp/${short}-capture-${rand}.png"

    local src
    src="$(cat <<'CSHARP'
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using UnityEngine;
using UnityEditor;

internal class CaptureWindowCmd : IRunCommand
{
    const string WINDOW_TYPE = "__WINDOW_TYPE__";
    const string OUTPUT_PATH = "__OUTPUT_PATH__";

    public void Execute()
    {
        var editorAsm   = typeof(EditorWindow).Assembly;
        var guiViewType = editorAsm.GetType("UnityEditor.GUIView");
        var parentField = typeof(EditorWindow).GetField("m_Parent", BindingFlags.NonPublic | BindingFlags.Instance);
        var grabPixels  = guiViewType.GetMethod("GrabPixels", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
        var repaintNow  = guiViewType.GetMethod("RepaintImmediately", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);

        var type = editorAsm.GetType(WINDOW_TYPE)
                   ?? AppDomain.CurrentDomain.GetAssemblies().Select(a => a.GetType(WINDOW_TYPE)).FirstOrDefault(t => t != null);
        if (type == null) throw new Exception("window type not found: " + WINDOW_TYPE);

        var window = Resources.FindObjectsOfTypeAll(type).OfType<EditorWindow>().FirstOrDefault();
        if (window == null) throw new Exception("no open instance of " + WINDOW_TYPE + " (open/focus it first)");

        var parent = parentField.GetValue(window);
        if (parent == null) throw new Exception(window.GetType().Name + " has no host view (not docked/visible)");

        Type hostViewType = editorAsm.GetType("UnityEditor.HostView");
        PropertyInfo actualViewProp = null;
        if (hostViewType != null)
            actualViewProp = hostViewType.GetProperty("actualView", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
        if (actualViewProp != null)
        {
            var active = actualViewProp.GetValue(parent) as EditorWindow;
            if (active != null && active != window)
                window.Focus();
        }

        float ppp = EditorGUIUtility.pixelsPerPoint;
        int w = Mathf.Max(1, Mathf.RoundToInt(window.position.width  * ppp));
        int h = Mathf.Max(1, Mathf.RoundToInt(window.position.height * ppp));

        var rt = new RenderTexture(w, h, 24, RenderTextureFormat.ARGB32) { antiAliasing = 1 };
        rt.Create();
        var prevActive = RenderTexture.active;
        Texture2D tex = null;
        try
        {
            repaintNow.Invoke(parent, null);                                       // fresh paint into the backing store
            grabPixels.Invoke(parent, new object[] { rt, new Rect(0, 0, w, h) });  // rect in PIXELS (points -> only top-left quarter on 2x)

            RenderTexture.active = rt;
            tex = new Texture2D(w, h, TextureFormat.RGBA32, false);
            tex.ReadPixels(new Rect(0, 0, w, h), 0, 0);
            tex.Apply();
            RenderTexture.active = prevActive;

            // GrabPixels uses a bottom-left origin -> flip vertically to upright.
            var srcPx = tex.GetPixels32();
            var dstPx = new Color32[srcPx.Length];
            for (int y = 0; y < h; y++) Array.Copy(srcPx, y * w, dstPx, (h - 1 - y) * w, w);
            tex.SetPixels32(dstPx);
            tex.Apply();

            var dir = Path.GetDirectoryName(OUTPUT_PATH);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            File.WriteAllBytes(OUTPUT_PATH, tex.EncodeToPNG());
            Debug.Log($"[editor-window-capture] {window.GetType().FullName} -> {OUTPUT_PATH} ({w}x{h})");
        }
        finally
        {
            RenderTexture.active = prevActive;
            if (tex != null) UnityEngine.Object.DestroyImmediate(tex);
            rt.Release();
            UnityEngine.Object.DestroyImmediate(rt);
        }
    }
}
CSHARP
)"
    src="${src//__WINDOW_TYPE__/$win}"
    src="${src//__OUTPUT_PATH__/$out}"

    local reply; reply="$(cmd_run "$src")"
    printf '%s\n' "$reply"
    if [[ "$reply" == OK:* ]]; then
        >&2 echo "Captured editor window $win: $out"
    fi
}
