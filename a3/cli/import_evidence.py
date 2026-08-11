import argparse
from a3.cli.common import DB, FIXTURE, load_jsonl
from a3.storage.sqlite_store import SQLiteEvidenceStore

def main():
    p=argparse.ArgumentParser(); p.add_argument("--input", default=str(FIXTURE)); a=p.parse_args()
    with SQLiteEvidenceStore(DB) as store:
        inserted=sum(store.insert_evidence(e) for e in load_jsonl(a.input)); print(f"inserted={inserted} current={len(store.list_current_evidence())}")
if __name__ == "__main__": main()
