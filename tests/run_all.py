"""Run the whole offline test suite.

    python3 -m tests.run_all
"""
from __future__ import annotations

import runpy
import sys
import traceback

SUITES = ["tests.test_physics", "tests.test_combat", "tests.test_modes",
          "tests.test_api"]


def main() -> int:
    failed = []
    for suite in SUITES:
        print("\n" + "=" * 68)
        print(f"  {suite}")
        print("=" * 68)
        try:
            runpy.run_module(suite, run_name="__main__")
        except SystemExit as e:
            if e.code:
                failed.append(suite)
        except Exception:
            traceback.print_exc()
            failed.append(suite)
    print("\n" + "=" * 68)
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    print("  ALL SUITES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
