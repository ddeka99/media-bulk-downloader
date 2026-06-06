# Media Bulk Downloader

Download your liked Instagram and TikTok videos from your export files.

## Folder Setup

Keep the project folder like this:

```plaintext
media_downloader.py
cookies_instagram.txt
cookies_tiktok.txt
data/
  liked_posts.json
  user_data_tiktok.json
logs/
  success.json
  failure.json
```

Downloaded media is saved into timestamped folders:

```plaintext
instagram_download_20260605_091500/
  someuser/
    someuser_ABC123.mp4
    someuser_ABC123.webp

tiktok_download_20260605_091500/
  tiktok/
    tiktok_7582799302204886293.mp4
```

## Commands

Download all new Instagram items:

```powershell
py .\media_downloader.py
```

Download all new TikTok liked videos:

```powershell
py .\media_downloader.py --platform tiktok
```

Download new Instagram and TikTok items together:

```powershell
py .\media_downloader.py --platform all
```

Download 10 new items:

```powershell
py .\media_downloader.py --limit 10
```

Use slower download pacing:

```powershell
py .\media_downloader.py --mode safe
```

Use faster download pacing:

```powershell
py .\media_downloader.py --mode fast
```

Use a different Instagram liked posts JSON file:

```powershell
py .\media_downloader.py --json ".\data\liked_posts.json"
```

Use a different TikTok user data JSON file:

```powershell
py .\media_downloader.py --platform tiktok --tiktok-json ".\data\user_data_tiktok.json"
```

Save the download folder somewhere else:

```powershell
py .\media_downloader.py --destination "D:\Media Backups"
```

Start over and redownload everything:

```powershell
py .\media_downloader.py --reset
```

Preview what would be downloaded:

```powershell
py .\media_downloader.py --platform tiktok --limit 10 --dry-run
```

## Resume Behavior

Downloaded items are recorded in `logs/success.json`. If an item is already listed there, it is skipped automatically.

Failed items are recorded in `logs/failure.json`. If a failed item later succeeds, it is removed from `failure.json`.

`--reset` empties both log files, but it does not delete media files.
