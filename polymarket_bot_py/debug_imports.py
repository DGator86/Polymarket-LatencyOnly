import asyncio
import json
import os
import sys
import time
import logging
from collections import deque
from typing import Optional, Dict, Any

print("Imports standard done")

import websockets
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType, Side

print("Imports external done")
