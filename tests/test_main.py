import sys
import argparse
from unittest.mock import patch, MagicMock
from main import main

def test_main_help(capsys):
    with patch.object(sys, 'argv', ['main.py', '--help']):
        try:
            main()
        except SystemExit as e:
            assert e.code == 0
        out, err = capsys.readouterr()
        assert "Unified CLI" in out

def test_main_no_args(capsys):
    with patch.object(sys, 'argv', ['main.py']):
        try:
            main()
        except SystemExit as e:
            assert e.code == 1
        out, err = capsys.readouterr()
        assert "Error: No action specified" in out
