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

# Ask for 1.5GB of memory
#$ -l h_vmem=1536M

# add the paths to use the shared Pywikibot libraries
source $HOME/add_shared_pywikibot.sh

## There's one command-line argument, and that's the path to the
## configuration file for the language we're running.
## Also, use the specific virtual environment built for this.
$HOME/venv/opentask/bin/python \
    $HOME/projects/opentask/opentasks.py $1
