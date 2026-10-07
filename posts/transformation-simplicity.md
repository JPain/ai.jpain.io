---
title: A Year of Heritage Transformation Taught Me About Simplicity
slug: transformation-simplicity
meta_description: Transformation isn’t just about upgrading technology. It’s about learning how much change your organisation can actually sustain. The hard part is knowing when to stop.
published_date: 2025-01-01T00:00:00+00:00
tags: architecture, heritage, platform
publish: true
discoverable: true
is_page: false
---


![Compass to city](compas-to-city.webp)

When I joined my current organisation, the engineering architecture was mid-transformation; shutting down a heritage system, introducing new platforms, and experimenting with AI.

It sounded exciting, and it was, but it was also messy, uncertain, and at times overwhelming. What I’ve learned since is that transformation isn’t just about upgrading technology. It’s about learning how much change your organisation can actually sustain.

The temptation is always to run faster, automate more, and rebuild everything. The hard part is knowing when to stop.

## Why We Transformed

It wasn’t change for its own sake. We had reached a point where the past was actively slowing us down:
- **Lead time:** small releases took days and carried outsized risk.
- **Reliability:** tightly coupled systems made incidents broad and hard to contain.
- **Cost:** running and nursing legacy code consumed disproportionate effort.
- **Autonomy:** teams were blocked by shared bottlenecks and unclear ownership.
- **Product velocity:** new customer experiences and integrations were hard to ship at all.

Modernising was necessary to restore speed, stability, and room to build.

## The Heritage Problem

We started with a sprawling .NET monolith that had quietly grown over a decade. It touched everything: billing, data handling, user workflows, reporting. All intertwined.

Turning it off wasn’t an engineering task; it was a negotiation.
Each migration had dependencies buried in unexpected places. Every change risked pulling the wrong thread.

Piece by piece, we replaced it with cloud-native services, untangling logic and rebuilding functionality in modern stacks. It was slow and painful, but it worked.

And yet, I realised something important: moving to modern tools doesn’t automatically make a system modern. Migration is not the same as simplification. If you don’t address the underlying complexity, all you’ve done is repackage it in shinier infrastructure.

## Incident Management and the Price of Speed

As the old system faded, deployment speed increased, and so did the frequency of incidents. That was inevitable. When you release faster, you fail faster too.

So we built structure around it. We unified on-call systems, defined ownership, and established clear escalation paths. The goal wasn’t to eliminate failure, but to make it survivable.

It worked, but it also showed how easily process can grow around velocity. The faster you move, the more coordination you need. And with every new coordination layer, you add a little more friction back into the system.

You can’t scale chaos, but you can over-stabilise too. Balance is everything.

## The Platform Dilemma

Once the dust settled, the next goal was to build a unified platform — something that would give developers freedom to create without waiting on dependencies.

We introduced shared infrastructure, API gateways, CI/CD pipelines, and developer tooling. It was efficient, consistent, and scalable.

But over time, something familiar crept in: the platform itself became a dependency. Every new service, every change, every feature now needed to fit within its rules and workflows.

What started as an enabler began to slow us down. Centralisation created reliability, but it also created bottlenecks.

That’s when I began thinking about proportional platforms: the idea that not every team needs the same level of control or abstraction. Sometimes, the best platform is no platform at all. Just a small, empowered team with ownership over everything they build.

## Experimentation Without Illusion

AI brought a wave of fresh enthusiasm and, once again, the potential for overreach. I’ve seen how easily organisations can leap toward AI before they’ve even defined the problem.

The better path, I’ve learned, is proportional experimentation: start small, use what’s already working, and expand only when it proves real value.

Not every process needs to be “AI-enhanced.” Sometimes, what you need isn’t intelligence; it’s clarity.

## Reflections on Change

After a year of transformation, my main takeaway is that progress and proportionality are inseparable.

Change is essential, but unbounded change becomes noise. The more systems you replace, the more you risk losing context. And once that context is gone, every future team ends up doing archaeology, trying to understand why things are the way they are.

Transformation should reduce friction, not relocate it.

## What I’ve Learned

1. **Migration isn’t modernisation.**  
If you don’t simplify the process, you’re just moving the same problems somewhere else.

2. **Centralisation is fragile.**  
Every shared system creates shared risk. Build only what you can sustain.

3. **Proportional solutions scale better.**  
A small, autonomous team can often deliver faster and with fewer dependencies than a perfectly orchestrated one.

4. **Simplicity compounds.**  
Complexity slows down every future decision. Simplicity accelerates them.

## Looking Ahead

Transformation isn’t a one-off event. It’s a cycle that can either make you stronger or bury you in unfinished progress.

I still believe in bold change, but only when it’s proportional to the problem. The real measure of progress isn’t how much you’ve built; it’s how much you can afford to maintain without losing momentum.

Sustainability, not sophistication, is what defines true maturity in engineering.