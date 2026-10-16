# Meta App Review: Instagram permissions

Paste-ready text for the App Review form. The app being reviewed is the Instagram workspace at
https://hsw365.github.io/iRUN/instagram.html (backend: Supabase edge function `irun-ig-auth`).

## Settings to have in place first

| Field | Value |
|---|---|
| OAuth redirect URI | `https://hsw365.github.io/iRUN/instagram.html` |
| Deauthorize callback URL | `https://lsxdlmrjrcivxwgfkpop.supabase.co/functions/v1/irun-ig-auth?a=deauthorize` |
| Data deletion request URL | `https://lsxdlmrjrcivxwgfkpop.supabase.co/functions/v1/irun-ig-auth?a=delete` |
| Privacy policy URL | `https://hsw365.github.io/iRUN/privacy.html` |
| Terms of service URL | `https://hsw365.github.io/iRUN/terms.html` |
| User data deletion (instructions URL, if asked) | `https://hsw365.github.io/iRUN/data-deletion.html` |
| App icon | 1024 x 1024 |
| Business verification | HSW365 Media LLC (Business Settings > Security Center) |

## 1. Can the app be loaded and tested externally?

```
Yes. iRun is a public web app. No download, install or iRun account is needed to test it.

1. Open https://hsw365.github.io/iRUN/instagram.html
2. Click "Connect Instagram" and log in with any Instagram Business or Creator account.
3. Approve the requested permissions. You return to the iRun workspace.
4. Use the tabs: Overview (profile and posts), Create post (publish), Comments, Inbox (DMs), Settings (disconnect).

To test messaging, send a DM to the connected account from a second Instagram account first.
To test comments, comment on one of the connected account's posts from a second account first.
```

## 2. Use case and step-by-step usage

```
iRun is a social media management tool for small businesses and creators, run by HSW365 Media LLC. A business owner connects their Instagram Business or Creator account and manages it from one dashboard: publishing posts and reels, handling comments, and replying to customer messages.

How a person uses iRun:
1. The user opens https://hsw365.github.io/iRUN/instagram.html and clicks "Connect Instagram".
2. They log in on Instagram (Instagram Business Login) and review and approve the permissions.
3. They return to iRun. The Overview tab shows their username, profile photo, post/follower counts and recent posts, confirming which account is connected.
4. In "Create post" they choose Photo or Reel, upload a file, write a caption, check the preview, and click "Publish to Instagram". iRun uploads the media, creates the container, waits for Instagram to process it and publishes it to their own account, then links to the live post.
5. In "Comments" they see comments on their recent posts and can reply, hide/unhide or delete each one.
6. In "Inbox" they see conversations that people started with their account and reply. iRun only allows a reply when the other person messaged first and the last message is within Instagram's 24-hour window. It never starts conversations or sends bulk or promotional messages.
7. In "Settings" they can disconnect, which deletes their access token and stored data immediately. Removing iRun in Instagram's Apps and websites also deletes their data through our deauthorize and data deletion callbacks.
```

## 3. Permission justifications

**instagram_business_basic**
```
Used to read the connected account's profile (user ID, username, name, profile photo, account type, follower/following/media counts) and its recent media. iRun shows this on the Overview tab so the user can confirm which account is connected and see what they have already posted. Every other feature depends on knowing the account's ID.
```

**instagram_business_content_publish**
```
Used on the "Create post" tab to publish a photo or reel that the user uploads and captions themselves. iRun creates a media container, checks its processing status and publishes it to the user's own account, only when the user clicks "Publish to Instagram". iRun never posts to any account other than the one the user connected.
```

**instagram_business_manage_comments**
```
Used on the "Comments" tab to read comments on the user's own recent posts and let the user reply to, hide, unhide or delete them. This lets a business handle customer questions and remove spam on its posts without leaving the dashboard. All actions are taken by the user, one comment at a time.
```

**instagram_business_manage_messages**
```
Used on the "Inbox" tab to read conversations that customers start with the business's Instagram account, and to send the business's reply. iRun only allows a reply inside a conversation the customer started, and only within 24 hours of the customer's last message; the send button is disabled otherwise and the server enforces the same rule. iRun does not send unsolicited, bulk or promotional messages.
```

## 4. Screen recordings (one per permission)

Under 2 minutes each, English UI, start from a signed-out browser so the Instagram login and permission screen are visible.

| Permission | Record this |
|---|---|
| instagram_business_basic | Open instagram.html > Connect Instagram > Instagram login > approve permissions > back in iRun: Overview shows @username, photo, counts and the post grid |
| instagram_business_content_publish | Login flow > Create post > Photo > upload image > type caption > Publish > status steps finish > click "View the post" and show it live on Instagram |
| instagram_business_manage_comments | Login flow > from a second account, comment on a post > Comments tab > Refresh > Reply (show reply on Instagram) > Hide > Delete |
| instagram_business_manage_messages | Login flow > from a second account, DM the connected account > Inbox > Refresh > open the conversation > reply > show the reply arriving in the second account's Instagram DMs |
