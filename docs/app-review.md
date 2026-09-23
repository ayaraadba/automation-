# Meta App Review kit

Paste-ready text for submitting this app to Meta App Review. Replace everything in
`[BRACKETS]`:

- `[BUSINESS NAME]`: your business or brand name
- `[@HANDLE]`: your Instagram account
- `[YOUR-DOMAIN]`: where the app is deployed, e.g. `ig-dm.up.railway.app`
- `[KEYWORD]` and `[RESOURCE]`: the keyword you use in the demo (e.g. "guide") and what the DM
  delivers (e.g. "a free PDF workout plan")

> This is a strong starting draft, not legal advice. Meta's form wording changes from time to
> time, so match each block to the question it answers.

---

## 1. Before you submit

- [ ] The app is deployed and `https://[YOUR-DOMAIN]/health` returns `{"status":"ok"}`.
- [ ] These environment variables are set, so the legal pages show your real details:
      `BUSINESS_NAME`, `CONTACT_EMAIL`, `INSTAGRAM_HANDLE`,
      `PRIVACY_EFFECTIVE_DATE`.
- [ ] `https://[YOUR-DOMAIN]/privacy` and `https://[YOUR-DOMAIN]/data-deletion` open in a private
      browser window without a login.
- [ ] **Business Verification** is complete (App settings → Basic → Verification, or Meta
      Business Suite → Settings → Security Center).
- [ ] At least one campaign is active, and the full flow works with an Instagram Tester account.
- [ ] The Instagram account has **Allow access to messages** turned on.
- [ ] The screencast is recorded (section 4).
- [ ] You're requesting **only** the permissions in section 3. Leave out `business_management`
      unless Meta explicitly says it's required. Every extra permission is another thing to
      justify, and another reason to reject.

## 2. App settings → Basic

| Field | Value |
| --- | --- |
| App display name | `[BUSINESS NAME] Comment Replies` (don't use "Instagram" or "Meta" in the name) |
| App domains | `[YOUR-DOMAIN]` |
| Contact email | `[CONTACT EMAIL]` |
| Privacy Policy URL | `https://[YOUR-DOMAIN]/privacy` |
| User data deletion | Choose **Data deletion instructions URL**: `https://[YOUR-DOMAIN]/data-deletion` |
| Terms of Service URL | Optional. Your website's terms page, if you have one |
| App icon | 1024×1024 logo |
| Category | Business and Pages (or "Messaging") |

Also add a **Website** platform (Add platform → Website) with the Site URL `https://[YOUR-DOMAIN]/`.

## 3. Permission descriptions

For each permission, Meta asks how you'll use it. Paste the matching block, then attach the same
screencast to every permission.

### `instagram_manage_messages`

> [BUSINESS NAME] uses this permission to send a single private reply to a person who comments a
> specific keyword on one of our own Instagram posts. Our posts invite followers to comment a word
> such as "[KEYWORD]" to receive [RESOURCE]. When someone comments that keyword, our app receives
> the comment through the Instagram `comments` webhook. It then uses the Private Replies feature
> (`POST /{page-id}/messages` with `recipient.comment_id`) to send that commenter one message
> containing the resource they asked for.
>
> The person always starts the interaction by commenting the keyword. We send at most one message
> per comment, within Instagram's 7-day private reply window. We never message people who haven't
> commented a keyword, and we don't send promotional follow-ups. The app only operates on our own
> Instagram Business account and is not offered to other businesses. Without this permission, we
> can't deliver the content users explicitly asked for, and they would have to wait for us to
> answer each comment manually.

### `instagram_manage_comments`

> [BUSINESS NAME] uses this permission to receive comments on our own Instagram posts through
> webhooks and to post a public reply to comments that contain a keyword we've set up (for example,
> replying "Sent! Check your DMs" when someone comments "[KEYWORD]"). The public reply confirms to
> the commenter, and to other followers, that the request was received. We only read comments on
> our own posts, we only store comments that match a keyword, and we don't hide, delete, or
> moderate anyone's comments. Comments that don't match a keyword are ignored and not stored.

### `instagram_basic`

> [BUSINESS NAME] uses this permission to read basic information about our own Instagram Business
> account (username and account ID) and our list of posts. In our management dashboard, an admin
> picks which of our posts to attach a keyword campaign to. The dashboard shows each post's
> thumbnail and caption so the admin can confirm they chose the right post. We don't access any
> other account's profile or media.

### `pages_show_list`

> Our Instagram Business account is linked to our Facebook Page, [PAGE NAME]. We use this
> permission to find the Page connected to our Instagram account during setup, and to obtain its
> Page access token. Instagram messaging through the Graph API is sent through the linked Page, so
> we need this to send private replies. We don't list, manage, or display any other Pages.

### `pages_read_engagement`

> We use this permission to read our own Facebook Page's metadata and to retrieve the Page access
> token for the Page linked to our Instagram Business account. That token is needed to send
> Instagram private replies through the Messenger Platform. We don't read Page posts, followers,
> or any other user content with this permission.

