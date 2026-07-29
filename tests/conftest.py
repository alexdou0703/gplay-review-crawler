import os
import sys

# Make src/ importable the same way app.py does at runtime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
