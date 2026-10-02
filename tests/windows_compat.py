"""Let the HA test harness load on Windows.

homeassistant.runner imports the Unix-only fcntl and resource modules at
module level (for a file lock and a file-descriptor limit tests never
touch), and the harness plugin imports runner. Loaded before the plugin
(pytest.ini addopts -p), this registers empty stand-ins. They are safe
for the other packages that probe for fcntl: atomicwrites branches on
sys.platform, and `from fcntl import ioctl` still raises ImportError.
"""
import sys
import types

if sys.platform == "win32":
    for name in ("fcntl", "resource"):
        sys.modules.setdefault(name, types.ModuleType(name))
