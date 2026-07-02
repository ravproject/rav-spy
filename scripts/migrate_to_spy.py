"""
Migrasi dari RAV-REMOTE ke RAV-SPY.
Merename semua direktori konfigurasi dan data pengguna.
"""
import shutil
import sys
from pathlib import Path

OLD_CONFIG = Path.home() / ".config" / "rav-remote"
NEW_CONFIG = Path.home() / ".config" / "rav-spy"
OLD_DOWNLOADS = Path.home() / "Downloads" / "rav-remote"
NEW_DOWNLOADS = Path.home() / "Downloads" / "rav-spy"

def migrate_dir(old: Path, new: Path):
    if old.exists() and not new.exists():
        print(f"  Rename: {old} → {new}")
        shutil.move(str(old), str(new))
    elif old.exists() and new.exists():
        print(f"  WARN: Both {old} and {new} exist. Merging {old} → {new}")
        for item in old.iterdir():
            dest = new / item.name
            if not dest.exists():
                shutil.move(str(item), str(dest))
        shutil.rmtree(str(old))
    elif new.exists():
        print(f"  OK: {new} already exists")
    else:
        print(f"  SKIP: {old} does not exist")

def migrate_chromadb():
    chroma = NEW_CONFIG / "memory" / "chroma"
    if chroma.exists():
        print(f"  ChromaDB at {chroma} — no migration needed")

def main():
    print("RAV-REMOTE → RAV-SPY Migration")
    print("=" * 40)

    print("\n1. Config directory:")
    migrate_dir(OLD_CONFIG, NEW_CONFIG)

    print("\n2. Downloads directory:")
    migrate_dir(OLD_DOWNLOADS, NEW_DOWNLOADS)

    print("\n3. ChromaDB:")
    migrate_chromadb()

    print("\n✅ Migration complete!")
    print("Config: " + str(NEW_CONFIG))
    print("Downloads: " + str(NEW_DOWNLOADS))

if __name__ == "__main__":
    main()
