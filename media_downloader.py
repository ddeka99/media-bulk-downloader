import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

INSTAGRAM_URL_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/(reel|p|tv)/([A-Za-z0-9_-]+)/?"
)
TIKTOK_VIDEO_RE = re.compile(
    r"https?://(?:www\.)?(?:tiktokv\.com/share/video/|tiktok\.com/@[^/]+/video/)(\d+)/?"
)

MEDIA_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".webm",
    ".mov",
    ".m4v",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}

SCRIPT_NAME = "media_downloader.py"


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def timestamp_slug():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def walk(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from walk(item)


def get_label_value(record, label_name):
    for item in walk(record):
        if isinstance(item, dict):
            if str(item.get("label", "")).lower() == label_name.lower():
                return str(item.get("value", ""))
    return ""


def timestamp_to_utc(timestamp):
    if isinstance(timestamp, (int, float)):
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    return ""


def parse_tiktok_date(value):
    value = str(value or "").strip()
    if not value:
        return "", 0

    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return value, 0

    return value, int(parsed.timestamp())


def sanitize_filename(value):
    value = str(value or "unknown").strip()
    value = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", value)
    value = re.sub(r"\s+", "_", value)
    return value[:120] or "unknown"


def make_key(row):
    platform = row.get("platform")

    if platform == "instagram":
        return "instagram|{kind}|{shortcode}|{url}".format(
            kind=str(row.get("kind", "")).strip(),
            shortcode=str(row.get("shortcode", "")).strip(),
            url=str(row.get("url", "")).strip(),
        )

    if platform == "tiktok":
        return "tiktok|video|{video_id}".format(
            video_id=str(row.get("video_id", "")).strip(),
        )

    return "{platform}|{url}".format(
        platform=str(platform or "unknown").strip(),
        url=str(row.get("url", "")).strip(),
    )


def empty_log(source):
    return {
        "schema_version": 1,
        "updated_timestamp_utc": now_utc(),
        "source": source,
        "entry_count": 0,
        "entries": {},
    }


def load_log(path, source):
    if not path.exists():
        return empty_log(source)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"ERROR: Could not read JSON log: {path}")
        sys.exit(1)

    if isinstance(payload, list):
        entries = {}
        for entry in payload:
            if isinstance(entry, dict):
                key = entry.get("key")
                if key:
                    entries[str(key)] = entry
        payload = {
            "schema_version": 1,
            "updated_timestamp_utc": now_utc(),
            "source": source,
            "entries": entries,
        }

    if not isinstance(payload, dict):
        return empty_log(source)

    entries = payload.get("entries")
    if not isinstance(entries, dict):
        entries = {}

    payload["schema_version"] = payload.get("schema_version", 1)
    payload["source"] = payload.get("source", source)
    payload["entries"] = entries
    payload["entry_count"] = len(entries)
    return payload


