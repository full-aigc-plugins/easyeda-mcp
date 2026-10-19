#!/usr/bin/env python3
"""从任意工作目录启动自包含 MCP 包，无需 pip install。"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from easyeda_mcp.server import main

if __name__ == '__main__':
    raise SystemExit(main())
