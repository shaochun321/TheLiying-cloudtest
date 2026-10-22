#!/usr/bin/env python3
"""Create a lossless, Git-sized evidence bundle; never starts a solver."""
from pathlib import Path
import gzip, hashlib, json, shutil
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "delivery"
OUT.mkdir(exist_ok=False)
def digest(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()
sources = [p for p in ROOT.iterdir() if p.is_file() and not p.name.startswith(".")]
for folder in ("inputs", "runs"):
    sources.extend(p for p in (ROOT / folder).rglob("*") if p.is_file())
raw_delivery = []
for src in sorted(sources):
    rel = src.relative_to(ROOT)
    target = OUT / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix == ".raw" and src.stat().st_size > 96 * 1024 * 1024:
        original_sha = digest(src)
        temp = ROOT / ("." + src.name + ".delivery.gz")
        with src.open("rb") as inp, temp.open("wb") as compressed:
            with gzip.GzipFile(filename="", mode="wb", fileobj=compressed,
                               compresslevel=6, mtime=0) as stream:
                shutil.copyfileobj(inp, stream, length=1024 * 1024)
        uncompressed_hash = hashlib.sha256()
        uncompressed_bytes = 0
        with gzip.open(temp, "rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                uncompressed_hash.update(block); uncompressed_bytes += len(block)
        if uncompressed_hash.hexdigest() != original_sha or uncompressed_bytes != src.stat().st_size:
            raise RuntimeError("Lossless compression verification failed.")
        parts = []
        with temp.open("rb") as compressed:
            index = 1
            while True:
                block = compressed.read(48 * 1024 * 1024)
                if not block:
                    break
                part = target.with_name(target.name + ".gz.part" + str(index).zfill(3))
                part.write_bytes(block)
                parts.append({"path": str(part.relative_to(OUT)), "bytes": len(block),
                              "sha256": hashlib.sha256(block).hexdigest()})
                index += 1
        raw_delivery.append({
            "original_path": str(rel), "original_bytes": src.stat().st_size,
            "original_sha256": original_sha,
            "encoding": "gzip, split into ordered binary chunks",
            "compressed_bytes": temp.stat().st_size, "compressed_sha256": digest(temp),
            "lossless_decompression_verified": True, "parts": parts,
        })
        temp.unlink()
    else:
        shutil.copy2(src, target)
        if digest(src) != digest(target):
            raise RuntimeError("Bundle copy changed bytes: " + str(rel))
        if src.suffix == ".raw":
            raw_delivery.append({"original_path": str(rel), "original_bytes": src.stat().st_size,
                                 "original_sha256": digest(src), "encoding": "none",
                                 "delivery_path": str(rel)})
(OUT / "RAW_DELIVERY.json").write_text(json.dumps(raw_delivery, indent=2) + "\n")
files = sorted(p for p in OUT.rglob("*") if p.is_file())
if any(p.stat().st_size >= 100 * 1024 * 1024 for p in files):
    raise RuntimeError("A bundle file exceeds GitHub's per-file size limit.")
with (OUT / "SHA256SUMS").open("w", encoding="ascii", newline="\n") as f:
    for p in files:
        f.write(digest(p) + "  " + str(p.relative_to(OUT)) + "\n")
print(json.dumps({"delivery": str(OUT), "files": len(files) + 1,
    "total_bytes": sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file()),
    "raw_delivery": raw_delivery}, indent=2))

