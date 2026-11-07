# Kino runtime libraries

This repository hosts the public runtime library catalog used by Kino. `libraries.json` describes the supported libraries, versions, ABI-specific release URLs, byte sizes, and SHA-256 checksums. The Android app fetches the catalog over HTTPS, downloads only the matching ABI package, verifies it, and stores it in app-private storage.

Packages are attached to GitHub Releases and are not committed to this repository. Run **Publish runtime library catalog** from Actions to fetch checksum-pinned upstream releases, package their Android ABI payloads, publish a runtime release, and update `libraries.json`.

Initial catalog entries are Kino Core (chat and provider features) and IronPress PDF renderer (HTML-to-PDF). Keep release publishing manual so library updates are deliberate and reviewable.
