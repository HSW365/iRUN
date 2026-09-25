# iRun: setup

iRun makes and posts short videos for @hsw365media and turns comments and DMs into leads.

- **Engine** (`engine/`): Claude writes the script, the voiceover is generated (free edge-tts by default, ElevenLabs if you add a key), the video is rendered in the HSW365 brand look, then it's posted to TikTok and Instagram Reels.
- **Schedule** (`.github/workflows/irun.yml`): 4 TikToks + 2 Reels a day at 8am, 11am, 2pm and 6pm ET. It runs free on GitHub Actions.
- **Lead bot** (Supabase edge function `irun-ig-webhook`, already deployed): when someone comments or DMs a keyword on Instagram, it DMs them the link and logs the lead.
- **Dashboard** (`dashboard.html`): shows leads, posts (with video players), and connection status.
- **Owner access**: `config/owners.json` and the `irun_accounts` table list your emails and handles as permanent elite comp accounts.

Data lives on the Supabase project `klipit` (`lsxdlmrjrcivxwgfkpop`) in the `irun_*` tables and the `irun-media` bucket. The dedicated "Irun" project is paused because the free plan caps you at 2 active projects.

## Keywords

| Keyword | App | Link |
|---|---|---|
| CLIP | Klipit | klipit.onrender.com |
| CALL | CallTwin | calltwin.onrender.com |
| SITE | QUEENEE | hsw365.github.io/queenee/ |
| FLIP | FLIPIT | flipit-m5ig.onrender.com |
| AUTO | iRun | hsw365.github.io/irun/ |
| BUILD | Build Series | hsw365.co |

To change these, edit `config/products.json`. The next run syncs them to the bot.

## 1. GitHub secrets
Go to repo **Settings > Secrets and variables > Actions > New repository secret** and add:

| Secret | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com > API keys |
| `SUPABASE_SERVICE_KEY` | Supabase > klipit project > Settings > API > `service_role` secret |
| `ELEVENLABS_API_KEY` (optional) | elevenlabs.io > Profile > API key. Without it, the free voice is used |
| `ELEVENLABS_VOICE_ID` (optional) | the voice you want |

With just these, **Actions > iRun autopilot > Run workflow** (mode `draft`) makes videos you can watch in the dashboard. Nothing gets posted in draft mode.

## 2. TikTok
1. Go to developers.tiktok.com, create an app, and add **Login Kit** and **Content Posting API** (turn on Direct Post). Scopes: `user.info.basic` and `video.publish`.
2. Set the redirect URI to `https://hsw365.github.io/irun/callback.html`.
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

## 4. Go live
After you've watched a few drafts in the dashboard, go to **Settings > Secrets and variables > Actions > Variables**, add `IRUN_MODE` = `live`, and scheduled runs will start posting. Set it back to `draft` to pause posting without stopping the drafts.

## Dashboard
`https://hsw365.github.io/irun/dashboard.html`: enter the owner key (stored in `irun_settings.owner_key`).

## Run locally
```
pip install -r requirements.txt
python engine/run.py --platform both --product klipit --mode draft
```
