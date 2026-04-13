# Withdraw Users Script

## Overview

This script is designed to offboard UMGC employees and students in Alma. It has the following steps:
1. Check the user associated with TEST_BARCODE to see whether the user has been updated this month. If the user has not, the program will assume the SIS load has not run and will abort. 
2. Pull analytics report for Staff members to be offboarded
3. Create an Alma set with up to 1000 staff members
4. If `RUN_JOBS` is true, run an Alma job to update the staff members as per UMGC offboarding practices
5. Pull analytics report for inactive students
6. Create an Alma set with all of these students (unlimited quantity supported)
7. If `RUN_JOBS` is true, run an Alma job to update the students as per UMGC offboarding practices.

## Quirks
1. This script can only offboard up to 1000 staff members.
2. The sets that this script creates must be deleted if you wish to run it again in the same day. 
3. The TEST_BARCODE is the test that determines whether SIS has been run. If this user has been updated for some OTHER reason and SIS has not run, the script will assume SIS has been run and will likely offboard unwanted users. 

## Requirements

This script requires Python Version 3.10 or higher.

## Setup Steps

1. Create a new environment variable file called `.env` in the directory root, and copy the contents of `.env.example` into that file.
2. Fill in the API key and test user barcode
3. Create a python virtual environment with the command `python3 -m venv .venv`. The virtual environment will be named `.venv`
4. Activate the virtual environment with the command `source .venv/bin/activate` (linux/MacOS) or `.\.venv\Scripts\Activate.ps1` on Windows PowerShell.
5. Install requirements with `pip install -r requirements.txt`
6. You can then run the program with `python3 -m withdraw`

## Automating Script with CRON

This script can be run using a single shell line, which is useful for CRON scheduling:
`source .venv/bin/activate && python3 -m withdraw`