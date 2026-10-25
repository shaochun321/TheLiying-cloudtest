#!/usr/bin/env python3
"""Restore the exact RAW original for this one case. Standard library only; refuse overwrites."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path


class PartStream:
    def __init__(self, root, record):
        self.root, self.record = root, record
        self.index, self.file, self.current = 0, None, None
        self.part_hash = None
        self.total_hash, self.total_bytes = hashlib.sha256(), 0

    def read(self, size=-1):
        result = bytearray()
        while size < 0 or len(result) < size:
            if self.file is None:
                if self.index == len(self.record['parts']):
                    break
                self.current = self.record['parts'][self.index]
                relative = Path(self.current['path'])
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('Invalid part path')
                path = self.root / relative
                if path.stat().st_size != self.current['bytes']:
                    raise ValueError('Part size mismatch: ' + str(relative))
                self.file = path.open('rb')
                self.part_hash = hashlib.sha256()
            block = self.file.read(4 * 1024 * 1024 if size < 0 else size - len(result))
            if block:
                self.part_hash.update(block)
                self.total_hash.update(block)
                self.total_bytes += len(block)
                result.extend(block)
            else:
                self.file.close()
                self.file = None
                if self.part_hash.hexdigest() != self.current['sha256']:
                    raise ValueError('Part SHA256 mismatch: ' + self.current['path'])
                self.index += 1
        return bytes(result)

    def finish(self):
        if self.read(1):
            raise ValueError('Unexpected compressed bytes after gzip EOF')
        if self.total_bytes != self.record['gzip_bytes'] or self.total_hash.hexdigest() != self.record['gzip_sha256']:
            raise ValueError('Combined gzip identity mismatch')


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, default=Path('raw-originals'))
    parser.add_argument('--verify-only', action='store_true', help='Decompress and verify without writing RAW')
    parser.add_argument('--only', help='Restore or verify one named RAW')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / 'RAW_MANIFEST.json').read_text(encoding='utf-8'))
    if len(manifest['files']) != 1 or 'compressed_total_bytes' not in manifest:
        raise ValueError('Incomplete transport manifest')
    if not args.verify_only:
        args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for record in manifest['files']:
        if args.only and record['name'] != args.only:
            continue
        name = record['name']
        if Path(name).name != name:
            raise ValueError('Invalid RAW name')
        target = args.output_dir / name
        if not args.verify_only and target.exists():
            if target.stat().st_size != record['bytes'] or file_hash(target) != record['sha256']:
                raise FileExistsError('Refusing to overwrite different file: ' + str(target))
            result = {'name': name, 'bytes': record['bytes'], 'sha256': record['sha256'], 'result': 'PASS_EXISTING'}
            results.append(result)
            print(json.dumps(result), flush=True)
            continue
        stream = PartStream(root, record)
        digest, size = hashlib.sha256(), 0
        temporary = target.with_name(name + '.partial')
        output = None if args.verify_only else temporary.open('xb')
        try:
            with gzip.GzipFile(fileobj=stream, mode='rb') as source:
                while True:
                    block = source.read(4 * 1024 * 1024)
                    if not block:
                        break
                    digest.update(block)
                    size += len(block)
                    if output:
                        output.write(block)
            stream.finish()
            if size != record['bytes'] or digest.hexdigest() != record['sha256']:
                raise ValueError('Restored RAW identity mismatch: ' + name)
            if output:
                output.flush()
                os.fsync(output.fileno())
        finally:
            if output:
                output.close()
        if not args.verify_only:
            if target.exists():
                raise FileExistsError('Refusing overwrite: ' + str(target))
            temporary.rename(target)
        result = {'name': name, 'bytes': size, 'sha256': digest.hexdigest(), 'result': 'PASS'}
        results.append(result)
        print(json.dumps(result), flush=True)
    if not results:
        raise ValueError('Requested RAW not found in manifest')
    if not args.verify_only:
        report = args.output_dir / 'RESTORE_VERIFICATION.json'
        if not report.exists():
            report.write_text(json.dumps({'result': 'PASS', 'files': results}, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
