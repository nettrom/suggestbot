#!/bin/bash

# Shell script to launch the update of task categories for a given language

LAUNCH_DIR=`dirname "$0"`;
cd $LAUNCH_DIR/../
source set_paths.sh;

cd bin;
$PYTHON_EXECUTABLE update-revisions.py $1;
