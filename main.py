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
from anthropic import Anthropic
from dotenv import load_dotenv
from urllib.parse import urlparse

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
