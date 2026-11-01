"""Single-process production scheduler; database leases/outbox also protect restarts."""

import logging
from contextlib import asynccontextmanager
from threading import Event, Thread

from .config import settings


def install_worker(app):
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        stop = Event()

        def work():
            from .bank_sync import jobs

            while not stop.wait(60):
                try:
                    jobs()
                except Exception:
                    logging.getLogger(__name__).warning("Bank background job failed; no credentials or provider payload logged")

        async with previous(application) as state:
            if settings.app_env == "production":
                Thread(target=work, name="bank-sync", daemon=True).start()
            try:
                yield state
            finally:
                stop.set()

    app.router.lifespan_context = lifespan
