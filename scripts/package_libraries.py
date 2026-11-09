#!/usr/bin/env python3
"""Create ABI-scoped runtime archives and a checksummed catalog from AARs."""

import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ABIS = ("arm64-v8a", "armeabi-v7a", "x86", "x86_64")
ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = Path(os.environ["RUNNER_TEMP"]) / "upstream"
DIST = ROOT / "dist"
DIST.mkdir(exist_ok=True)
CORE_TAG = os.environ["CORE_TAG"]
REPOSITORY = os.environ["CATALOG_REPOSITORY"]
RUN_ID = os.environ["RUN_ID"]
CORE_PACKAGE_VERSION = f"{CORE_TAG}-dex1"
RELEASE_TAG = f"runtime-{CORE_TAG}-r{RUN_ID}"


def entry(zip_file: zipfile.ZipFile, path: str) -> zipfile.ZipInfo:
    try:
        return zip_file.getinfo(path)
    except KeyError as error:
        raise RuntimeError(f"Required AAR entry is missing: {path}") from error


def find_native(zip_file: zipfile.ZipFile, abi: str, expected: str) -> str:
    candidates = [name for name in zip_file.namelist() if name.startswith(f"jni/{abi}/") and name.endswith(".so")]
    matches = [name for name in candidates if name.rsplit("/", 1)[-1] == expected]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one jni/{abi}/{expected}, found {matches}")
    return matches[0]


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def package_core(aar: Path, abi: str) -> Path:
    destination = DIST / f"kino-core-{abi}.zip"
    with tempfile.TemporaryDirectory() as temporary:
        temporary_path = Path(temporary)
        class_jar = temporary_path / "source-classes.jar"
        with zipfile.ZipFile(aar) as source:
            class_jar.write_bytes(source.read(entry(source, "classes.jar")))
            native_name = find_native(source, abi, "libgojni.so")
            native_bytes = source.read(entry(source, native_name))
        dex_dir = temporary_path / "dex"
        dex_dir.mkdir()
        subprocess.run([os.environ["D8_PATH"], "--min-api", "26", "--output", str(dex_dir), str(class_jar)], check=True)
        dex_files = sorted(dex_dir.glob("classes*.dex"))
        if not dex_files or dex_files[0].name != "classes.dex":
            raise RuntimeError("D8 did not produce classes.dex for Kino Core")
        # DexClassLoader accepts jars containing DEX entries; a raw JVM classes.jar is not executable on Android.
        dex_jar = temporary_path / "classes.jar"
        with zipfile.ZipFile(dex_jar, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as jar:
            for dex_file in dex_files:
                jar.write(dex_file, dex_file.name)
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as output:
            output.write(dex_jar, "classes.jar")
            output.writestr("libgojni.so", native_bytes)
            output.writestr("library.json", json.dumps({"id": "kino-core", "version": CORE_PACKAGE_VERSION, "source_version": CORE_TAG, "abi": abi}, separators=(",", ":")))
    return destination


def artifact(path: Path, abi: str) -> dict:
    return {
        "abi": abi,
        "file_name": path.name,
        "download_url": f"https://github.com/{REPOSITORY}/releases/download/{RELEASE_TAG}/{path.name}",
        "sha256": digest(path),
        "size_bytes": path.stat().st_size,
    }


core_aar = UPSTREAM / "core" / "kino-core.aar"
core_artifacts = [artifact(package_core(core_aar, abi), abi) for abi in ABIS]

catalog = {
    "schema_version": 1,
    "catalog_version": int(RUN_ID),
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "libraries": [
        {
            "id": "kino-core",
            "name": "Kino Core",
            "version": CORE_PACKAGE_VERSION,
            "source_version": CORE_TAG,
            "description": "DeepSeek account, chat, search, history, and file support.",
            "required_for": ["chat"],
            "format": "gomobile-dex-runtime-zip-v1",
            "classes_file": "classes.jar",
            "native_library": "libgojni.so",
            "license": "MIT",
            "min_android_api": 26,
            "artifacts": core_artifacts,
        },
    ],
}
(ROOT / "libraries.json").write_text(json.dumps(catalog, indent=2) + "\n")
