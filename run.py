"""Start a local demonstration. Python 3.11+ and no pip packages required."""
import argparse
import logging
import os
from pathlib import Path
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

from app.database import initialize, seed_demo
from app.server import Application
from app.config import load_env
from app.llm import build_classifier


class ThreadedServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--database", default=str(Path(__file__).parent / "instance" / "routing.sqlite3"))
    parser.add_argument("--sprint", type=int, choices=[1, 2], default=2)
    parser.add_argument("--demo", action="store_true", help="Create demonstration accounts explicitly.")
    parser.add_argument("--secure-cookies", action="store_true", help="Enable only behind HTTPS.")
    parser.add_argument("--ai", choices=["auto", "local", "gemini"], help="Override AI_ROUTER from .env.")
    args = parser.parse_args()
    load_env(Path(__file__).resolve().parent)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    initialize(args.database)
    if args.demo:
        seed_demo(args.database)
    try:
        classifier = build_classifier(Path(__file__).resolve().parent, args.ai)
    except ValueError as error:
        parser.error(str(error))
    app = Application(args.database, sprint=args.sprint, secure_cookies=args.secure_cookies, classifier=classifier)
    status = classifier.status()
    print(f"AI mode: {status['provider']} | Model: {status['model']}")
    if status['provider'] == 'gemini' and not status['configured']:
        print("Gemini key missing: requests will be saved for staff review. Run setup_gemini_windows.bat or python scripts/configure_gemini.py.")
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print("Development server exposed beyond localhost. Use synthetic data only.")
    try:
        with make_server(args.host, args.port, app, server_class=ThreadedServer) as server:
            print(f"\nAI Student Routing - Sprint {args.sprint}\nOpen http://{args.host}:{args.port}\nPress Ctrl+C to stop.\n", flush=True)
            server.serve_forever()
    except OSError as error:
        print(f"Could not start the server: {error}\nTry another port: python run.py --demo --port 8001")
        raise SystemExit(1) from error
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
