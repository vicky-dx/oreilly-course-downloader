from .browsers import Logger
import re
import requests
from typing import List, Dict, Optional
from colorama import Fore


class VttProcessor:
    @staticmethod
    def download_vtt(url: str) -> Optional[str]:
        Logger.info(f"📥 Downloading VTT file from: {url}")
        try:
            response = requests.get(url)
            response.raise_for_status()
            Logger.success(f" Downloaded {len(response.content)} bytes")
            return response.text
        except Exception as e:
            Logger.error(f" Error: {e}")
            return None

    @staticmethod
    def parse_vtt(vtt_content: str) -> List[Dict[str, str]]:
        Logger.info("📝 Parsing VTT file...")
        lines = vtt_content.split("\n")
        captions = []

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            if "-->" in line:
                timestamp_match = re.match(
                    r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})",
                    line,
                )
                if timestamp_match:
                    start_time = timestamp_match.group(1)
                    end_time = timestamp_match.group(2)

                    caption_text = []
                    i += 1
                    while i < len(lines) and lines[i].strip() and "-->" not in lines[i]:
                        text = lines[i].strip()
                        # Remove VTT formatting tags
                        text = re.sub(r"<[^>]+>", "", text)
                        if text:
                            caption_text.append(text)
                        i += 1

                    if caption_text:
                        captions.append(
                            {
                                "start": start_time[:8],
                                "end": end_time[:8],
                                "text": " ".join(caption_text),
                            }
                        )
            i += 1

        Logger.success(f" Parsed {len(captions)} caption entries")
        return captions

    @staticmethod
    def format_transcript(captions: List[Dict[str, str]], event_name: str) -> str:
        Logger.info("📄 Formatting transcript...")

        transcript = f"{event_name}\n"
        transcript += "O'Reilly Live Event - Video Transcript\n"
        transcript += "Source: ON24 VTT Captions\n"
        transcript += f"Total Captions: {len(captions)}\n"
        transcript += "=" * 80 + "\n\n"

        for caption in captions:
            transcript += f"[{caption['start']}] {caption['text']}\n\n"

        Logger.success(f" Formatted {len(transcript)} characters")
        return transcript
