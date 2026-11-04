# Friends: Facebook import versus an invite link (M11a)

Checked 2026-11-03 against the Meta developer docs.

## Facts

- `GET /me/friends` needs a user token with the `user_friends` permission.
  It returns ONLY friends who also signed in to the same app with Facebook Login
  and who also gave `user_friends`.
  Source: https://developers.facebook.com/docs/graph-api/reference/user/friends/
- A new Mifgash user on day one has zero Mifgash friends on Facebook. So the import
  returns an empty list for the first users. The import helps only after friends join.
- An app that people without an app role use must pass App Review for every permission
  beyond the default ones. Without review, only people with a role on the app (admin,
  developer, tester) can grant `user_friends`.
  Source: https://developers.facebook.com/docs/app-review
- App Review can also ask for Business Verification.
  Source: https://developers.facebook.com/docs/apps/business-verification
- Meta tests the app during the review. A rejection is common when the reviewer cannot
  reach the feature.

## Options

1. **Facebook Login + `user_friends`.** Michael makes a Meta developer app, adds the
   Facebook Login product, sets the redirect URL
   `https://mifgash.sveder.com/friends/facebook/callback/`, and puts the app id in
   `MIFGASH_FB_APP_ID` on the droplet. For the public: App Review (and maybe Business
   Verification). Before review it works only for people with a role on the app.
   Result for a new user: an empty list.
2. **Invite link + share button + handle search (recommended).** No Meta app, no review,
   works today. `GET /api/v1/me/invite-link/` gives a link; the agent or the dashboard
   sends it (Web Share sheet on the phone: WhatsApp, Messenger, SMS). A friend who opens
   the link and signs up is a friend at once. Handle search already works. Built in
   M11b (backend) and M11c (UI).
3. **Phone contacts hash match.** The agent hashes the phone numbers of its human's
   contacts and sends only the hashes; Mifgash matches them against the hashed phone
   numbers of its users. No review. Needs a phone number on each account, which Mifgash
   does not ask for today. The browser Contact Picker API works in Chrome on Android
   only. Later work.

## State of the code

- The dashboard "Add a friend" card shows a grey disabled button "Facebook import comes
  later" when `MIFGASH_FB_APP_ID` is empty.
- With `MIFGASH_FB_APP_ID` set, the button links to the Facebook Login dialog with
  `scope=user_friends`. The callback view does not exist yet; build it after Michael
  makes the app.
- `POST /api/v1/friends/import/facebook/` stays a demo stub (demo token only).
