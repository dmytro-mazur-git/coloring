import json
import subprocess
import sys

from conftest import SCRIPTS

CLI = [sys.executable, str(SCRIPTS / "coloring.py")]


def run(*args):
    return subprocess.run([*CLI, *args], capture_output=True, text=True)


def test_generation_disabled_by_default():
    assert json.loads(run("config", "get", "generate.enabled").stdout) is False
    res = run("generate", "--prompt", "cow", "--out", "/dev/null")
    assert res.returncode != 0 and "disabled" in res.stderr


def test_config_get_unknown_key():
    res = run("config", "get", "generate.nope")
    assert res.returncode != 0 and "unknown config key" in res.stderr
