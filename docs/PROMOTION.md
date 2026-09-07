# PC Remote launch / promotion kit

This file keeps the public positioning and launch copy in one place so releases can be promoted consistently.

## One-line positioning

**Control your Windows PC from any phone browser. No mobile app, no account, no cloud — just run PC Remote, scan a QR code, and use it over your LAN.**

## Short descriptions

### 80-ish characters

Open-source Windows remote controlled from any phone browser over your local network.

### Short listing description

PC Remote is an open-source local Windows remote that lets Android and iPhone users control apps, windows, media, audio, and power actions directly from a browser. No mobile app or cloud account is required.

### Longer listing description

PC Remote turns any modern phone browser into a lightweight control panel for a Windows 10/11 PC. Run the tray application, scan the QR code, and control apps, windows, system volume, media playback, audio outputs, and power actions over the same local network.

The project is local-first: it does not require a mobile app, external account, or cloud backend. Ready-made Windows builds are provided for normal users, while the source remains available under Apache-2.0.

## Recommended GitHub metadata

Repository description:

> Open-source local Windows remote from any phone browser — no app, account or cloud.

Recommended topics (GitHub allows up to 20):

- remote-control
- pc-remote
- phone-remote
- windows-remote
- windows
- windows-app
- media-control
- htpc
- local-first
- self-hosted
- lan
- web-ui
- tray-app
- fastapi
- python

## Reddit / r/selfhosted

Suggested title:

> I made an open-source Windows remote that works entirely in your phone browser — no app, account or cloud

Suggested body:

> I wanted a very small remote for a Windows PC without installing another mobile app or depending on a cloud service, so I built PC Remote.
>
> The Windows tray app exposes a local web controller. You run it, scan a QR code, then use the browser on an Android or iPhone on the same LAN.
>
> Current controls include volume/mute, media, audio output, launching apps, managing windows and Windows power actions. It has PIN-based pairing/authentication, light/dark UI, English/Russian UI and ready-made Windows builds.
>
> It is intentionally LAN/local-first rather than a remote-desktop product. I would especially like feedback on missing everyday controls and setup friction.
>
> GitHub: https://github.com/mimaxon1/pc-remote

Do not cross-post identical text to many subreddits at once. Adapt the first paragraph to the community and answer comments after posting.

## Show HN

Title:

> Show HN: PC Remote – control Windows from any phone browser, locally

Body:

> PC Remote is a small open-source Windows tray app that turns a phone browser into a local PC controller. There is no Android/iOS app, account, or cloud backend: run the Windows build, scan a QR code and connect over the LAN.
>
> It currently controls apps/windows, system audio, media and power actions. The backend is Python/FastAPI and the phone UI is web-based. I built it to keep the setup path as close as possible to “download → run → scan → control”.
>
> Source and Windows releases: https://github.com/mimaxon1/pc-remote

## AlternativeTo listing

Name: **PC Remote**

Website / source: `https://github.com/mimaxon1/pc-remote`

License: **Apache License 2.0**

Platforms: **Windows; Android/iPhone through a web browser**

Suggested summary:

> Open-source local remote control for Windows that works from any phone browser without a mobile app or cloud account.

Suggested feature bullets:

- Browser-based phone controller
- Local/LAN operation
- QR pairing
- App and window controls
- Media and system audio controls
- Audio output switching
- Windows power actions
- No cloud account
- Open source

Position it as a lightweight local alternative to phone-to-PC remote-control tools, not as full remote desktop or screen sharing.

## Release announcement

Suggested title:

> PC Remote vX.Y.Z — Windows installer + portable build

Suggested text:

> PC Remote vX.Y.Z is available for Windows.
>
> PC Remote lets you control a Windows PC from any Android or iPhone browser on the same local network. No mobile app, account, or cloud service is required.
>
> Download the normal Windows installer or the portable ZIP from GitHub Releases. SHA-256 checksums are included.
>
> https://github.com/mimaxon1/pc-remote/releases/latest

Then add 3–5 release-specific changes below this intro.

## Screenshot / demo checklist

When screenshots are added, prioritize product proof rather than architecture:

1. QR pairing window on Windows.
2. Phone home/control screen.
3. Media + volume controls.
4. App/window controls.
5. One light/dark theme comparison if space allows.

For a short demo video/GIF, the ideal sequence is:

`launch PC Remote → show QR → scan → tap volume/media/app control → visible PC response`

Keep it under about 15 seconds and put it near the top of the README.

## Launch sequence

1. Merge packaging/README changes.
2. Create the next tagged release so the automated workflow publishes both installer and portable ZIP.
3. Verify both files on a clean Windows account if possible.
4. Add 3–5 screenshots or one short demo.
5. Update GitHub repository description/topics using the metadata above.
6. Submit to AlternativeTo.
7. Post to one relevant community first (for example r/selfhosted), answer feedback, then adapt the post for the next community.
8. After the project has initial users/stars and the landing page looks active, submit a Show HN post.

## Message to keep consistent

The strongest differentiator is not “many features”. It is the setup and privacy model:

**Download → run → scan → control. No phone app. No account. No cloud.**
