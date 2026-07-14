"""Test setup: make the evaluator importable without Home Assistant.

evaluator.py is deliberately stdlib-only, but importing it through the
custom_components.temperature_alarm package would execute __init__.py,
which needs homeassistant installed. Import it as a top-level module
instead.
"""
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).parent.parent / "custom_components" / "temperature_alarm"),
)
