#!/bin/bash

# Shell script to launch the update of and post of suggestions to subscribers

LAUNCH_DIR=`dirname "$0"`;
cd $LAUNCH_DIR/../
source set_paths.sh;

cd bin;
$PYTHON_EXECUTABLE post-to-subscribers.py $1;
