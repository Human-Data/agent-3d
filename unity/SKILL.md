---
name: unity
description: Control Unity through unity cli
allowed-tools: Bash(unity:*)
---

unity cli is already installed

use `unity open --args "-automated"` to open projects (run from the project directory)

Run editor commands with `unity cmd <command> [args...]`.

## Connected editors

Run `unity --no-banner status`

## Available editor commands

Run `unity --no-banner command`

To run arbitrary C# script in editor, use `unity --no-banner cmd eval`
📖 Command documentation:
  eval  --code --timeout?
  Evaluate C# code dynamically using Roslyn compiler
    --code: C# code to evaluate (required) [default: undefined]
    --timeout: Timeout in milliseconds [default: 5000]