### `pages_manage_metadata`

> We use this permission once, during setup, to subscribe our own Facebook Page (linked to our
> Instagram Business account) to our app's webhooks (`POST /{page-id}/subscribed_apps`). Without
> this subscription, Instagram doesn't deliver comment webhooks to our app, and the automation
> can't respond to people who comment our keywords. We don't change any other Page settings.

## 4. Screencast script (about 2–3 minutes)

Record in English, or add English captions. Use a screen recorder with a visible cursor. Zoom in
so text is readable, and don't cut between steps; reviewers look for one continuous flow. Where
possible, show the permission names in the Meta login dialog on screen.

1. **Intro caption** (on screen, 5 s): "[BUSINESS NAME] Comment Replies: sends one requested
   resource by DM when someone comments a keyword on our Instagram post."
2. **Login and permissions** (30 s): In Graph API Explorer (or your token flow), select the app,
   click *Generate Access Token*, and show the Facebook login dialog. Pause on the permission list,
   then select your Page and Instagram account. Caption: "Admin connects our own Instagram Business
   account."
3. **Dashboard setup** (30 s): Open `https://[YOUR-DOMAIN]/dashboard/settings`, paste the token,
   and click **Test connection** so "Connected as @[HANDLE]" is visible. *(instagram_basic,
   pages_show_list, pages_read_engagement)*
4. **Create a campaign** (30 s): Go to Campaigns → New campaign → **Browse posts**, pick the post,
   and show the thumbnail and caption preview. Enter the keyword `[KEYWORD]`, the public reply
   text, and the DM text. Save, and show it as **Active**. *(instagram_basic)*
5. **Webhook subscription** (15 s): Show the Meta dashboard's Webhooks page with the Instagram
   `comments` field subscribed, and the callback URL pointing to your domain.
   *(pages_manage_metadata)*
6. **Trigger it** (30 s): On a phone, or in a second browser window logged in as a **test
   Instagram account**, open the post and comment "[KEYWORD] please".
7. **Public reply** (15 s): Refresh the post's comments. Show the automatic public reply under the
   test comment. *(instagram_manage_comments)*
8. **DM received** (15 s): Open the test account's Instagram inbox (check Message Requests) and
   show the DM containing [RESOURCE]. *(instagram_manage_messages)*
9. **Activity log** (10 s): Back in the dashboard, show **Recent activity** with the comment and
   "sent" for both reply and DM.
10. **Non-matching comment** (15 s, optional but convincing): Comment "nice post" from the test
    account. Show that no reply or DM is sent.

## 5. Reviewer instructions (the "step-by-step" field)

> 1. The app automates replies for our own Instagram Business account [@HANDLE]. It isn't a
>    consumer login app, so there is no public sign-up.
> 2. To test: from any Instagram account, open this post: [POST URL]. Comment the word
>    "[KEYWORD]".
> 3. Within a few seconds, our account posts a public reply under your comment, and sends your
>    account one direct message containing [RESOURCE]. Check your Instagram Message Requests
>    folder if it's not in your main inbox.
> 4. Comments without the keyword receive no reply and no message.
> 5. The admin dashboard is shown in the screencast. If you need access, use:
>    URL `https://[YOUR-DOMAIN]/dashboard`, username `[REVIEWER USER]`, password `[REVIEWER PASSWORD]`.
>    (Set up a temporary reviewer password and change it after review.)

**Note:** while the app is in Development mode, the webhook only fires for accounts with a role on
the app. Meta reviewers usually test with the screencast or with their own test users. If they
report that "nothing happened", reply that the app is in Development mode, and point to the
screencast.

## 6. If you're rejected

Meta gives a reason for each permission. Fix what they named, then resubmit.

| Rejection reason | What to change |
| --- | --- |
| "Screencast doesn't show the permission being used" | Re-record with that permission's step clearly visible, and add an on-screen caption naming the permission. |
| "Use case isn't clear / not allowed" | Stress that users start the interaction by commenting, that it's one message per comment, and that it only runs on your own account. |
| "Unable to test" / "couldn't reproduce" | Make the reviewer instructions more explicit, give a public post URL, and say where the DM lands (Message Requests). |
| "Privacy policy invalid" | Check that `/privacy` loads without login, names your business, and matches what the app does. |
| "Requested permission not needed" | Remove that permission and resubmit with fewer. |
| Business Verification required | Complete it first; nothing else helps until it's done. |

## 7. Handling a deletion request

When someone emails or DMs asking for deletion, remove their records immediately:

```bash
curl -u admin:$DASHBOARD_PASSWORD -X DELETE \
  "https://[YOUR-DOMAIN]/api/activity?username=THEIR_USERNAME"
# → {"deleted": 3}
```

Then reply to confirm. Records are also deleted automatically after `DATA_RETENTION_DAYS` (90 by
default).
