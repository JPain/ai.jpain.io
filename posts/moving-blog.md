---
title: Moving to Bearblog - Choosing constraints over customisation so I actually write.
slug: moving-blog
meta_description: I’ve spent the last decade (or two) trying to write on a blog while also building the perfect blog. Those are two different hobbies and I’ve been treating them like one.
published_date: 2025-11-09T15:26:00+00:00
tags: blog, smallweb, wordpress
publish: true
discoverable: true
is_page: false
outdated: This post is old, and things have changed since: this blog no longer runs on Bear Blog. It's on my own server now.
---

I’ve spent the last decade (or two) trying to write on a blog while also building the perfect blog. Those are two different hobbies and I’ve been treating them like one. As a software developer who loves the [small web](tab:https://benhoyt.com/writings/the-small-web-is-beautiful/), privacy, and self‑hosting, it always felt right to run my own stack. In practice, it meant I shipped fewer posts and more tweaks.

## The tinkering trap

Give me knobs and I’ll turn them. Any time I opened my editor to write, I’d find a rabbit hole:
- “Maybe I should inline critical CSS per page.”
- “What if I add a filter that only bundles the selectors this post needs?”
- “Could I squeeze a few more kilobytes off the payload?”

None of these are bad ideas. They’re even fun. But they’re pre‑writing rituals that reliably eat the hour I planned to spend drafting.

## My tour of platforms

I’ve tried most of the usual suspects:
- WordPress on my own server
- Jekyll on GitHub Pages
- Eleventy on GitHub Pages (my most recent)
- Ghost
- Blogger

They all worked. The problem wasn’t the tools; it was me, with too much control and not enough guardrails. Eleventy in particular is a joy and dangerously customisable. To publish, I’d create a Markdown file, push, and wait for the build. That’s fine on a laptop. On a phone, it’s friction. Creativity rarely survives a branch switch and a “I’ll clean this up later.”

## Perfectionism vs publishing

Because I’m a web developer, I’ve felt my blog should embody everything I care about: tiny pages, low latency, minimal dependencies, no tracking, accessible markup, immaculate semantics, and images compressed just so. An artisan site that proves I practice what I preach.

I still care about all of that. But I care more about publishing. The truth is simple: **if the choice is between a perfect platform and a published post, I pick the post.**

## Why Bearblog

Bearblog fits my [small‑web](tab:https://benhoyt.com/writings/the-small-web-is-beautiful/) leanings and gives me an opinionated, lightweight output that’s already the kind of HTML/CSS I’d aim for anyway. Crucially, it removes most of the levers I keep reaching for.

Like bread: I can bake my own, but the loaf I enjoy most is often the one someone else made. Not because mine is bad, because it lets me sit down and eat.

Yes, Bearblog is a paid service. Yes, any platform can change over time. I’m choosing to support the [philosophy it represents today](tab:https://herman.bearblog.dev/manifesto/): simple, fast, privacy‑respecting publishing with sensible defaults. If it ever drifts, I can move.

And there's one tiny touch that sealed the deal for me: in the HTTP headers, Bearblog includes `x-clacks-overhead: GNU Terry Pratchett`. A quiet [cult reference](tab:https://xclacksoverhead.org/home/about) I adore.

## Constraints as a feature

I used to see Bearblog’s limitations as a downside. Lately, I see them as guardrails that keep me writing:
- Fewer knobs, fewer detours. I can’t spend an afternoon shaving 3 KB off CSS I shouldn’t have written.
- Phone‑friendly publishing. When inspiration hits, I can post from my phone without a yak‑shave.
- Defaults I don’t need to second‑guess. The output is already lean and accessible enough for my standards.

## What I’m keeping (and where)

I still enjoy self‑hosting and building web toys. I’ll keep that energy, just not in the writing lane. Expect separate little experiments and demos elsewhere. The blog’s job is words.

Working principles for this blog
- Content over cleverness. If a choice slows down publishing, I’ll pick the option that ships.
- Performance by default, not obsession. Good enough, consistently, beats perfect, rarely.
- Accessibility matters. I’ll meet standards through writing habits, not custom build steps.

## What to expect next

I’ll probably write about the same things; software, the web, small tools, just without pausing to reinvent the template first.

If you spot a rough edge on this site, that’s fine. It means I wrote this instead of polishing a build script.