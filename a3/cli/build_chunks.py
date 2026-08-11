import argparse

from a3.cli.common import DEFAULT_CONFIG
from a3.config import ConfigLoader
from a3.indexing.chunking import ChunkPolicy, chunk_evidence
from a3.storage.sqlite_store import SQLiteEvidenceStore


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    loaded = ConfigLoader.load(parser.parse_args().config); cfg = loaded.config.chunk_policy
    policy = ChunkPolicy(version=cfg.version, max_chars=cfg.max_chars,
        overlap_chars=cfg.overlap_chars, natural_boundary_ratio=cfg.natural_boundary_ratio)
    with SQLiteEvidenceStore(loaded.database_path) as store:
        for evidence in store.list_current_evidence():
            chunks, spans = chunk_evidence(evidence, policy); store.replace_chunks(evidence, chunks, spans)
        print(f"chunks={len(store.list_current_chunks())} spans={len(store.list_current_spans())}")


if __name__ == "__main__": main()
