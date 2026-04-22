# Withdraw Users Script

## Overview

This script is designed to offboard UMGC employees and students in Alma. It has the following steps:
1. Pull analytics report for Staff members to be offboarded
2. Compare the `STAFF_USER_THRESHOLD` environment variable to the number of staff returned. If the number of staff returned is greater than this variable, the program will assume the SIS load update of Status dates has not happened and will quit with an error message. This check prevents the accidental update of too many users in the event the SIS update of status dates has not happened.
3. Create an Alma set with up to 1000 staff members
4. If `RUN_JOBS` is true, run an Alma job to update the staff members as per UMGC offboarding practices
5. Pull analytics report for inactive students
6. Create an Alma set with all of these students (unlimited quantity supported)
7. If `RUN_JOBS` is true, run an Alma job to update the students as per UMGC offboarding practices.

## Quirks
1. This script can only offboard up to 1000 staff members at a time.

## Requirements

This script requires Python Version 3.10 or higher.


## Environment Variables

1. `API_KEY`: An Alma API key with 2 permissions: Analytics Read/Write, and Configuration Read/Write
2. `STAFF_USER_THRESHOLD`: If the number of staff to offboard (as returned by the Analytics Report) is greater than this number, the program will assume the SIS load update of Status dates has not happened and will quit with an error message. This check prevents the accidental update of too many users in the event the SIS update of status dates has not happened. This will also cancel the Student offboarding.

## Setup Steps

1. Create a new environment variable file called `.env` in the directory root, and copy the contents of `.env.example` into that file.
2. Fill in the API key and the `STAFF_USER_THRESHOLD` environment variables.
3. Create a python virtual environment with the command `python3 -m venv .venv`. The virtual environment will be named `.venv`
4. Activate the virtual environment with the command `source .venv/bin/activate` (linux/MacOS) or `.\.venv\Scripts\Activate.ps1` on Windows PowerShell.
5. Install requirements with `pip install -r requirements.txt`
6. You can then run the program with `python3 -m withdraw`

## Automating Script with CRON

This script can be run using a single shell line, which is useful for CRON scheduling:
`source .venv/bin/activate && python3 -m withdraw`