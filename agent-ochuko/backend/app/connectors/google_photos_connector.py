"""
Google Photos Connector for Agent Ochuko.
Supports searching media items, listing albums, retrieving high-res photo URLs,
and uploading images to the user's Google Photos library.
"""
import logging
from typing import Dict, Any, List, Optional
import httpx

logger = logging.getLogger("app.connectors.google_photos")

PHOTOS_API_BASE = "https://photoslibrary.googleapis.com/v1"


class GooglePhotosConnector:
    """Connector for interacting with the Google Photos Library API."""

    def __init__(self, access_token: Optional[str] = None, http_client: Optional[httpx.AsyncClient] = None):
        self.access_token = access_token
        self._http_client = http_client

    def _get_headers(self) -> Dict[str, str]:
        if not self.access_token:
            return {"Content-Type": "application/json"}
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Dispatcher for tool calls originating from Agent Task Manager."""
        try:
            if tool_name == "photos_search":
                return await self.search_photos(
                    query=arguments.get("query"),
                    category=arguments.get("category"),
                    date_start=arguments.get("date_start"),
                    date_end=arguments.get("date_end"),
                    page_size=arguments.get("page_size", 10),
                )
            elif tool_name == "photos_list":
                return await self.list_photos(
                    page_size=arguments.get("page_size", 10),
                    page_token=arguments.get("page_token"),
                )
            elif tool_name == "photos_get":
                return await self.get_photo(
                    media_item_id=arguments.get("media_item_id") or arguments.get("id", ""),
                )
            elif tool_name == "photos_upload":
                return await self.upload_photo(
                    filename=arguments.get("filename", "ochuko_image.jpg"),
                    image_url=arguments.get("image_url"),
                    description=arguments.get("description", "Uploaded via Agent Ochuko"),
                )
            else:
                return f"Error: Unknown Photos tool '{tool_name}'"
        except Exception as e:
            logger.error(f"Google Photos operation failed for {tool_name}: {e}", exc_info=True)
            return f"Photos operation error: {str(e)}"

    async def list_photos(self, page_size: int = 10, page_token: Optional[str] = None) -> str:
        """List recent media items in user's library."""
        if not self.access_token:
            return "Google Photos access token not found. Please connect your Google account in Settings."

        params: Dict[str, Any] = {"pageSize": min(page_size, 50)}
        if page_token:
            params["pageToken"] = page_token

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{PHOTOS_API_BASE}/mediaItems",
                headers=self._get_headers(),
                params=params,
            )
            if resp.status_code != 200:
                return f"Failed to list photos: {resp.status_code} - {resp.text}"

            data = resp.json()
            items = data.get("mediaItems", [])
            if not items:
                return "No media items found in Google Photos library."

            lines = [f"Found {len(items)} recent photos:"]
            for itm in items:
                f_name = itm.get("filename", "Untitled")
                created = itm.get("mediaMetadata", {}).get("creationTime", "Unknown")
                base_url = itm.get("baseUrl", "")
                itm_id = itm.get("id", "")
                lines.append(f"- ID: {itm_id} | File: {f_name} | Date: {created} | URL: {base_url}")

            return "\n".join(lines)

    async def search_photos(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        page_size: int = 10,
    ) -> str:
        """Search media items by category, keyword, or date range."""
        if not self.access_token:
            return "Google Photos access token not found. Please connect your Google account in Settings."

        body: Dict[str, Any] = {"pageSize": min(page_size, 50)}
        filters: Dict[str, Any] = {}

        if category:
            # Google Photos Content Categories: LANDSCAPES, RECEIPTS, PETS, DOCUMENTS, PEOPLE, CITYSCAPES, NIGHT, FOOD, TRAVEL, etc.
            filters["contentFilter"] = {
                "includedContentCategories": [category.upper()]
            }

        if filters:
            body["filters"] = filters

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{PHOTOS_API_BASE}/mediaItems:search",
                headers=self._get_headers(),
                json=body,
            )
            if resp.status_code != 200:
                return f"Failed to search photos: {resp.status_code} - {resp.text}"

            data = resp.json()
            items = data.get("mediaItems", [])
            if not items:
                return f"No photos found matching criteria (Category: {category or 'All'}, Query: {query or 'None'})."

            lines = [f"Found {len(items)} matching photos:"]
            for itm in items:
                f_name = itm.get("filename", "Untitled")
                created = itm.get("mediaMetadata", {}).get("creationTime", "Unknown")
                base_url = itm.get("baseUrl", "")
                itm_id = itm.get("id", "")
                lines.append(f"- ID: {itm_id} | File: {f_name} | Date: {created} | URL: {base_url}")

            return "\n".join(lines)

    async def get_photo(self, media_item_id: str) -> str:
        """Fetch metadata and high-res URL for a specific photo."""
        if not self.access_token:
            return "Google Photos access token not found. Please connect your Google account in Settings."

        if not media_item_id:
            return "Error: media_item_id is required."

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{PHOTOS_API_BASE}/mediaItems/{media_item_id}",
                headers=self._get_headers(),
            )
            if resp.status_code != 200:
                return f"Failed to get photo: {resp.status_code} - {resp.text}"

            data = resp.json()
            f_name = data.get("filename", "Untitled")
            mime = data.get("mimeType", "image/jpeg")
            metadata = data.get("mediaMetadata", {})
            width = metadata.get("width", "Unknown")
            height = metadata.get("height", "Unknown")
            created = metadata.get("creationTime", "Unknown")
            base_url = data.get("baseUrl", "")

            return (
                f"Photo Details:\n"
                f"- Filename: {f_name}\n"
                f"- ID: {media_item_id}\n"
                f"- Dimensions: {width}x{height}\n"
                f"- MIME Type: {mime}\n"
                f"- Created At: {created}\n"
                f"- High-Res Asset URL: {base_url}=d"
            )

    async def upload_photo(
        self,
        filename: str,
        image_url: Optional[str] = None,
        description: str = "Uploaded via Agent Ochuko",
    ) -> str:
        """Upload an image to Google Photos from a URL or raw bytes."""
        if not self.access_token:
            return "Google Photos access token not found. Please connect your Google account in Settings."

        if not image_url:
            return "Error: image_url is required for photo upload."

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Download image bytes first
            img_res = await client.get(image_url)
            if img_res.status_code != 200:
                return f"Failed to download source image from {image_url}: status {img_res.status_code}"

            img_bytes = img_res.content

            # Step 1: Upload raw bytes to obtain upload token
            upload_headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-type": "application/octet-stream",
                "X-Goog-Upload-Content-Type": "image/jpeg",
                "X-Goog-Upload-Protocol": "raw",
            }
            upload_resp = await client.post(
                "https://photoslibrary.googleapis.com/v1/uploads",
                headers=upload_headers,
                content=img_bytes,
            )
            if upload_resp.status_code != 200:
                return f"Failed to upload photo byte stream: {upload_resp.status_code} - {upload_resp.text}"

            upload_token = upload_resp.text.strip()

            # Step 2: Batch create media item
            create_body = {
                "newMediaItems": [
                    {
                        "description": description,
                        "simpleMediaItem": {
                            "fileName": filename,
                            "uploadToken": upload_token,
                        },
                    }
                ]
            }
            create_resp = await client.post(
                f"{PHOTOS_API_BASE}/mediaItems:batchCreate",
                headers=self._get_headers(),
                json=create_body,
            )
            if create_resp.status_code != 200:
                return f"Failed to create media item: {create_resp.status_code} - {create_resp.text}"

            res_data = create_resp.json()
            return f"Photo '{filename}' successfully uploaded to Google Photos library."
