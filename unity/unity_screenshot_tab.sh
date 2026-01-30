#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNITY_RUN_CS="$SCRIPT_DIR/unity_run_cs.sh"

usage() {
    echo "Usage: $0 <tab_name> [output_path]"
    echo ""
    echo "Capture a screenshot of a Unity Editor tab/window."
    echo ""
    echo "Arguments:"
    echo "  tab_name     Name of the Unity tab (case-insensitive)"
    echo "  output_path  Optional output path (default: /tmp/unity_<tab>.png)"
    echo ""
    echo "Supported tabs:"
    echo "  hierarchy    - Scene Hierarchy window"
    echo "  inspector    - Inspector window"
    echo "  project      - Project Browser window"
    echo "  console      - Console window"
    echo "  scene        - Scene View"
    echo "  game         - Game View"
    echo "  animation    - Animation window"
    echo "  animator     - Animator window"
    echo "  profiler     - Profiler window"
    echo ""
    echo "Examples:"
    echo "  $0 hierarchy"
    echo "  $0 inspector /tmp/my_inspector.png"
    exit 1
}

if [ $# -lt 1 ]; then
    usage
fi

TAB_NAME=$(echo "$1" | tr '[:upper:]' '[:lower:]')
OUTPUT_PATH="${2:-/tmp/unity_${TAB_NAME}.png}"
BOUNDS_FILE="/tmp/unity_window_bounds_$$.txt"
TEMP_WINDOW_CAPTURE="/tmp/unity_window_full_$$.png"

# Map tab name to Unity Editor window type
case "$TAB_NAME" in
    hierarchy)
        WINDOW_TYPE="UnityEditor.SceneHierarchyWindow"
        ;;
    inspector)
        WINDOW_TYPE="UnityEditor.InspectorWindow"
        ;;
    project)
        WINDOW_TYPE="UnityEditor.ProjectBrowser"
        ;;
    console)
        WINDOW_TYPE="UnityEditor.ConsoleWindow"
        ;;
    scene)
        WINDOW_TYPE="UnityEditor.SceneView"
        ;;
    game)
        WINDOW_TYPE="UnityEditor.GameView"
        ;;
    animation)
        WINDOW_TYPE="UnityEditor.AnimationWindow"
        ;;
    animator)
        WINDOW_TYPE="UnityEditor.Graphs.AnimatorControllerTool"
        ;;
    profiler)
        WINDOW_TYPE="UnityEditor.ProfilerWindow"
        ;;
    *)
        echo "Error: Unknown tab name '$1'"
        echo ""
        usage
        ;;
esac

# Step 1: Get window bounds from Unity (no screen capture - this is safe)
# Returns: containerX,containerY,containerW,containerH,tabOffsetX,tabOffsetY,tabW,tabH
"$UNITY_RUN_CS" <<EOF
var windowType = typeof(UnityEditor.Editor).Assembly.GetType("$WINDOW_TYPE");
if (windowType == null) {
    Debug.LogError("Window type not found: $WINDOW_TYPE");
    return null;
}

var window = UnityEditor.EditorWindow.GetWindow(windowType, false, null, false);
if (window == null) {
    Debug.LogError("Could not get window: $TAB_NAME");
    return null;
}

// Focus and repaint
window.Focus();
window.Repaint();

// Get the DockArea (parent) and ContainerWindow for position calculation
var hostView = window.GetType().GetField("m_Parent", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)?.GetValue(window);
if (hostView == null) {
    Debug.LogError("Could not get parent DockArea");
    return null;
}

// Get ContainerWindow
var containerWindow = hostView.GetType().GetProperty("window", System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance)?.GetValue(hostView);
if (containerWindow == null) {
    Debug.LogError("Could not get ContainerWindow");
    return null;
}
Rect cwPos = (Rect)containerWindow.GetType().GetProperty("position")?.GetValue(containerWindow);

