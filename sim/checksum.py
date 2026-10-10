"""Rewrite every 40-hex address literal in sim/test/*.sol with its EIP-55 checksum (via cast)."""
import re
import subprocess
from pathlib import Path

for f in Path(__file__).with_name("test").glob("*.sol"):
    s = f.read_text(encoding="utf-8")
    for a in set(re.findall(r"(?<![0-9a-fA-Fx])0x[0-9a-fA-F]{40}(?![0-9a-fA-F])", s)):
        s = s.replace(a, subprocess.check_output(["cast", "to-check-sum-address", a], text=True).strip())
    f.write_text(s, encoding="utf-8")
