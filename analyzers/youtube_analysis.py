"""유튜브 부동산 채널 분석 — 영상 검색 + 자막 키워드 분석"""
from __future__ import annotations
import os
import asyncio
import re
from collections import Counter
from dataclasses import dataclass

import aiohttp
import anthropic
from youtube_transcript_api import YouTubeTranscriptApi

_anthropic_client = anthropic.Anthropic() if os.environ.get("ANTHROPIC_API_KEY") else None

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
YT_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YT_CHANNEL_URL = "https://www.googleapis.com/youtube/v3/channels"


@dataclass
class VideoAnalysis:
    channel_name: str
    video_id: str
    title: str
    published_at: str
    keyword_counts: dict[str, int]
    summary: str = ""


async def _resolve_channel_id(handle: str) -> str:
    """@handle → UC... 채널 ID 변환"""
    if not YOUTUBE_API_KEY:
        return ""
    handle_clean = handle.lstrip("@")
    async with aiohttp.ClientSession() as session:
        params = {
            "key": YOUTUBE_API_KEY,
            "forHandle": handle_clean,
            "part": "id",
        }
        async with session.get(YT_CHANNEL_URL, params=params) as resp:
            data = await resp.json()
    items = data.get("items", [])
    if not items:
        print(f"[youtube] API 응답: {data}")
    return items[0]["id"] if items else ""


async def _search_recent_videos(channel_id: str, max_results: int = 10) -> list[dict]:
    """채널의 최근 30일 이내 영상 목록"""
    if not YOUTUBE_API_KEY or not channel_id:
        return []
    from datetime import datetime, timedelta, timezone
    published_after = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    async with aiohttp.ClientSession() as session:
        params = {
            "key": YOUTUBE_API_KEY,
            "channelId": channel_id,
            "part": "snippet",
            "order": "date",
            "type": "video",
            "maxResults": max_results,
            "publishedAfter": published_after,
        }
        async with session.get(YT_SEARCH_URL, params=params) as resp:
            data = await resp.json()
    return data.get("items", [])


def _fetch_transcript(video_id: str, regions: list[str]) -> tuple[dict[str, int], str]:
    """자막 추출 + 키워드 카운트. 자막 텍스트 전체를 반환."""
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["ko", "ko-KR"])
        text = " ".join(t["text"] for t in transcript)
        print(f"[youtube] 자막 추출 성공: {video_id} ({len(text)}자)")
    except Exception as e:
        print(f"[youtube] 자막 추출 실패: {video_id} — {e}")
        return {}, ""

    counts: dict[str, int] = {}
    for region in regions:
        count = len(re.findall(region, text))
        if count > 0:
            counts[region] = count

    return counts, text


def _claude_summarize(text: str) -> str:
    if not _anthropic_client:
        return text[:80] + "…"
    try:
        msg = _anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{
                "role": "user",
                "content": f"다음 유튜브 영상 자막을 한 문장(50자 이내)으로 핵심만 요약해줘. 한국어로:\n\n{text[:3000]}"
            }]
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f"[youtube] Claude 요약 실패: {e}")
        return text[:80] + "…"


async def analyze_channels(channels: list[dict], watch_regions: list[str]) -> list[VideoAnalysis]:
    results: list[VideoAnalysis] = []

    for channel in channels:
        handle = channel.get("handle", "")
        name = channel.get("name", handle)

        channel_id = await _resolve_channel_id(handle)
        if not channel_id:
            print(f"[youtube] 채널 ID 조회 실패: {name} ({handle})")
            continue

        videos = await _search_recent_videos(channel_id, max_results=5)
        for video in videos:
            video_id = video["id"].get("videoId", "")
            if not video_id:
                continue

            title = video["snippet"]["title"]
            keyword_counts, transcript_text = await asyncio.get_event_loop().run_in_executor(
                None, _fetch_transcript, video_id, watch_regions
            )
            if transcript_text:
                summary = await asyncio.get_event_loop().run_in_executor(
                    None, _claude_summarize, transcript_text
                )
            else:
                summary = f"[자막 없음] {title}"

            results.append(VideoAnalysis(
                channel_name=name,
                video_id=video_id,
                title=title,
                published_at=video["snippet"]["publishedAt"][:10],
                keyword_counts=keyword_counts,
                summary=summary,
            ))
            await asyncio.sleep(10)

    return results


def summarize(analyses: list[VideoAnalysis]) -> dict:
    """전체 키워드 빈도 집계 + 채널별 그룹화"""
    total: Counter = Counter()
    for a in analyses:
        total.update(a.keyword_counts)

    by_channel: dict[str, list[dict]] = {}
    for a in analyses:
        entry = {
            "title": a.title,
            "published_at": a.published_at,
            "keywords": a.keyword_counts,
            "summary": a.summary,
            "url": f"https://youtu.be/{a.video_id}",
        }
        by_channel.setdefault(a.channel_name, []).append(entry)

    return {
        "total_videos": len(analyses),
        "keyword_ranking": total.most_common(10),
        "by_channel": by_channel,
        "all_analyses": list(by_channel.values()),
    }
