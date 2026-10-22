#!/usr/bin/env python3
"""Restore original RAW bytes from this evidence bundle; does not run any simulation."""
from pathlib import Path
import argparse, gzip, hashlib, json, shutil, tempfile
ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--output-dir", type=Path, default=ROOT / "restored-raw")
args = parser.parse_args()
entries = json.loads((ROOT / "RAW_DELIVERY.json").read_text())
args.output_dir.mkdir(parents=True, exist_ok=True)
for item in entries:
    rel = Path(item["original_path"])
    if rel.is_absolute() or ".." in rel.parts:
        raise SystemExit("Unsafe RAW relative path.")
    target = args.output_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise SystemExit("Refusing to overwrite existing file: " + str(target))
    with tempfile.TemporaryDirectory(dir=args.output_dir) as tmp:
        if item["encoding"] == "none":
            source = ROOT / item["delivery_path"]
            opener = lambda: source.open("rb")
        else:
            compressed = Path(tmp) / "joined.raw.gz"
            joined_hash = hashlib.sha256()
            joined_bytes = 0
            with compressed.open("xb") as joined:
                for part in item["parts"]:
                    part_path = ROOT / part["path"]
                    part_hash = hashlib.sha256()
                    part_bytes = 0
                    with part_path.open("rb") as stream:
                        for block in iter(lambda: stream.read(1024 * 1024), b""):
                            joined.write(block); part_hash.update(block)
                            joined_hash.update(block); part_bytes += len(block); joined_bytes += len(block)
                    if part_hash.hexdigest() != part["sha256"] or part_bytes != part["bytes"]:
                        raise SystemExit("Part checksum/size mismatch: " + part["path"])
            if joined_hash.hexdigest() != item["compressed_sha256"] or joined_bytes != item["compressed_bytes"]:
                raise SystemExit("Combined gzip checksum/size mismatch.")
            opener = lambda: gzip.open(compressed, "rb")
        output_hash = hashlib.sha256()
        output_bytes = 0
        try:
            with opener() as stream, target.open("xb") as out:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    out.write(block); output_hash.update(block); output_bytes += len(block)
            if output_hash.hexdigest() != item["original_sha256"] or output_bytes != item["original_bytes"]:
                raise RuntimeError("Restored RAW checksum/size mismatch.")
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        print(str(target) + "  SHA256 " + output_hash.hexdigest())