def save_log(path, payload, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["schema_version"] = payload.get("schema_version", 1)
    payload["updated_timestamp_utc"] = now_utc()
    payload["source"] = source
    payload["entry_count"] = len(payload.get("entries", {}))
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def resolve_file_path(value, script_dir):
    candidate = Path(value).expanduser()

    if candidate.is_absolute():
        return candidate

    cwd_path = Path.cwd() / candidate
    if cwd_path.exists():
        return cwd_path.resolve()

    return (script_dir / candidate).resolve()


def resolve_data_path(value, script_dir, default_name, glob_pattern):
    data_dir = script_dir / "data"

    if value:
        candidate = Path(value).expanduser()
        candidates = [candidate]

        if not candidate.is_absolute():
            candidates.extend([
                Path.cwd() / candidate,
                script_dir / candidate,
                data_dir / candidate,
            ])

        for path in candidates:
            if path.exists():
                return path.resolve()

        print(f"ERROR: JSON file not found: {value}")
        sys.exit(1)

    default_path = data_dir / default_name
    if default_path.exists():
        return default_path.resolve()

    matches = sorted(
        data_dir.glob(glob_pattern),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not matches:
        print(f"ERROR: No matching JSON found in {data_dir}: {glob_pattern}")
        sys.exit(1)

    return matches[0].resolve()


def extract_instagram_rows(json_path):
    data = json.loads(json_path.read_text(encoding="utf-8"))
    rows_by_key = {}

    for record in walk(data):
        if not isinstance(record, dict):
            continue

        record_text = json.dumps(record, ensure_ascii=False)
        match = INSTAGRAM_URL_RE.search(record_text)

        if not match:
            continue

        kind = match.group(1)
        shortcode = match.group(2)
        url = f"https://www.instagram.com/{kind}/{shortcode}/"
        timestamp = record.get("timestamp", "")

        row = {
            "platform": "instagram",
            "timestamp": timestamp,
            "sort_timestamp": int(timestamp or 0),
            "timestamp_utc": timestamp_to_utc(timestamp),
            "owner_username": get_label_value(record, "Username") or "unknown",
            "kind": kind,
            "shortcode": shortcode,
            "url": url,
            "caption": get_label_value(record, "Caption"),
            "title": get_label_value(record, "Title"),
            "fbid": record.get("fbid", ""),
        }

        key = make_key(row)
        existing = rows_by_key.get(key)

        if existing is None or row["sort_timestamp"] > existing.get("sort_timestamp", 0):
            rows_by_key[key] = row

    rows = list(rows_by_key.values())
    rows.sort(key=lambda row: row.get("sort_timestamp", 0), reverse=True)
    return rows


def extract_tiktok_rows(json_path):
    data = json.loads(json_path.read_text(encoding="utf-8"))
    liked_items = (
        data.get("Likes and Favorites", {})
        .get("Like List", {})
        .get("ItemFavoriteList", [])
    )

    if not isinstance(liked_items, list):
        return []

    rows_by_key = {}

    for item in liked_items:
        if not isinstance(item, dict):
            continue

        url = str(item.get("link", "")).strip()
        match = TIKTOK_VIDEO_RE.search(url)

        if not match:
            continue

        video_id = match.group(1)
        liked_timestamp, sort_timestamp = parse_tiktok_date(item.get("date", ""))
        row = {
            "platform": "tiktok",
            "timestamp": liked_timestamp,
            "sort_timestamp": sort_timestamp,
            "liked_timestamp": liked_timestamp,
            "kind": "video",
            "video_id": video_id,
            "url": url,
        }

        key = make_key(row)
        existing = rows_by_key.get(key)

        if existing is None or sort_timestamp > existing.get("sort_timestamp", 0):
            rows_by_key[key] = row

    rows = list(rows_by_key.values())
    rows.sort(key=lambda row: row.get("sort_timestamp", 0), reverse=True)
    return rows


def get_rate_limit_settings(total_to_download, threshold, mode):
    if mode == "fast":
        return {
            "sleep_requests": "2",
            "sleep_interval": "8",
            "max_sleep_interval": "20",
        }

    if mode == "safe":
        return {
            "sleep_requests": "5",
            "sleep_interval": "20",
            "max_sleep_interval": "60",
        }

    if total_to_download > threshold:
        return {
            "sleep_requests": "5",
            "sleep_interval": "20",
            "max_sleep_interval": "60",
        }

    return {
        "sleep_requests": "2",
        "sleep_interval": "8",
        "max_sleep_interval": "20",
    }


def row_output_parts(row):
    if row.get("platform") == "instagram":
        owner = sanitize_filename(row.get("owner_username") or "unknown")
        shortcode = sanitize_filename(row.get("shortcode") or "unknown")
        return owner, f"{owner}_{shortcode}", f"{owner} / {shortcode}"

    if row.get("platform") == "tiktok":
        video_id = sanitize_filename(row.get("video_id") or "unknown")
        return "tiktok", f"tiktok_{video_id}", f"tiktok / {video_id}"

    item_id = sanitize_filename(row.get("url") or "unknown")
    return "unknown", item_id, item_id


def get_output_files(download_dir, row):
    folder, stem, _ = row_output_parts(row)
    output_dir = download_dir / folder

    if not output_dir.exists():
        return []

    files = []
    for path in output_dir.glob(f"{stem}*"):
        if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS:
            files.append(path)

    return sorted(files)


def extract_failure_reason(returncode, output, media_files):
    if returncode == 0 and not media_files:
        return "yt-dlp_returned_0_but_no_media_file_found"

    if returncode != 0 and media_files:
        return "partial_download_or_playlist_failure"

    for line in reversed((output or "").splitlines()):
        stripped = line.strip()
        if stripped.startswith("ERROR:"):
            return stripped[:500]

    return "yt-dlp_failed"


def refresh_failure_log(success_log, failure_log):
    success_keys = set(success_log.get("entries", {}))
    failure_entries = failure_log.get("entries", {})
    removed = 0

    for key in list(failure_entries):
        if key in success_keys:
            del failure_entries[key]
            removed += 1

    failure_log["entries"] = failure_entries
    failure_log["entry_count"] = len(failure_entries)
    return removed


def select_rows_to_download(rows, success_log, limit):
    success_keys = set(success_log.get("entries", {}))
    selected = []
    skipped_success = 0

    for row in rows:
        if make_key(row) in success_keys:
            skipped_success += 1
            continue

        if limit is None or len(selected) < limit:
            selected.append(row)

    return selected, skipped_success


def log_common_entry(row):
    entry = {
        "key": make_key(row),
        "platform": row.get("platform", ""),
        "url": row.get("url", ""),
        "kind": row.get("kind", ""),
    }

    if row.get("platform") == "instagram":
        entry.update({
            "shortcode": row.get("shortcode", ""),
            "owner_username": row.get("owner_username", ""),
            "liked_timestamp_utc": row.get("timestamp_utc", ""),
        })
    elif row.get("platform") == "tiktok":
        entry.update({
            "video_id": row.get("video_id", ""),
            "liked_timestamp": row.get("liked_timestamp", ""),
        })

    return entry


def success_entry(row, output_files):
    entry = log_common_entry(row)
    entry.update({
        "downloaded_timestamp_utc": now_utc(),
        "output_files": [str(path.as_posix()) for path in output_files],
    })
    return entry


def failure_entry(row, returncode, reason, existing=None):
    existing = existing or {}
    attempt_count = int(existing.get("attempt_count") or 0) + 1
    first_failed = existing.get("first_failed_timestamp_utc") or now_utc()
    entry = log_common_entry(row)
    entry.update({
        "first_failed_timestamp_utc": first_failed,
        "last_failed_timestamp_utc": now_utc(),
        "reason": reason,
        "returncode": returncode,
        "attempt_count": attempt_count,
    })
    return entry


def cookies_path_for_row(row, paths):
    if row.get("platform") == "instagram":
        return paths["instagram_cookies_path"]

    if row.get("platform") == "tiktok":
        return paths["tiktok_cookies_path"]

    print(f"ERROR: No cookies file configured for platform: {row.get('platform')}")
    sys.exit(1)


def download_rows(rows, args, paths, success_log, failure_log):
    download_dir = paths["download_dir"]
    rate = get_rate_limit_settings(
        total_to_download=len(rows),
        threshold=args.safe_threshold,
        mode=args.mode,
    )

    print(f"Downloads selected: {len(rows)}")
    print(f"Download mode: {args.mode}")
    print(
        "Rate settings: "
        f"--sleep-requests {rate['sleep_requests']}, "
        f"--sleep-interval {rate['sleep_interval']}, "
        f"--max-sleep-interval {rate['max_sleep_interval']}"
    )
    print(f"Download folder: {download_dir}")
    print()

    if args.dry_run:
        print("Dry run only. Selected downloads:")
        for idx, row in enumerate(rows, start=1):
            print(
                f"{idx}. {row.get('platform')} | "
                f"{row.get('timestamp_utc') or row.get('liked_timestamp')} | "
                f"{row_output_parts(row)[2]} | "
                f"{row.get('url')}"
            )
        return

    download_dir.mkdir(parents=True, exist_ok=True)

    for idx, row in enumerate(rows, start=1):
        key = make_key(row)
        url = row.get("url", "").strip()
        folder, stem, label = row_output_parts(row)
        cookies_path = cookies_path_for_row(row, paths)

        if not url:
            continue

        if not cookies_path.exists():
            print(f"ERROR: Cookies file not found: {cookies_path}")
            sys.exit(1)

        print(f"[{idx}/{len(rows)}] Downloading: {row.get('platform')} / {label}")

        output_template = f"{folder}/{stem}.%(ext)s"
        cmd = [
            "yt-dlp",
            "--cookies",
            str(cookies_path),
            "--no-overwrites",
            "--retries",
            "3",
            "--fragment-retries",
            "3",
            "--sleep-requests",
            rate["sleep_requests"],
            "--sleep-interval",
            rate["sleep_interval"],
            "--max-sleep-interval",
            rate["max_sleep_interval"],
            "-P",
            str(download_dir),
            "-o",
            output_template,
            "--write-info-json",
            "--write-thumbnail",
            "--embed-metadata",
            "--merge-output-format",
            "mp4",
            "--windows-filenames",
            url,
        ]

        result = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
        )

        output = result.stdout or ""
        media_files = get_output_files(download_dir, row)
        success = result.returncode == 0 and bool(media_files)

        if success:
            success_log["entries"][key] = success_entry(row, media_files)
            failure_log["entries"].pop(key, None)
            save_log(paths["success_path"], success_log, SCRIPT_NAME)
            save_log(paths["failure_path"], failure_log, SCRIPT_NAME)
            print(f"[{idx}/{len(rows)}] OK: {row.get('platform')} / {label}")
        else:
            reason = extract_failure_reason(result.returncode, output, media_files)
            failure_log["entries"][key] = failure_entry(
                row,
                result.returncode,
                reason,
                existing=failure_log["entries"].get(key),
            )
            save_log(paths["failure_path"], failure_log, SCRIPT_NAME)
            print(f"[{idx}/{len(rows)}] FAILED: {row.get('platform')} / {label}")
            print(f"Reason: {reason}")

        print()


def selected_platforms(platform):
    if platform == "all":
        return ["instagram", "tiktok"]
    return [platform]


def load_rows(args, script_dir):
    rows = []
    platforms = selected_platforms(args.platform)

    if "instagram" in platforms:
        json_path = resolve_data_path(
            args.json,
            script_dir,
            default_name="liked_posts.json",
            glob_pattern="liked_posts*.json",
        )
        print(f"Reading Instagram data: {json_path}")
        rows.extend(extract_instagram_rows(json_path))

    if "tiktok" in platforms:
        json_path = resolve_data_path(
            args.tiktok_json,
            script_dir,
            default_name="user_data_tiktok.json",
            glob_pattern="*tiktok*.json",
        )
        print(f"Reading TikTok data: {json_path}")
        rows.extend(extract_tiktok_rows(json_path))

    rows.sort(key=lambda row: row.get("sort_timestamp", 0), reverse=True)
    return rows


def build_parser():
    parser = argparse.ArgumentParser(
        description="Bulk download liked Instagram and TikTok media from export JSON files."
    )
    parser.add_argument(
        "--platform",
        choices=["instagram", "tiktok", "all"],
        default="instagram",
        help="Platform to download. Default: instagram.",
    )
    parser.add_argument(
        "--json",
        default=None,
        help="Instagram liked posts JSON file. Defaults to data/liked_posts.json.",
    )
    parser.add_argument(
        "--tiktok-json",
        default=None,
        help="TikTok user data JSON file. Defaults to data/user_data_tiktok.json.",
    )
    parser.add_argument(
        "--cookies",
        default="cookies_instagram.txt",
        help="Instagram cookies file in Netscape format.",
    )
    parser.add_argument(
        "--tiktok-cookies",
        default="cookies_tiktok.txt",
        help="TikTok cookies file in Netscape format.",
    )
    parser.add_argument(
        "--destination",
        "--output",
        dest="destination",
        default=None,
        help="Folder where the timestamped download folder will be created.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Download only N new items that are not already in logs/success.json.",
    )
    parser.add_argument(
        "--safe-threshold",
        type=int,
        default=50,
        help="If selected downloads exceed this count, auto mode uses slower rate-limit settings.",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "fast", "safe"],
        default="auto",
        help="Download pacing mode.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Empty logs/success.json and logs/failure.json before downloading.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show selected downloads without downloading media.",
    )
    return parser


