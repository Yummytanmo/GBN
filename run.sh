#!/bin/bash
python server.py > ./logs/server_log.txt 2>&1 &
python client.py > ./logs/client_log.txt 2>&1 &