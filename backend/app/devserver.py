"""Local dev entry point, run under `python -m watchfiles app.devserver.serve app`.

watchfiles restarts this process on code changes by terminating it, which is reliable on
Windows, unlike uvicorn --reload's console CTRL+C mechanism.
"""

import uvicorn


def serve() -> None:
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
