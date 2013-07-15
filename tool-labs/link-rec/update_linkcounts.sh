#!/bin/bash

# Name the job "ilcupdate".
#$ -N ilcupdate

# Tell the server we'll be running for a maximum of 24 hours (default is 6,
# which we'll easily break)
####$ -l h_rt=24:00:00

# Store output in a different place.
#$ -o $HOME/logs/inlink-update.out

# Store errors in a different place.
#$ -e $HOME/logs/inlink-update.err

# Ask for 512MB of memory
#$ -l h_vmem=512M

# Command-line option is the language we're updating for
python $HOME/link-rec/inlink-table-updater-2.6.py -l $1
