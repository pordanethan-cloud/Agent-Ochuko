import json
import os
import subprocess
import sys
import urllib.request

def main():
    video_url = "https://youtu.be/dWHc4H-jELY"
    output_dir = os.path.abspath("downloaded_stream")
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"[*] Extracting livestream DVR playlist URL for {video_url}...")
    
    # Try 1080p (format 96) first, fallback to 720p (format 95)
    selected_format = "96"
    cmd = ["yt-dlp", "-g", "-f", selected_format, video_url]
    res = subprocess.run(cmd, capture_output=True, text=True)
    m3u8_url = res.stdout.strip()
    
    if not m3u8_url or res.returncode != 0:
        print(f"[!] Format 96 not found, falling back to format 95...")
        selected_format = "95"
        cmd = ["yt-dlp", "-g", "-f", selected_format, video_url]
        res = subprocess.run(cmd, capture_output=True, text=True)
        m3u8_url = res.stdout.strip()
        
    if not m3u8_url or not m3u8_url.startswith("http"):
        print(f"[X] Failed to extract m3u8 URL: {res.stderr}")
        sys.exit(1)
        
    print(f"[+] Selected format: {selected_format}")
    print(f"[+] Fetching full DVR playlist...")
    
    req = urllib.request.Request(m3u8_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        playlist_content = resp.read().decode("utf-8")
        
    lines = playlist_content.splitlines()
    segs = [l for l in lines if l.startswith("http")]
    print(f"[+] Total streamed segments captured: {len(segs)}")
    est_duration_sec = len(segs) * 5
    hrs = est_duration_sec // 3600
    mins = (est_duration_sec % 3600) // 60
    secs = est_duration_sec % 60
    print(f"[+] Estimated duration: {hrs:02d}:{mins:02d}:{secs:02d} ({est_duration_sec} seconds)")
    
    # Ensure #EXT-X-ENDLIST is appended so ffmpeg treats this as a static complete VOD
    vod_lines = []
    for l in lines:
        if l.strip() == "#EXT-X-ENDLIST":
            continue
        vod_lines.append(l)
    vod_lines.append("#EXT-X-ENDLIST")
    
    playlist_path = os.path.join(output_dir, "stream_vod.m3u8")
    with open(playlist_path, "w", encoding="utf-8") as f:
        f.write("\n".join(vod_lines))
        
    output_mp4 = os.path.join(output_dir, "WHO_DESIGNED_THE_RAT_RACE.mp4")
    print(f"[+] Starting FFmpeg copy stream to: {output_mp4}")
    
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-protocol_whitelist", "file,http,https,tcp,tls",
        "-i", playlist_path,
        "-c", "copy",
        "-movflags", "+faststart",
        output_mp4
    ]
    
    proc = subprocess.run(ffmpeg_cmd)
    if proc.returncode != 0:
        print(f"[X] FFmpeg exited with error code {proc.returncode}")
        sys.exit(proc.returncode)
        
    print(f"[+] Download complete! Verifying output file...")
    if os.path.exists(output_mp4):
        size_mb = os.path.getsize(output_mp4) / (1024 * 1024)
        print(f"[+] Final Video Saved: {output_mp4} ({size_mb:.2f} MB)")
        # Clean up temporary playlist file
        if os.path.exists(playlist_path):
            os.remove(playlist_path)
    else:
        print(f"[X] Output file {output_mp4} was not created.")

if __name__ == "__main__":
    main()
