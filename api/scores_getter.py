import json
import os

from flask import Flask, jsonify
from upstash_redis import Redis

app = Flask(__name__)


@app.route("/api/scores_getter", methods=["GET"])
def get_scores():
    try:
        redis = Redis(
            url=os.environ["KV_REST_API_URL"],
            token=os.environ["KV_REST_API_TOKEN"]
        )

        scores = redis.get("scores_json")

        if scores is None:
            return jsonify({"error": "Scores not found"}), 404

        if isinstance(scores, str):
            scores = json.loads(scores)

        response = jsonify(scores)
        response.headers["Cache-Control"] = "no-store"

        return response

    except Exception as e:
        print(f"Error loading scores: {e}")
        return jsonify({"error": "Could not load scores"}), 500
