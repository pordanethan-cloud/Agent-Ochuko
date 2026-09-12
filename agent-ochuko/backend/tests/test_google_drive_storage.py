import os
import tempfile
import time
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.services.google_drive import (
    get_drive_credentials,
    get_or_create_folder,
    download_google_drive_files,
    upload_to_google_drive
)
from app.services.code_sandbox import prune_expired_sandboxes


@pytest.mark.asyncio
async def test_google_drive_credentials_fallback():
    """Verify credentials fetch handles missing tokens gracefully without crashing."""
    with patch("app.services.google_drive.get_supabase_admin") as mock_sb:
        mock_table = MagicMock()
        mock_sb.return_value.table.return_value = mock_table
        mock_table.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(data=None)

        with patch.dict(os.environ, {"GOOGLE_REFRESH_TOKEN": ""}, clear=False):
            creds = get_drive_credentials("user_test_123")
            assert creds is None


@pytest.mark.asyncio
async def test_google_drive_upload_flow():
    """Verify upload_to_google_drive discovers files and calls drive service upload."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_file = os.path.join(tmp_dir, "output_chart.png")
        with open(test_file, "wb") as f:
            f.write(b"PNG_MOCK_IMAGE_DATA")

        with patch("app.services.google_drive.get_drive_credentials") as mock_creds, \
             patch("app.services.google_drive.get_drive_client") as mock_client, \
             patch("app.services.google_drive.get_conversation_folders") as mock_folders, \
             patch("app.services.google_drive.MediaFileUpload") as mock_media_upload:

            mock_creds.return_value = MagicMock()
            mock_service = MagicMock()
            mock_client.return_value = mock_service
            mock_folders.return_value = {"uploads": "folder_uploads", "sandbox_file": "folder_sandbox"}
            mock_media_upload.return_value = MagicMock()

            mock_files = MagicMock()
            mock_service.files.return_value = mock_files
            mock_create = MagicMock()
            mock_files.create.return_value = mock_create
            mock_create.execute.return_value = {
                "id": "drive_file_id_777",
                "webViewLink": "https://drive.google.com/file/d/drive_file_id_777/view"
            }

            uploaded = await upload_to_google_drive("user_abc", "conv_xyz", tmp_dir)
            assert len(uploaded) == 1
            assert uploaded[0]["filename"] == "output_chart.png"
            assert "drive_file_id_777" in uploaded[0]["download_url"]


@pytest.mark.asyncio
async def test_google_drive_download_flow():
    """Verify download_google_drive_files pulls remote files into local directory."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        with patch("app.services.google_drive.get_drive_credentials") as mock_creds, \
             patch("app.services.google_drive.get_drive_client") as mock_client, \
             patch("app.services.google_drive.get_conversation_folders") as mock_folders:

            mock_creds.return_value = MagicMock()
            mock_service = MagicMock()
            mock_client.return_value = mock_service
            mock_folders.return_value = {"uploads": "folder_uploads", "sandbox_file": "folder_sandbox"}

            mock_files = MagicMock()
            mock_service.files.return_value = mock_files
            mock_list = MagicMock()
            mock_files.list.return_value = mock_list
            mock_list.execute.return_value = {
                "files": [{"id": "file_123", "name": "data.csv"}]
            }

            mock_get = MagicMock()
            mock_files.get_media.return_value = mock_get

            with patch("app.services.google_drive.MediaIoBaseDownload") as mock_dl:
                mock_downloader = MagicMock()
                mock_downloader.next_chunk.return_value = (None, True)
                mock_dl.return_value = mock_downloader

                downloaded = await download_google_drive_files("user_abc", "conv_xyz", tmp_dir)
                assert len(downloaded) == 1
                assert downloaded[0] == "data.csv"
                assert os.path.exists(os.path.join(tmp_dir, "data.csv"))


def test_sandbox_pruning_ttl():
    """Verify prune_expired_sandboxes removes directories older than 2 hours."""
    with tempfile.TemporaryDirectory() as base_tmp:
        old_sandbox = os.path.join(base_tmp, "sandbox_old_session")
        new_sandbox = os.path.join(base_tmp, "sandbox_new_session")
        os.makedirs(old_sandbox, exist_ok=True)
        os.makedirs(new_sandbox, exist_ok=True)

        # Set old sandbox mtime to 3 hours ago
        three_hours_ago = time.time() - (3 * 3600)
        os.utime(old_sandbox, (three_hours_ago, three_hours_ago))

        with patch("tempfile.gettempdir", return_value=base_tmp):
            pruned = prune_expired_sandboxes(max_age_seconds=7200)
            assert pruned >= 1
            assert not os.path.exists(old_sandbox)
            assert os.path.exists(new_sandbox)
