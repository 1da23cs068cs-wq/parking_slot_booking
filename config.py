"""
config.py — Flask + AWS RDS Configuration
Cloud-Based Parking Slot Booking System
"""
import os
from dotenv import load_dotenv

load_dotenv()  # Load variables from .env file

class Config:
    # ── Flask Settings ──────────────────────────────────────────────────────
    SECRET_KEY = os.getenv('SECRET_KEY', 'parking-secret-key-change-in-production')
    DEBUG = os.getenv('DEBUG', 'True') == 'True'

    # ── AWS RDS MySQL Connection Settings ───────────────────────────────────
    # Replace these with your actual AWS RDS credentials
    DB_HOST     = os.getenv('DB_HOST', 'parking-slotdb.czueuwkgimc0.ap-southeast-2.rds.amazonaws.com')
    DB_PORT     = int(os.getenv('DB_PORT', 3306))
    DB_NAME     = os.getenv('DB_NAME', 'parking_system')
    DB_USER     = os.getenv('DB_USER', 'admin')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '1DA23CS068')

    # ── For Local Development, use: ─────────────────────────────────────────
    # DB_HOST = 'localhost'
    # DB_USER = 'root'
    # DB_PASSWORD = 'your_local_password'
