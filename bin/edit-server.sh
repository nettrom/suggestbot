#!/bin/bash

# Shell script to launch the edit profiler

LAUNCH_DIR=`dirname "$0"`;
cd $LAUNCH_DIR/../
source set_paths.sh;

cd bin;
$PYTHON_EXECUTABLE edit-server.py -v
