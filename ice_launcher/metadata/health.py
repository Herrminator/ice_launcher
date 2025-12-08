import sys, argparse, requests
from typing import Any

from ..main import __version__
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 9854

def get_status(args: argparse.Namespace) -> dict[str, Any]:
    rsp = requests.get(f"http://{args.host}:{args.port}/api/status.json")
    rsp.raise_for_status()
    return rsp.json()

def verbose(args: argparse.Namespace, message: str) -> None:
    if args.verbose or args.errors > 0 or args.warnings > 0:
        print(message, file=sys.stderr if args.errors > 0 or args.warnings > 0 else sys.stdout)
    
def check_status(args: argparse.Namespace, data: dict[str, Any]) -> int:
    args.errors = 0
    args.warnings = 0
    if "icecast" not in data:
        print("Error: 'icecast' section missing in status data", file=sys.stderr)
        args.errors += 1
    icecast = data.get("icecast", {})
    icecast_sources = icecast.get("source", {})
    
    ns = len(icecast_sources)
    nl = icecast.get("listeners", 0)
    nc = sum(len(clients) for clients in data.get("clients", {}).values())
    np = len(data.get("processes", {}))
    nd = len(data.get("metadata", {}))
    if ns != nc: args.errors += 1
    if ns != np: args.errors += 1
    if ns >  0 and nl == 0: args.errors += 1
    if np >  nd: args.warnings += 1
    verbose(args, f"Found {ns} mount(s) on icecast server.")
    verbose(args, f"Found {nl} listeners(s) connected to icecast server.")
    verbose(args, f"Found {nc} total client(s) connected to ice-launcher.")
    verbose(args, f"Found {np} mount process(es) running on ice-launcher.")
    verbose(args, f"Found {nd} metadata updater(s) running on ice-launcher.")
    stale = dict(filter(lambda m: int(m[1].get("listeners", 0)) == 0, icecast_sources.items()))
    for mount, source in stale.items():
        args.errors += 1
        verbose(args, f"Mount '{mount}' has no more listeners connected.")
    

    return args.errors


def main(argv=tuple(sys.argv[1:])) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(       "--host",    default=DEFAULT_HOST, help="Host to bind the health check server to")
    ap.add_argument(       "--port",    default=DEFAULT_PORT, type=int, help="Port to bind the health check server to")
    ap.add_argument("-v", "--verbose",  default=False,        action="store_true", help="Enable verbose output")
    ap.add_argument("-V", "--version",  action="version",     version=f"%(prog)s {__version__}, Python {sys.version}")
    args = ap.parse_args(argv)

    try:
        data = get_status(args)
    except Exception as exc:
        print(f"Error getting ice-launcher status: {exc}", file=sys.stderr)
        return 1
    
    errors = check_status(args, data)
    
    if errors == 0:
        print("ice-launcher health checks OK.")
    else:
        print(f"ice-launcher health checks failed with {errors} error(s).", file=sys.stderr)
    return errors

if __name__ == "__main__":
    sys.exit(main())