#!/bin/bash

# Shell script to launch the links recommender

LAUNCH_DIR=`dirname "$0"`;
cd $LAUNCH_DIR/../
source set_paths.sh;

cd bin;
$PYTHON_EXECUTABLE links-server.py -v
