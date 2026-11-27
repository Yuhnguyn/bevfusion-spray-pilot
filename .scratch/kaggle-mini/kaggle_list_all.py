#!/usr/bin/env python3
"""List every file in a Kaggle dataset by following Next Page Token.

The CLI prints the token on stdout above the table, so parse stdout and stop
only when the token is absent — a single page is NOT the whole listing.
"""
import collections
import json
import re
import subprocess
import sys


def list_files(slug, page_size=200, max_pages=2000):
    names, token, pages = [], None, 0
    while pages < max_pages:
        cmd = ["kaggle", "datasets", "files", slug, "--csv",
               "--page-size", str(page_size)]
        if token:
            cmd += ["--page-token", token]
        out = subprocess.run(cmd, capture_output=True, text=True).stdout
        match = re.search(r"Next Page Token = (\S+)", out)
        token = match.group(1) if match else None
        for line in out.splitlines():
            if not line or "," not in line:
                continue
            if line.startswith(("name,", "Warning", "Next Page Token")):
                continue
            name = line.split(",")[0]
            if name:
                names.append(name)
        pages += 1
        if not token:
            break
    return names, pages, token


def main():
    slug = sys.argv[1]
    names, pages, token = list_files(slug)
    counts = collections.Counter()
    for name in names:
        parts = name.split("/")
        counts["/".join(parts[:2]) if len(parts) > 1 else "<root>"] += 1
    print(f"DATASET {slug}")
    print(f"  pages={pages} files={len(names)} last_token={'yes' if token else 'none'}")
    print(f"  unique_top_dirs={len({n.split('/')[0] for n in names})}")
    for key, value in sorted(counts.items()):
        print(f"  {key:44s} {value}")
    json.dump(names, open(f"/tmp/files_{slug.replace('/', '_')}.json", "w"))


if __name__ == "__main__":
    main()
