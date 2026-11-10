#!/usr/bin/env python3
"""Unsigned, device-free native regression; optional immutable baseline proof."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
BASELINE = "af865dee787734a11b518f267cdc9488c0f90a45"
CASES = ("path", "bytes", "copy", "grayscale", "size", "thumbnail", "arrays", "scalars")
FAILURES = {
    "path": "ownership regression: string disposed twice or borrowed",
    "bytes": "ownership regression: setBytes temporary released",
    "copy": "AddressSanitizer: heap-buffer-overflow",
    "grayscale": "ownership regression: grayscale initial picture released",
    "size": "ownership regression: size borrowed owner preserved",
    "thumbnail": "ownership regression: thumbnail borrowed input and owned output",
}


def build(source, destination):
    api = source / "4D Plugin API"
    subprocess.run([
        "clang++", "-std=c++17", "-x", "objective-c++", "-g",
        "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
        "-Wno-deprecated-declarations", "-Wno-extern-c-compat",
        "-include", "Cocoa/Cocoa.h", "-include", str(source / "4D Plugin_Prefix.pch"),
        "-I", str(api), "-I", str(api / "Classes"),
        str(ROOT / "tests/native_ownership.cpp"), str(api / "4DPluginAPI.c"),
        *map(str, sorted((api / "Classes").glob("*.cpp"))),
        "-framework", "Cocoa", "-framework", "Carbon", "-o", str(destination),
    ], check=True)


def run(binary, baseline=False):
    env = {**os.environ, "ASAN_OPTIONS": "detect_leaks=0:abort_on_error=1",
           "UBSAN_OPTIONS": "halt_on_error=1"}
    for case in CASES:
        for empty in ("allocated", "null"):
            result = subprocess.run([str(binary), case, empty], env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            failed = baseline and case not in ("arrays", "scalars")
            if failed:
                marker = FAILURES[case]
                if result.returncode == 0 or marker not in result.stderr:
                    raise RuntimeError(f"baseline did not reproduce {case}: {result.stderr}")
                print(f"EXPECTED BASELINE FAILURE {case} ({empty}): "
                      + next(line for line in result.stderr.splitlines() if marker in line))
            else:
                if result.returncode:
                    raise RuntimeError(f"{case} ({empty}): {result.stderr}")
                print(result.stdout.strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", action="store_true",
                        help="also prove named failures on immutable pre-fix sources")
    args = parser.parse_args()
    sdk_files = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", BASELINE, "4D Plugin API"],
        cwd=ROOT, text=True).splitlines()
    for name in sdk_files:
        if "/Classes/" not in name:
            original = subprocess.check_output(["git", "show", f"{BASELINE}:{name}"], cwd=ROOT)
            if (ROOT / name).read_bytes() != original:
                raise RuntimeError(f"bundled SDK changed: {name}")
    print(f"Bundled SDK byte-identical to {BASELINE}", flush=True)
    with tempfile.TemporaryDirectory(prefix="audio-ownership-") as directory:
        scratch = Path(directory)
        if args.baseline:
            baseline = scratch / "baseline"
            baseline.mkdir()
            paths = subprocess.check_output(
                ["git", "ls-tree", "-r", "--name-only", BASELINE,
                 "4D Plugin API", "4D Plugin_Prefix.pch"], cwd=ROOT, text=True).splitlines()
            for name in paths:
                target = baseline / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(subprocess.check_output(
                    ["git", "show", f"{BASELINE}:{name}"], cwd=ROOT))
            build(baseline, scratch / "baseline-test")
            run(scratch / "baseline-test", baseline=True)
        build(ROOT, scratch / "fixed-test")
        run(scratch / "fixed-test")


if __name__ == "__main__":
    main()
