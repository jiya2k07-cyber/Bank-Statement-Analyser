"""Fallback runner when pytest is not installed: python run_tests.py"""
import importlib, inspect, sys, types, traceback, glob, os

try:
    import pytest  # noqa
except ImportError:
    pt = types.ModuleType("pytest")
    class _Raises:
        def __init__(self, exc): self.exc = exc
        def __enter__(self): return self
        def __exit__(self, t, v, tb):
            if t is None: raise AssertionError("did not raise")
            return issubclass(t, self.exc)
    pt.raises = _Raises
    sys.modules["pytest"] = pt

fails = total = 0
for f in sorted(glob.glob("tests/test_*.py")):
    mod = importlib.import_module(f[:-3].replace(os.sep, "."))
    for name, fn in inspect.getmembers(mod, inspect.isfunction):
        if name.startswith("test_"):
            total += 1
            try: fn()
            except Exception: fails += 1; print("FAIL", f, name); traceback.print_exc()
print(f"{total - fails}/{total} passed")
sys.exit(1 if fails else 0)
