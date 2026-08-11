import argparse
from a3.cli.build_all import build
def main():
    p=argparse.ArgumentParser(); p.add_argument("--offline-smoke",action="store_true"); a=p.parse_args()
    build(real_embedding=not a.offline_smoke)
if __name__ == "__main__": main()
