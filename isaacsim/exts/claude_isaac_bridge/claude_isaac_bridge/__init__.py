"""Kit extension wrapper: starts isaac_bridge.py (repo root) on enable, stops it on disable."""

import importlib.util
import os

import omni.ext

_BRIDGE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "isaac_bridge.py"))


class ClaudeIsaacBridgeExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        spec = importlib.util.spec_from_file_location("isaac_bridge", _BRIDGE)  # this name skips autostart
        self._bridge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self._bridge)
        self._bridge.start()

    def on_shutdown(self):
        self._bridge.stop()
