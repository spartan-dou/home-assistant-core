"""Tests for the Zepp OS integration."""

from importlib.util import find_spec
import sys
from types import ModuleType

# assist_pipeline imports pymicro-vad and pyspeex-noise as it loads, and neither has a
# wheel for the Python of the fork CI. Voice detection stays off for a recorded message,
# so neither ever runs here: stand-ins only let the import through.
for _module, _name in (
    ("pymicro_vad", "MicroVad"),
    ("pyspeex_noise", "AudioProcessor"),
):
    if find_spec(_module) is None:
        sys.modules[_module] = ModuleType(_module)
        setattr(sys.modules[_module], _name, None)
