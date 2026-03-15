#!/bin/bash
export POCKETCODE_BASIC_CLI=1
source .venv/bin/activate
pocketcode --prompt 'dummy' --auto-confirm-tools << 'INPUTS'
/flow agents.survey
/start

INPUTS
