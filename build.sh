#!/bin/bash
cd "$(dirname "$0")"

mkdir -p build
cp -rp ./src/* build/

pip3 install -r requirements.txt -t build
