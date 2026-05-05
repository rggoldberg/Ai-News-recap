"""
Weekly AI News Recap -- Monday Morning Email
=============================================
Automated pipeline: RSS feeds + AI Twitter -> Claude API -> email digest.
Runs via GitHub Actions every Monday at 7am EST.

Built by Ryan using AI-assisted development (Claude).
"""

import os
import json
import re
import smtplib
import feedparser
import requests
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from anthropic import Anthropic, OverloadedError
from dotenv import load_dotenv
from urllib.parse import urlparse
import time
import random

load_dotenv()

# -- Config --------------------------------------------------------------------

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")  # Gmail: use App Password
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER)

# How many days back to look for news
LOOKBACK_DAYS = 7

# -- Retry Logic for OverloadedError ------------------------------------------
def execute_request_with_retries(client, *args, **kwargs):
    max_retries = 5
    for attempt in range(max_retries):
        try:
            # Replace this with the actual API call
            return client.request(*args, **kwargs)
        except OverloadedError:
            wait_time = (2 ** attempt) + random.uniform(0, 1)
            print(f"Request failed due to OverloadedError. Retrying in {wait_time:.2f} seconds...")
            time.sleep(wait_time)
    raise Exception("Max retries exceeded. The Anthropic API remains overloaded.")


# Use execute_request_with_retries when performing requests using the Anthropic client.

# The rest of your main.py file will go here (unchanged from the file retrieved).