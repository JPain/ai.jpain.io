---
title: Notes on building a natural-language interface for small home jobs
slug: natural-language-home-jobs
meta_description: Express let homeowners book small jobs in their own words. The problem wasn’t “search” but translation, and AI was the proportional choice for the time we had.
published_date: 2025-11-02T00:00:00+00:00
tags: ai, search
publish: true
discoverable: true
is_page: false
---

Express is a small experiment I led to make hiring tradespeople simple, fast, and trustworthy. The idea was straightforward: let homeowners book and pay for small jobs instantly, with clear prices and no waiting for quotes. We launched in one city, learned quickly, and then expanded.

At its heart, the problem wasn’t “search” but translation. People say things like “my tap’s leaking” or “can someone mount my TV?” Tradespeople, meanwhile, need structured requests they can accept with confidence. Express is the bridge between the two.

## Finding the right interface

We tried a few approaches.
- Images. In a previous project we experimented with photo uploads. It handled scenes (“bathroom”, “kitchen”) but struggled with precision (“fix dripping tap”).
- Structured menus. We prototyped a category picker and a Google-style search box. The menu added friction; the box encouraged vague, two-word queries.

For Express we did the opposite of clever: one blank box. Write what you need in your own words. Thanks to tools like ChatGPT, people are comfortable doing exactly that. The blank box gave us richer context and better inputs than any taxonomy.

## Why we chose AI

We didn’t have months to curate keywords or tune a traditional search index. We had a day.

Generative models are good at understanding natural language and emitting structured outputs. So we asked the model to return strict JSON describing the requested services. Not because AI was fashionable, but because it was the proportional choice for the time and constraints we had.

## The first attempt (and why it failed)

Version one used a large model and a long prompt listing ~40 services. The instruction was: “Given this list, return the most relevant services for the query.”

It worked ... inconsistently. Identical inputs produced different outputs:

“I’d like my door knob replaced & my TV mounted.”
- Attempt 1: only “Replace door knob.”
- Attempt 2: both services.
- Attempt 3: only “Replace door knob” again.
- Attempt 4: “No services to add.”

After debugging, three issues stood out:
1. Output discipline. We asked for JSON but wrapped it in a chat schema; ~40% of responses failed parsing because the model added friendly prose before/after the JSON.
2. Prompt conflict. We’d mixed goals (exact matches, related matches, suggestions, return nothing if unsure). The model oscillated between “strict search engine” and “creative assistant.”
3. Latency. ~8s average. Fine for a report; unacceptable for a search box.

Even so, it proved the key point: the model genuinely understood intent.

## Refining the prompt

We rewrote from scratch and tightened the contract:
- JSON only. No extra text.
- Simple schema. One structure plus a lowConfidence flag.
- Inclusive matching. Always include close variants and related services.
- Short, non-conflicting instructions. One job, clearly stated.

We also switched to a smaller, faster model, reduced randomness, and removed example outputs that biased results.

Results: latency dropped from ~8s to ~0.5s; accuracy across 300 test queries was near-perfect. The lowConfidence flag let the UI be honest when unsure, which increased trust.

## Why this worked

Traditional search expects users to think in categories. Homeowners don’t. They describe problems as they experience them.

Generative AI closes that gap by modelling intent and context, not just keywords. One of my favourite tests:

> “I need my TV moted and the white stuff around the bath replaced as it is getting mouldy.”

Despite the typo and two distinct jobs, the system returned TV mounting and bathroom sealant. No autocomplete, no deep taxonomy, no manual tuning. Just a box that listens and a model constrained to reply in a machine-readable way.

We didn’t build an “AI interface.” We built a listening interface.

## What’s next

Express will evolve with real usage. We started with a fixed set of services to protect reliability and pricing. As patterns emerge in how people describe jobs, from terse phrases to paragraph-long explanations, we’ll keep simplifying the experience and tightening the contract between free text and structured work orders.

The goal remains unchanged: fast, trustworthy booking for homeowners and tradespeople, with as little friction as possible.

## What I learned building Express

1. Start with the simplest interface. A blank box beats a fragile taxonomy when language is the input.
2. Constrain the model, not the user. Strict JSON, tight prompts, and low-latency models matter more than clever prose.
3. Proportional beats perfect. Use the smallest model and shortest instruction that solve the problem. Optimise later.
4. Trust is a UI feature. Admit uncertainty (lowConfidence) and design graceful fallbacks.
5. Simplicity compounds. Less scaffolding today means fewer brittle dependencies tomorrow.

The best part of this project wasn’t the AI. It was discovering that the right amount of sophistication is often the smallest one that works.