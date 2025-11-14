"""
Unit tests for the movie scraper functionality.
Tests are written before implementation following TDD approach.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json
from typing import Dict, List, Any

# Import from our new modular structure
from src.kinoweek.scraper import scrape_movies
from src.kinoweek.notifier import format_message, send_telegram, notify
from src.kinoweek.main import run_scraper, main


class TestScrapeMovies:
    """Test the core scraping functionality."""

    def test_scrape_movies_returns_dict(self):
        """Test that scrape_movies returns a dictionary with expected structure."""
        result = scrape_movies()
        assert isinstance(result, dict)

    def test_scrape_movies_has_correct_data_structure(self):
        """Test that returned data has correct nested structure."""
        result = scrape_movies()
        for date, movies in result.items():
            assert isinstance(date, str)
            assert isinstance(movies, dict)
            for title, showtimes in movies.items():
                assert isinstance(title, str)
                assert isinstance(showtimes, list)
                for showtime in showtimes:
                    assert isinstance(showtime, str)

    @patch('src.kinoweek.scraper.sync_playwright')
    def test_scrape_movies_handles_browser_errors(self, mock_playwright):
        """Test that browser errors are handled gracefully."""
        mock_playwright.return_value.__enter__.side_effect = Exception("Browser failed")
        with pytest.raises(Exception):
            scrape_movies()


class TestFormatMessage:
    """Test the message formatting functionality."""

    def test_format_message_returns_string(self):
        """Test that format_message returns a string."""
        test_data = {"Mon 24.11": {"Wicked": ["19:30 (Cinema 10, 2D OV)"]}}
        result = format_message(test_data)
        assert isinstance(result, str)

    def test_format_message_includes_all_data(self):
        """Test that formatted message includes all movie data."""
        test_data = {
            "Mon 24.11": {
                "Wicked": ["19:30 (Cinema 10, 2D OV)", "16:45 (Cinema 10, 2D OmU)"],
                "Dune": ["20:00 (Cinema 5, 2D OV)"]
            }
        }
        result = format_message(test_data)
        assert "Mon 24.11" in result
        assert "Wicked" in result
        assert "19:30 (Cinema 10, 2D OV)" in result
        assert "Dune" in result

    def test_format_message_handles_empty_data(self):
        """Test that empty data is handled gracefully."""
        test_data = {}
        result = format_message(test_data)
        assert isinstance(result, str)
        assert "No movies found" in result

    def test_format_message_respects_telegram_limits(self):
        """Test that formatted message doesn't exceed Telegram limits."""
        test_data = {"Mon 24.11": {"Wicked": ["19:30 (Cinema 10, 2D OV)"] * 1000}}
        result = format_message(test_data)
        assert len(result) <= 4096  # Telegram message limit


class TestSendTelegram:
    """Test the Telegram notification functionality."""

    @patch('src.kinoweek.notifier.requests.post')
    @patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test_token', 'TELEGRAM_CHAT_ID': 'test_chat'})
    def test_send_telegram_makes_api_call(self, mock_post):
        """Test that send_telegram makes correct API call."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        message = "Test message"
        result = send_telegram(message)
        mock_post.assert_called_once()
        assert result is True

    @patch('src.kinoweek.notifier.requests.post')
    @patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test_token', 'TELEGRAM_CHAT_ID': 'test_chat'})
    def test_send_telegram_handles_api_error(self, mock_post):
        """Test that API errors are handled properly."""
        mock_post.return_value.status_code = 400
        mock_post.return_value.json.return_value = {"ok": False, "error": "Bad request"}
        message = "Test message"
        result = send_telegram(message)
        assert result is False

    @patch('src.kinoweek.notifier.requests.post')
    @patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test_token', 'TELEGRAM_CHAT_ID': 'test_chat'})
    def test_send_telegram_handles_network_error(self, mock_post):
        """Test that network errors are handled properly."""
        mock_post.side_effect = Exception("Network error")
        message = "Test message"
        result = send_telegram(message)
        assert result is False

    @patch.dict('os.environ', {}, clear=True)
    def test_send_telegram_requires_env_vars(self):
        """Test that environment variables are required."""
        with pytest.raises(Exception):
            send_telegram("test")


class TestIntegration:
    """Integration tests for the complete workflow."""

    @patch('src.kinoweek.main.notify')
    @patch('src.kinoweek.main.scrape_movies')
    def test_full_workflow(self, mock_scrape, mock_notify):
        """Test the complete scraping and notification workflow."""
        mock_scrape.return_value = {"Mon 24.11": {"Wicked": ["19:30 (Cinema 10, 2D OV)"]}}
        mock_notify.return_value = True
        
        # Test the main() function
        result = run_scraper(local_only=False)
        assert result is True
        mock_scrape.assert_called_once()
        mock_notify.assert_called_once_with(mock_scrape.return_value, local_only=False)


class TestDataValidation:
    """Test data validation and edge cases."""

    def test_validate_movie_data_structure(self):
        """Test validation of movie data structure."""
        # valid_data = {"Mon 24.11": {"Wicked": ["19:30 (Cinema 10, 2D OV)"]}}
        # invalid_data = {"invalid": "structure"}
        
        # assert validate_movie_data(valid_data) is True
        # assert validate_movie_data(invalid_data) is False
        pytest.skip("Validation function not implemented yet")

    def test_handle_missing_website_elements(self):
        """Test handling of missing website elements."""
        # This would test the scraper's robustness
        pytest.skip("Scraper not implemented yet")

    def test_handle_empty_schedule(self):
        """Test handling of empty movie schedule."""
        # Test when no movies are found for a day
        pytest.skip("Scraper not implemented yet")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
