from __future__ import annotations

import argparse
import json

from a2.mcp.server import build_mcp_server
from deployment.a2.health import check_a2_readiness


def main() -> None:
    parser = argparse.ArgumentParser(description="A2 read-only MCP deployment entry point")
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--health", action="store_true")
    args = parser.parse_args()
    readiness = check_a2_readiness()
    if args.health:
        print(readiness.model_dump_json(indent=2))
        return
    if not readiness.ready:
        raise SystemExit(json.dumps(readiness.model_dump(mode="json"), ensure_ascii=False))
    server = build_mcp_server()
    if args.transport == "stdio":
        server.run("stdio")
    else:
        server.run(
            "streamable-http",
            host=args.host,
            port=args.port,
            streamable_http_path="/mcp",
            json_response=True,
            stateless_http=True,
            max_request_body_size=1_048_576,
        )


if __name__ == "__main__":
    main()
