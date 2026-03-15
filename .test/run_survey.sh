#!/bin/bash
export POCKETCODE_BASIC_CLI=1
source .venv/bin/activate
pocketcode --prompt '/stackvm run agent survey' --auto-confirm-tools << 'INPUTS'
My Survey
Question 1
Question 2

Answer 1
Answer 2
INPUTS
