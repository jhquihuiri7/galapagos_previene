"""Pruebas unitarias de las validaciones que protegen el flujo."""

from __future__ import annotations

import math
import re

import pytest

from app.handlers import report_flow
from app.handlers.report_flow import normalize_description, validate_location
from app.keyboards import event_type_keyboard
from app.models import EVENT_TYPE_BUTTONS, EVENT_TYPE_LABELS, EventType


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (0, 0),
        (-0.75, -90.31),
        (-90, -180),
        (90, 180),
        ("-0.75", "-90.31"),
    ],
)
def test_validate_location_accepts_finite_coordinates_including_boundaries(
    latitude: object,
    longitude: object,
) -> None:
    assert validate_location(latitude, longitude) is True  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (-90.000001, 0),
        (90.000001, 0),
        (0, -180.000001),
        (0, 180.000001),
        (math.nan, 0),
        (0, math.inf),
        (True, 0),
        (0, False),
        (None, 0),
        ("Galápagos", 0),
    ],
)
def test_validate_location_rejects_invalid_or_non_finite_values(
    latitude: object,
    longitude: object,
) -> None:
    assert validate_location(latitude, longitude) is False  # type: ignore[arg-type]


def test_normalize_description_strips_only_outer_whitespace() -> None:
    text = "  Se observa humo cerca del sendero.  \n"

    assert normalize_description(text) == "Se observa humo cerca del sendero."


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        " " * 20,
        "123456789",
        " 123456789 ",
    ],
)
def test_normalize_description_rejects_non_text_or_less_than_ten_characters(
    text: str | None,
) -> None:
    assert normalize_description(text) is None


def test_normalize_description_accepts_exactly_ten_characters() -> None:
    assert normalize_description(" 1234567890 ") == "1234567890"


def test_event_catalog_covers_the_fifteen_official_codes() -> None:
    """El catálogo, sus etiquetas y sus botones no pueden desincronizarse."""

    expected = [
        "TSU",
        "ERV",
        "LLI",
        "INU",
        "OLJ",
        "SEQ",
        "CQM",
        "AMA",
        "PLG",
        "INF",
        "SIS",
        "COI",
        "DES",
        "CAD",
        "VDV",
    ]

    assert [event.value for event in EventType] == expected
    assert set(EVENT_TYPE_LABELS) == set(EventType)
    assert set(EVENT_TYPE_BUTTONS) == set(EventType)


def test_event_type_keyboard_lists_every_code_two_per_row() -> None:
    rows = event_type_keyboard().inline_keyboard
    buttons = [button for row in rows for button in row]

    assert max(len(row) for row in rows) == 2
    assert [button.callback_data for button in buttons] == [
        f"event:{event.value}" for event in EventType
    ]


def test_event_callback_pattern_only_accepts_current_codes() -> None:
    pattern = re.compile(report_flow._EVENT_CALLBACK_PATTERN)

    assert pattern.match("event:LLI")
    assert pattern.match("event:VDV")
    # Códigos retirados en la migración al catálogo oficial.
    assert pattern.match("event:RAIN") is None
    assert pattern.match("event:FIRE") is None
