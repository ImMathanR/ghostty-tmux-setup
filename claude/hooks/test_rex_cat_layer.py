"""rex-cat-layer.lua must parse: the hook tests use a fake launcher, so a syntax
error there only shows up as "no cat". Compile locally without touching a Rex session.
Run: python3 test_rex_cat_layer.py"""
import os, shutil, subprocess, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LUA = shutil.which("lua") or shutil.which("luajit")


@unittest.skipUnless(LUA, "Lua or LuaJIT not installed")
class LayerScript(unittest.TestCase):
    def test_layer_script_compiles(self):
        path = os.path.join(HERE, "rex-cat-layer.lua")
        out = subprocess.run([LUA, "-e", 'assert(loadfile(%r)); print("ok")' % path],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(out.stdout.strip(), "ok")


if __name__ == "__main__":
    unittest.main()
