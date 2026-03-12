---
name: autocad
description: Control AutoCAD via AutoLISP. Run arbitrary AutoLISP code in a running AutoCAD instance to inspect, create and modify drawings.
---

# AutoCAD Skill

Execute AutoLISP in the active drawing of a running AutoCAD. Command-line output (`princ`/`print`/`prompt`, command echo) comes back, followed by `=> <value of the last expression>`.

## Usage

Pipe code via stdin — heredocs are the natural way to send multi-line scripts:

```bash
python3 ~/.claude/skills/autocad/acad_run.py <<'EOF'
(princ (getvar "CLAYER"))
EOF
```

One-liners as a single argument: `python3 ~/.claude/skills/autocad/acad_run.py '(getvar "DWGNAME")'`. Files: `acad_run.py < script.lsp`.

Exit code 0 on success, 1 if the code raised (message printed). Default timeout 30s.
