# Feature request draft: Google Maps Platform Issue Tracker

Where to file it: https://developers.google.com/maps/support, then "Feature Request" next to the API
it concerns (Routes API or Places API). Search the existing requests first and +1 a match instead
of filing a duplicate. Replace the placeholders in [brackets] before submitting.

---

**Title:** Rank nearby-place results by heading-aware drive time, not distance from the current fix

**Summary**

When a user is already driving and asks for a nearby place (a coffee shop, a gas station), a ranking by
straight-line or direction-blind distance can return a place the vehicle has just passed, even when an
equally good place lies ahead. I'd like an option to rank by estimated drive time that takes the
vehicle's current heading and one-way streets into account, so a place that needs a U-turn or a loop
around the block is ranked below a comparable place ahead.

**Proposed shape**

An optional heading/bearing for the origin when ranking by drive time (for example alongside the
existing routing parameters for Places requests), applied to the first segment of the route. Where a
route origin already accepts a heading, reusing it for ranking would be enough.

**Evidence from a public benchmark**

I built a reproducible simulator and benchmark: https://github.com/sambringit/detour. It compares nearest-by-distance,
nearest-by-drive-time (heading-blind) and a heading-aware ranking against a ground-truth ETA, using
noisy GPS (8 m / 10 degrees) and real OpenStreetMap street networks (San Francisco and Helsinki
extracts), with 95% confidence intervals.

- Average time lost versus the best stop: San Francisco Starbucks 3.9 s (distance) vs 0.1 s
  (heading-aware); Helsinki core cafes 67 s vs 7.4 s.
- The gain is larger on fast roads (San Francisco, 5.2 s vs 2.3 s lost for nearest-by-distance).
- A track-aware map matcher matters on dense one-way streets (single-fix matching loses 2 to 3x more).

**Limitations of this evidence (please read)**

Drives are simulated, not real traces. The ground truth shares its cost model with the ranking. Travel
times use default speeds with no traffic, signals or turn restrictions. I did not measure Google
Maps' own ranking, so I cannot say how often the behaviour above occurs in production; my
motivation is personal observation while driving. The repo documents all of this.

**Use case**

Navigation and ride-hailing apps that suggest stops while a vehicle is in motion, where a place just
behind the vehicle is worse than the number suggests.

[Sam B / sambringit@gmail.com]
