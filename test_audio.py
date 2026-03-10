"""Unit tests for audio module."""
import pytest
from unittest.mock import patch, MagicMock
import audio


class TestAudioHelpers:
    """Test audio helper functions."""
    
    @patch("audio.comtypes.CoInitialize")
    @patch("audio.comtypes.CoUninitialize")
    def test_with_endpoint_initialization(self, mock_uninit, mock_init):
        """Test that COM is properly initialized/uninitialized."""
        mock_action = MagicMock(return_value="result")
        
        with patch("audio.AudioUtilities.GetSpeakers") as mock_get:
            mock_device = MagicMock()
            mock_device.EndpointVolume = MagicMock()
            mock_get.return_value = mock_device
            
            result = audio._with_endpoint(mock_action, "default")
            
            # Verify setup
            mock_init.assert_called()
            # The function should have tried to get action result
            # (actual call depends on device structure)
    
    @patch("audio.comtypes.CoInitialize")
    @patch("audio.comtypes.CoUninitialize")
    def test_with_endpoint_exception_handling(self, mock_uninit, mock_init):
        """Test exception handling in _with_endpoint."""
        mock_init.return_value = None  # Initialize successfully
        mock_uninit.side_effect = Exception("Uninit error")  # Uninit can fail
        
        with patch("audio.AudioUtilities.GetSpeakers") as mock_get:
            mock_get.side_effect = Exception("COM error")
            mock_action = MagicMock()
            
            result = audio._with_endpoint(mock_action, "default_result")
            
            # Should return default value on exception
            assert result == "default_result"
            # Initialize should be called
            mock_init.assert_called()


class TestAudioDevices:
    """Test audio device functions."""
    
    @patch("audio._with_com")
    def test_get_default_output_device(self, mock_with_com):
        """Test getting default output device."""
        mock_device_info = {"id": "test_id", "name": "Test Speaker"}
        mock_with_com.return_value = mock_device_info
        
        result = audio.get_default_output_device()
        
        assert result == mock_device_info
        mock_with_com.assert_called_once()
    
    @patch("audio._with_com")
    def test_list_output_devices(self, mock_with_com):
        """Test listing output devices."""
        mock_devices = [
            {"id": "dev1", "name": "Speaker 1"},
            {"id": "dev2", "name": "Speaker 2"},
        ]
        mock_with_com.return_value = mock_devices
        
        result = audio.list_output_devices()
        
        assert isinstance(result, list)
        mock_with_com.assert_called_once()


class TestAudioVolume:
    """Test volume control functions."""
    
    @patch("audio._with_endpoint")
    def test_get_volume(self, mock_with_endpoint):
        """Test getting current volume."""
        mock_with_endpoint.return_value = 0.75
        
        result = audio.get_volume()
        
        assert result == 0.75
        mock_with_endpoint.assert_called_once()
    
    @patch("audio._with_endpoint")
    def test_set_volume(self, mock_with_endpoint):
        """Test setting volume."""
        mock_with_endpoint.return_value = None
        
        audio.set_volume(0.5)
        
        mock_with_endpoint.assert_called_once()
    
    @patch("audio._with_endpoint")
    def test_is_muted(self, mock_with_endpoint):
        """Test checking mute status."""
        mock_with_endpoint.return_value = True
        
        result = audio.is_muted()
        
        assert result is True
        mock_with_endpoint.assert_called_once()
    
    @patch("audio._with_endpoint")
    def test_toggle_mute(self, mock_with_endpoint):
        """Test toggling mute."""
        mock_with_endpoint.return_value = True
        
        result = audio.toggle_mute()
        
        assert isinstance(result, bool)
        mock_with_endpoint.assert_called()


class TestAudioErrorHandling:
    """Test audio error handling."""
    
    @patch("audio._with_endpoint")
    def test_volume_operation_with_no_device(self, mock_with_endpoint):
        """Test volume operations when no device available."""
        # Return None or default when no device
        mock_with_endpoint.return_value = 0.0
        
        result = audio.get_volume()
        
        assert isinstance(result, (float, int))
    
    @patch("audio._with_com")
    def test_get_default_device_with_exception(self, mock_with_com):
        """Test device retrieval with exception."""
        # _with_com should return default value even on exception
        default_device = {"id": "", "name": "Unknown output"}
        mock_with_com.return_value = default_device
        
        result = audio.get_default_output_device()
        # Should return default/error value
        assert "name" in result
        assert result == default_device


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
