# Halo - the design system of the scan service

This is the reasoning behind everything in [`frontend/`](frontend/README.md):
the palette, the three typefaces, the frosted panes, the aurora behind them
and the motion that carries a page in. `frontend/README.md` is the working
reference - the file tree, the template contract, the rules a change must not
break. This file is the *why*, so that the next person to touch `app.css`
extends the system instead of adding to it.

* [The idea](#the-idea)
* [Colour](#colour)
* [Typography](#typography)
* [The glass](#the-glass)
* [The aurora](#the-aurora)
* [The command bar](#the-command-bar)
* [Motion](#motion)
* [Contrast](#contrast)
* [What the policy forces](#what-the-policy-forces)
* [Extending it](#extending-it)
* [Trademarks and affiliation](#trademarks-and-affiliation)

## The idea

A stranger arrives, types the address of a system they are responsible for,
and waits perhaps twenty seconds for a letter grade. The design has one job in
that minute: to make the service feel like a precision instrument rather than
a form.

So the page is built as **an instrument panel under glass**. Cold frosted
panes float over a slow aurora, every fact a machine measured is set in
monospace, every sentence a person wrote is set in a humanist sans, and the
one thing the visitor came to do - type an address and press a button - is the
largest object on the screen.

Three rules hold the whole thing together, and each of them is a *no*:

1. **One hue does interaction.** Iris, running to magenta at its hottest. A
   link, a focus ring, a button, a marker: all the same family. Nothing else
   on the page is allowed to be that colour, so the eye learns in one screen
   what is clickable.
2. **Status colour lives inside its own container.** Green, amber, red and
   blue appear in chips, dials and severity tags, never as page furniture. A
   green rule across a page reads as decoration; a green **A+** in a ring
   reads as a verdict.
3. **Chrome is a hairline.** No filled toolbars, no boxed sections, no drop
   shadows doing the work of structure. Where something must be separated
   from something else, a one-pixel line does it.

## Colour

Every colour is a custom property at the top of `app.css`, and the dark theme
redefines *the same names*. There is no second stylesheet: a token added
without a dark value will look wrong on half the machines that visit.

**The system decides, until somebody says otherwise.** The dark tokens are
written twice, and the pair is the whole mechanism:

```css
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { … } }
:root[data-theme="dark"] { … }
```

The first is the original behaviour, untouched: with nothing stored, the
operating system is the only thing that decides, on a first visit and on
every visit after it. The second is the override, and `data-theme` is only
ever on the root element because a visitor pressed the switch in the header -
`theme.js` writes it back before the first paint, `theme-toggle.js` puts it
there. A token defined in one block and forgotten in the other is a token
half the readers see in the wrong colour, so the two are kept adjacent and
edited together. Anything that cannot be expressed as a token - the `select`
chevron, which is a data URI and cannot read one - needs the same pair of
rules for the same reason.

The switch itself is one icon: the scheme a press would move *to*, chosen in
CSS from those same two questions rather than drawn from script, so it is
never briefly wrong. It is hidden until `theme.js` marks the document, so a
reader without scripting is not shown a control that cannot work - they still
get the scheme their system asked for, which is the part that never depended
on us.

| Role | Light | Dark |
|:-----|:------|:-----|
| `--ink` / `--ink-soft` / `--ink-faint` | `#0d0f17` / `#474e61` / `#61687b` | `#eaedf7` / `#a6aec5` / `#7b839a` |
| `--paper` | `#eceff7` | `#07080e` |
| `--card` | white at 62% | `#161924` at 60% |
| `--brand` / `--brand-deep` | `#5b4bff` / `#4132d6` | `#a89dff` / `#c8c1ff` |
| `--on-accent` | `#ffffff` | `#0a0b14` |

Two decisions in that table are worth keeping:

- **The paper is not white and the ink is not black.** `#eceff7` is a cool
  paper with a trace of the brand hue in it, which is what lets a white pane
  read as *glass* rather than as a slightly different white. Pure black in
  dark mode does the same job in reverse: `#07080e` is deep enough for the
  aurora to glow through it and still carries a blue cast.
- **`--on-accent` flips.** In dark mode the brand hue is a luminous violet,
  and white text on it is unreadable. The token becomes near-black. Any new
  surface painted in the brand colour must use `--on-accent` for its text
  rather than hardcoding white, or it will be legible in exactly one scheme.

The action gradient `--cta` is the single exception to "one flat hue": iris
through violet, with the magenta arriving past the button's own edge so it is
felt as heat rather than seen as a second colour. `--accent` is that
gradient's midpoint, for the places a flat fill has to agree with it.

Status colours come in threes - `--good`, `--good-soft`, `--good-ink` - and
the split is what keeps the page bright without becoming unreadable. `--x` is
the graphic tone, for a dial or a marker where nothing has to be read at 13px;
`--x-soft` is the tint behind text; `--x-ink` is the text on that tint. Tie a
colour to a meaning and never to a position: a green **F** would be a very
expensive joke.

## Typography

Three voices, all self-hosted from `/static/fonts/` under the SIL Open Font
Licence, each with its licence file beside it. Nothing is fetched from a font
service - not as a fallback, not as a `preconnect`, not ever. The pitch of
this service is that it is quiet, and a page that quietly fetched a font from
a third party would make that a lie.

| Token | Face | What it carries |
|:------|:-----|:----------------|
| `--font-display` | **Space Grotesk** (Medium, Bold) | Headlines, the grade, section titles |
| `--font` | **Inter** (Regular → Bold, Italic) | Every sentence a person wrote |
| `--mono` | **JetBrains Mono** (Regular, Medium, Bold) | Every fact a machine measured |

Space Grotesk was chosen for the same reason a template would avoid it: its
`g`, its `k` and its question mark have enough character that "How secure is
your **OpenCloud instance**?" is recognisably this project. Inter is chosen
because it disappears. JetBrains Mono does the load-bearing work - the address
field, the kickers, the counters, the check identifiers, the resolved IP
addresses, the code blocks - so that *a machine-read fact never wears the same
face as a sentence somebody wrote*. That distinction is the closest thing this
design has to a thesis.

Space Grotesk and JetBrains Mono are subset to Latin-1 plus the arrows and
marks the templates actually use, which is why they are 18-37 KB rather than
several hundred. Only the three faces the first screen needs are preloaded in
`base.html`.

## The glass

A pane is not a slab. `.card` composes two backgrounds in one declaration:

```css
background:
    linear-gradient(var(--card), var(--card)) padding-box,
    var(--glass-edge) border-box;
border: 1px solid transparent;
backdrop-filter: var(--glass-blur);   /* blur(22px) saturate(1.7) */
```

The first layer is the translucent surface, clipped to the padding box; the
second paints the *border* box with a gradient, so the hairline is lit at the
top-left and fades out before the opposite corner, the way a real bevel
catches one light source. `saturate(1.7)` on the backdrop filter is what makes
the aurora bloom through the pane instead of turning to grey mud.

One trap, discovered the hard way and worth writing down: **`backdrop-filter`
creates a stacking context**, so a `z-index: -1` pseudo-element intended to
glow *behind* a card paints above the card's own background instead. The halo
around the scan form is therefore an animated `box-shadow` on `.brackets`, not
a blurred pseudo-element. Any future glow has the same constraint.

`--card-solid` is the same surface with the frost turned off, for the few
places something must be opaque: the dial's centre, a focused field, a
floating menu.

## The aurora

`body::before` carries `--sky`: three soft radial masses - iris top-left,
magenta top-right, a cold teal rising from the bottom - drifting on a
half-minute cycle in the `aurora` keyframes. `body::after` lays a monochrome
noise tile over it, baked into an SVG data URI, so a large flat surface has
texture rather than visible banding.

It is the only purely decorative thing on the page, which is why it is also
the faintest and the slowest. If it is ever noticeable as *movement*, it is
too strong.

## The command bar

The brief was that the target-URL field should be prominent, and the answer
was to stop treating it as a field. `.command` is a bar the full width of the
form pane containing three things: a reticle mark, a large monospace input,
and the primary button inset inside the bar's own rounded edge. It is the
biggest object on the landing page and it is the only one with a gradient.

The focus ring sits on the **bar** - `.command:focus-within` - while
`.command-input` clears its own border and outline. A visitor tabbing into the
page lights up an object 1100px wide; the ring it replaced was 2px around a
box. Below 620px the bar becomes a stack and the button goes full width,
because a 40-character address and a button do not share 390px.

## Motion

Motion here is meant to be felt rather than seen. There are five movements and
no more:

| Movement | Where |
|:---------|:------|
| `aurora` | the backdrop, a 30s drift |
| `rise` | above-the-fold blocks arriving, line by line, out of a blur |
| `[data-reveal]` | below-the-fold blocks, the same arrival, driven by `reveal.js` |
| `halo` | the scan form breathing while it waits to be used |
| `dial` / `sweep` | the grade ring drawing itself to the rating |

Plus one hand-off: when `scan.js` has a terminal state it marks the document
`data-exit="true"`, the report falls a few pixels into blur, and only then is
the rendered result requested. The reload stops being a cut.

Two easings, and only two: `--ease` for anything that responds to a pointer,
`--ease-out` for anything that arrives on its own.

**Every one of them dies under `prefers-reduced-motion: reduce`.** The reset
in the stylesheet clamps every animation and transition to a millisecond and
turns off smooth scrolling; the exit hand-off is never marked at all, so a
reader who asked for stillness gets the old immediate reload. A new animation
that is not covered by that reset - a JavaScript-driven one, say - has to opt
out itself. This is not a nicety; motion sickness is a real accessibility
failure.

`reveal.js` hides nothing until it has run, by marking `<html>` itself, so a
browser that never executes it shows the whole page. It also sweeps up blocks
a jump-scroll carried past the viewport between two frames, which an
IntersectionObserver reports as no crossing at all - without that, an anchor
link could strand a section invisible for good.

## Contrast

Measured, not eyeballed. Every text pair clears WCAG AA (4.5:1) in both
schemes, over the paper and over a card composited on it:

| Pair | Light | Dark |
|:-----|------:|-----:|
| `--ink` on `--paper` | 16.6 | 17.1 |
| `--ink-soft` on `--paper` | 7.2 | 9.0 |
| `--ink-faint` on `--paper` | 4.8 | 5.3 |
| `--ink-faint` on a card | 5.3 | 4.9 |
| `--brand-deep` on `--paper` | 6.9 | 11.9 |
| each `--x-ink` on its `--x-soft` | 6.2-6.8 | 9.0-11.0 |
| `--on-accent` on `--brand` | 5.4 | 8.3 |

`--ink-faint` is the tightest of them and it carries hint text at 13px, so it
is the one to re-measure after any change to the paper or the card opacity.
Colour never carries meaning alone: a severity is a word as well as a tint, a
grade is a letter as well as a ring.

## What the policy forces

Several things in the system look like taste and are not:

- **No `unsafe-inline` in the CSP**, so there are no `style=` attributes, no
  `<style>` blocks, no `onclick` and no inline `<script>`. A one-off style
  becomes a utility class or a `[data-…]` rule - which is why the dial's six
  sweeps are six rules and not a custom property set from the template.
- **Assets are referenced as `/static/…`**, never through `url_for`, which
  emits an absolute URL and hands the page's own hostname back to it.
- **Nothing comes from a third party**, and Twitter/X, Google and Meta are
  excluded by name, as requests *and* as metadata. Platform-neutral OpenGraph
  tags stay: nothing fetches them.
- **The artwork is hand-drawn.** `logo.svg`, `hero.svg`, `expired.svg` and
  `og-image.svg` are small hand-written SVGs carrying their own light and dark
  variants. No stock photography, no icon pack, no generic illustration.
- **`opencloud.example.com` is the only address that may appear** in a
  placeholder, an example or a screenshot.

## Extending it

- Add a **token**, not a colour at a call site - and give it a dark value in
  the same commit.
- Reuse an existing **component** before inventing one. There are already
  panes, chips, tags, counters, toggles, kickers, steps and page-nav cards.
- If a new element moves, add it to the reduced-motion reset. If it carries
  text on a tint, measure it.
- Keep the voices apart: display for headlines, sans for prose, mono for data.
  A sentence in monospace reads as data and a measurement in prose reads as an
  opinion.
- Read [`frontend/README.md`](frontend/README.md) for the template contract
  before touching markup - the tests encode parts of it.

## Trademarks and affiliation

This is an independent community project. It is not affiliated with, endorsed
by, sponsored by or supported by OpenCloud GmbH. "OpenCloud" and all related
names and marks belong to their respective owners and are used here only to
identify the software being checked. The notice in the footer of
`base.html` is part of the design, not decoration around it: do not remove it
from a template, and add it to any new surface that stands on its own.
