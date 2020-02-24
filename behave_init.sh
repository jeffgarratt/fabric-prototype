#!/bin/bash

# This script sets up variables that are required for packaging chaincode through the behave fabric prototype mechanism

# Export fabric samples folder as it is root of all required folders for peer executable.
if [ -z "$FABRIC_SAMPLES_DIR" ]
then
  echo "---- FABRIC_SAMPLES_DIR not set.  Please set to location of fabric samples install with binaries available. ----"
  exit -1
else
  echo "Using fabric samples in: " $FABRIC_SAMPLES_DIR
fi

# Make sure peer executable is in path (This is available after running bootstrap from samples
export PATH=$PATH:$FABRIC_SAMPLES_DIR/bin

# MSP config needed
export CORE_PEER_MSPCONFIGPATH=$FABRIC_SAMPLES_DIR/chaincode-docker-devmode/msp

# Config path
export FABRIC_CFG_PATH=$FABRIC_SAMPLES_DIR/config
