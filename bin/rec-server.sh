#!/bin/bash

# Shell script to launch the central recommendation server

LAUNCH_DIR=`dirname "$0"`;
cd $LAUNCH_DIR/../
source set_paths.sh;

cd bin;
$PYTHON_EXECUTABLE rec-server.py -v
