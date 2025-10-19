#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Oct 15 19:11:33 2025

@author: sean
"""

from flask import Flask, request, jsonify
import os
from strava_functions import update_scores

# Vercel will automatically detect and run this Flask app
app = Flask(__name__)

# This handles all requests to /api/run_manual_task
@app.route('/api/manual_update_scores', methods=['POST'])
def handler():
    # 1. Security Check: Verify the secret token from the request header
    auth_header = request.headers.get('Authorization')
    expected_token = f"Bearer {os.environ.get('VERCEL_MANUAL_SECRET')}"

    if not auth_header or auth_header != expected_token:
        return jsonify(message="Unauthorized"), 401

    # 2. Your Script's Logic Goes Here
    # This function can now access any Vercel environment variable
    try:
        update_scores()

        # 3. Send a success response
        return jsonify(message="Script executed successfully."), 200

    except Exception as e:
        print(f"An error occurred: {e}")
        return jsonify(message="An error occurred during script execution."), 500