// Get DockArea screenPosition (relative to ContainerWindow)
var screenPosProp = hostView.GetType().GetProperty("screenPosition", System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
Rect dockRect = (Rect)screenPosProp.GetValue(hostView);

// Tab position relative to container window
float tabOffsetX = dockRect.x - cwPos.x;
float tabOffsetY = dockRect.y;  // dockRect.y is already relative
float tabWidth = dockRect.width;
float tabHeight = dockRect.height;

// Container window bounds (absolute screen position)
float containerX = cwPos.x;
float containerY = cwPos.y;
float containerW = cwPos.width;
float containerH = cwPos.height;

// Validate bounds
if (tabWidth <= 0 || tabHeight <= 0) {
    Debug.LogError("Invalid window size");
    return null;
}

// Write bounds to file: containerX,containerY,containerW,containerH,tabOffsetX,tabOffsetY,tabW,tabH
string boundsPath = "$BOUNDS_FILE";
string bounds = string.Format("{0},{1},{2},{3},{4},{5},{6},{7}",
    (int)containerX, (int)containerY, (int)containerW, (int)containerH,
    (int)tabOffsetX, (int)tabOffsetY, (int)tabWidth, (int)tabHeight);
System.IO.File.WriteAllText(boundsPath, bounds);

return "Bounds: " + bounds;
EOF

# Step 2: Check if bounds file was created
if [ ! -f "$BOUNDS_FILE" ]; then
    echo "Error: Failed to get window bounds from Unity"
    exit 1
fi

# Read bounds
BOUNDS=$(cat "$BOUNDS_FILE")
rm -f "$BOUNDS_FILE"

if [ -z "$BOUNDS" ]; then
    echo "Error: Empty bounds returned"
    exit 1
fi

# Parse bounds: containerX,containerY,containerW,containerH,tabOffsetX,tabOffsetY,tabW,tabH
IFS=',' read -r CONTAINER_X CONTAINER_Y CONTAINER_W CONTAINER_H TAB_OFFSET_X TAB_OFFSET_Y TAB_W TAB_H <<< "$BOUNDS"

# Step 3: Find Unity's window ID using Swift (built-in, no dependencies)
WINDOW_ID=$(swift - << SWIFTEOF
import CoreGraphics
import Foundation

let targetX = $CONTAINER_X
let targetY = $CONTAINER_Y

guard let windowList = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] else {
    exit(1)
}

var unityWindows: [(id: Int, x: Int, y: Int, w: Int, h: Int)] = []

for window in windowList {
    guard let owner = window[kCGWindowOwnerName as String] as? String,
          owner.contains("Unity"),
          let windowID = window[kCGWindowNumber as String] as? Int,
          let bounds = window[kCGWindowBounds as String] as? [String: Any],
          let x = bounds["X"] as? Int,
          let y = bounds["Y"] as? Int,
          let w = bounds["Width"] as? Int,
          let h = bounds["Height"] as? Int,
          let layer = window[kCGWindowLayer as String] as? Int,
          layer == 0, w > 100, h > 100 else {
        continue
    }
    unityWindows.append((windowID, x, y, w, h))
}

guard !unityWindows.isEmpty else {
    exit(1)
}

// Find window closest to target position
var bestMatch: Int? = nil
var bestDist = Int.max

for win in unityWindows {
    let dist = abs(win.x - targetX) + abs(win.y - targetY)
    if dist < bestDist {
        bestDist = dist
        bestMatch = win.id
    }
}

if let match = bestMatch, bestDist < 50 {
    print(match)
} else {
    // Fall back to largest Unity window
    let largest = unityWindows.max(by: { \$0.w * \$0.h < \$1.w * \$1.h })!
    print(largest.id)
}
SWIFTEOF
2>/dev/null)

if [ -z "$WINDOW_ID" ]; then
    echo "Error: Could not find Unity window"
    exit 1
fi

# Step 4: Capture the Unity window by ID
screencapture -l "$WINDOW_ID" -o "$TEMP_WINDOW_CAPTURE" 2>/dev/null

if [ ! -f "$TEMP_WINDOW_CAPTURE" ]; then
    echo "Error: Window capture failed"
    exit 1
fi

# Step 5: Crop to the specific tab region using sips
# sips uses --cropToHeightWidth height width --cropOffset y x
# Account for Retina: screencapture captures at screen resolution (pixels)
# Check if we need to scale the crop coordinates

# Get the actual captured image dimensions
CAPTURED_W=$(sips -g pixelWidth "$TEMP_WINDOW_CAPTURE" | tail -1 | awk '{print $2}')
CAPTURED_H=$(sips -g pixelHeight "$TEMP_WINDOW_CAPTURE" | tail -1 | awk '{print $2}')

# Calculate scale factor (for Retina displays)
if [ "$CAPTURED_W" -gt "$CONTAINER_W" ]; then
    SCALE=$(echo "$CAPTURED_W / $CONTAINER_W" | bc)
    # Scale the crop coordinates
    TAB_OFFSET_X=$((TAB_OFFSET_X * SCALE))
    TAB_OFFSET_Y=$((TAB_OFFSET_Y * SCALE))
    TAB_W=$((TAB_W * SCALE))
    TAB_H=$((TAB_H * SCALE))
fi

# Crop the image
sips "$TEMP_WINDOW_CAPTURE" --cropToHeightWidth "$TAB_H" "$TAB_W" --cropOffset "$TAB_OFFSET_Y" "$TAB_OFFSET_X" --out "$OUTPUT_PATH" >/dev/null 2>&1

# Clean up
rm -f "$TEMP_WINDOW_CAPTURE"

if [ -f "$OUTPUT_PATH" ]; then
    echo "Screenshot saved: $OUTPUT_PATH"
else
    echo "Error: Crop failed"
    exit 1
fi
