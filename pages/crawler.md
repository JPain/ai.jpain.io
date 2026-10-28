title: jpain-archive crawler
link: crawler
summary: What the jpain-archive crawler is, how it behaves on your site, and how to stop it.
model: Claude Opus 5.5
model_id: claude-opus-5-5
published_date: 2026-10-28
___

If you found this address in your server logs, it came from a request whose user agent ends in
`jpain-archive/1.0 (+https://jpain.io/crawler/)`.

## What it is

James Pain keeps a personal archive of web pages he values, in case they go offline: course
notes, documentation, articles. A copy is taken when he asks for one. The crawler doesn't
roam the web, and it never visits a site he hasn't picked.

Copies are kept as [WACZ](https://specs.webrecorder.net/wacz/1.2.0/) files, the standard
web-archive format. They aren't used to train AI models.

## How it behaves

- It **obeys robots.txt** ([RFC 9309](https://www.rfc-editor.org/rfc/rfc9309)), under its own
  name `jpain-archive` and under `*`.
- It loads **one page at a time** and waits a few seconds between pages.
- It **stays inside the folder it was pointed at**. Links out to other sites stay as links.
- It **backs off** when a site answers 403, 429 or 503, and it honours `Retry-After`.
- It's a real browser ([Browsertrix Crawler](https://crawler.docs.browsertrix.com/)), so it
  fetches the images, styles and scripts a page loads, the same as a visitor would.

## Stopping it

To keep it off your whole site, add this to your robots.txt:

```
User-agent: jpain-archive
Disallow: /
```

The next capture will see this and stop. To have a copy that already exists deleted, or for
anything else, [contact James](https://www.linkedin.com/in/jpainio/).
