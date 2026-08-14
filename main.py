import asyncio
import importlib
import logging
import os
import sys

# Force Python to read source modules for this deployment and make the loaded file/version visible in Railway logs.
sys.dont_write_bytecode = True
importlib.invalidate_caches()

from app import main as facetalk_app

FORCE_BUILD_VERSION = "v3.5.1-force-rebuild-logo-3lang-splash"

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.info("FaceTalk launcher: %s", FORCE_BUILD_VERSION)
    logging.info("FaceTalk app.main loaded from: %s", os.path.abspath(facetalk_app.__file__))
    logging.info("FaceTalk app build: %s", getattr(facetalk_app, "BUILD_VERSION", "unknown"))
    asyncio.run(facetalk_app.main())
