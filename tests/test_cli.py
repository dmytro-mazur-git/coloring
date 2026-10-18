import json
import subprocess
import sys

from conftest import SCRIPTS

CLI = [sys.executable, str(SCRIPTS / "coloring.py")]


def run(*args):
    return subprocess.run([*CLI, *args], capture_output=True, text=True)


def test_config_get():
    assert json.loads(run("config", "get", "max_pages").stdout) == 10


def test_generate_command_is_gone():
    res = run("generate", "--prompt", "cow", "--out", "/dev/null")
    assert res.returncode != 0 and "invalid choice" in res.stderr


def test_config_get_unknown_key():
    res = run("config", "get", "search.nope")
    assert res.returncode != 0 and "unknown config key" in res.stderr
