#!/bin/bash
## Update the list of open tasks on a non-English Wikipedia

# Name the job "opentask".
#$ -N opentask

# Tell the server we'll be running for a maximum of 15 mins
#$ -l h_rt=00:15:00

# Store output in a different place.
#$ -o $HOME/logs/opentask.out

# Store errors in a different place.
#$ -e $HOME/logs/opentask.err

# Ask for 1GB of memory
#$ -l h_vmem=1024M

# source the bash profile to add pywikibot to the Python path
source $HOME/.bash_profile

## CLI parameters:
## 1: language code (e.g. "pl" for Polish)
## 2: the page to update
## 3: the path to the JSON task definition file
python $HOME/projects/opentask/opentasks.py -l $1 -p "${2}" -f $3
