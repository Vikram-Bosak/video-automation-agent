#!/usr/bin/env python3
"""
tools/dry_run.py
────────────────
Dry run mode: sirf Sheet check karo, browser mat chalao.
GitHub Actions workflow se call hota hai.
"""

import sys
from pathlib import Path

# Project root को path में add करो
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.sheet_reader import SheetReader


def main():
    print("🔍 DRY RUN MODE — only checking Sheet\n")

    try:
        sr = SheetReader()
        row = sr.get_next_pending_row()

        if row:
            print(f"✅ Pending row found: Row {row.row_index} | {row.title}")
            print(f"   Prompts: {len(row.get_prompts())}")
            for i, p in enumerate(row.get_prompts(), 1):
                print(f"   Prompt {i}: {p[:80]}...")
        else:
            print("ℹ️  No pending rows — nothing to process")

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
