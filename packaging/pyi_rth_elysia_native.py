"""Load interpreter-matched native libraries before packaged application imports."""

from __future__ import annotations

import ctypes
from pathlib import Path
import sys


bundle_root = Path(getattr(sys, "_MEIPASS"))
libexpat_candidates = sorted((bundle_root / "elysia-native").glob("libexpat.so*"))
if len(libexpat_candidates) != 1:
    raise RuntimeError("The packaged interpreter-matched libexpat is missing.")
libexpat = libexpat_candidates[0]

# The library keeps its normal libexpat.so.1 SONAME. Preloading the exact copy
# linked by the selected interpreter makes pyexpat reuse it instead of an
# incompatible host-discovered copy collected elsewhere in the onefile image.
ctypes.CDLL(str(libexpat), mode=ctypes.RTLD_GLOBAL)
