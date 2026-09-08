"""Cross-platform paths for Allure analysis artifacts.

Default analysis directory:
  - Windows: %LOCALAPPDATA%\\allure-analysis
  - macOS/Linux: $XDG_DATA_HOME/allure-analysis or ~/.local/share/allure-analysis

Override with environment variable ALLURE_ANALYSIS_DIR.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ENV_OVERRIDE = "ALLURE_ANALYSIS_DIR"


def default_analysis_dir() -> Path:
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        return Path(override).expanduser()

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "allure-analysis"
        return Path.home() / "AppData" / "Local" / "allure-analysis"

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / "allure-analysis"
    return Path.home() / ".local" / "share" / "allure-analysis"


def main() -> None:
    print(default_analysis_dir())


if __name__ == "__main__":
    main()
