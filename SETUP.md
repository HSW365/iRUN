# iRun: setup

iRun makes and posts short videos for @hsw365media and turns comments and DMs into leads.

- **Engine** (`engine/`): Claude writes the script, the voiceover is generated (free edge-tts by default, ElevenLabs if you add a key), the video is rendered in the HSW365 brand look, then it's posted to TikTok and Instagram Reels.
- **Faceless videos** (`engine/faceless.py`): type an idea and iRun writes the story, makes an AI picture for every line in the look you pick, voices it, and burns in word-by-word captions. See "Faceless videos" below.
- **Schedule** (`.github/workflows/irun.yml`): 4 TikToks + 2 Reels a day at 8am, 11am, 2pm and 6pm ET. The 6pm slot is the daily faceless video for accounts that have a series, and it also goes to YouTube Shorts. It runs free on GitHub Actions.
- **Lead bot** (Supabase edge function `irun-ig-webhook`, already deployed): when someone comments or DMs a keyword on Instagram, it DMs them the link and logs the lead.
- **Dashboard** (`dashboard.html`): shows leads, posts (with video players), and connection status.
- **Owner access**: `config/owners.json` and the `irun_accounts` table list your emails and handles as permanent elite comp accounts.

Data lives on the Supabase project `klipit` (`lsxdlmrjrcivxwgfkpop`) in the `irun_*` tables and the `irun-media` bucket. The dedicated "Irun" project is paused because the free plan caps you at 2 active projects.

- **Accounts** (`config/accounts.json`): every brand iRun runs: @hsw365media, @hoodstar365, and clients. See CLIENTS.md.
- **Content queue** (`content/queue/`): scripts written ahead of time by the daily Claude writer. iRun uses these first,
  so it runs without an Anthropic API key. Posted scripts move to `content/posted/`.

Every run starts with a **preflight** block in the log that lists which keys are set and which accounts are connected.
Read that first when something isn't posting.

## Keywords

| Keyword | App | Link |
|---|---|---|
| CLIP | Klipit | klipit.onrender.com |
| CALL | CallTwin | calltwin.onrender.com |
| SITE | QUEENEE | hsw365.github.io/queenee/ |
| FLIP | FLIPIT | flipit-m5ig.onrender.com |
| AUTO | iRun | hsw365.github.io/iRUN/ |
| BUILD | Build Series | hsw365.co |

To change these, edit `config/products.json`. The next run syncs them to the bot.

## 1. GitHub secrets
Go to repo **Settings > Secrets and variables > Actions > New repository secret** and add:

| Secret | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` (optional) | console.anthropic.com > API keys. Only needed when the content queue runs dry |
| `SUPABASE_SERVICE_KEY` | Supabase > klipit project > Settings > API > `service_role` secret |
| `ELEVENLABS_API_KEY` (optional) | elevenlabs.io > Profile > API key. Without it, the free voice is used |
| `ELEVENLABS_VOICE_ID` (optional) | the voice you want |

With just these, **Actions > iRun autopilot > Run workflow** (mode `draft`) makes videos you can watch in the dashboard. Nothing gets posted in draft mode.

## 2. TikTok
1. Go to developers.tiktok.com, create an app, and add **Login Kit** and **Content Posting API** (turn on Direct Post). Scopes: `user.info.basic` and `video.publish`.
2. Set the redirect URI to `https://hsw365.github.io/iRUN/callback.html`.
3. Add the secrets `TIKTOK_CLIENT_KEY` and `TIKTOK_CLIENT_SECRET`.
4. On your PC, set those two values as environment variables, then run `python engine/tiktok_auth.py`. Approve the login with @hsw365media and paste the code it shows you. Save the printed token as `TIKTOK_REFRESH_TOKEN`.
5. **Important:** TikTok only lets an app post **publicly** after it passes TikTok's app audit, which you submit in the developer portal. Until then, TikTok forces every post to "Only me". iRun detects this and logs it.

