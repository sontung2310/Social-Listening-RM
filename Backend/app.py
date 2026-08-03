from flask import Flask
from flask_cors import CORS
import config  # noqa: F401 — load env + put Backend root on sys.path
from api.views import api_bp
import sys

def create_app():
    app = Flask(__name__)
    CORS(app)
    app.register_blueprint(api_bp, url_prefix="/api")
    return app

if __name__ == "__main__":
    app = create_app()

    # Allow custom port argument, default to 8000
    port = 8000
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])

    app.run(host="127.0.0.1", port=port, debug=True)
