#!/usr/bin/env python3
"""
Nexus Peripheral Control — Caelestia Material 3 Expressive Theme Engine
Dynamically loads and synchronizes color tokens from ~/.local/state/caelestia/scheme.json
with high-contrast light and dark mode terminal styling.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

STATE_DIR = Path.home() / ".local" / "state" / "caelestia"
SCHEME_FILE = STATE_DIR / "scheme.json"

DEFAULT_THEME = {
    "background": "#0F1015",
    "surface": "#1A1B23",
    "surface_lowest": "#121318",
    "surface_container": "#242531",
    "surface_high": "#2E303E",
    "surface_highest": "#383B4C",
    "primary": "#D0BCFF",
    "on_primary": "#381E72",
    "primary_container": "#4F378B",
    "on_primary_container": "#EADDFF",
    "secondary": "#CCC2DC",
    "secondary_container": "#4A4458",
    "tertiary": "#EFB8C8",
    "error": "#F2B8B5",
    "outline": "#79747E",
    "outline_variant": "#49454F",
    "text": "#E6E1E5",
    "subtext0": "#CAC4D0",
    "accent_green": "#76FF03",
    "accent_cyan": "#00E5FF",
    "mode": "dark",
}


@dataclass(frozen=True)
class ThemeTokens:
    background: str
    surface: str
    surface_lowest: str
    surface_container: str
    surface_high: str
    surface_highest: str
    primary: str
    on_primary: str
    primary_container: str
    on_primary_container: str
    secondary: str
    secondary_container: str
    tertiary: str
    error: str
    outline: str
    outline_variant: str
    text: str
    subtext0: str
    accent_green: str
    accent_cyan: str
    mode: str = "dark"
    source: str = "dark M3 fallback"

    @staticmethod
    def _hex(value: object, fallback: str) -> str:
        if not isinstance(value, str):
            return fallback
        candidate = value.strip()
        if not candidate.startswith("#"):
            candidate = f"#{candidate}"
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", candidate):
            return fallback
        return candidate.upper()

    @classmethod
    def load(cls, path: Path = SCHEME_FILE) -> ThemeTokens:
        values = dict(DEFAULT_THEME)
        aliases = {
            "background": ("background",),
            "surface": ("surface",),
            "surface_lowest": ("surfaceContainerLowest", "surface_lowest", "crust"),
            "surface_container": ("surfaceContainer", "surface_container", "surface0"),
            "surface_high": ("surfaceContainerHigh", "surface_high", "surface1"),
            "surface_highest": ("surfaceContainerHighest", "surface_highest", "surface2"),
            "primary": ("primary",),
            "on_primary": ("onPrimary", "on_primary"),
            "primary_container": ("primaryContainer", "primary_container"),
            "on_primary_container": ("onPrimaryContainer", "on_primary_container"),
            "secondary": ("secondary",),
            "secondary_container": ("secondaryContainer", "secondary_container"),
            "tertiary": ("tertiary",),
            "error": ("error",),
            "outline": ("outline",),
            "outline_variant": ("outlineVariant", "outline_variant"),
            "text": ("text", "onSurface", "on_surface"),
            "subtext0": ("subtext0", "subtext1", "onSurfaceVariant", "on_surface_variant"),
        }
        source_name = "dark M3 fallback"
        if path.exists():
            try:
                raw_json = json.loads(path.read_text(encoding="utf-8"))
                values["mode"] = raw_json.get("mode", "dark")
                colors = raw_json.get("colours", raw_json.get("colors", raw_json))
                if isinstance(colors, dict):
                    for role, keys in aliases.items():
                        raw_val = next((colors[k] for k in keys if k in colors), None)
                        if raw_val:
                            values[role] = cls._hex(raw_val, values[role])
                source_name = f"Caelestia ({path.name})"
            except Exception:
                source_name = "dark M3 fallback (error reading scheme)"
        return cls(**values, source=source_name)


def generate_tcss(tokens: ThemeTokens) -> str:
    """Generate high-contrast dynamic Textual CSS with Caelestia Material 3 color tokens."""
    is_light = tokens.mode == "light"
    # Choose high-contrast accent highlights for light vs dark mode
    highlight_color = tokens.primary if is_light else tokens.accent_cyan
    gauge_bg = tokens.surface_high

    return f"""
Screen {{
    background: {tokens.background};
    color: {tokens.text};
}}

Header {{
    background: {tokens.surface_container};
    color: {tokens.primary};
    dock: top;
    height: 3;
    content-align: center middle;
    text-style: bold;
    border-bottom: solid {tokens.outline_variant};
}}

HeaderTitle {{
    color: {tokens.primary};
    text-style: bold;
}}

HeaderClock {{
    color: {tokens.text};
    text-style: bold;
}}

