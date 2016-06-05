#!/bin/bash

# Shell script to launch the coedit recommender

LAUNCH_DIR=`dirname "$0"`;
cd $LAUNCH_DIR/../
source set_paths.sh;

cd bin;
$PYTHON_EXECUTABLE coedit-server.py -v
