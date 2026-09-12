# app/services/youtube_intelligence.py
"""
YouTube Intelligence & Transcript Extraction Service.
Extracts video metadata and timestamped spoken transcripts for any YouTube URL,
enabling direct video content search, summarization, and timestamp citation.
"""

import re
import asyncio
import logging
from typing import Dict, Any, Optional, List
import httpx

logger = logging.getLogger("app.services.youtube_intelligence")

# Regex to match all YouTube URL variations
YOUTUBE_URL_REGEX = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?(?:youtube\.com/(?:watch\?(?:.*&)?v=|embed/|v/|shorts/)|youtu\.be/)([\w-]{11})",
    re.IGNORECASE,
)


class YouTubeIntelligence:
    """Provides video metadata and timed transcript extraction for YouTube links."""

    @staticmethod
    def extract_video_id(url_or_text: str) -> Optional[str]:
        """Extracts 11-character YouTube video ID from a URL or free-text snippet."""
        if not url_or_text:
            return None
        url_clean = url_or_text.strip()
        match = YOUTUBE_URL_REGEX.search(url_clean)
        if match:
            return match.group(1)
        # If passed an exact 11-character YouTube video ID string
        if re.match(r"^[a-zA-Z0-9_-]{11}$", url_clean):
            return url_clean
        return None

    @staticmethod
    def contains_youtube_link(text: str) -> bool:
        """Returns True if the text contains a YouTube video reference."""
        return bool(YouTubeIntelligence.extract_video_id(text))

    @staticmethod
    async def get_video_metadata(video_id: str, timeout_seconds: float = 6.0) -> Dict[str, Any]:
        """Fetches public video metadata via YouTube oEmbed API."""
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                res = await client.get(oembed_url)
                if res.status_code == 200:
                    data = res.json()
                    return {
                        "video_id": video_id,
                        "title": data.get("title") or "YouTube Video",
                        "author": data.get("author_name") or "Unknown Creator",
                        "author_name": data.get("author_name") or "Unknown Creator",
                        "author_url": data.get("author_url") or "",
                        "thumbnail_url": data.get("thumbnail_url") or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                        "watch_url": f"https://www.youtube.com/watch?v={video_id}",
                    }
        except Exception as e:
            logger.warning(f"Failed to fetch oEmbed metadata for YouTube video {video_id}: {e}")

        return {
            "video_id": video_id,
            "title": "YouTube Video",
            "author": "YouTube Creator",
            "author_name": "YouTube Creator",
            "author_url": "",
            "thumbnail_url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            "watch_url": f"https://www.youtube.com/watch?v={video_id}",
        }

    @staticmethod
    async def get_video_transcript(
        video_id: str,
        languages: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Fetches the complete spoken transcript with timestamps for a YouTube video.
        Uses youtube_transcript_api run asynchronously in a thread.
        """
        target_languages = languages or ["en", "en-US", "en-GB", "a.en", "es", "fr", "de"]

        def _fetch_sync() -> Dict[str, Any]:
            try:
                from youtube_transcript_api import YouTubeTranscriptApi
                api = YouTubeTranscriptApi()

                # Try preferred languages, then list available transcript tracks
                try:
                    transcript_obj = api.fetch(video_id, languages=target_languages)
                    raw_snippets = transcript_obj.snippets if hasattr(transcript_obj, "snippets") else transcript_obj
                except Exception:
                    # Fallback: list transcripts and fetch the first generated or manual track
                    transcript_list = api.list(video_id)
                    first_transcript = None
                    try:
                        first_transcript = transcript_list.find_manually_created_transcript(target_languages)
                    except Exception:
                        pass
                    if not first_transcript:
                        try:
                            first_transcript = transcript_list.find_generated_transcript(target_languages)
                        except Exception:
                            pass
                    if not first_transcript:
                        for t in transcript_list:
                            first_transcript = t
                            break

                    if not first_transcript:
                        return {"success": False, "error": "No transcripts available for this video."}

                    transcript_data = first_transcript.fetch()
                    raw_snippets = transcript_data.snippets if hasattr(transcript_data, "snippets") else transcript_data

                items = []
                total_duration = 0.0
                full_text_parts = []

                for s in raw_snippets:
                    # Handle both object attributes and dict access
                    text = getattr(s, "text", None) if hasattr(s, "text") else (s.get("text") if isinstance(s, dict) else str(s))
                    start = getattr(s, "start", 0.0) if hasattr(s, "start") else (s.get("start", 0.0) if isinstance(s, dict) else 0.0)
                    duration = getattr(s, "duration", 0.0) if hasattr(s, "duration") else (s.get("duration", 0.0) if isinstance(s, dict) else 0.0)

                    if not text or not text.strip():
                        continue

                    text_clean = text.replace("\n", " ").strip()
                    total_duration = max(total_duration, float(start) + float(duration))
                    full_text_parts.append(text_clean)

                    items.append({
                        "start": float(start),
                        "duration": float(duration),
                        "timestamp": YouTubeIntelligence._format_timestamp(float(start)),
                        "text": text_clean,
                    })

                total_words = sum(len(p.split()) for p in full_text_parts)

                return {
                    "success": True,
                    "snippets": items,
                    "full_text": " ".join(full_text_parts),
                    "total_words": total_words,
                    "duration_seconds": int(total_duration),
                }

            except Exception as e:
                err_msg = str(e)
                logger.warning(f"YouTube transcript extraction failed for {video_id}: {err_msg}")
                return {
                    "success": False,
                    "error": f"Could not retrieve transcript: {err_msg[:200]}",
                }

        return await asyncio.to_thread(_fetch_sync)

    @staticmethod
    async def process_youtube_url(url_or_id: str) -> Dict[str, Any]:
        """
        High-level helper: extracts video ID, gets metadata, and fetches full transcript.
        Returns complete intelligence payload.
        """
        video_id = YouTubeIntelligence.extract_video_id(url_or_id) or (url_or_id or "").strip()
        if not video_id or len(video_id) != 11:
            return {
                "success": False,
                "error": f"Invalid YouTube video ID or URL: '{url_or_id}'",
            }

        metadata, transcript_res = await asyncio.gather(
            YouTubeIntelligence.get_video_metadata(video_id),
            YouTubeIntelligence.get_video_transcript(video_id),
        )

        has_transcript = transcript_res.get("success", False)
        snippets = transcript_res.get("snippets", [])
        total_words = transcript_res.get("total_words", 0)

        formatted_context = YouTubeIntelligence.format_transcript_for_prompt(
            metadata=metadata,
            snippets=snippets,
            has_transcript=has_transcript,
            error=transcript_res.get("error"),
            video_id=video_id,
        )

        return {
            "success": True,
            "video_id": video_id,
            "title": metadata.get("title", "YouTube Video"),
            "author_name": metadata.get("author", "YouTube Creator"),
            "url": metadata.get("watch_url", f"https://www.youtube.com/watch?v={video_id}"),
            "metadata": metadata,
            "has_transcript": has_transcript,
            "transcript_segments": snippets,
            "transcript_text": transcript_res.get("full_text", ""),
            "snippets_count": len(snippets),
            "total_words": total_words,
            "word_count": total_words,
            "formatted_context": formatted_context,
            "summary": formatted_context,
            "error": transcript_res.get("error") if not has_transcript else None,
        }

    @staticmethod
    def format_transcript_for_prompt(
        metadata: Optional[Dict[str, Any]] = None,
        snippets: Optional[List[Dict[str, Any]]] = None,
        has_transcript: Optional[bool] = None,
        error: Optional[str] = None,
        max_words: int = 12000,
        video_id: Optional[str] = None,
        transcript_segments: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Formats the YouTube video data into an organized, timestamped prompt context."""
        meta = metadata or {}
        snippets_list = snippets if snippets is not None else (transcript_segments or [])
        if has_transcript is None:
            has_transcript = bool(snippets_list)

        title = meta.get("title", "YouTube Video")
        author = meta.get("author") or meta.get("author_name") or "YouTube Creator"
        url = meta.get("watch_url") or (f"https://www.youtube.com/watch?v={video_id}" if video_id else "")

        header = [
            f"--- YOUTUBE VIDEO INTELLIGENCE ---",
            f"Title: {title}",
            f"Creator: {author}",
            f"URL: {url}",
        ]

        if not has_transcript:
            header.append(f"Transcript Status: Unavailable ({error or 'Captions not enabled by creator'})")
            header.append("Note: Answer using the video title, creator, and web search context if needed.")
            header.append("--- END YOUTUBE VIDEO INTELLIGENCE ---")
            return "\n".join(header)

        header.append(f"Transcript: Available ({len(snippets_list)} timestamped caption segments)")
        header.append("--- BEGIN TIMESTAMPED SPOKEN TRANSCRIPT ---")

        # Group captions into readable timestamped paragraphs every ~30 seconds
        paragraphs = []
        current_time_str = "00:00"
        current_words = []
        word_count = 0

        for s in snippets_list:
            timestamp = s.get("timestamp", "00:00")
            text = s.get("text", "")
            if not current_words:
                current_time_str = timestamp
            current_words.append(text)
            word_count += len(text.split())

            if len(current_words) >= 6:  # group ~6 sentences or ~30s
                paragraphs.append(f"[{current_time_str}] {' '.join(current_words)}")
                current_words = []

            if word_count >= max_words:
                paragraphs.append("[Transcript truncated due to length...]")
                break

        if current_words:
            paragraphs.append(f"[{current_time_str}] {' '.join(current_words)}")

        content = "\n".join(header) + "\n" + "\n".join(paragraphs) + "\n--- END YOUTUBE VIDEO INTELLIGENCE ---"
        return content

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        """Converts raw seconds into MM:SS or HH:MM:SS."""
        s = int(seconds)
        hours = s // 3600
        minutes = (s % 3600) // 60
        secs = s % 60
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"
