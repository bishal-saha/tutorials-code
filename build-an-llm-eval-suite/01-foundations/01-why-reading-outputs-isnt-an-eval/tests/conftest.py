import sys
from pathlib import Path

# Let tests import read_five.py directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
