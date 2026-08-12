from __future__ import annotations

import argparse

from evaluation.preflight import write_preflight


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("output")
    args = parser.parse_args()
    result = write_preflight(args.manifest, args.output)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
