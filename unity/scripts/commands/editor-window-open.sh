cmd_editor-window-open() {
    local mode="get" rect=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --new)   mode="new";   shift;;
            --asset) mode="asset"; shift;;
            --rect)  [[ $# -ge 2 ]] || { echo "error: --rect needs x,y,w,h" >&2; exit 2; }
                     rect="$2"; shift 2;;
            -*)      echo "error: unknown flag '$1'" >&2; exit 2;;
            *)       break;;
        esac
    done

    local target="${1:-}"
    local rx=100 ry=100 rw=1280 rh=720 has_rect=false

    if [[ "$mode" == "asset" ]]; then
        [[ -n "$target" ]] || { echo "error: --asset needs an asset path (e.g. Assets/Foo.uxml)" >&2; exit 2; }
    else
        target="${target:-SceneView}"
        [[ "$target" == *.* ]] || target="UnityEditor.$target"   # short name -> UnityEditor.<name>
        if [[ -n "$rect" ]]; then
            IFS=',' read -r rx ry rw rh <<< "$rect"; has_rect=true
        elif [[ "$mode" == "new" ]]; then
            has_rect=true       # give a fresh window a usable default size, not the tiny built-in one
        fi
    fi

    local src
    src="$(cat <<'CSHARP'
using System;
using System.Linq;
using UnityEngine;
using UnityEditor;

internal class OpenWindowCmd : IRunCommand
{
    const string MODE     = "__MODE__";     // get | new | asset
    const string TARGET   = "__TARGET__";   // window type name (get/new), or asset path (asset)
    const bool   HAS_RECT = __HAS_RECT__;
    static readonly Rect RECT = new Rect(__RX__, __RY__, __RW__, __RH__);

    static Type Resolve(string name)
    {
        var ed = typeof(Editor).Assembly;
        return ed.GetType(name) ?? AppDomain.CurrentDomain.GetAssemblies()
            .Select(a => a.GetType(name)).FirstOrDefault(t => t != null);
    }

    public void Execute()
    {
        if (MODE == "asset")
        {
            var obj = AssetDatabase.LoadAssetAtPath<UnityEngine.Object>(TARGET);
            if (obj == null) throw new Exception("asset not found: " + TARGET);
            bool ok = AssetDatabase.OpenAsset(obj);   // routes to whatever editor is registered for that asset type
            // plain string concatenation here keeps the bash 3.2 heredoc parser happy; see note above
            Debug.Log("[editor-window-open] OpenAsset " + TARGET + " -> " + ok + " type=" + obj.GetType().Name);
            return;
        }

        var type = Resolve(TARGET);
        if (type == null) throw new Exception("window type not found: " + TARGET);
        if (!typeof(EditorWindow).IsAssignableFrom(type)) throw new Exception(TARGET + " is not an EditorWindow");

        EditorWindow w;
        if (MODE == "new")
        {
            w = (EditorWindow)ScriptableObject.CreateInstance(type);   // always a brand-new instance
            w.Show();
            if (HAS_RECT) w.position = RECT;   // set size AFTER Show(), else Show() overrides it
            w.Focus();
        }
        else
        {
            w = EditorWindow.GetWindow(type, false, null, true);       // focus existing, else create one
            if (HAS_RECT) w.position = RECT;
        }

        int total = Resources.FindObjectsOfTypeAll(type).Length;
#if UNITY_6000_5_OR_NEWER
        var id = w.GetEntityId();
#else
        var id = w.GetInstanceID();
#endif
        Debug.Log("[editor-window-open] " + type.FullName + "  mode=" + MODE +
                  " id=" + id + " pos=" + w.position + " total=" + total);
    }
}
CSHARP
)"
    src="${src//__MODE__/$mode}"
    src="${src//__TARGET__/$target}"
    src="${src//__HAS_RECT__/$has_rect}"
    src="${src//__RX__/$rx}"
    src="${src//__RY__/$ry}"
    src="${src//__RW__/$rw}"
    src="${src//__RH__/$rh}"

    local reply; reply="$(cmd_run "$src")"
    printf '%s\n' "$reply"
    if [[ "$reply" == OK:* ]]; then
        if [[ "$mode" == "asset" ]]; then >&2 echo "Opened asset in its editor: $target"
        else                              >&2 echo "Opened window ($mode): $target"; fi
    fi
}
