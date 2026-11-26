import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from emptyclean.gui import main
main()