"""Builds the OPTIONAL C++ extension `detour._ctg`. Everything else is in pyproject.toml.

* Default: try to build it; if there is no compiler (or the build fails) the install still
  succeeds and detour silently uses its pure-Python cost_to_go.
* DETOUR_NO_NATIVE=1       skip the extension entirely.
* DETOUR_REQUIRE_NATIVE=1  make a failed extension build an error (used by the CI job that
                           tests the C++ path, so it cannot pass by accident without it).
Running the compiled code also needs numpy:  pip install -e ".[native]"
"""
import os

from setuptools import setup


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


ext_modules, cmdclass = [], {}
if not _flag("DETOUR_NO_NATIVE"):
    try:
        from pybind11.setup_helpers import Pybind11Extension, build_ext
    except ImportError:  # pybind11 not available in this build environment
        if _flag("DETOUR_REQUIRE_NATIVE"):
            raise
    else:
        # -ffp-contract=off / /fp:strict: keep double arithmetic exactly as written so the
        # seconds stay bit-identical to Python (the core has no multiplications, so this is
        # belt and braces).
        flags = ["/fp:strict"] if os.name == "nt" else ["-ffp-contract=off"]
        ext_modules = [Pybind11Extension("detour._ctg", ["cpp/ctg.cpp"], cxx_std=17,
                                         extra_compile_args=flags,
                                         optional=not _flag("DETOUR_REQUIRE_NATIVE"))]
        cmdclass = {"build_ext": build_ext}

setup(ext_modules=ext_modules, cmdclass=cmdclass)
