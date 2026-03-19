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

Exit code 0 on success, 1 if the code raised (message printed). Default timeout 30s; `ACAD_RUN_TIMEOUT=120` for slow commands.

## Perceive

Drawing overview — read the `=>` line:
```lisp
(list (getvar "DWGPREFIX") (getvar "DWGNAME") (getvar "INSUNITS") (getvar "CLAYER") (getvar "EXTMIN") (getvar "EXTMAX"))
```

Layers (same pattern for `"BLOCK"`, `"LTYPE"`, `"STYLE"`, `"DIMSTYLE"`; `tblsearch` for one by name):
```lisp
(setq l (tblnext "LAYER" T))
(while l
  (princ (strcat "\n" (cdr (assoc 2 l)) "  color=" (itoa (cdr (assoc 62 l))) "  ltype=" (cdr (assoc 6 l))))
  (setq l (tblnext "LAYER")))
```

Entity counts by type (`ssget "X"` = everything; add `'((410 . "Model"))` for model space only):
```lisp
(setq ss (ssget "X") i 0 acc nil)
(while (and ss (< i (sslength ss)))
  (setq ty (cdr (assoc 0 (entget (ssname ss i)))) i (1+ i)
        acc (if (assoc ty acc)
              (subst (cons ty (1+ (cdr (assoc ty acc)))) (assoc ty acc) acc)
              (cons (cons ty 1) acc))))
acc
```

Entity data — filter, then dump DXF lists:
```lisp
(setq ss (ssget "X" '((0 . "LINE,CIRCLE") (8 . "Walls"))) i 0)   ; nil if nothing matches
(repeat (min 20 (sslength ss)) (print (entget (ssname ss i))) (setq i (1+ i)))
```
DXF codes: `0` type · `5` handle · `8` layer · `10`/`11` point (start/end, center, insert) · `40` radius / text height · `1` text · `2` block name · `62` color · `-1` entity name. `(handent "2B3")` turns a handle back into an entity.

Look at it — screenshot the current view, then Read the PNG:
```lisp
(setvar "FILEDIA" 0) (command "_.ZOOM" "_E") (command "_.PNGOUT" "/tmp/view.png" "") (setvar "FILEDIA" 1)
```
(Windows: `C:/Temp/view.png`.)

## Act

Prefer `entmake`/`entmod` (no prompts, no UI) over `command`:
```lisp
(entmake '((0 . "LAYER") (100 . "AcDbSymbolTableRecord") (100 . "AcDbLayerTableRecord") (2 . "Walls") (70 . 0) (62 . 1) (6 . "Continuous")))
(entmake '((0 . "LINE") (8 . "Walls") (10 0.0 0.0 0.0) (11 100.0 50.0 0.0)))
(entmake '((0 . "CIRCLE") (8 . "Walls") (10 50.0 25.0 0.0) (40 . 10.0)))
(entmake '((0 . "TEXT") (8 . "0") (10 0.0 60.0 0.0) (40 . 2.5) (1 . "Hello")))
(setq e (entget en)) (entmod (subst (cons 8 "Walls") (assoc 8 e) e))   ; en from ssname / handent
(entdel en)
```

Commands — keyboard equivalents; `_.` = English name, not redefined; `""` = Enter:
```lisp
(command "_.PLINE" '(0 0) '(10 0) '(10 10) "_C")
(command "_.-LAYER" "_M" "Walls" "")
(command "_.ZOOM" "_E")
(command "_.QSAVE")        ; drawing needs a path already; else SAVEAS with FILEDIA 0
(command "_.U")            ; undo last change
```

## Rules

- AutoCAD must be idle at the `Command:` prompt; the active drawing is the target.
- Points are `(x y z)` lists in drawing units; angles in radians. `T` and `nil` are constants — never use `t` as a variable.
- Each run is a fresh `load`; `defun`/`setq` globals persist for the session. The bridge cancels any command left pending.
- `(vl-load-com)` then `vla-*`/`vlax-*` for the ActiveX API (Windows only).

## Setup (once)

AutoCAD (SECURELOAD) refuses to `load` .lsp files from untrusted folders. With AutoCAD running:

```bash
python3 ~/.claude/skills/autocad/acad_run.py --setup
```

Windows: driven over COM (`AutoCAD.Application`). macOS: the expression is typed into the AutoCAD window via System Events — grant your terminal Accessibility access and keep the AutoCAD window frontmost.