## 3. Instagram
1. @hsw365media must be a **Professional** (Business or Creator) account.
2. Go to developers.facebook.com, create an app (type Business), and add **Instagram > API setup with Instagram login**. Add @hsw365media and generate a token. Permissions: `instagram_business_basic`, `instagram_business_content_publish`, `instagram_business_manage_messages`, `instagram_business_manage_comments`.
3. Add the secret `IG_ACCESS_TOKEN` (the long-lived token). Optionally add `IG_USER_ID`. iRun refreshes the token on every run and stores the fresh copy.
4. Set up webhooks for the lead bot:
   - Callback URL: `https://lsxdlmrjrcivxwgfkpop.supabase.co/functions/v1/irun-ig-webhook`
   - Verify token: stored in `irun_settings.ig_verify_token`
   - Subscribe to the `comments` and `messages` fields.
5. Optionally, to enforce webhook signatures, insert your app secret as `ig_app_secret` into `irun_settings`.
6. For the bot to DM people other than your app's testers, Meta has to approve the messaging and comments permissions through App Review. Until then, the bot only works for accounts that have a role on the app.

## 4. YouTube Shorts (optional)
1. Go to console.cloud.google.com, create a project, and enable **YouTube Data API v3**.
2. Set up the OAuth consent screen (External) and add your Google account as a test user. Then create credentials: **OAuth client ID**, type **Desktop app**.
3. Add the secrets `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET`.
4. On your PC, set those two values as environment variables, then run `python engine/youtube_auth.py --account hoodstar365`. Approve in the browser. Save the printed token as `YOUTUBE_REFRESH_TOKEN`.
5. **Important:** until Google audits the API project, YouTube locks every video uploaded through it to private. iRun logs when that happens. Request the audit in the Google Cloud console (YouTube API Services compliance audit) to post publicly. While the consent screen is in "Testing", the login also expires after 7 days; publish the consent screen to stop that.

Other accounts: add `"youtube"` to the account's `platforms` in `config/accounts.json` and run the login with `--account <id>` and the Supabase variables set.

## Faceless videos

A faceless video is a voiceover over AI pictures with captions that light up word by word. No product pitch, no camera.

**Three ways to make one**
- **Studio** (`https://hsw365.github.io/iRUN/app.html` > **Faceless**): type an idea, pick a look and length, edit the lines and pictures, render, then Share or Download. Needs your Anthropic key in Settings. Add an ElevenLabs key for a voiceover.
- **Actions > iRun autopilot > Run workflow**: fill in **idea** (and optionally **style** and **account**). The video shows up in the dashboard. Needs the `ANTHROPIC_API_KEY` secret.
- **Autopilot**: every day at the 6pm ET slot, each account with a series in `config/series.json` gets one faceless video, posted to its TikTok, Instagram and YouTube. It uses queued scripts first (`content/queue/*-faceless-*.json`), then Claude if `ANTHROPIC_API_KEY` is set.

**Series** (`config/series.json`): one entry per faceless channel: account, topic, look, angles and the follow line. Set `"enabled": false` to pause one.

**Looks** (`config/styles.json`): cinematic, noir, anime, comic, 3d, dark-fantasy, cyberpunk, oil, watercolor, vintage, photoreal, minimal.

**Pictures**: made by Pollinations. With no key it is free, but the pictures are lower resolution, carry a small pollinations.ai mark in the bottom corner, and the service refuses requests for a few seconds after a burst (iRun waits and retries; if a picture still can't be made, that scene gets a plain backdrop and the log says so). For sharp, unmarked pictures, get a key at enter.pollinations.ai and add it as the secret `POLLINATIONS_TOKEN`.

**Voice and captions**: the free voice gives exact word timing, so captions stay in sync. With `ELEVENLABS_API_KEY` set, ElevenLabs is used instead.

## 5. Go live
After you've watched a few drafts in the dashboard, go to **Settings > Secrets and variables > Actions > Variables**, add `IRUN_MODE` = `live`, and scheduled runs will start posting. Set it back to `draft` to pause posting without stopping the drafts.

## Dashboard
`https://hsw365.github.io/iRUN/dashboard.html`: enter the owner key (stored in `irun_settings.owner_key`).

## Run locally
```
pip install -r requirements.txt
python engine/run.py --platform both --product klipit --mode draft
python engine/run.py --kind faceless --account hoodstar365 --mode draft
python engine/run.py --idea "why discipline beats motivation" --account hoodstar365 --style anime
```
