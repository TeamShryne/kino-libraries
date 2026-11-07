#!/usr/bin/env python3
"""Create ABI-scoped runtime archives and a checksummed catalog from AARs."""

import hashlib
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ABIS = ("arm64-v8a", "armeabi-v7a", "x86", "x86_64")
ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = Path(os.environ["RUNNER_TEMP"]) / "upstream"
DIST = ROOT / "dist"
DIST.mkdir(exist_ok=True)
CORE_TAG = os.environ["CORE_TAG"]
IRONPRESS_TAG = os.environ["IRONPRESS_TAG"]
REPOSITORY = os.environ["CATALOG_REPOSITORY"]
RELEASE_TAG = f"runtime-{CORE_TAG}-{IRONPRESS_TAG}"


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
    with zipfile.ZipFile(aar) as source, zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        output.writestr("classes.jar", source.read(entry(source, "classes.jar")))
        native_name = find_native(source, abi, "libgojni.so")
        output.writestr("libgojni.so", source.read(entry(source, native_name)))
        output.writestr("library.json", json.dumps({"id": "kino-core", "version": CORE_TAG, "abi": abi}, separators=(",", ":")))
    return destination


def package_ironpress(aar: Path, abi: str) -> Path:
    destination = DIST / f"ironpress-{abi}.zip"
    with zipfile.ZipFile(aar) as source, zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        native_name = find_native(source, abi, "libironpress_android.so")
        output.writestr("libironpress_android.so", source.read(entry(source, native_name)))
        output.writestr("library.json", json.dumps({"id": "ironpress-pdf", "version": IRONPRESS_TAG, "abi": abi}, separators=(",", ":")))
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
ironpress_aar = UPSTREAM / "ironpress" / "ironpress-android.aar"
core_artifacts = [artifact(package_core(core_aar, abi), abi) for abi in ABIS]
ironpress_artifacts = [artifact(package_ironpress(ironpress_aar, abi), abi) for abi in ABIS]

catalog = {
    "schema_version": 1,
    "catalog_version": int(os.environ["RUN_ID"]),
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "libraries": [
        {
            "id": "kino-core",
            "name": "Kino Core",
            "version": CORE_TAG,
            "description": "DeepSeek account, chat, search, history, and file support.",
            "required_for": ["chat"],
            "format": "gomobile-runtime-zip-v1",
            "classes_file": "classes.jar",
            "native_library": "libgojni.so",
            "license": "MIT",
            "min_android_api": 26,
            "artifacts": core_artifacts,
        },
        {
            "id": "ironpress-pdf",
            "name": "IronPress PDF renderer",
            "version": IRONPRESS_TAG,
            "description": "Native paged HTML-to-PDF renderer.",
            "required_for": ["html_to_pdf"],
            "format": "jni-runtime-zip-v1",
            "native_library": "libironpress_android.so",
            "license": "MIT",
            "min_android_api": 26,
            "artifacts": ironpress_artifacts,
        },
    ],
}
(ROOT / "libraries.json").write_text(json.dumps(catalog, indent=2) + "\n")
