# Instagram Bulk Downloader

Download your liked Instagram posts and reels from a Meta liked posts JSON file.

## Folder Setup

Keep the project folder like this:

```plaintext
downloader_instagram.py
cookies_instagram.txt
data/
  liked_posts_2026-06-05.json
logs/
  success.json
  failure.json
```

Downloaded media is saved into a timestamped folder:

```plaintext
instagram_download_20260605_091500/
  someuser/
    someuser_ABC123.mp4
    someuser_ABC123.webp
```

## Commands

Download everything that has not already been downloaded:

```powershell
py .\downloader_instagram.py
```

Download 10 new items:

```powershell
py .\downloader_instagram.py --limit 10
```

Use slower download pacing:

```powershell
py .\downloader_instagram.py --mode safe
```

Use faster download pacing:

```powershell
py .\downloader_instagram.py --mode fast
```

Use a different liked posts JSON file:

```powershell
py .\downloader_instagram.py --json ".\data\liked_posts_2026-06-05.json"
```

Save the download folder somewhere else:

```powershell
py .\downloader_instagram.py --destination "D:\Instagram Backups"
```

Start over and redownload everything:

```powershell
py .\downloader_instagram.py --reset
```

Preview what would be downloaded:

```powershell
py .\downloader_instagram.py --limit 10 --dry-run
```

## Resume Behavior

Downloaded items are recorded in `logs/success.json`. If an item is already listed there, it is skipped automatically.

Failed items are recorded in `logs/failure.json`. If a failed item later succeeds, it is removed from `failure.json`.

`--reset` empties both log files, but it does not delete media files.
