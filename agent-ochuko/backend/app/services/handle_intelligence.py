# app/services/handle_intelligence.py
"""
Handle & Social/Developer Profile Intelligence Service.
Fetches live metadata, public repositories, bio stats, and career activity for profiles
across GitHub, LinkedIn, Facebook, and Twitter/X using live APIs and Google Search Grounding.
"""

import os
import re
import asyncio
import logging
from typing import Dict, Any, Optional, List
import httpx

logger = logging.getLogger("app.services.handle_intelligence")


class HandleIntelligence:
    """Provides structured profile lookups across developer and social networks."""

    @staticmethod
    def detect_platform(raw_handle: str) -> str:
        """Detects target platform ('github', 'linkedin', 'facebook', 'twitter') from handle or URL."""
        clean = (raw_handle or "").strip().lower()
        if "github.com/" in clean:
            return "github"
        elif "linkedin.com/" in clean:
            return "linkedin"
        elif "facebook.com/" in clean or "fb.com/" in clean:
            return "facebook"
        elif "twitter.com/" in clean or "x.com/" in clean:
            return "twitter"
        elif "linkedin" in clean:
            return "linkedin"
        elif "facebook" in clean or "fb" in clean:
            return "facebook"
        return "generic"

    @staticmethod
    def clean_handle(raw_handle: str) -> str:
        """Extracts clean username/slug from URL or handle."""
        clean = (raw_handle or "").strip().lstrip("@")
        if "github.com/" in clean:
            return clean.split("github.com/")[1].split("/")[0].strip()
        elif "linkedin.com/in/" in clean:
            return clean.split("linkedin.com/in/")[1].split("/")[0].split("?")[0].strip()
        elif "facebook.com/" in clean or "fb.com/" in clean:
            prefix = "facebook.com/" if "facebook.com/" in clean else "fb.com/"
            return clean.split(prefix)[1].split("/")[0].split("?")[0].strip()
        elif "twitter.com/" in clean or "x.com/" in clean:
            return clean.split("/")[-1].split("?")[0].strip()
        return clean

    @staticmethod
    async def lookup_profile(
        raw_handle: str,
        platform: str = "auto",
        timeout_seconds: float = 8.0,
    ) -> Dict[str, Any]:
        """
        Looks up a profile on GitHub, LinkedIn, Facebook, or Twitter/X.
        Auto-detects platform from URL or keyword if platform is 'auto'.
        """
        detected_platform = platform.lower()
        if detected_platform == "auto":
            detected_platform = HandleIntelligence.detect_platform(raw_handle)
            if detected_platform == "generic":
                detected_platform = "github"

        clean = HandleIntelligence.clean_handle(raw_handle)
        if detected_platform == "linkedin":
            clean = re.sub(r"\blinkedin\b", "", clean, flags=re.IGNORECASE).strip(" :-")
        elif detected_platform == "facebook":
            clean = re.sub(r"\b(facebook|fb)\b", "", clean, flags=re.IGNORECASE).strip(" :-")

        if detected_platform == "github":
            return await HandleIntelligence._fetch_github_profile(clean, timeout_seconds)
        elif detected_platform == "linkedin":
            return await HandleIntelligence._fetch_linkedin_profile(clean)
        elif detected_platform == "facebook":
            return await HandleIntelligence._fetch_facebook_profile(clean)
        elif detected_platform in ("twitter", "x"):
            return await HandleIntelligence._fetch_twitter_profile(clean)
        else:
            return await HandleIntelligence._fetch_generic_profile(clean, detected_platform)

    @staticmethod
    async def _fetch_github_profile(username: str, timeout_seconds: float) -> Dict[str, Any]:
        """Fetches public GitHub profile and top repositories."""
        headers = {
            "User-Agent": "Agent-Ochuko-Bot/1.0",
            "Accept": "application/vnd.github.v3+json",
        }
        try:
            async with httpx.AsyncClient(headers=headers, timeout=timeout_seconds) as client:
                user_res = await client.get(f"https://api.github.com/users/{username}")
                if user_res.status_code == 404:
                    return {
                        "success": False,
                        "platform": "github",
                        "username": username,
                        "error": f"GitHub user '{username}' was not found.",
                        "summary": f"GitHub user @{username} does not exist.",
                    }
                user_data = user_res.json()

                # Fetch top repos
                repos_res = await client.get(f"https://api.github.com/users/{username}/repos?sort=updated&per_page=4")
                repos_data = repos_res.json() if repos_res.status_code == 200 and isinstance(repos_res.json(), list) else []

            top_repos = []
            for r in repos_data:
                top_repos.append({
                    "name": r.get("name"),
                    "description": r.get("description") or "No description",
                    "language": r.get("language") or "Code",
                    "stars": r.get("stargazers_count", 0),
                    "forks": r.get("forks_count", 0),
                    "url": r.get("html_url"),
                })

            profile_data = {
                "success": True,
                "platform": "github",
                "username": user_data.get("login", username),
                "name": user_data.get("name") or username,
                "avatar_url": user_data.get("avatar_url"),
                "profile_url": user_data.get("html_url", f"https://github.com/{username}"),
                "bio": user_data.get("bio") or "GitHub Developer",
                "location": user_data.get("location"),
                "company": user_data.get("company"),
                "public_repos_count": user_data.get("public_repos", 0),
                "followers_count": user_data.get("followers", 0),
                "following_count": user_data.get("following", 0),
                "top_repositories": top_repos,
            }

            repos_md = "\n".join([f"- **[{r['name']}]({r['url']})** ({r['language']} ⭐ {r['stars']}): {r['description']}" for r in top_repos])
            summary = (
                f"### GitHub Profile: @{profile_data['username']} ({profile_data['name']})\n"
                f"**Bio**: {profile_data['bio']}\n"
                f"**Stats**: {profile_data['public_repos_count']} Repos | {profile_data['followers_count']} Followers\n\n"
                f"**Top Repositories**:\n{repos_md}"
            )
            profile_data["summary"] = summary
            return profile_data

        except Exception as err:
            logger.warning(f"GitHub profile lookup error for {username}: {err}")
            return {
                "success": False,
                "platform": "github",
                "username": username,
                "error": str(err),
                "summary": f"Could not retrieve GitHub profile for @{username}: {str(err)[:100]}",
            }

    @staticmethod
    async def _fetch_linkedin_profile(identifier: str) -> Dict[str, Any]:
        """
        Bypasses LinkedIn's 999 authwall by executing a targeted Google Grounding search
        specifically targeting public LinkedIn indexed snippets and knowledge cards.
        """
        query = f'site:linkedin.com/in "{identifier}"' if " " in identifier else f'site:linkedin.com/in/{identifier} OR "{identifier}" linkedin'
        grounded_data = await HandleIntelligence._execute_social_grounding_search(
            platform="LinkedIn",
            identifier=identifier,
            search_query=query,
            system_instruction=(
                "You are an executive OSINT profile researcher. "
                "Extract the person's verified LinkedIn profile details from the Google Search results. "
                "Provide: Full Name, Current Headline/Role, Organization/Company, Location, Past Roles, Education, and the direct LinkedIn URL. "
                "Do not make up facts; only state what is grounded in search."
            ),
        )
        return grounded_data

    @staticmethod
    async def _fetch_facebook_profile(identifier: str) -> Dict[str, Any]:
        """
        Bypasses Facebook's login wall by querying Google Grounding for public Facebook pages,
        public figures, and bio information.
        """
        query = f'site:facebook.com "{identifier}"'
        grounded_data = await HandleIntelligence._execute_social_grounding_search(
            platform="Facebook",
            identifier=identifier,
            search_query=query,
            system_instruction=(
                "You are a public social intelligence researcher. "
                "Extract the public profile, page, or organization details for this query from the Facebook search results. "
                "Provide: Page/Profile Name, Verified Category/Bio, Current Activities, and direct URL. "
                "Only state verified facts present in the search results."
            ),
        )
        return grounded_data

    @staticmethod
    async def _fetch_twitter_profile(identifier: str) -> Dict[str, Any]:
        """Queries Twitter/X profile information via search grounding."""
        query = f'site:x.com/{identifier} OR site:twitter.com/{identifier} OR "{identifier}" twitter x'
        return await HandleIntelligence._execute_social_grounding_search(
            platform="X / Twitter",
            identifier=identifier,
            search_query=query,
            system_instruction=(
                "Extract the user's Twitter/X handle, display name, bio, follower highlights, and profile link."
            ),
        )

    @staticmethod
    async def _execute_social_grounding_search(
        platform: str,
        identifier: str,
        search_query: str,
        system_instruction: str,
    ) -> Dict[str, Any]:
        """
        Executes Google Search Grounding to extract public social profiles and knowledge snippets.
        """
        try:
            from app.core.config import get_config
            get_config()
        except Exception:
            pass

        keys = []
        for var in ["GOOGLE_API_KEY", "GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3", "GEMINI_API_KEY_4"]:
            val = os.getenv(var)
            if val and val.strip() and val.strip() not in keys:
                keys.append(val.strip())

        if not keys:
            try:
                from app.core.config import get_config
                cfg = get_config()
                for key_val in [
                    getattr(cfg, "GEMINI_API_KEY", None),
                    getattr(cfg, "GOOGLE_API_KEY", None),
                    getattr(cfg, "GEMINI_API_KEY_2", None),
                ]:
                    if key_val and str(key_val).strip() and str(key_val).strip() not in keys:
                        keys.append(str(key_val).strip())
            except Exception:
                pass

        if not keys:
            # Fallback to plain profile URL if no API keys are present
            url = f"https://www.linkedin.com/in/{identifier}" if platform.lower() == "linkedin" else f"https://facebook.com/{identifier}"
            return {
                "success": True,
                "platform": platform.lower(),
                "username": identifier,
                "profile_url": url,
                "summary": f"**{platform} Profile**: [{identifier}]({url})\n*(API search keys not configured for deep extraction)*",
            }

        def _run_grounding_sync() -> Dict[str, Any]:
            from google import genai
            from google.genai import types as genai_types

            last_err = None
            for key in keys:
                try:
                    client = genai.Client(api_key=key)
                    prompt = (
                        f"{system_instruction}\n\n"
                        f"Search Query: {search_query}\n"
                        f"Target: {identifier}"
                    )
                    resp = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=prompt,
                        config=genai_types.GenerateContentConfig(
                            tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
                            temperature=0.1,
                        ),
                    )

                    text = getattr(resp, "text", "") or ""
                    sources = []
                    seen_urls = set()
                    profile_url = ""

                    if resp.candidates and resp.candidates[0].grounding_metadata:
                        chunks = resp.candidates[0].grounding_metadata.grounding_chunks or []
                        for c in chunks:
                            web = getattr(c, "web", None)
                            if web:
                                uri = getattr(web, "uri", "") or ""
                                title = getattr(web, "title", "") or uri
                                if uri and uri not in seen_urls:
                                    seen_urls.add(uri)
                                    sources.append({"title": title, "url": uri})
                                    if platform.lower() in uri.lower() and not profile_url:
                                        profile_url = uri

                    if not profile_url:
                        if platform.lower() == "linkedin":
                            profile_url = f"https://www.linkedin.com/in/{identifier.replace(' ', '-').lower()}"
                        elif platform.lower() == "facebook":
                            profile_url = f"https://www.facebook.com/{identifier.replace(' ', '').lower()}"
                        else:
                            profile_url = f"https://x.com/{identifier}"

                    summary = f"### {platform} Intelligence: {identifier}\n\n{text}"
                    if sources:
                        summary += f"\n\n**Verified Sources**:\n" + "\n".join([f"- [{s['title']}]({s['url']})" for s in sources[:4]])

                    return {
                        "success": True,
                        "platform": platform.lower(),
                        "identifier": identifier,
                        "profile_url": profile_url,
                        "summary": summary,
                        "extracted_text": text,
                        "sources": sources,
                    }
                except Exception as ex:
                    last_err = ex
                    continue

            return {
                "success": False,
                "platform": platform.lower(),
                "identifier": identifier,
                "error": str(last_err),
                "summary": f"Could not retrieve {platform} information for '{identifier}': {str(last_err)[:100]}",
            }

        return await asyncio.to_thread(_run_grounding_sync)

    @staticmethod
    async def _fetch_generic_profile(username: str, platform: str) -> Dict[str, Any]:
        """Generic fallback profile resolver."""
        platform_urls = {
            "twitter": f"https://x.com/{username}",
            "x": f"https://x.com/{username}",
            "linkedin": f"https://www.linkedin.com/in/{username}",
            "facebook": f"https://www.facebook.com/{username}",
            "instagram": f"https://www.instagram.com/{username}",
        }
        url = platform_urls.get(platform, f"https://{platform}.com/{username}")
        return {
            "success": True,
            "platform": platform,
            "username": username,
            "name": username,
            "profile_url": url,
            "summary": f"**{platform.capitalize()} Profile**: [@{username}]({url})",
        }
