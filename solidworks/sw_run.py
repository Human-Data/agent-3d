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
    swconst  every SolidWorks enum: swconst.swDocPART, swconst.swDocumentTypes_e.swDocPART
    api(q)   search the type library: api("IFeature"), api("Extrusion"), api("swEndConditions_e")
    byref(v) ByRef/out argument (int/float/bool/str); read .value after the call
    NOTHING  null object argument (VBA "Nothing"), e.g. SelectByID2's Callout
    arr(seq) typed array argument: numbers -> doubles, COM objects -> dispatch, str -> strings

SolidWorks objects give pywin32 no type info, so plain late binding can't tell
methods from properties. The SolidWorks type library is read once (and cached in
%TEMP%\\sw_run_cache) so calls behave like the VBA docs: methods take (),
properties don't.

Env: SW_PROGID (default SldWorks.Application).
"""

import hashlib
import json
import linecache
import locale
import os
import re
import sys
import tempfile
import time
import traceback
from types import SimpleNamespace

PROGID = os.environ.get("SW_PROGID", "SldWorks.Application")

SCRIPT = "<sw_run>"
CACHE_DIR = os.path.join(tempfile.gettempdir(), "sw_run_cache")
CACHE_VERSION = 1
TLB_GUIDS = {  # type library GUIDs are stable across SolidWorks versions
    "sldworks.tlb": "{83A33D31-27C5-11CE-BFD4-00400513BB57}",
    "swconst.tlb": "{4687F359-55D0-4CD3-B6CF-2EB42C11F989}",
}

# Names the type library declares callable (method or parameterized property)
# and never as a plain property. Filled by load_typelib_info().
METHODS = set()

MK_E_UNAVAILABLE = 0x800401E3
BUSY = (0x80010001, 0x8001010A)  # RPC_E_CALL_REJECTED, RPC_E_SERVERCALL_RETRYLATER
TYPE_MISMATCH, PARAM_NOT_FOUND = 0x80020005, 0x80020004
DISP_E_EXCEPTION, RPC_E_SERVERFAULT = 0x80020009, 0x80010105
_NEVER_OPTIONAL = "SolidWorks API arguments are never optional - pass every one."
_GONE = "SolidWorks is not reachable (closed or crashed)."
HINTS = {
    TYPE_MISMATCH: "type mismatch - ByRef/out args need byref(...), 'Nothing' args need NOTHING, array args need arr([...]).",
    PARAM_NOT_FOUND: _NEVER_OPTIONAL,
    0x8002000E: _NEVER_OPTIONAL,  # DISP_E_BADPARAMCOUNT
    0x80020003: "member not found - a property called with (), or the member isn't on this object type.",
    RPC_E_SERVERFAULT: "SolidWorks failed inside the call - bad arguments, wrong document type, or nothing/wrong thing selected.",
    BUSY[0]: "SolidWorks is busy (modal dialog open, or still loading) - dismiss it / retry.",
    BUSY[1]: "SolidWorks is busy (modal dialog open, or still loading) - dismiss it / retry.",
    0x80010108: _GONE,  # RPC_E_DISCONNECTED
    0x800706BA: _GONE,  # RPC_S_SERVER_UNAVAILABLE
    0x800706BE: _GONE,  # RPC_S_CALL_FAILED
}


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
        """Late-bound SolidWorks object; methods vs properties decided by the type library."""

        def __getattr__(self, attr):
            if attr.startswith("_"):
                return base.__getattr__(self, attr)
            missing = f"'{attr}' is not a member of this object (wrong object type or name? try api({attr!r}))"
            if attr in METHODS and attr not in self._olerepr_.mapFuncs:
                try:
                    self._FlagAsMethod(attr)  # invoke as a method, never as a property read
                except pythoncom.com_error:
                    raise AttributeError(missing) from None
                return base.__getattr__(self, attr)
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


class Consts(SimpleNamespace):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        if not self.__dict__:
            raise AttributeError("swconst unavailable (SolidWorks type library not found) - use numeric values")
        raise AttributeError(f"swconst.{name} not found - search with api({name!r})")


def make_consts(enums):
    flat = {}
    for members in enums.values():
        flat.update(members)
    ns = Consts(**flat)
    for name, members in enums.items():
        setattr(ns, name, SimpleNamespace(**members))
    return ns


def make_api(enums, api_path):
    cache = {}

    def api(query, limit=80):
        """api("IFeature") lists an interface, api("swEndConditions_e") an enum,
        anything else is a case-insensitive substring search over member and enum names."""
        if not api_path or not os.path.isfile(api_path):
            print("api() unavailable: SolidWorks type library not found")
            return
        if "ifaces" not in cache:
            with open(api_path, encoding="utf-8") as f:
                cache["ifaces"] = json.load(f)
        ifaces = cache["ifaces"]
        q = query.strip().lower()
        for n, lines in ifaces.items():
            if n.lower() in (q, "i" + q):
                print(f"{n}:\n  " + "\n  ".join(lines))
                return
        for e, members in enums.items():
            if e.lower() == q:
                print(f"{e}:\n" + "\n".join(f"  {k} = {v}" for k, v in members.items()))
                return
        hits = []
        for n, lines in ifaces.items():
            if q in n.lower():
                hits.append(f"{n}  (interface, {len(lines)} members)")
            hits += [f"{n}.{l}" for l in lines if q in re.split(r"[(:]", l, 1)[0].lower()]
        for e, members in enums.items():
            if q in e.lower():
                hits.append(f"{e}  (enum, {len(members)} values)")
            hits += [f"{e}.{k} = {v}" for k, v in members.items() if q in k.lower()]
        print("\n".join(hits[:limit]) or f"no match for {query!r}")
        if len(hits) > limit:
            print(f"... {len(hits) - limit} more (narrow the query, or api({query!r}, limit={len(hits)}))")

    return api


# --- type library: method/property names, enums, signatures --------------------

VT_NAMES = {
    0: "None", 2: "int", 3: "int", 4: "float", 5: "float", 6: "currency", 7: "date", 8: "str",
    9: "object", 10: "int", 11: "bool", 12: "variant", 13: "object", 14: "decimal", 16: "int",
    17: "int", 18: "int", 19: "int", 20: "int", 21: "int", 22: "int", 23: "int", 24: "None",
    25: "None", 30: "str", 31: "str",
}


def _udt(href, ti):
    """(name, is_object, alias_typedesc, alias_typeinfo) for a VT_USERDEFINED reference."""
    rti = ti.GetRefTypeInfo(href)
    attr = rti.GetTypeAttr()
    if attr.typekind == pythoncom.TKIND_ALIAS:
        return None, False, attr.tdescAlias, rti
    is_obj = attr.typekind in (pythoncom.TKIND_DISPATCH, pythoncom.TKIND_INTERFACE, pythoncom.TKIND_COCLASS)
    return rti.GetDocumentation(-1)[0], is_obj, None, None


def _tname(td, ti, deref=False):
    """Readable type: 'int', 'str', 'IFeature', 'int*' (ByRef), 'float[]'."""
    try:
        if not isinstance(td, tuple):
            return VT_NAMES.get(td, f"vt{td}")
        vt, sub = td[0], td[1]
        if vt == pythoncom.VT_PTR:
            inner = _tname(sub, ti)
            if deref:
                return inner
            if isinstance(sub, tuple) and sub[0] == pythoncom.VT_USERDEFINED and _udt(sub[1], ti)[1]:
                return inner  # interface pointer = plain object argument
            return inner + "*"
        if vt == pythoncom.VT_SAFEARRAY:
            return _tname(sub, ti) + "[]"
        if vt == pythoncom.VT_USERDEFINED:
            name, _, alias, ati = _udt(sub, ti)
            return _tname(alias, ati) if alias is not None else name
        return f"vt{vt}"
    except Exception:
        return "?"


def _scan_interface(ti, funcs, props):
    attr = ti.GetTypeAttr()
    members, gets, sets = {}, {}, set()
    for j in range(attr[6]):
        try:
            fd = ti.GetFuncDesc(j)
            if fd.wFuncFlags & pythoncom.FUNCFLAG_FRESTRICTED:
                continue
            names = ti.GetNames(fd.memid)
            name = names[0]
            ret, params = _tname(fd.rettype[0], ti), []
            for k, a in enumerate(fd.args):
                if a[1] & pythoncom.PARAMFLAG_FRETVAL:
                    ret = _tname(a[0], ti, deref=True)
                    continue
                pname = names[k + 1] if k + 1 < len(names) else f"arg{k + 1}"
                params.append(f"{pname}: {_tname(a[0], ti)}")
            if fd.invkind == pythoncom.INVOKE_FUNC or (fd.invkind == pythoncom.INVOKE_PROPERTYGET and params):
                funcs.add(name)
                tag = "  [property]" if fd.invkind == pythoncom.INVOKE_PROPERTYGET else ""
                members[name] = f"{name}({', '.join(params)}) -> {ret}{tag}"
            elif fd.invkind == pythoncom.INVOKE_PROPERTYGET:
                props.add(name)
                gets[name] = ret
            else:  # PROPERTYPUT / PROPERTYPUTREF
                sets.add(name)
        except pythoncom.com_error:
            continue
    for name, t in gets.items():
        members[name] = f"{name}: {t}  ({'get/set' if name in sets else 'get'})"
    for name in sets - set(members):
        members[name] = f"{name}  (set only)"
    return [members[k] for k in sorted(members, key=str.lower)]


def _scan_enum(ti):
    out = {}
    for j in range(ti.GetTypeAttr()[7]):
        vd = ti.GetVarDesc(j)  # (memid, value, ..., varkind)
        if vd[4] == pythoncom.VAR_CONST and isinstance(vd[1], (int, float, str)):
            out[ti.GetNames(vd[0])[0]] = vd[1]
    return out


def scan_typelibs(paths):
    funcs, props, ifaces, enums = set(), set(), {}, {}
    for path in paths:
        tlb = pythoncom.LoadTypeLib(path)
        for i in range(tlb.GetTypeInfoCount()):
            try:
                kind = tlb.GetTypeInfoType(i)
                name = tlb.GetDocumentation(i)[0]
                ti = tlb.GetTypeInfo(i)
                if kind == pythoncom.TKIND_ENUM:
                    enums[name] = _scan_enum(ti)
                elif kind in (pythoncom.TKIND_DISPATCH, pythoncom.TKIND_INTERFACE):
                    if kind == pythoncom.TKIND_INTERFACE and ti.GetTypeAttr()[11] & pythoncom.TYPEFLAG_FDUAL:
                        ti = ti.GetRefTypeInfo(ti.GetRefTypeOfImplType(-1))  # dual -> dispatch view
                    lines = _scan_interface(ti, funcs, props)
                    if lines and (name not in ifaces or kind == pythoncom.TKIND_DISPATCH):
                        ifaces[name] = lines
            except pythoncom.com_error:
                continue
    return {"methods": sorted(funcs - props), "enums": enums}, ifaces


def _registry_tlb(guid):
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "TypeLib\\" + guid) as k:
            versions, i = [], 0
            while True:
                try:
                    versions.append(winreg.EnumKey(k, i))
                    i += 1
                except OSError:
                    break

        def vkey(v):  # registry versions are hex, e.g. "20.0"
            try:
                return tuple(int(p, 16) for p in v.split("."))
            except ValueError:
                return (-1,)

        for v in sorted(versions, key=vkey, reverse=True):
            for plat in ("win64", "win32"):
                try:
                    p = winreg.QueryValue(winreg.HKEY_CLASSES_ROOT, f"TypeLib\\{guid}\\{v}\\0\\{plat}")
                except OSError:
                    continue
                if p and os.path.isfile(p):
                    return p
    except (OSError, ImportError):
        pass
    return None


def find_typelibs(swApp):
    """Prefer the running instance's install dir, fall back to the registry."""
    found = {}
    try:
        d = swApp.GetExecutablePath
        d = str(d() if callable(d) else d)
        if d.lower().endswith(".exe"):
            d = os.path.dirname(d)
        for fname in TLB_GUIDS:
            if os.path.isfile(os.path.join(d, fname)):
                found[fname] = os.path.join(d, fname)
    except Exception:
        pass
    for fname, guid in TLB_GUIDS.items():
        if fname not in found:
            p = _registry_tlb(guid)
            if p:
                found[fname] = p
    return found


