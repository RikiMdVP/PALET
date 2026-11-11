"""Entry point of the PALET 2.0 command line: ``python -m palet <command>``."""

import sys

from palet.cli import main

if __name__ == "__main__":
    sys.exit(main())