def download_folder_name(platform):
    slug = timestamp_slug()
    if platform == "all":
        return f"media_download_{slug}"
    return f"{platform}_download_{slug}"


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.limit is not None and args.limit < 1:
        print("ERROR: --limit must be 1 or greater.")
        sys.exit(1)

    script_dir = Path(__file__).resolve().parent
    logs_dir = script_dir / "logs"
    success_path = logs_dir / "success.json"
    failure_path = logs_dir / "failure.json"

    destination = Path(args.destination).expanduser() if args.destination else Path.cwd()
    if not destination.is_absolute():
        destination = (Path.cwd() / destination).resolve()

    download_dir = destination / download_folder_name(args.platform)

    paths = {
        "download_dir": download_dir,
        "instagram_cookies_path": resolve_file_path(args.cookies, script_dir),
        "tiktok_cookies_path": resolve_file_path(args.tiktok_cookies, script_dir),
        "success_path": success_path,
        "failure_path": failure_path,
    }

    if args.reset:
        save_log(success_path, empty_log(f"{SCRIPT_NAME} --reset"), SCRIPT_NAME)
        save_log(failure_path, empty_log(f"{SCRIPT_NAME} --reset"), SCRIPT_NAME)
        print("Reset complete: logs/success.json and logs/failure.json were emptied.")

    success_log = load_log(success_path, SCRIPT_NAME)
    failure_log = load_log(failure_path, SCRIPT_NAME)

    removed_failures = refresh_failure_log(success_log, failure_log)
    save_log(failure_path, failure_log, SCRIPT_NAME)

    rows = load_rows(args, script_dir)

    if not rows:
        print("No supported media URLs found.")
        sys.exit(1)

    selected_rows, skipped_success = select_rows_to_download(
        rows,
        success_log,
        args.limit,
    )

    print(f"Found {len(rows)} unique media URLs.")
    print(f"Already successful: {skipped_success}")
    if removed_failures:
        print(f"Cleaned {removed_failures} stale failure entries.")

    if args.limit is not None:
        print(f"Limit applied: downloading {len(selected_rows)} new item(s).")

    if not selected_rows:
        print("Nothing new to download.")
        return

    download_rows(selected_rows, args, paths, success_log, failure_log)
    print("Done.")


if __name__ == "__main__":
    main()

