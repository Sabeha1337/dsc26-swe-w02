# AI usage

## Tools

I used DeepSeek for almost everything except the visual illustration, and ChatGPT for the visual illustration.

The AI helped me with:

- building explanatory tables for the parcel event system;
- correcting some programming and writing mistakes;
- proofreading the general writing as a spell checker;
- writing comments that make the domain rules easier to read;
- breaking the task into small steps and organising the ideas;
- checking the test results.

## What AI got wrong

The AI did not hallucinate, but the first test script we ran was outside the project folder, so it failed with `ModuleNotFoundError: No module named 'app'`. I opened it with `PYTHONPATH` set to the project root and it worked.

## In my own words

1. Why does `listParcels` need a cursor rather than an offset?

A cursor was needed because it depends on its position, not on the elements' condition, so it preserves its own position if it is saved on the server. Offset uses the number of elements, so if elements leave the `state=created` filter, the offset will skip another 10 steps; instead of items 11–20 it will return items 21–30.

2. Which of your four operations would break the courier app if you renamed one field, and who would have to approve that change?

Renaming `state` in `getParcel`, `listParcels`, or `recordParcelEvent` would break the courier app because it uses the `state` field to decide what to show; if there is no `state` field, it will break. The courier app team and the API developers would have to approve because the field is part of the shared contract.
