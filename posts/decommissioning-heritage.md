---
title: Decommissioning Heritage Without Toppling the Tower
slug: decommissioning-heritage
meta_description: I inherited Checkatrade’s stalled ‘Heritage Switch Off’. Instead of flipping the switch and fixing whatever broke, we mapped 86 use-cases and rebuilt piece by piece.
tags: heritage, architecture, platform, legacy systems
published_date: 2024-12-15T00:00:00+00:00
publish: true
discoverable: true
is_page: false
meta_image: jenga-tower.webp
---


![Jenga Tower](jenga-tower.webp)

This year I inherited Checkatrade’s long-running ‘Heritage Switch Off’ project. All previous attempts had stalled, the supporting documentation was scattered to the wind, and all past contributors had left. The stakeholders offered me a bold suggestion: failure-driven migration. Flip the off-switch and fix whatever breaks.

I had to make the tough call to take the harder, more time-consuming path. We faced pushback, but by meticulously mapping use-cases and rebuilding piece by piece, we’ve now retired or rebuilt nearly everything that once made Heritage so formidable.

Here’s how we carefully untangled Heritage piece by piece, avoided catastrophe, and finally made real progress on a project that had lingered for far too long.

## The Unravelling Begins  
Heritage wasn’t just one monolith; it was a labyrinth of twenty separate web apps, more than a hundred services, and a database stuffed with thousands of tables. For at least five years, the business had a project shutting this thing down, but progress was slow. The project’s catchphrase was ‘We’ll be done by end of the year’ but never happened.

When I stepped in as project lead earlier this year, I quickly realised that any attempt to analyse each component upfront would be painfully slow and possibly redundant, there was a good chance half of it wasn’t even in use any more.

![The monolith, shown as a database schema map](heritage-schema.webp)
The monolith, shown as a database schema map. This is showing about 10% of the tables.

We decided to flip the approach. Rather than try to decipher every service, my technical project manager and I focused on how Heritage was being used in the real world. We identified “Agent Use Cases” by talking to agent teams who depended on Heritage daily. We asked which UIs they clicked through, what data they needed, and why. Meanwhile, we uncovered “System Use Cases” by implementing logging at the edge of Heritage and analysing which services sent or received data from it.

That gave us a clear boundary around the parts of the infrastructure still in play.

After a few weeks of interviews, logging, and detective work, we found ourselves with a list of 86 concrete use‐cases. That number was daunting at first, but it gave us clarity. We knew exactly what features mattered, who relied on them, and which services could be safely turned off or split out.

## When Outages Demand a Parallel Plan  
During all this, Heritage kept showing off its age. Nearly every month, there was at least one incident traceable to the on-prem provider hosting Heritage. About nine out of ten outages were tied to things like VMware mis-configurations or hardware failures. We couldn’t wait until the final Heritage service was decomposed to address these outages. So in parallel, we spun up a dedicated team of infrastructure specialists to lift and shift the legacy VMs into Google Cloud.

They wrapped that up in four months, and just like that, the outages stopped completely. With reliability restored, it eased pressure off the switch-off project.

## Chipping Away at the Monolith  
With 86 use-cases mapped, we started grouping them into manageable projects and assigning them to various development teams. We also had a bit of luck on our side: Heritage, for all its age, had source code we could still work with and a halfway-decent deployment pipeline. That allowed us to use a monolith-decomposition pattern on several services, carving out sections into standalone microservices, redirecting traffic to the new services, and only rebuilding from scratch when we really had to.

Some workflows were so broken that any attempt to “lift and shift” them would have been an exercise in futility. If we were already renovating the house, why not fix the broken windows while we were at it? In many cases, we rebuilt these services from the ground up, making them more stable and user-friendly. Where possible, we took advantage of Retool for quick internal UI builds, or we replaced outdated functionality with a SaaS app.

We even found a few duplicates or features that had been quietly retired long ago, no one told the agents there was an alternative, or an error in an existing product prevented it from being adopted. By investigating and communicating better, we eliminated a lot of unnecessary complexity.

## From Five Years to Five Use Cases  
By year’s end, we’d whittled down the original 86 use-cases to just five. That might not sound like a victory parade, but for context, Heritage had resisted attempts at decommissioning for half a decade. Seeing most of it done in less than a year was a huge morale boost for everyone involved. The final pieces are on track to be turned off soon, freeing us from the last vestiges of a system that, for too long, weighed on our ability to innovate.

I’m proud of the energy I brought to this project and grateful for the incredible teams who jumped in alongside me. Whether it was analysing logs, rewriting brittle .NET code, or staying up late to watch the last VM migrate to the cloud, each piece of the puzzle came together to create real progress.

## Looking Ahead  
The best part of saying goodbye to Heritage is the freedom it unlocks. We’re no longer tied to an aging monolith that dictated how fast we could move, or how often we’d be woken up in the middle of the night. Now, our developers, agents, and support teams can lean into new technologies with confidence, and we have the infrastructure to scale without fear of a hidden subsystem crashing and burning.

For anyone else considering a similar journey, I can’t stress enough the importance of identifying true user-needs before diving head-first into the code. Without a user-centric discovery process, we’d probably still be trying to map out endless `.config` files. It also pays to tackle infrastructure issues early. No one wants to refactor a service that’s constantly on fire. And sometimes, the biggest changes happen when you’re willing to question whether a feature needs to exist at all.

Heritage may not have disappeared with a single switch, but by breaking off one piece at a time, we’ve proven it can be done. Now, we can finally shift our focus from the past to what comes next. I can’t wait to see how far we’ll go.