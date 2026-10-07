---
title: Proportional Solutions Matter - The Cost of Being a Bigger Company Than You Are
slug: proportional-solutions-matter
meta_description: There’s a quiet trap in modern engineering culture: the belief that maturity comes from infrastructure sophistication. Many organisations are trying to be bigger than they are.
published_date: 2025-08-13T23:00:00+00:00
tags: platform, solution architecture
publish: true
discoverable: true
is_page: false
---

There’s a quiet trap in modern engineering culture: the belief that maturity comes from infrastructure sophistication. You start with a few microservices, then a platform team, then centralized Terraform, Kubernetes, Backstage, and a layer of automations on top. Before long, it feels like you’ve arrived. You’ve built a “serious engineering organisation.”

The problem is that these systems are rarely free, and I don’t mean just financially. They come with enormous cognitive, operational, and organizational costs that most companies never fully see, because those costs are paid in friction, not invoices.

In many organisations, the hidden truth is that they’re trying to be bigger than they actually are.

## The Hidden Cost of Over-Equipping

It’s easy to see why teams fall into this pattern. Tools like Backstage or Kubernetes have become status symbols,  shorthand for technical credibility. They promise standardization, scalability, and developer empowerment. But the unspoken assumption is that you have the time, expertise, and headcount to actually run them.

When your developers are salaried, the cost of complexity doesn’t show up as a line item. You’ve already “paid” for the engineers, so building something grand feels justified. But complexity compounds. Every new layer of abstraction, every internal tool or automation, becomes something else that needs documentation, maintenance, and eventually, archaeology.

And that’s the part no one budgets for: long-term support.

## The Self-Perpetuating Complexity Trap

Overengineering doesn’t just slow you down. It creates the illusion of growth.

Here’s how the cycle works:

Complexity breeds friction → friction slows delivery → slower delivery justifies hiring more developers → more developers justify more process → more process breeds more complexity.

Each step feels logical, even responsible. But together, they create a self-fulfilling prophecy: the friction introduced by overengineering makes the organization appear larger and more complex than it really is, which then justifies even more complexity.

If you stripped it all back, the abstractions, orchestration layers, and internal tooling, you’d often find that many products could be owned end-to-end by a small, focused team. In many cases, four engineers with direct access to their own infrastructure could handle it all.

When you have that kind of autonomy, you don’t need a central platform. You just need capable engineers, clear ownership, and a bit of trust.

## The Archaeology of Complexity

I’ve seen teams fall into a strange situation where no one actually understands how their own platform works anymore.
Terraform scripts, Kubernetes clusters, pipelines, and automation layers pile up over time until they become a system of rituals, things you keep running because they must be important to something.

New engineers arrive and spend months performing “archaeology,” trying to understand why things are the way they are. Old systems are rebuilt from scratch every few years because no one wants to take ownership of what already exists. Each generation of engineers thinks, “Let’s start over, we’ll do it properly this time.” And maybe they do. But then the team changes, context fades, and the cycle repeats.

We talk a lot about automation and scalability, but what many teams have actually automated is forgetting.

## When the Simple Thing Already Works

In one place I worked, there was a simple system that handled team ownership and access control: a YAML file in a repo listing engineers, teams, and email addresses. When a pull request was merged, a script updated GitHub access, Google Groups, and a few other integrations.

It was small, transparent, and effective. But because nobody “owned” it, it was considered untouchable, something people would fix if it broke, but never claim. Eventually, new teams proposed rebuilding it from scratch.

It was a perfect metaphor for how organisations lose confidence in simplicity. We’d rather reinvent something new than improve something that quietly works.

## Proportional Platforms

In another environment, I took a different approach.
Instead of relying on a central platform team, each product group had its own sandbox: its own GitHub organization, cloud project, and budget. The rule was simple: you build it, you own it.

Teams deployed however they liked, usually via lightweight CI/CD directly to managed cloud services, and managed their own infrastructure using native IAM permissions. It was fast, autonomous, and low-friction.

For over a year, we didn’t need a centralised platform team to intervene. That, to me, is success.

It’s not anti-platform. It’s proportional platform.
It’s about matching the sophistication of your tools to the actual complexity of your problems.

## The Principle of Proportionality

Proportionality isn’t about being minimalist for the sake of it. It’s about respecting scale.
It’s the recognition that not every company needs the same infrastructure footprint as a global tech giant, and not every product deserves an enterprise-grade platform.

The goal isn’t to look big; it’s to be effective.
Sophistication isn’t how much complexity you can add; it’s how much you can afford to leave out.

If your systems require a team of archaeologists to understand them, you’ve stopped building a platform and started building a dependency.
Proportional solutions don’t just make software better, they make organisations healthier.

The real mark of engineering maturity isn’t how many platforms you can run. It’s how little you need to.