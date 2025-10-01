#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Sep 30 22:45:37 2025

@author: sean
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta
from dateutil import parser

def token_expired(expires_at):
    """Check if the Strava token is expired."""
    return time.time() >= expires_at

def refresh_strava_token(client_id, client_secret, refresh_token):
    """Refresh the Strava access token."""
    print("Strava token is expired, refreshing...")
    response = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
    )
    
    if response.status_code != 200:
        raise Exception(f"Token refresh failed: {response.text}")
    
    token_data = response.json()
    print("Token refreshed successfully.")
    #print("IMPORTANT: You must manually update the STRAVA_USERS secret in your GitHub repository with the new token values below.")
    #print(f"New tokens: {token_data}")
    return token_data

def get_activities(user_creds, after_timestamp):
    """Fetch recent activities for a user."""
    headers = {'Authorization': f'Bearer {user_creds["access_token"]}'}
    params = {'after': after_timestamp, 'per_page': 50}
    activities = []
    page = 1
    while True:
        params['page'] = page
        response = requests.get('https://www.strava.com/api/v3/athlete/activities', headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        if not data:
            break
        activities.extend(data)
        page += 1
    return activities