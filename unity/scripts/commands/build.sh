cmd_build() {
    # build --target iOS [--sim|--device] [--output <dir>]
    # Exports a player by driving BuildPipeline.BuildPlayer inside the running Editor (via cmd_run).
    # Only iOS is supported for now; iOS output is an Xcode project (compile/sign it with Xcode).
    local target="" sdk="simulator" out=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --target) [[ $# -ge 2 ]] || { echo "error: --target needs a value (iOS)" >&2; exit 2; }
                      target="$2"; shift 2;;
            --sim)    sdk="simulator"; shift;;
            --device) sdk="device"; shift;;
            --output) [[ $# -ge 2 ]] || { echo "error: --output needs a directory path" >&2; exit 2; }
                      out="$2"; shift 2;;
            *)        echo "error: unknown argument '$1' (usage: build --target iOS [--sim|--device] [--output <dir>])" >&2; exit 2;;
        esac
    done

    [[ "$target" == "iOS" ]] || { echo "error: build requires --target iOS (only iOS supported for now)" >&2; exit 2; }

    local sdkEnum
    case "$sdk" in
        simulator) sdkEnum="SimulatorSDK";;
        device)    sdkEnum="DeviceSDK";;
    esac

    # Default the output dir to a unitybuild-prefixed temp folder; randomize result/log file names too.
    local rand; printf -v rand '%04x%04x' "$RANDOM" "$RANDOM"
    [[ -n "$out" ]] || out="/tmp/unitybuild-ios-${rand}"
    local resultFile="/tmp/unitybuild-${rand}.result"
    local sockLog="/tmp/unitybuild-${rand}.socket.log"

    local src
    src="$(cat <<'CSHARP'
using System;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

internal class MiniBuildPlayer : IRunCommand
{
    const string OutDir     = "__OUTPUT_DIR__";
    const string ResultFile = "__RESULT_FILE__";
    const string SdkName    = "__IOS_SDK__";   // SimulatorSDK or DeviceSDK

    public void Execute()
    {
        try
        {
            File.WriteAllText(ResultFile, "BUILDING\n");

            if (EditorApplication.isPlayingOrWillChangePlaymode)
            {
                File.WriteAllText(ResultFile, "ERROR: exit play mode before building\n");
                return;
            }

            if (EditorUserBuildSettings.activeBuildTarget != BuildTarget.iOS)
            {
                File.WriteAllText(ResultFile,
                    "ERROR: active build target is " + EditorUserBuildSettings.activeBuildTarget +
                    ", not iOS. Switch the active build target to iOS first, then rebuild.\n");
                return;
            }

            var scenes = EditorBuildSettings.scenes
                .Where(s => s.enabled)
                .Select(s => s.path)
                .ToArray();

            if (scenes.Length == 0)
            {
                File.WriteAllText(ResultFile, "ERROR: no enabled scenes in Build Settings\n");
                return;
            }

            Directory.CreateDirectory(OutDir);

            var opts = new BuildPlayerOptions
            {
                scenes = scenes,
                locationPathName = OutDir,
                target = BuildTarget.iOS,
                targetGroup = BuildTargetGroup.iOS,
                options = BuildOptions.None,
            };

            var prevSdk  = PlayerSettings.iOS.sdkVersion;
            var prevArch = PlayerSettings.iOS.simulatorSdkArchitecture;

            PlayerSettings.iOS.sdkVersion =
                SdkName == "SimulatorSDK" ? iOSSdkVersion.SimulatorSDK : iOSSdkVersion.DeviceSDK;
            if (SdkName == "SimulatorSDK")
                PlayerSettings.iOS.simulatorSdkArchitecture = AppleMobileArchitectureSimulator.ARM64;

            BuildSummary sum;
            try
            {
                sum = BuildPipeline.BuildPlayer(opts).summary;
            }
            finally
            {
                // So that we don't emit a diff on ProjectSettings.asset
                PlayerSettings.iOS.sdkVersion = prevSdk;
                PlayerSettings.iOS.simulatorSdkArchitecture = prevArch;
                AssetDatabase.SaveAssets();
            }

            var sb = new StringBuilder();
            sb.AppendLine("RESULT=" + sum.result);
            sb.AppendLine("target=iOS");
            sb.AppendLine("sdk=" + SdkName);
            sb.AppendLine("outputPath=" + sum.outputPath);
            sb.AppendLine("totalErrors=" + sum.totalErrors);
            sb.AppendLine("totalWarnings=" + sum.totalWarnings);
            sb.AppendLine("totalSizeBytes=" + sum.totalSize);
            sb.AppendLine("totalTime=" + sum.totalTime);
            File.WriteAllText(ResultFile, sb.ToString());
            Debug.Log("[unity.sh build] iOS " + sum.result + " sdk=" + SdkName + " -> " + sum.outputPath);
        }
        catch (Exception e)
        {
            File.WriteAllText(ResultFile, "EXCEPTION: " + e.Message + "\n" + e.StackTrace + "\n");
            Debug.LogError("[unity.sh build] " + e);
        }
    }
}
CSHARP
)"
    src="${src//__OUTPUT_DIR__/$out}"
    src="${src//__RESULT_FILE__/$resultFile}"
    src="${src//__IOS_SDK__/$sdkEnum}"

    >&2 echo "[build] running BuildPipeline.BuildPlayer in the Editor (blocks the Editor main thread; polling for completion)..."

    rm -f "$resultFile" "$sockLog"
    # Fire into the Editor in the background: a real build blocks the main thread past the bridge's
    # 60s socket-reply timeout, but it keeps running. Poll the result file for the verdict instead.
    ( cmd_run "$src" >"$sockLog" 2>&1 ) &

    local start firstline now elapsed lastBeat=0
    start="$(date +%s)"
    while true; do
        firstline=""
        if [[ -f "$resultFile" ]]; then firstline="$(head -n1 "$resultFile" 2>/dev/null || true)"; fi
        case "$firstline" in
            RESULT=*|EXCEPTION:*|ERROR:*)
                now="$(date +%s)"; elapsed=$(( now - start ))
                >&2 echo "[build] finished in ${elapsed}s"
                cat "$resultFile"
                if [[ "$firstline" == "RESULT=Succeeded" ]]; then
                    >&2 echo "[build] OK -> Xcode project at: $out"
                    return 0
                fi
                >&2 echo "[build] FAILED (socket log: $sockLog)"
                return 1
                ;;
        esac
        now="$(date +%s)"; elapsed=$(( now - start ))
        if (( elapsed > 1800 )); then
            >&2 echo "[build] timed out after ${elapsed}s (the Editor build may still be running)"
            >&2 echo "[build] last result-file line: ${firstline:-<none>}"
            if [[ -f "$sockLog" ]]; then >&2 echo "[build] socket log:"; cat "$sockLog" >&2; fi
            return 1
        fi
        if (( elapsed - lastBeat >= 15 )); then
            >&2 echo "[build] still building... ${elapsed}s"
            lastBeat=$elapsed
        fi
        sleep 3
    done
}
