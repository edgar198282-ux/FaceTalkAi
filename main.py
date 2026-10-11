import asyncio
import importlib
import logging
import os
import sys
import atexit
import resource
import signal
import time

# Force Python to read source modules for this deployment and make the loaded file/version visible in Railway logs.
sys.dont_write_bytecode = True
importlib.invalidate_caches()

from app import main as facetalk_app

FORCE_BUILD_VERSION = "v3.5.1-force-rebuild-logo-3lang-splash"

def _on_shutdown_signal(signum, frame):
    logging.error("PROCESS_DIAGNOSTIC shutdown_signal=%s pid=%s", signal.Signals(signum).name, os.getpid())
    raise SystemExit(128 + signum)


def _on_process_exit():
    logging.warning("PROCESS_DIAGNOSTIC interpreter_exiting pid=%s", os.getpid())


def _loop_exception_handler(loop, context):
    logging.error(
        "PROCESS_DIAGNOSTIC asyncio_unhandled_error=%s",
        context.get("message"),
        exc_info=(type(context["exception"]), context["exception"], context["exception"].__traceback__)
        if context.get("exception") else None,
    )
    loop.default_exception_handler(context)


async def _heartbeat():
    while True:
        await asyncio.sleep(60)
        rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        logging.info(
            "PROCESS_DIAGNOSTIC alive pid=%s uptime_s=%d peak_rss_mb=%.1f",
            os.getpid(), int(time.monotonic() - _START_TIME), rss_kb / 1024,
        )


async def _run_with_diagnostics():
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(_loop_exception_handler)
    heartbeat = asyncio.create_task(_heartbeat())
    try:
        await facetalk_app.main()
    except BaseException:
        logging.exception("PROCESS_DIAGNOSTIC main_coroutine_terminated")
        raise
    finally:
        heartbeat.cancel()
        logging.warning("PROCESS_DIAGNOSTIC main_coroutine_finished")


_START_TIME = time.monotonic()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.info("FaceTalk launcher: %s", FORCE_BUILD_VERSION)
    logging.info("FaceTalk app.main loaded from: %s", os.path.abspath(facetalk_app.__file__))
    logging.info("FaceTalk app build: %s", getattr(facetalk_app, "BUILD_VERSION", "unknown"))
    atexit.register(_on_process_exit)
    signal.signal(signal.SIGTERM, _on_shutdown_signal)
    asyncio.run(_run_with_diagnostics())
