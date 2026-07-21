"""Guard the frontend asset lookup against the repo/container layout difference.

The repo keeps this module at backend/app/main.py, so the frontend directory is two
parents up. The deployed image flattens it to /app/app/main.py, where the same
directory is one parent up. A lookup that hardcodes either depth passes every local
test and then 404s only in production, which is how the /oauth/authorize page — the
one the entire browser consent flow depends on — nearly shipped broken.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


BUNDLED_ASSETS = ("index.html", "authorize.html")


def _main_module():
    """Import app.main lazily.

    get_settings() is lru_cached and app.main builds it at import time, so importing
    at module scope would populate that cache during test discovery and clobber the
    environment other tests set up before their own deferred import.
    """
    import app.main as main

    return main


class FrontendAssetLayoutTest(unittest.TestCase):
    def test_assets_resolve_in_the_repository_layout(self) -> None:
        main = _main_module()
        for asset in BUNDLED_ASSETS:
            self.assertTrue(main.frontend_asset(asset).exists(), f"{asset} missing from the repo layout")

    def test_assets_resolve_in_the_flattened_container_layout(self) -> None:
        """Simulate the image: /app/app/main.py next to /app/frontend/."""
        main = _main_module()
        with tempfile.TemporaryDirectory() as directory:
            # resolve() so the comparison survives macOS's /var -> /private/var symlink.
            container_root = Path(directory).resolve() / "app"
            (container_root / "app").mkdir(parents=True)
            (container_root / "frontend").mkdir()
            for asset in BUNDLED_ASSETS:
                (container_root / "frontend" / asset).write_text("<html></html>", encoding="utf-8")

            original = main.__file__
            main.__file__ = str(container_root / "app" / "main.py")
            try:
                for asset in BUNDLED_ASSETS:
                    resolved = main.frontend_asset(asset)
                    self.assertEqual(resolved, container_root / "frontend" / asset)
            finally:
                main.__file__ = original

    def test_a_missing_asset_fails_loudly_rather_than_silently(self) -> None:
        main = _main_module()
        with self.assertRaises(Exception) as caught:
            main.frontend_asset("definitely-not-bundled.html")
        self.assertIn("definitely-not-bundled.html", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
