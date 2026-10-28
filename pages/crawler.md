title: jpain-archive crawler
link: crawler
summary: Hi! If jpain-archive turned up in your logs, that was me. Here's what it is and how to stop it.
published_date: 2026-10-28
byline: none
___

Hi! If you've found this page through your server logs, a request with
`jpain-archive/1.0 (+https://jpain.io/crawler/)` on the end of its user agent came from me,
James Pain.

## What I'm doing

I keep copies of web pages I care about, in case they disappear one day. Old course notes,
documentation, articles I want to be able to find again in ten years. I've lost too many
good bookmarks to link rot.

It isn't a bot wandering the web. I point it at a page I like, it takes one copy, and it
stops. If it visited you, that's because something on your site was worth keeping, so
thank you for making it.

I don't use the copies to train AI models.

## How I try to be a good guest

- **I follow your robots.txt** ([RFC 9309](https://www.rfc-editor.org/rfc/rfc9309)), both the
  `*` rules and anything you set for `jpain-archive`.
- **It goes slowly.** One page at a time, with a pause of a few seconds between pages, or
  longer if your robots.txt sets a `Crawl-delay`.
- **It stays in the folder I pointed it at.** Links out to other sites stay as links.
- **It backs off** if your server answers 403, 429 or 503, and it waits as long as your
  `Retry-After` header asks.
- It's a real browser ([Browsertrix Crawler](https://crawler.docs.browsertrix.com/)), so it
  loads your images, styles and scripts just like any visitor.

## If you'd rather it didn't

That's completely fine. Add this to your robots.txt and it won't crawl your site again:

```
User-agent: jpain-archive
Disallow: /
```

If you'd like me to delete a copy I already have, or something's gone wrong, or you'd just
like to say hello, email me at [crawler@j3p.uk](mailto:crawler@j3p.uk).
