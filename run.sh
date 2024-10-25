#!/bin/bash
python server.py > ./logs/server_log.txt 2>&1 &
python client.py > ./logs/client_log.txt 2>&1 &
-testsr 0.2 0.2 test_figure.png
-send test_figure.png