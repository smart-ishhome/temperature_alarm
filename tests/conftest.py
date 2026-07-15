"""Test setup.

evaluator.py is deliberately stdlib-only; its tests import it as a
top-level module so they run without homeassistant installed.
The Threshold Resolution tests import the real package (repo root on
sys.path) and need the pytest-homeassistant-custom-component harness.
"""
import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent

sys.path.insert(0, str(_REPO_ROOT / "custom_components" / "temperature_alarm"))
sys.path.insert(0, str(_REPO_ROOT))

if importlib.util.find_spec("homeassistant") is None:
    # HA harness not installed (evaluator-only CI): skip the HA-facing tests
    collect_ignore = [
        "test_thresholds.py",
        "test_integration.py",
        "test_settings.py",
        "test_config_flow.py",
    ]
else:
    import pytest_socket

    # The HA test plugin bans sockets per-test. Windows event loops create a
    # socketpair self-pipe, which the ban breaks (on Linux the pipe is an
    # allowed unix socket), so neuter the ban before the plugin applies it.
    pytest_socket.disable_socket = lambda *args, **kwargs: None
