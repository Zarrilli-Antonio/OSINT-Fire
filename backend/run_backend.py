"""Entry point of the packaged backend (PyInstaller). Also serves as the Maigret launcher: a frozen app has no `python -m`."""
import multiprocessing
import os
import sys


def main() -> None:
    multiprocessing.freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] == "--maigret":
        sys.argv = ["maigret", *sys.argv[2:]]
        from maigret.maigret import run
        run()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--mcp":  # MCP server over stdio for Claude Desktop & co. (the app must be running)
        from osint.mcp_server import build_server
        build_server().run()
        return
    import uvicorn
    from osint.main import app
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("OSINT_PORT", "8765")), log_level="warning")


if __name__ == "__main__":
    main()
