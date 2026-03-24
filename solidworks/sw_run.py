#!/usr/bin/env python3
"""
Run Python code against a live SolidWorks (Windows; COM via pywin32).

Usage:
    sw_run.py 'print(model.GetTitle())'     # one-liner argument
    sw_run.py <<'EOF'                       # multi-line heredoc
    f = model.FirstFeature()
    while f:
        print(f.Name)
        f = f.GetNextFeature()
    EOF
    sw_run.py < script.py                   # from a file

The code runs in a fresh namespace with:
    swApp    the running SolidWorks (ISldWorks)
    model    swApp.ActiveDoc when the run started (None if no document is open)
    byref(v) ByRef/out argument (int/float/bool/str); read .value after the call
    NOTHING  null object argument (VBA "Nothing"), e.g. SelectByID2's Callout
    arr(seq) typed array argument: numbers -> doubles, COM objects -> dispatch, str -> strings

Env: SW_PROGID (default SldWorks.Application).
"""

import linecache
import locale
import os
import sys
import time
import traceback

PROGID = os.environ.get("SW_PROGID", "SldWorks.Application")

SCRIPT = "<sw_run>"
MK_E_UNAVAILABLE = 0x800401E3
BUSY = (0x80010001, 0x8001010A)  # RPC_E_CALL_REJECTED, RPC_E_SERVERCALL_RETRYLATER
DISP_E_EXCEPTION, RPC_E_SERVERFAULT = 0x80020009, 0x80010105


def die(msg):
    sys.stdout.flush()
    sys.exit("ERROR: " + msg)


# --- pywin32 -----------------------------------------------------------------

def _import_pywin32():
    global pythoncom, VARIANT, build, dynamic, SWDispatch
    import pythoncom
    from win32com.client import VARIANT, build, dynamic

    base = dynamic.CDispatch

    class SWDispatch(base):
        """Late-bound SolidWorks object."""

        def __getattr__(self, attr):
            if attr.startswith("_"):
                return base.__getattr__(self, attr)
            missing = f"'{attr}' is not a member of this object (wrong object type or name? try api({attr!r}))"
            try:
                return base.__getattr__(self, attr)
            except AttributeError:
                raise AttributeError(missing) from None
            except pythoncom.com_error as e:
                # Reading a method as a property makes SolidWorks throw; hand back a callable.
                if attr in self._olerepr_.mapFuncs or (e.hresult & 0xFFFFFFFF) not in (
                    RPC_E_SERVERFAULT,
                    DISP_E_EXCEPTION,
                ):
                    raise
                self._FlagAsMethod(attr)
                return base.__getattr__(self, attr)

        def _wrap_dispatch_(self, ob, userName=None, *args, **kwargs):
            return wrap(ob, userName)

        def __repr__(self):
            return "<SolidWorks COM object>"

        __str__ = __repr__  # base __str__ invokes the default member


def wrap(disp, name=None):
    """PyIDispatch -> SWDispatch with no type info (uniform late binding for every object)."""
    return SWDispatch(disp, build.DispatchItem(), name)


def connect():
    import pywintypes

    try:
        clsid = pywintypes.IID(PROGID)
    except pywintypes.com_error:
        die(f"'{PROGID}' is not registered - is SolidWorks installed?")
    for attempt in range(40):
        try:
            unk = pythoncom.GetActiveObject(clsid)
            return wrap(unk.QueryInterface(pythoncom.IID_IDispatch), "swApp")
        except pythoncom.com_error as e:
            hr = e.hresult & 0xFFFFFFFF
            if hr == MK_E_UNAVAILABLE:
                die("SolidWorks is not running - start it (and let it finish loading) first.")
            if hr not in BUSY or attempt == 39:
                raise
            time.sleep(0.5)


# --- helpers exposed to scripts ------------------------------------------------

def byref(value=0):
    """ByRef/out argument: pass it, then read .value."""
    if isinstance(value, bool):
        vt = pythoncom.VT_BOOL
    elif isinstance(value, int):
        vt = pythoncom.VT_I4
    elif isinstance(value, float):
        vt = pythoncom.VT_R8
    elif isinstance(value, str):
        vt = pythoncom.VT_BSTR
    else:
        vt = pythoncom.VT_VARIANT
    return VARIANT(pythoncom.VT_BYREF | vt, value)


def arr(values, vt=None):
    """Typed SAFEARRAY argument. Numbers -> doubles (pass vt=pythoncom.VT_I4 for ints)."""
    values = list(values)
    if vt is None:
        if values and all(hasattr(v, "_oleobj_") or isinstance(v, dynamic.PyIDispatchType) for v in values):
            vt = pythoncom.VT_DISPATCH
        elif values and all(isinstance(v, str) for v in values):
            vt = pythoncom.VT_BSTR
        elif values and all(isinstance(v, bool) for v in values):
            vt = pythoncom.VT_BOOL
        elif all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
            vt = pythoncom.VT_R8
        else:
            vt = pythoncom.VT_VARIANT
    if vt == pythoncom.VT_DISPATCH:
        values = [getattr(v, "_oleobj_", v) for v in values]
    elif vt == pythoncom.VT_R8:
        values = [float(v) for v in values]
    return VARIANT(pythoncom.VT_ARRAY | vt, values)


# --- running the script ----------------------------------------------------------

def run(code, swApp):
    linecache.cache[SCRIPT] = (len(code), None, code.splitlines(True), SCRIPT)
    ns = {
        "__name__": "__main__",
        "swApp": swApp,
        "model": swApp.ActiveDoc,
        "byref": byref,
        "arr": arr,
        "NOTHING": VARIANT(pythoncom.VT_DISPATCH, None),
        "VARIANT": VARIANT,
        "pythoncom": pythoncom,
    }
    try:
        exec(compile(code, SCRIPT, "exec"), ns)
        return 0
    except SystemExit as e:
        if e.code is None or isinstance(e.code, int):
            return e.code or 0
        print(e.code)
        return 1
    except BaseException as e:
        traceback.print_exc()
        return 1


def read_code():
    if len(sys.argv) == 2:
        return sys.argv[1]
    data = sys.stdin.buffer.read()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode(locale.getpreferredencoding(False), errors="replace")


def main():
    if len(sys.argv) > 2 or sys.argv[1:] in (["-h"], ["--help"]):
        print(__doc__)
        sys.exit(0 if len(sys.argv) == 2 else 2)
    code = read_code()
    if not code.strip():
        sys.exit("error: no code given (pass as argument or via stdin/heredoc)")
    if sys.platform != "win32":
        sys.exit("ERROR: SolidWorks is driven over Windows COM - run this with Windows Python "
                 "(python.exe), not macOS/Linux/WSL.")
    try:
        _import_pywin32()
    except ImportError:
        sys.exit("ERROR: pywin32 is missing - run: python -m pip install pywin32")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except (AttributeError, ValueError):
            pass

    swApp = connect()
    sys.exit(run(code, swApp))


if __name__ == "__main__":
    main()