def _write_json(path, data):
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def load_typelib_info(swApp):
    """-> (enums, api_index_path); fills METHODS. Scans once per SolidWorks install, then cached."""
    tlbs = find_typelibs(swApp)
    if "sldworks.tlb" not in tlbs:
        raise RuntimeError("sldworks.tlb not found next to sldworks.exe or in the registry")
    stamp = "|".join(f"{p}:{os.path.getmtime(p)}" for p in sorted(tlbs.values()))
    base = os.path.join(CACHE_DIR, hashlib.sha1(f"{stamp}|v{CACHE_VERSION}".encode()).hexdigest()[:16])
    try:
        with open(base + ".json", encoding="utf-8") as f:
            info = json.load(f)
    except (OSError, ValueError):
        print("(indexing the SolidWorks type library - first run only)", file=sys.stderr)
        info, ifaces = scan_typelibs(sorted(tlbs.values()))
        os.makedirs(CACHE_DIR, exist_ok=True)
        _write_json(base + "-api.json", ifaces)
        _write_json(base + ".json", info)  # written last: its presence means the cache is complete
    METHODS.update(info["methods"])
    return info["enums"], base + "-api.json"


# --- running the script ----------------------------------------------------------

def hint(e):
    if isinstance(e, pythoncom.com_error):
        hr = e.args[0] & 0xFFFFFFFF
        h = HINTS.get(hr)
        if hr == DISP_E_EXCEPTION:
            excep = e.args[2] or ()
            inner = excep[5] & 0xFFFFFFFF if len(excep) > 5 and excep[5] else None
            h = HINTS.get(inner, "SolidWorks rejected the call - check arguments and state against api(...).")
        argerr = e.args[3] if len(e.args) > 3 else None
        if h and argerr is not None and hr in (TYPE_MISMATCH, PARAM_NOT_FOUND):
            h = f"argument {argerr}: {h}"
        return h
    if isinstance(e, TypeError) and "not callable" in str(e):
        return "a property (or an already-evaluated value) was called with () - drop the ()."
    if isinstance(e, AttributeError) and "'NoneType'" in str(e):
        return ("an API call returned None - no active document, nothing selected, wrong name, "
                "or the operation failed (check return values).")
    return None


def report(e):
    frames = [f for f in traceback.extract_tb(e.__traceback__) if f.filename == SCRIPT]
    out = "".join(traceback.format_exception_only(type(e), e))
    if frames:
        out = "Traceback (most recent call last):\n" + "".join(traceback.format_list(frames)) + out
    print(out, end="")
    h = hint(e)
    if h:
        print("hint: " + h)


def run(code, swApp, enums, api_path):
    linecache.cache[SCRIPT] = (len(code), None, code.splitlines(True), SCRIPT)
    ns = {
        "__name__": "__main__",
        "swApp": swApp,
        "model": swApp.ActiveDoc,
        "swconst": make_consts(enums),
        "api": make_api(enums, api_path),
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
        report(e)
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
    enums, api_path = {}, None
    try:
        enums, api_path = load_typelib_info(swApp)
    except Exception as e:
        print(f"warning: SolidWorks type library unavailable ({e}); swconst/api() are empty and "
              "zero-argument methods may need to be read without ()", file=sys.stderr)
    sys.exit(run(code, swApp, enums, api_path))


if __name__ == "__main__":
    main()
