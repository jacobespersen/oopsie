"""Worker entrypoint — workaround for Python 3.14 event loop compatibility."""

import asyncio

from arq.worker import run_worker

from oopsie.worker.settings import WorkerSettings

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    run_worker(WorkerSettings)
