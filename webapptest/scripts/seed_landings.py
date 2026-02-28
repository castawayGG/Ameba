#!/usr/bin/env python3
"""Seed the database with pre-built landing page templates.

Usage:
    docker compose run --rm web python scripts/seed_landings.py
"""
import sys
import os

# Ensure project root is on the path when running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.app import create_app
from web.extensions import db
from models.landing_page import LandingPage
from services.landing_templates import LANDING_TEMPLATES


def seed():
    app = create_app()
    with app.app_context():
        for key, tpl in LANDING_TEMPLATES.items():
            existing = db.session.query(LandingPage).filter_by(slug=tpl['slug']).first()
            if existing:
                existing.name = tpl['name']
                existing.html_content = tpl['html_content']
                existing.language = tpl['language']
                existing.theme = tpl['theme']
                print(f"Updated: {tpl['slug']}")
            else:
                landing = LandingPage(
                    slug=tpl['slug'],
                    name=tpl['name'],
                    html_content=tpl['html_content'],
                    language=tpl['language'],
                    theme=tpl['theme'],
                    is_active=True,
                )
                db.session.add(landing)
                print(f"Created: {tpl['slug']}")
        db.session.commit()
        print("Done!")


if __name__ == '__main__':
    seed()
