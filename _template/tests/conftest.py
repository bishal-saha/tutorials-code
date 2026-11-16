import sys
from pathlib import Path

# Let tests import the folder's modules (main.py, src files) directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
