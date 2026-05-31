#!/bin/bash
# Helper script to run AWS CLI with correct library path
DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib:$DYLD_LIBRARY_PATH aws "$@"
