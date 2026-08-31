import os
import sys

# tests import "src.*" and "main"; without this pytest only sees its own rootdir
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
