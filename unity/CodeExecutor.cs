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

    static CodeExecutor()
    {
        var homeDir = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        WatchDir = Path.Combine(homeDir, ".unity_code_executor");
        InputPath = Path.Combine(WatchDir, "input.cs");

        if (!Directory.Exists(WatchDir))
        {
            Directory.CreateDirectory(WatchDir);
        }

        EditorApplication.update += CheckForInput;

        UnityEngine.Debug.Log("[CodeExecutor] Initialized. Watching: " + InputPath);
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
            // Extract using statements from user code
            var lines = code.Split('\n');
            var usingStatements = new StringBuilder();
            var codeWithoutUsings = new StringBuilder();
            bool inUsingSection = true;

            foreach (var line in lines)
            {
                var trimmed = line.Trim();
                if (inUsingSection && trimmed.StartsWith("using ") && trimmed.EndsWith(";"))
                {
                    usingStatements.AppendLine(line);
                }
                else if (!string.IsNullOrWhiteSpace(trimmed))
                {
                    inUsingSection = false;
                    codeWithoutUsings.AppendLine(line);
                }
                else if (!inUsingSection)
                {
                    codeWithoutUsings.AppendLine(line);
                }
            }

            fullCode = $@"
using UnityEngine;
using UnityEditor;
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using UnityEngine.SceneManagement;
{usingStatements}
public static class DynamicCode
{{
    public static object Execute()
    {{
        {codeWithoutUsings}
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
        finally
        {
            AssetDatabase.Refresh();
        }
    }
}
