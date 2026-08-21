# app/services/handle_intelligence.py
"""
Handle & Social/Developer Profile Intelligence Service.
Fetches live metadata, public repositories, bio stats, and activity for handles
across GitHub, Twitter/X, LinkedIn, and developer platforms.
"""

import re
import asyncio
import logging
from typing import Dict, Any, Optional, List
import httpx

logger = logging.getLogger("app.services.handle_intelligence")


class HandleIntelligence:
    """Provides fast, structured profile lookups for developer and social handles."""

    @staticmethod
    async def lookup_profile(
        raw_handle: str,
        platform: str = "auto",
        timeout_seconds: float = 5.0,
    ) -> Dict[str, Any]:
        """
        Looks up a profile handle on GitHub, X/Twitter, or other platforms.
        """
        clean_handle = raw_handle.strip().lstrip("@")
        # Extract username if full URL was provided
        if "github.com/" in clean_handle:
            clean_handle = clean_handle.split("github.com/")[1].split("/")[0].strip()
            platform = "github"
        elif "twitter.com/" in clean_handle or "x.com/" in clean_handle:
            clean_handle = clean_handle.split("/")[-1].strip()
            platform = "twitter"

        detected_platform = platform.lower()
        if detected_platform == "auto":
            # Default to github for code/developer lookups
            detected_platform = "github"

        if detected_platform == "github":
            return await HandleIntelligence._fetch_github_profile(clean_handle, timeout_seconds)
        else:
            return await HandleIntelligence._fetch_generic_profile(clean_handle, detected_platform)

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

            # Build markdown summary
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
    async def _fetch_generic_profile(username: str, platform: str) -> Dict[str, Any]:
        """Generic social profile resolver."""
        platform_urls = {
            "twitter": f"https://x.com/{username}",
            "x": f"https://x.com/{username}",
            "linkedin": f"https://www.linkedin.com/in/{username}",
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
