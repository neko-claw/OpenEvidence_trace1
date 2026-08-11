import argparse

from a3.cli.common import DEFAULT_CONFIG, load_jsonl
from a3.config import ConfigLoader
from a3.storage.sqlite_store import SQLiteEvidenceStore


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--input"); args = parser.parse_args(); loaded = ConfigLoader.load(args.config)
    source = args.input or loaded.fixture_path
    with SQLiteEvidenceStore(loaded.database_path) as store:
        inserted = sum(store.insert_evidence(evidence) for evidence in load_jsonl(source))
        print(f"inserted={inserted} current={len(store.list_current_evidence())}")


if __name__ == "__main__": main()