Footer {{
    background: {tokens.surface_container};
    color: {tokens.text};
    dock: bottom;
    height: 1;
    border-top: solid {tokens.outline_variant};
}}

FooterKey {{
    background: transparent;
}}

FooterKey .footer-key--key {{
    background: {tokens.primary};
    color: {tokens.on_primary};
    text-style: bold;
    padding: 0 1;
}}

FooterKey .footer-key--description {{
    color: {tokens.text};
    text-style: bold;
    padding: 0 1 0 0;
}}

FooterKey:hover {{
    background: {tokens.surface_high};
}}

FooterLabel {{
    color: {tokens.text};
    text-style: bold;
}}

TabbedContent {{
    height: 1fr;
    background: {tokens.background};
}}

Tabs {{
    background: {tokens.surface_container};
    border-bottom: solid {tokens.outline_variant};
    height: 3;
}}

Tabs Tab {{
    padding: 0 2;
    color: {tokens.text};
    background: transparent;
    text-style: bold;
}}

Tabs Tab:hover {{
    color: {tokens.primary};
    background: {tokens.surface_high};
}}

Tabs Tab.-active {{
    color: {tokens.on_primary};
    background: {tokens.primary};
    text-style: bold;
}}

Tabs:focus & .-active {{
    color: {tokens.on_primary};
    background: {tokens.primary};
    text-style: bold;
}}

Underline > .underline--bar {{
    color: {tokens.primary};
    background: {tokens.surface_high};
}}

TabPane {{
    padding: 1 2;
    background: {tokens.background};
}}

.bento-grid {{
    layout: grid;
    grid-size: 2 1;
    grid-columns: 1fr 1fr;
    grid-gutter: 2;
    height: 1fr;
}}

.device-card {{
    background: {tokens.surface_container};
    border: solid {tokens.primary};
    padding: 1 2;
    height: 100%;
}}

.device-card:hover {{
    border: double {tokens.primary};
}}

.card-title {{
    color: {tokens.primary};
    text-style: bold;
    margin-bottom: 1;
}}

.status-badge {{
    background: {tokens.primary_container};
    color: {tokens.on_primary_container};
    padding: 0 1;
    margin-bottom: 1;
    width: auto;
    text-style: bold;
}}

.info-label {{
    color: {tokens.secondary};
    text-style: bold;
    margin-top: 1;
}}

.value-text {{
    color: {tokens.text};
    text-style: bold;
}}

.highlight-val {{
    color: {highlight_color};
    text-style: bold;
}}

ProgressBar {{
    margin: 1 0;
    height: 1;
}}

Bar > .bar--bar {{
    color: {tokens.accent_green if not is_light else tokens.primary};
    background: {gauge_bg};
}}

Button {{
    background: {tokens.surface_high};
    color: {tokens.text};
    border: solid {tokens.outline_variant};
    margin-top: 1;
    min-width: 14;
    text-style: bold;
}}

Button:hover {{
    background: {tokens.primary};
    color: {tokens.on_primary};
}}

Button:focus {{
    background: {tokens.primary_container};
    color: {tokens.on_primary_container};
    border: solid {tokens.primary};
}}

Select {{
    margin-top: 1;
    background: {tokens.surface};
    border: solid {tokens.outline_variant};
    color: {tokens.text};
}}

SelectOverlay {{
    background: {tokens.surface_container};
    color: {tokens.text};
    border: solid {tokens.primary};
}}

Input {{
    background: {tokens.surface};
    border: solid {tokens.outline_variant};
    color: {tokens.text};
    margin-top: 1;
}}

Input:focus {{
    border: solid {tokens.primary};
}}

#log-container {{
    height: 6;
    margin: 0 2 1 2;
    background: {tokens.surface_container};
    border: solid {tokens.outline_variant};
    padding: 0 1;
}}

Log {{
    background: {tokens.surface_container};
    color: {tokens.text};
}}

.home-hero-pill {{
    background: {tokens.primary_container};
    border: solid {tokens.primary};
    padding: 0 2;
    margin-bottom: 1;
    height: 3;
    content-align: center middle;
}}

.hero-title {{
    color: {tokens.on_primary_container};
    text-style: bold;
}}

.tab-subnav {{
    height: 3;
    margin-bottom: 1;
    content-align: center middle;
}}

.tab-heading {{
    color: {tokens.primary};
    text-style: bold;
    width: 1fr;
}}

.btn-back {{
    background: {tokens.surface_high};
    color: {tokens.text};
    min-width: 22;
    text-style: bold;
}}

.btn-primary {{
    background: {tokens.primary};
    color: {tokens.on_primary};
    text-style: bold;
}}

.btn-primary:hover {{
    background: {tokens.primary_container};
    color: {tokens.on_primary_container};
}}
"""
