"""Tests for genre normalization."""

import json
from datetime import datetime

from boringhannover.constants import BERLIN_TZ
from boringhannover.exporters import export_web_json
from boringhannover.genre import CANONICAL_GENRES, normalize_genre
from boringhannover.models import Event


class TestNormalizeGenre:
    """Tests for normalize_genre function."""

    def test_normalize_punk_variants(self) -> None:
        """Punk variants should normalize to 'Punk / Hardcore'."""
        assert normalize_genre("punk") == "Punk / Hardcore"
        assert normalize_genre("Punk") == "Punk / Hardcore"
        assert normalize_genre("PUNK") == "Punk / Hardcore"
        assert normalize_genre("punk rock") == "Punk / Hardcore"
        assert normalize_genre("hardcore") == "Punk / Hardcore"
        assert normalize_genre("hardcore punk") == "Punk / Hardcore"
        assert normalize_genre("post-punk") == "Punk / Hardcore"
        assert normalize_genre("postpunk") == "Punk / Hardcore"

    def test_normalize_electronic_variants(self) -> None:
        """Electronic variants should normalize to 'Electronic'."""
        assert normalize_genre("electronic") == "Electronic"
        assert normalize_genre("techno") == "Electronic"
        assert normalize_genre("house") == "Electronic"
        assert normalize_genre("trance") == "Electronic"
        assert normalize_genre("elektronisch") == "Electronic"
        assert normalize_genre("edm") == "Electronic"

    def test_normalize_rock_variants(self) -> None:
        """Rock variants should normalize to 'Rock'."""
        assert normalize_genre("rock") == "Rock"
        assert normalize_genre("indie") == "Rock"
        assert normalize_genre("alternative") == "Rock"
        assert normalize_genre("krautrock") == "Rock"
        assert normalize_genre("britpop") == "Rock"

    def test_normalize_metal_variants(self) -> None:
        """Metal variants should normalize to 'Metal'."""
        assert normalize_genre("metal") == "Metal"
        assert normalize_genre("heavy metal") == "Metal"
        assert normalize_genre("death metal") == "Metal"
        assert normalize_genre("neue deutsche härte") == "Metal"

    def test_normalize_hiphop_variants(self) -> None:
        """Hip-Hop variants should normalize to 'Hip-Hop'."""
        assert normalize_genre("hip hop") == "Hip-Hop"
        assert normalize_genre("hip-hop") == "Hip-Hop"
        assert normalize_genre("hiphop") == "Hip-Hop"
        assert normalize_genre("rap") == "Hip-Hop"

    def test_normalize_jazz_variants(self) -> None:
        """Jazz/Blues variants should normalize to 'Jazz / Blues'."""
        assert normalize_genre("jazz") == "Jazz / Blues"
        assert normalize_genre("blues") == "Jazz / Blues"
        assert normalize_genre("soul") == "Jazz / Blues"
        assert normalize_genre("funk") == "Jazz / Blues"

    def test_normalize_klassik_variants(self) -> None:
        """Classical variants should normalize to 'Klassik'."""
        assert normalize_genre("klassik") == "Klassik"
        assert normalize_genre("classical") == "Klassik"
        assert normalize_genre("orchestra") == "Klassik"

    def test_normalize_folk_variants(self) -> None:
        """Folk/World variants should normalize to 'Folk / World'."""
        assert normalize_genre("folk") == "Folk / World"
        assert normalize_genre("reggae") == "Folk / World"
        assert normalize_genre("ska") == "Folk / World"
        assert normalize_genre("schlager") == "Folk / World"
        assert normalize_genre("liedermacher") == "Folk / World"

    def test_normalize_pop_variants(self) -> None:
        """Pop variants should normalize to 'Pop'."""
        assert normalize_genre("pop") == "Pop"
        assert normalize_genre("synth-pop") == "Pop"
        assert normalize_genre("ndw") == "Pop"

    def test_normalize_unknown_returns_none(self) -> None:
        """Unknown genres should return None."""
        assert normalize_genre("zydeco") is None
        assert normalize_genre("polka") is None
        assert normalize_genre("unknown genre") is None

    def test_normalize_empty_returns_none(self) -> None:
        """Empty input should return None."""
        assert normalize_genre("") is None
        assert normalize_genre("   ") is None

    def test_normalize_case_insensitive(self) -> None:
        """Normalization should be case-insensitive."""
        assert normalize_genre("METAL") == "Metal"
        assert normalize_genre("Metal") == "Metal"
        assert normalize_genre("metal") == "Metal"
        assert normalize_genre("JAZZ") == "Jazz / Blues"

    def test_normalize_strips_whitespace(self) -> None:
        """Normalization should strip whitespace."""
        assert normalize_genre("  punk  ") == "Punk / Hardcore"
        assert normalize_genre("\trock\n") == "Rock"

    def test_normalize_genre_from_descriptive_tagline(self) -> None:
        """Known genre words inside descriptive taglines should normalize."""
        assert normalize_genre("Garage Punk") == "Punk / Hardcore"
        assert normalize_genre("Feine elektronische Musik") == "Electronic"
        assert normalize_genre("Indie Rock aus Hannover") == "Rock"

    def test_descriptive_tagline_without_genre_returns_none(self) -> None:
        """Artist billing must not be exposed as a genre."""
        assert normalize_genre("Mit Big Honey") is None


class TestCanonicalGenres:
    """Tests for CANONICAL_GENRES constant."""

    def test_canonical_genres_count(self) -> None:
        """Should have exactly 9 canonical genres."""
        assert len(CANONICAL_GENRES) == 9

    def test_canonical_genres_contains_expected(self) -> None:
        """Should contain all expected genres."""
        expected = {
            "Rock",
            "Punk / Hardcore",
            "Metal",
            "Pop",
            "Hip-Hop",
            "Electronic",
            "Jazz / Blues",
            "Klassik",
            "Folk / World",
        }
        assert set(CANONICAL_GENRES) == expected


def test_web_export_only_emits_canonical_genres(tmp_path) -> None:
    """The frontend JSON boundary must not expose arbitrary source labels."""
    events = [
        Event(
            title="Garage Night",
            date=datetime(2026, 8, 1, 20, 0, tzinfo=BERLIN_TZ),
            venue="Venue",
            url="https://example.com/garage",
            category="radar",
            metadata={"genre": "Garage Punk"},
        ),
        Event(
            title="Guest Night",
            date=datetime(2026, 8, 2, 20, 0, tzinfo=BERLIN_TZ),
            venue="Venue",
            url="https://example.com/guest",
            category="radar",
            metadata={"genre": "Mit Big Honey"},
        ),
    ]

    export_web_json([], events, tmp_path, 31, 2026)
    data = json.loads((tmp_path / "web_events.json").read_text(encoding="utf-8"))

    assert data["concerts"][0]["genre"] == "Punk / Hardcore"
    assert data["concerts"][1]["genre"] is None
