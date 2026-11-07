---
name: ship-launch
description: >-
  Launch kit for an iOS app that is approved or about to be: an App Store
  preview video and a short launch video recorded from the real app in the
  simulator, a press kit page, launch posts drafted for X, Reddit, Product Hunt,
  Hacker News, Indie Hackers and relevant communities, a launch-day checklist,
  and in-app review prompts. Use when the user is about to launch or just
  launched an app, wants launch posts, a press kit, an app preview video, a
  launch trailer, or asks how to get the first users.
---

# ship-launch

Launch is a day, not a strategy, but it is the day with the most attention you
will get for free. Prepare everything before approval so release day is just
pressing buttons. Everything goes in `.ship/launch/`.

Ask which channels fit the app and the user (`launch.channels`): founders with an
audience on X lean on X; niche apps do better in the subreddit or forum where
those people already are; developer tools on Hacker News; consumer apps on
Product Hunt and TikTok.

## 1. Videos from the real app

Record, do not fake. Boot the same simulator as ship-screenshots, set the clean
status bar, then:

```bash
xcrun simctl io booted recordVideo --codec h264 .ship/launch/raw/take1.mov
# Ctrl+C to stop
```

- **App Store preview** (optional, appears before screenshots): 15 to 30 seconds,
  only footage captured from the app (no hands, no people, no device frames in
  the video itself), the first seconds show the core action. Export at the exact
  preview resolution for the device size (for 6.9 inch iPhones 886x1920 portrait),
  30 fps, H.264, with or without audio. Upload in App Store Connect.
- **Launch video** for social (9:16, 15 to 30 seconds): the core action within the
  first second, captions burned in large and inside the safe area (keep text away
  from the top 10% and bottom 20% where app UI covers it), music the user has
  rights to, the app name and "on the App Store" at the end.

Use ffmpeg to trim, scale and caption. Look at every export before handing it over.

## 2. Press kit

A `/press` page on the website (or `.ship/launch/press/` folder zipped): one
paragraph about the app, the founder line, key facts (price, platforms, launch
date), the icon (1024 and 512), 3 to 5 screenshots, the launch video, contact
email, and the App Store link. Journalists and curators use what is easy to copy.

## 3. Launch posts

Draft one post per chosen channel in `.ship/launch/posts.md`. Write each in that
community's own voice and rules:

- **X / Threads**: the problem in one line, a 10 second clip, the link in a reply.
  Founder story beats feature lists.
- **Reddit**: read the subreddit's rules first; many ban self-promotion or allow it
  only on certain days. Lead with what you learned or a free useful thing, mention
  the app plainly, reply to every comment.
- **Product Hunt**: tagline (60 chars), description, 3 to 5 gallery images (the
  screenshots), a maker comment telling why you built it. Launch at 00:01
  Pacific.
- **Hacker News "Show HN"**: plain, technical, honest about limits; only if the
  build or the tech is genuinely interesting to that audience.
- **Indie Hackers, niche forums, Discords**: share the journey and numbers.

The user publishes every post themselves; never post or message on their behalf
without an explicit yes for that specific post.

## 4. In the app

- Ask for a rating with `SKStoreReviewController` / `requestReview` after a
  success moment (third completed core action), never on launch, never behind a
  "do you like the app?" filter.
- A share button where sharing is natural, with a link to the App Store page.
- Release notes that thank early users.

## 5. Launch-day checklist

- [ ] App approved and set to manual release; release it in the morning of the
      main audience's time zone
- [ ] Website shows the App Store badge with the live link; Smart App Banner on
- [ ] Posts scheduled or ready; the user is around for the first hours to reply
- [ ] Analytics dashboard open: installs, onboarding completion, paywall views
- [ ] Support email monitored
- [ ] A day-two plan: answer every review and comment, fix the top complaint fast

Tick the launch line in `.ship/PROGRESS.md` and record the App Store URL in
`ship.json`.
