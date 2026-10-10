"""以"可执行命令"的形式运行源码版 CLI，便于测试套件直接调用。

用法：python tools/run-source-cli.py info
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "desktop"))

if __name__ == "__main__":
    from mediaconv.Cli import main

    sys.exit(main(sys.argv[1:]))
