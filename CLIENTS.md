# Running iRun for clients

iRun runs short-form video for any brand, not just HSW365. Each brand is an **account** in
`config/accounts.json`. Every scheduled run makes videos for every enabled account: 4 TikToks and 2 Reels a day
per account at 8am, 11am, 2pm and 6pm ET.

## Add a client

1. Add an entry to `config/accounts.json`:

```json
{
  "id": "acmeplumbing",
  "brand": "Acme Plumbing",
  "handle": "acmeplumbing",
  "type": "client",
  "enabled": true,
  "platforms": ["tiktok", "instagram"],
  "lead_bot": false,
  "voice": "Acme Plumbing, a family-owned plumber in Vineland NJ. Friendly, straight-talking, local.",
  "products": [
    {
      "id": "emergency",
      "name": "24/7 PLUMBING",
      "keyword": "FIX",
      "link": "https://acmeplumbing.com",
      "cta": {
        "spoken": "Call Acme Plumbing. Link in bio",
        "screen": ["CALL ACME PLUMBING", "LINK IN BIO"],
        "caption": "Call Acme Plumbing any time. Link in bio."
      },
      "audience": "homeowners in South Jersey",
      "pitch": "Only what the client actually offers, in plain words.",
      "angles": ["burst pipe at 2am", "the plumber who picks up"]
    }
  ]
}
```

   Use only facts the client gave you. No prices unless the client confirmed them.

2. Connect their logins. Use one TikTok developer app for every account; each client just approves it.
   - **TikTok:** the client approves iRun with `python engine/tiktok_auth.py --account acmeplumbing`, with the
     Supabase variables set so the login saves straight into iRun. TikTok only allows public posts after
     TikTok approves the app; until then, posts go out as "Only me".
   - **Instagram:** the client's account must be Business or Creator. Save their long-lived token in Supabase
     table `irun_tokens` as name `instagram:acmeplumbing`.

   Until a login is connected, iRun still makes the client's videos as drafts, so you can show them before
   they go live.

3. Give them content. Queue scripts in `content/queue/` with `"account": "acmeplumbing"` (the daily Claude
   writer does this for every enabled account), or set `ANTHROPIC_API_KEY` and iRun writes its own when the
   queue runs dry.

## Pause or remove a client

Set `"enabled": false`. Their logins and history stay in place.

## Where to see results

`irun_posts` records every video with its `account`, platform, status and link. Failed publishes keep their
queue item for up to 3 tries, then move to `content/failed/`. Published items move to `content/posted/`.
