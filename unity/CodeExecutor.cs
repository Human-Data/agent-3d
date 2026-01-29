using UnityEngine;
using UnityEditor;
using System;
using System.IO;
using System.Reflection;
using System.CodeDom.Compiler;
using Microsoft.CSharp;
using System.Text;
using System.Linq;

[InitializeOnLoad]
public static class CodeExecutor
{
    private static readonly string WatchDir;
    private static readonly string InputPath;
    private static readonly string OutputPath;
    private static int lastLogCount = 0;

    static CodeExecutor()
    {
        var homeDir = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        WatchDir = Path.Combine(homeDir, ".unity_code_executor");
        InputPath = Path.Combine(WatchDir, "input.cs");
        OutputPath = Path.Combine(WatchDir, "output.jsonl");

        if (!Directory.Exists(WatchDir))
        {
            Directory.CreateDirectory(WatchDir);
        }

        // Subscribe to all Unity logs
        Application.logMessageReceived += OnLogReceived;
        EditorApplication.update += CheckForInput;
        EditorApplication.update += CheckForConsoleClear;

        UnityEngine.Debug.Log("[CodeExecutor] Initialized. Watching: " + InputPath);
    }

    private static void OnLogReceived(string message, string stackTrace, LogType type)
    {
        // Skip our own initialization message
        if (message.StartsWith("[CodeExecutor]")) return;

        string logType = type switch
        {
            LogType.Error => "error",
            LogType.Assert => "assert",
            LogType.Exception => "exception",
            LogType.Warning => "warning",
            _ => "log"
        };

        // Escape JSON string
        var escapedMessage = message
            .Replace("\\", "\\\\")
            .Replace("\"", "\\\"")
            .Replace("\n", "\\n")
            .Replace("\r", "\\r")
            .Replace("\t", "\\t");

        var jsonLine = $"{{\"message\":\"{escapedMessage}\",\"type\":\"{logType}\"}}";

        try
        {
            File.AppendAllText(OutputPath, jsonLine + "\n");
        }
        catch { }
    }

    private static void CheckForInput()
    {
        if (!File.Exists(InputPath)) return;

        string code = null;
        try
        {
            code = File.ReadAllText(InputPath);
            File.Delete(InputPath);
        }
        catch (Exception ex)
        {
            UnityEngine.Debug.LogWarning($"[CodeExecutor] Failed to read input file: {ex.Message}");
            return;
        }

        if (string.IsNullOrWhiteSpace(code)) return;

        ExecuteCode(code);
    }

    private static void CheckForConsoleClear()
    {
        int currentLogCount = GetLogCount();

        if (lastLogCount > 0 && currentLogCount == 0)
        {
            ClearOutputFile();
        }
        lastLogCount = currentLogCount;
    }

    private static int GetLogCount()
    {
        var logEntriesType = typeof(Editor).Assembly.GetType("UnityEditor.LogEntries");
        if (logEntriesType == null) return 0;

        var getCountMethod = logEntriesType.GetMethod("GetCount", BindingFlags.Public | BindingFlags.Static);
        if (getCountMethod == null) return 0;

        return (int)getCountMethod.Invoke(null, null);
    }

    private static void ClearOutputFile()
    {
        try
        {
            if (File.Exists(OutputPath))
            {
                File.Delete(OutputPath);
            }
        }
        catch { }
    }

    [MenuItem("Tools/Code Executor/Clear Output")]
    public static void ClearOutputMenuItem()
    {
        ClearOutputFile();
        UnityEngine.Debug.Log("[CodeExecutor] Output cleared");
    }

    [MenuItem("Tools/Code Executor/Test Executor")]
    public static void TestExecutor()
    {
        ExecuteCode("Debug.Log(\"Hello from CodeExecutor! Unity version: \" + Application.unityVersion);");
    }

    public static void ExecuteCode(string code)
    {
        // Wrap code in a class if it's just statements
        string fullCode;
        if (code.Contains("class ") || code.Contains("namespace "))
        {
            fullCode = code;
        }
        else
        {
            fullCode = $@"
using UnityEngine;
using UnityEditor;
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using UnityEngine.SceneManagement;

public static class DynamicCode
{{
    public static object Execute()
    {{
        {code}
        return null;
    }}
}}";
        }

        var provider = new CSharpCodeProvider();
        var parameters = new CompilerParameters
        {
            GenerateInMemory = true,
            GenerateExecutable = false
        };

        var assemblies = AppDomain.CurrentDomain.GetAssemblies();
        foreach (var assembly in assemblies)
        {
            try
            {
                if (!string.IsNullOrEmpty(assembly.Location))
                {
                    parameters.ReferencedAssemblies.Add(assembly.Location);
                }
            }
            catch { }
        }

        var compileResult = provider.CompileAssemblyFromSource(parameters, fullCode);

        if (compileResult.Errors.HasErrors)
        {
            foreach (CompilerError error in compileResult.Errors)
            {
                UnityEngine.Debug.LogError($"Line {error.Line}: {error.ErrorText}");
            }
            return;
        }

        try
        {
            var compiledAssembly = compileResult.CompiledAssembly;
            var type = compiledAssembly.GetType("DynamicCode");

            if (type != null)
            {
                var method = type.GetMethod("Execute", BindingFlags.Public | BindingFlags.Static);
                if (method != null)
                {
                    method.Invoke(null, null);
                }
            }
        }
        catch (Exception ex)
        {
            UnityEngine.Debug.LogError(ex.InnerException?.Message ?? ex.Message);
        }
    }
}
