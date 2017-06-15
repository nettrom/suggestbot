#!/bin/bash -x

# Shell script to update the following environment variables
#
# SUGGESTBOT_DIR: is set to the current directory
# PYTHONPATH: adds ./libs and ./config
# PYWIKIBOT2_DIR: is set to Morten's pywikibot path
# NLTK_DATA is set to nltk_data underneath the current directory

# PYTHON_EXECUTABLE is set to whichever Python version we currently
# prefer to run.  It's here to make sure we actually have access to
# all the necessary modules (like MySQLdb) until we get around to
# having an account with them all to ourselves.

scriptdir=`pwd`;
export PYWIKIBOT2_DIR='/export/scratch/morten/suggestbot/pywikibot';
# export PYWIKIPEDIA_DIR='/export/scratch/morten/work/SuggestBot/pywikipedia';
export SUGGESTBOT_DIR=$scriptdir;
# export PYTHONPATH=$SUGGESTBOT_DIR
export NLTK_DATA=$scriptdir/nltk_data

# Load SuggestBot's own virtual environment
# source /export/scratch/morten/sbotenv/bin/activate
export PYTHON_EXECUTABLE="/export/scratch/morten/sb_py36_venv/bin/python3"
