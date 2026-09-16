import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location("format_check", HERE / "format_check.py")
fc = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = fc
SPEC.loader.exec_module(fc)


class AutomaticExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old_root = fc.ROOT
        fc.ROOT = self.root

    def tearDown(self):
        fc.ROOT = self.old_root
        self.temp.cleanup()

    def test_community_hooks_are_rejected(self):
        plugin = self.root / "community" / "plugin"
        hooks = plugin / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "hooks.json").write_text("{}")
        report = fc.Report()

        fc.check_hooks(plugin, report)

        self.assertTrue(any(f.level == "fail" and f.check == "hooks" for f in report.findings))

    def test_community_local_mcp_command_is_rejected(self):
        plugin = self.root / "community" / "plugin"
        plugin.mkdir(parents=True)
        config = plugin / ".mcp.json"
        config.write_text(json.dumps({"mcpServers": {"local": {"command": "sh", "args": ["-c", "env"]}}}))
        report = fc.Report()

        fc.scan_text_file(config, set(), set(), report, pdir=plugin)

        self.assertTrue(any(f.level == "fail" and f.check == "mcp-command" for f in report.findings))

    def test_featured_hooks_remain_reviewable(self):
        plugin = self.root / "featured" / "plugin"
        hooks = plugin / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "hooks.json").write_text("{}")
        report = fc.Report()

        fc.check_hooks(plugin, report)

        self.assertFalse(report.failed)
        self.assertTrue(any(f.level == "note" and f.check == "hooks" for f in report.findings))


if __name__ == "__main__":
    unittest.main()
