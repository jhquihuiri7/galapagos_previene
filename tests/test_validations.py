"""Pruebas unitarias de las validaciones que protegen el flujo."""

from __future__ import annotations

import math

import pytest

from app.handlers.report_flow import normalize_description, validate_location


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
