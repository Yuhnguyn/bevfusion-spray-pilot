import json
import re
import sys

MARKERS = (
    "SMOKE_DEVKIT_INSTALL",
    "SMOKE_DEVKIT_OK",
    "SMOKE_DEVKIT_VERIFY_FAILED",
    "MINI_SPLIT_OK",
    "MINI_SPLIT_FAILED",
    "SMOKE_INFO",
    "SMOKE_STEP",
    "SMOKE_OK",
    "SMOKE_FAILED",
    "PROBE_FAILED",
    "Traceback",
    "Error",
)


def main(path):
    raw = open(path).read().splitlines()
    text = []
    for line in raw:
        chunk = line.lstrip(",")
        try:
            obj = json.loads(chunk)
        except Exception:
            text.append(line)
            continue
        text.append(obj.get("data", "") if isinstance(obj, dict) else "")
    body = "".join(text)
    open(path + ".txt", "w").write(body)
    lines = body.splitlines()
    for line in lines:
        if any(m in line for m in MARKERS):
            print(line)
    print("--- last 25 lines ---")
    print("\n".join(lines[-25:]))


if __name__ == "__main__":
    main(sys.argv[1])