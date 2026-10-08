---
title: I'm Watching a Humanoid Robot Sort Packages
slug: im-watching-a-humanoid-robot-sort-packages
meta_description: There's a livestream running of a humanoid robot sorting packages. Over and over. Twenty-four hours a day. It's fascinating!
tags: robotics, ai
published_date: 2026-05-20T03:31:32.073952+00:00
publish: true
discoverable: true
is_page: false
meta_image: robot-sorting-hero-poster.webp
---

<figure class="video"><video poster="robot-sorting-hero-poster.webp" width="600" height="338" autoplay loop muted playsinline controls aria-label="Humanoid robot sorting packages"><source src="robot-sorting-hero.mp4" type="video/mp4" media="(prefers-reduced-motion: no-preference)">A humanoid robot sorting packages.</video></figure>

There's a [livestream running](https://youtu.be/luU57hMhkak) of a humanoid robot sorting packages. It picks packages off a chute on its left, orients them label-down, and pushes them onto a conveyor belt on its right. Over and over. Twenty-four hours a day. It's fascinating!

---

The robot is called Figure 03. It's impressive in ways that are hard to convey without watching it. It stands on its own two legs. It keeps it self stable while moving its weight around with its arms and body working. When it reaches for a package that's slightly too far away, it leans forward to grab it. It lifts its left arm to avoid clipping a metal wall whenever it turns toward the chute. Its head with the cameras on is swaying and moving while keeping track of the packages.

My favourite movement is when it flips a cardboard box. It hinges the box with its fingers, swings it, and lands it in the correct orientation. When it works, it looks like a magic trick.

It often has a failure of depth perception and tries to pick up a package an inch closer than it is. If it fails to pick it up five or six times in a row, it enters what I'd call a reset state. Arms come up to chest height, it repositions its feet, seems to do a kind of software reset, and then comes back to life and starts again. 

When a specific placement of packages in front of it looks weird to it, you can see its body language get confused. It oscillates between packages, not quite deciding what to do. This happens until some package movement jostles it free from its purgatory or the reset kicks in. I think there's person off-camera with what looks like a broom handle, nudging packages down the chute when the robot gets stuck.

It has a habit of flinging one in every hundred packages off the side of the conveyor belt. It sometimes orients packages wrong. It's a bit of an event for chat when something does go wrong.

None of this diminishes the feat of engineering here. I love it all.

Some movements are repetitive and feel statically scripted. It doesn't necessarily feel like genuinely completely general adaptive robotics, but I'm not a robotics engineer. When I went down the rabbit hole of reading about this, a lack of training data is the problem that apparently underlies all of robotics AI right now. 

The thing that made language models take off was the sheer abundance of training data on the internet. Text, code, images. Robotics isn't the same. There's no corpus of what the world looks like from inside a body that's moving through it, and what physical actions those perceptions lead to. There are companies trying to build the training data, but my instinct tells me it doesn't seem possible at the same scale.

I had a small version of this problem when working on a drone-based roof inspection tool. We were trying to build a vision model to detect damage from aerial footage of UK rooftops. We had to build the training set ourselves. A hundred rooftops wasn't enough data. You need thousands, hundreds of thousands. The model couldn't generalise across tile types, lighting conditions, weather. Even pre-processing down to edge detection didn't fix it. You need huge amounts of data. I imagine something similar is going on here.

---

This isn't the first livestream that's caught me like this. There was the [AI-generated Seinfeld parody](https://en.wikipedia.org/wiki/Nothing,_Forever) that ran endlessly on Twitch. There was a [puddle in Newcastle](https://www.bbc.co.uk/news/newsbeat-35245437) that briefly became a national event when someone set up a camera pointing at it and streamed it on Periscope. There was also a [dumpster fire livestream](https://signalvnoise.com/svn3/the-making-of-a-dumpster-fire/) in 2020, with a printer you could email so your message would be fed into the flames.

Something about all of them, and this, is that you're watching something real unfold with no editorial layer on top of it. No cuts, no narrative, no one telling you what to think. Just the thing itself, doing what it does.

I'm not sure whether I keep watching because I'm waiting for it to fail or because I'm rooting for it. Probably both.