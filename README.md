# Instagram Comment-to-DM Automation

A small, self-hosted, ManyChat-style tool. When someone comments a trigger keyword
(e.g. "guide") on an Instagram post you picked, the app:

1. posts a **public reply** under their comment, and
2. sends them a **private DM**.

It uses **only the official Instagram Graph API**: no Selenium, no scraping, no
unofficial libraries.

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy (SQLite by default, Postgres-ready)
- **Frontend:** Jinja2 templates plus plain JS/CSS (no build step)
- **Deploy:** Dockerfile, `railway.toml`, `render.yaml`

---

## Contents

1. [How it works](#how-it-works)
2. [Project structure](#project-structure)
3. [Run it locally](#run-it-locally)
4. [Instagram API setup (step by step)](#instagram-api-setup-step-by-step)
5. [Important: DM limitations and permission review](#important-dm-limitations-and-permission-review)
6. [Deploying](#deploying)
7. [Environment variables](#environment-variables)
8. [API reference](#api-reference)
9. [Troubleshooting](#troubleshooting)

---

## How it works

```
Instagram ──(comment webhook)──▶ POST /webhook/instagram
                                   │ 1. verify X-Hub-Signature-256 (HMAC with App Secret)
                                   │ 2. respond 200 immediately, process in background
                                   ▼
                         is the post tracked by an active campaign?
                         does the comment contain a keyword? (case-insensitive, partial)
                                   │ yes
                                   ▼
                  claim comment_id in processed_comments (unique → dedup)
                                   │
              ┌────────────────────┴─────────────────────┐
     POST /{comment-id}/replies               POST /{page-id}/messages
       (public reply)                  recipient: {comment_id}  ("Private Reply")
                                       fallback → recipient: {id: commenter}
```

- **Deduplication.** Meta retries webhooks and sometimes delivers the same event
  twice. Each matching comment ID is inserted into `processed_comments` (unique
  column) *before* any API call, so a comment is only ever handled once.
- **No loops.** Your own replies also trigger comment webhooks. Comments from
  your own account are ignored.
- **Retries.** Every Graph API call is logged (with the token redacted). On a
  rate limit (HTTP 429, or error codes 4, 17, 32, 613, …) or a 5xx error, the
  call is retried with exponential backoff (1s, 2s, 4s), and `Retry-After` is
  respected.
- **Activity log.** Each processed comment records whether the reply and the DM
  succeeded or failed, and the error if any. You can see this under **Recent
  activity** on the dashboard.

## Project structure

```
/
├── main.py              # FastAPI app entry point (+ /health)
├── instagram.py         # Instagram Graph API client (retry/backoff, logging)
├── models.py            # SQLAlchemy models: Config, Campaign, ProcessedComment
├── database.py          # Engine / session setup
├── auth.py              # Optional HTTP Basic auth for dashboard + API
├── routes/
│   ├── webhook.py       # GET/POST /webhook/instagram
│   ├── dashboard.py     # /dashboard HTML pages
│   └── api.py           # REST API for campaigns / config / post previews
├── static/              # style.css, app.js
├── templates/           # base.html, campaigns.html, settings.html
├── tests/               # pytest suite (mocks the Graph API)
├── .env.example
├── Dockerfile
├── railway.toml
├── render.yaml
└── requirements.txt
```

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env         # then fill in the values (see below)
uvicorn main:app --reload
```

Open <http://localhost:8000/dashboard>.

Run the tests:

```bash
pip install -r requirements-dev.txt
pytest
```

Meta can only deliver webhooks to a **public HTTPS URL**. While developing,
expose your local server with a tunnel such as `ngrok http 8000` or
`cloudflared tunnel --url http://localhost:8000`, and use that URL in the
webhook setup below.

---

## Instagram API setup (step by step)

You'll need an Instagram account, a Facebook account, and about 30 minutes.

### Step 1: Convert your Instagram account to Business or Creator

1. In the Instagram app, go to **Profile → ☰ → Settings and privacy → Account type and tools**.
2. Tap **Switch to professional account** and choose **Business** or **Creator**.
3. Link it to a **Facebook Page**. If you don't have a Page, create one at
   <https://www.facebook.com/pages/create>. The Page is required because
   Instagram messaging goes through it.
   - To check the link later, go to Instagram **Settings → Business tools and
     controls → Connect or create a Facebook Page**. You can also check from
     the Facebook Page: **Settings → Linked accounts → Instagram**.
4. In Instagram go to **Settings → Messages and story replies → Message
   controls → Connected tools**, and turn **Allow access to messages** **ON**.
   Without this, DMs from the API fail.

### Step 2: Create a Facebook Developer App

1. Go to <https://developers.facebook.com>. Log in and, if prompted, register as
   a developer.
2. Click **My Apps → Create App**.
3. For the use case, choose **Other**. Then choose app type **Business**. (The
   wording changes from time to time. Pick the option that lets you add
   "Instagram" and "Webhooks" products.)
4. Give it a name, such as "Comment to DM", and create it.
5. In **App settings → Basic**, note the **App ID** and click **Show** next to
   **App Secret**. These are `FACEBOOK_APP_ID` and `FACEBOOK_APP_SECRET`.
   Also fill in a **Privacy Policy URL**, which you need to go Live later.

### Step 3: Add the Instagram Graph API product

1. In the app dashboard, click **Add Product**.
2. Add **Instagram**. This is the Instagram Graph API; use the *"API setup
   with Facebook login"* path.
3. Add **Webhooks** as well. You'll configure it in step 6.

### Step 4: Add the required permissions

This app uses these permissions (scopes):

| Permission | Why |
| --- | --- |
| `instagram_basic` | Read the account and media (post previews) |
| `instagram_manage_comments` | Read comments and **post replies** |
| `instagram_manage_messages` | **Send DMs** / Private Replies |
| `pages_show_list` | Find the Page linked to the IG account |
| `pages_read_engagement` | Read Page data and derive the Page token |
| `pages_manage_metadata` | Subscribe the Page to webhooks |
| `business_management` | Sometimes required when the Page is in a Business Manager |

In **App Review → Permissions and Features**, you'll see these listed. In
**Development mode** you can use all of them straight away with accounts that
have a **role on the app** (Admin/Developer/Tester, set under **App roles**).
To use them with other people's comments in production, see
[DM limitations](#important-dm-limitations-and-permission-review).

> Development mode caveat: while the app is in Development mode, webhooks and DMs
> only work for users who have a role on the app. To test end to end, comment
> from a second Instagram account that you've added as an **Instagram Tester**
> (App roles → Roles → Add Instagram Testers, then accept the invite on
> instagram.com → Settings → Apps and websites → Tester invites). Or switch the
> app to **Live** after App Review.

### Step 5: Generate a long-lived User Access Token

**5a. Get a short-lived token (valid about 1 hour).**

1. Open the **Graph API Explorer**: <https://developers.facebook.com/tools/explorer/>.
2. Top right: select **your app**, then choose **User Token** under "User or Page".
3. Under **Permissions**, add all the permissions from step 4.
4. Click **Generate Access Token** and approve the Facebook login dialog. Make
   sure you **select your Page and Instagram account** when asked.
5. Copy the token.

**5b. Exchange it for a long-lived token (valid about 60 days).**

```bash
curl -G "https://graph.facebook.com/v23.0/oauth/access_token" \
  -d grant_type=fb_exchange_token \
  -d client_id=YOUR_APP_ID \
  -d client_secret=YOUR_APP_SECRET \
  -d fb_exchange_token=SHORT_LIVED_TOKEN
```

The `access_token` in the response is your **long-lived token**
(`INSTAGRAM_ACCESS_TOKEN`). You can also use the **Access Token Debugger**
(<https://developers.facebook.com/tools/debug/accesstoken/>). Paste the token and
click **Extend Access Token**.

**5c. Find your Page ID and Instagram Business Account ID.**

In Graph API Explorer (with the long-lived token), run:

```
GET /me/accounts?fields=id,name,instagram_business_account
```

The response looks like this:

```json
{ "data": [ { "id": "1234567890",                     ← FACEBOOK_PAGE_ID
              "name": "My Page",
              "instagram_business_account": { "id": "17841400000000000" } } ] }  ← INSTAGRAM_BUSINESS_ACCOUNT_ID
```

Enter the token, Page ID, and IG account ID in **Dashboard → Settings** and
click **Test connection**. You should see "Connected as @yourhandle".

**Refreshing the token (it expires after 60 days).** Long-lived user tokens
last about 60 days, and **you must refresh them before they expire**.
Refreshing requires a still-valid token (at least 24 hours old).

- **Easiest:** set `FACEBOOK_APP_ID` and `FACEBOOK_APP_SECRET`. A **Refresh
  token (60 days)** button then appears in Settings. It runs the exchange above
  with the current token and saves the new one with its expiry date.
- **Manually:** run the same `fb_exchange_token` curl command above, passing
  your *current long-lived token* as `fb_exchange_token`, then paste the result
  into Settings.
- Set a calendar reminder for roughly day 50. If the token does expire, repeat
  5a and 5b.
- Tip: messaging uses a *Page* access token. The app derives it automatically
  from your user token via `GET /{page-id}?fields=access_token`. A Page token
  derived from a long-lived user token doesn't expire. Advanced users can paste
  that Page token directly as the access token for a longer-lived setup.

### Step 6: Configure the webhook

1. Deploy the app, or start a tunnel, so it's reachable at
   `https://YOUR-DOMAIN`. Make sure `WEBHOOK_VERIFY_TOKEN` and
   `FACEBOOK_APP_SECRET` are set in its environment.
2. In the developer dashboard, go to **Webhooks** (or **Instagram → Configure
   webhooks**). Select the **Instagram** object and click **Subscribe to this
   object**:
   - **Callback URL:** `https://YOUR-DOMAIN/webhook/instagram` (shown with a
     Copy button on the Settings page)
   - **Verify token:** the exact value of `WEBHOOK_VERIFY_TOKEN`
   - Click **Verify and save**. Meta calls `GET /webhook/instagram` and the app
     echoes back `hub.challenge`.
3. In the field list, **subscribe to `comments`**. Optionally, click **Test**
   next to it and watch the app logs.
4. **Subscribe your Page to the app.** Webhooks only fire for accounts whose
   Page is subscribed. In Graph API Explorer, using the **Page token** (switch
   "User or Page" to your Page), run:

   ```
   POST /{PAGE_ID}/subscribed_apps?subscribed_fields=feed
   ```

   It should return `{"success": true}`. (On Instagram, installing the app for
   the connected account via the login dialog in step 5 usually handles this
   too. This step makes sure of it.)
5. Make sure the app is **Live**, or that the commenter has a role on the app
   (see the Development mode caveat above).

Every incoming webhook is validated against `X-Hub-Signature-256`, an
HMAC-SHA256 of the raw body keyed with your App Secret. Requests with a missing
or invalid signature are rejected with `403`.

### Step 7: Get the Post ID for a specific Instagram video

The Post ID is the **media ID**, a long number such as `17895695668004550`. It
is **not** the short code in the URL (`instagram.com/reel/C8xYz…`).

**Option A: from the dashboard (easiest).** In **New campaign**, click **Browse
posts** and pick the video from your recent posts. The ID is filled in and a
preview loads.

**Option B: Graph API Explorer.**

```
GET /{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media?fields=id,caption,media_type,permalink,timestamp,thumbnail_url&limit=50
```

Find the entry whose `permalink` matches the video's URL, or whose caption you
recognise, and copy its `id`. Reels have `media_type: "VIDEO"`. For older
posts, follow `paging.next`.

When you enter the ID in the campaign form and tab out, the app calls
`get_post_details()` and shows the thumbnail and caption, so you can confirm
it's the right post.

---

## Important: DM limitations and permission review

Instagram restricts who a business can message:

- **Standard messaging window.** A business can freely DM a user only within
  **24 hours of that user messaging the business**. A cold DM to someone who
  has never messaged you (`recipient: {"id": ...}`) is rejected.
- **Private Replies (what this app uses).** Instagram allows a business to send
  **one private DM in response to a comment**, **within 7 days** of the comment,
  even with no prior conversation. The message is addressed with
  `recipient: {"comment_id": "<id>"}`. This is the official mechanism behind
  ManyChat-style "comment for a DM" flows. The app tries a Private Reply first,
  and falls back to a normal DM (`recipient: {"id": <user id>}`) only if that
  fails, which will only work if the user has messaged you in the last 24h.
- **The `instagram_manage_messages` permission needs Advanced Access for
  production.** In Development mode it only works with people who have a role
  on the app. To message the general public:
  1. Complete **Business Verification** (App settings → Basic → Verification,
     or through Meta Business Suite → Security Center).
  2. In **App Review → Permissions and Features**, request **Advanced Access**
     for `instagram_manage_messages`, `instagram_manage_comments`,
     `instagram_basic`, `pages_manage_metadata`, `pages_show_list`, and
     `pages_read_engagement`.
  3. For each permission, describe the use case, for example: *"When a user
     comments a keyword on our post, we reply to the comment and send them a
     single private reply DM with the resource they requested."* Include a
     **screencast** showing the flow end to end: commenting, the automatic
     reply, the DM arriving, and the dashboard configuration.
  4. Provide a privacy policy URL, and test credentials if the reviewer needs
     them.
  5. After approval, switch the app to **Live** mode.
- Instagram also applies its own spam limits. Use plain, useful DM text, and
  avoid sending the same link to huge volumes in a short time.
- The recipient must not have blocked your account, and **Allow access to
  messages** (step 1.4) must be on.

---

## Deploying

The app is a single container listening on `$PORT` with a health check at
`GET /health` → `{"status": "ok"}`. SQLite is stored at `/data/app.db` inside the
container. **Mount a persistent volume at `/data`**, or your campaigns will be
wiped on every redeploy. You can also point `DATABASE_URL` at Postgres (see
below).

### Railway

1. Create a Railway project from this GitHub repo. Railway picks up
   `railway.toml` and the `Dockerfile` automatically.
2. **Settings → Volumes → New volume**, mount path `/data`.
3. **Variables:** add everything from `.env.example`. Don't set `DATABASE_URL`
   (the Dockerfile default `sqlite:////data/app.db` is correct). **Set
   `DASHBOARD_PASSWORD`.**
4. **Settings → Networking → Generate domain**. Use
   `https://<domain>/webhook/instagram` as the webhook callback URL.

### Render

`render.yaml` is a Blueprint. In Render, click **New → Blueprint**, pick the
repo, and fill in the `sync: false`
secrets. `WEBHOOK_VERIFY_TOKEN` is generated for you; copy it from the
dashboard into Meta. The persistent disk requires a paid instance type.

### Plain Docker

```bash
docker build -t ig-comment-dm .
docker run -p 8000:8000 --env-file .env -v igdata:/data ig-comment-dm
```

### Moving to Postgres

Install a driver (`pip install "psycopg[binary]"`, and add it to
`requirements.txt`), then set:

```
DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname
```

Tables are created automatically on startup. No code changes are needed.

---

## Environment variables

| Variable | Required | Description |
| --- | --- | --- |
| `INSTAGRAM_ACCESS_TOKEN` | yes* | Long-lived user access token. *Can be set in the dashboard instead; dashboard values take precedence. |
| `INSTAGRAM_BUSINESS_ACCOUNT_ID` | yes* | IG Business/Creator account ID (`17841…`). *Or set in the dashboard. |
| `FACEBOOK_PAGE_ID` | yes* | Page linked to the IG account; used for sending DMs. *Or set in the dashboard. |
| `FACEBOOK_APP_SECRET` | **yes** | Validates `X-Hub-Signature-256`. Without it, all webhooks are rejected. |
| `WEBHOOK_VERIFY_TOKEN` | **yes** | Any random string; must match the value entered in the Meta webhook setup. |
| `FACEBOOK_APP_ID` | no | Enables the one-click token refresh button. |
| `DATABASE_URL` | no | Default `sqlite:///./app.db` (Docker: `sqlite:////data/app.db`). |
| `DASHBOARD_USERNAME` | no | Basic-auth username for `/dashboard` and `/api` (default `admin`). |
| `DASHBOARD_PASSWORD` | **strongly recommended** | Enables Basic auth on the dashboard and API. Without it, anyone who finds the URL can change your token. |
| `GRAPH_API_VERSION` | no | Default `v23.0`. |
| `LOG_LEVEL` | no | Default `INFO`. |

**Security notes:**

- Secrets are loaded from `.env` via python-dotenv. `.env` is git-ignored.
- The API **never returns the access token**, only a masked preview
  (`EAAG…9xYz`). The token field in Settings is write-only; leave it blank to
  keep the saved token.
- `/health` and `/webhook/instagram` are public. The webhook is protected by
  signature validation. Everything under `/dashboard` and `/api` sits behind
  Basic auth when `DASHBOARD_PASSWORD` is set.

---

## API reference

All `/api` routes require Basic auth when `DASHBOARD_PASSWORD` is set.

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health` | `{"status": "ok"}` |
| GET | `/webhook/instagram` | Meta verification handshake |
| POST | `/webhook/instagram` | Comment events (signature-validated) |
| GET/PUT | `/api/config` | Read (masked) or save credentials |
| POST | `/api/config/test` | Fetch the IG account to verify credentials |
| POST | `/api/config/refresh-token` | Exchange the current token for a fresh 60-day token |
| GET/POST | `/api/campaigns` | List or create campaigns |
| GET/PUT/DELETE | `/api/campaigns/{id}` | Read, update, or delete a campaign |
| POST | `/api/campaigns/{id}/toggle` | Toggle a campaign active/inactive |
| GET | `/api/posts/recent` | Recent media for the post picker |
| GET | `/api/posts/{post_id}` | Post preview (caption, thumbnail) |
| GET | `/api/activity` | Recently processed comments with reply/DM status |

Interactive docs are at `/docs`.

Campaign payload:

```json
{
  "name": "Free guide reel",
  "post_id": "17895695668004550",
  "keywords": "guide, link, info",
  "comment_reply": "Sent! Check your DMs 📩",
  "dm_message": "Here's your guide: https://example.com/guide",
  "is_active": true
}
```

If several active campaigns track the same post, the oldest campaign with a
matching keyword wins.

---

## Troubleshooting

| Symptom | Likely cause / fix |
| --- | --- |
| "Verify and save" fails in Meta | `WEBHOOK_VERIFY_TOKEN` doesn't match, the URL isn't public HTTPS, or the app isn't running. Check the logs for `Webhook verification failed`. |
| Webhooks never arrive | Not subscribed to the `comments` field; Page not subscribed (step 6.4); app in Development mode and the commenter has no app role. |
| Logs show `Rejected webhook with invalid X-Hub-Signature-256` | `FACEBOOK_APP_SECRET` is wrong (use the App Secret of *this* app), or a proxy is modifying the request body. |
| Reply works but the DM fails with `(#10) … outside of allowed window` | The Private Reply window (7 days) has passed, or the comment already got a private reply. |
| DM fails with `(#200)` or `(#3)` permission errors | `instagram_manage_messages` is missing from the token, **Allow access to messages** is off (step 1.4), or Advanced Access isn't approved yet. |
| Error code `190` | Token expired or invalid. Refresh or regenerate it (step 5). |
| Error codes `4`, `17`, `32`, or `613` | Rate limited. The app retries automatically with backoff. Sustained errors mean you're sending too much. |
| Campaigns disappear after deploy | No persistent volume at `/data`. |
