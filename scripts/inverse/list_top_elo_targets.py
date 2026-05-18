#!/usr/bin/env python3
"""Compatibility wrapper for `revenge_bench.scripts.inverse.list_top_elo_targets`."""

import importlib
import runpy
import sys
import types

_WRAPPED_MODULE_NAME = "revenge_bench.scripts.inverse.list_top_elo_targets"
_wrapped = importlib.import_module(_WRAPPED_MODULE_NAME)

class _WrapperModule(types.ModuleType):
    def __getattr__(self, name):
        return getattr(_wrapped, name)

    def __setattr__(self, name, value):
        if not name.startswith("_"):
            setattr(_wrapped, name, value)
        super().__setattr__(name, value)

globals().update(
    {
        name: getattr(_wrapped, name)
        for name in dir(_wrapped)
        if not (name.startswith("__") and name.endswith("__"))
    }
)
sys.modules[__name__].__class__ = _WrapperModule

if __name__ == "__main__":
    runpy.run_module(_WRAPPED_MODULE_NAME, run_name="__main__")
