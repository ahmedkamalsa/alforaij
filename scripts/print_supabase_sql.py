from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "supabase" / "migrations" / "001_initial_schema.sql",
    ROOT / "supabase" / "migrations" / "002_source_quality_and_runs.sql",
    ROOT / "supabase" / "seed_source_registry.sql",
]


def main() -> None:
    for path in FILES:
        print(f"\n-- {path.relative_to(ROOT)}\n")
        print(path.read_text(encoding="utf-8").strip())
        print("\n")


if __name__ == "__main__":
    main()
