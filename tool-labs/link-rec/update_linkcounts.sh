#!/bin/bash

# Name the job "ilcupdate".
#$ -N ilcupdate

# Tell the server we'll be running for a maximum of 24 hours
#$ -l h_rt=24:00:00

# Store output in a different place.
#$ -o $HOME/logs/inlink-update.out

# Store errors in a different place.
#$ -e $HOME/logs/inlink-update.err

# Ask for 1GB of memory
#$ -l h_vmem=1024M

# Run on trusty to have all necessary libraries
#$ -l release=trusty

# Command-line option is the language we're updating for
$HOME/venv/3.4/bin/python3 $HOME/link-rec/inlink-table-updater.py $1
