import sys

from calcucalo.cli import main

if __name__ == "__main__":
    sys.argv.insert(1, "prepare-dataset")
    raise SystemExit(main())
