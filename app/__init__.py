from flask import Flask
from config import Config
from app.routes import bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    app.register_blueprint(bp)

    return app
