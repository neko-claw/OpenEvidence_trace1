from a3.cli.common import DB
from a3.indexing.chunking import chunk_evidence
from a3.storage.sqlite_store import SQLiteEvidenceStore
def main():
    with SQLiteEvidenceStore(DB) as store:
        for e in store.list_current_evidence(): c,s=chunk_evidence(e); store.replace_chunks(e,c,s)
        print(f"chunks={len(store.list_current_chunks())} spans={len(store.list_current_spans())}")
if __name__ == "__main__": main()
