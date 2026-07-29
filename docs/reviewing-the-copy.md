# Reviewing the farmer-facing copy

This guide is for the Universitas Hasanuddin team checking SawahPintar's content.
You do not need to be a programmer. Almost everything lives in one plain file,
and you can edit it in any text editor or straight in the GitHub web interface.

There are **two kinds of reviewer**, and this guide gives each a short path:

- A **language reviewer** checks and improves the Bahasa Indonesia so it is
  accurate and natural for rice farmers in South Sulawesi.
- An **agronomy reviewer** checks that each message's advice actually fits the
  condition that triggers it, and that the nutrient bands suit local rice.

You may be one person doing both passes, or two people. Either way, do the two
passes separately - it is easier to judge language and agronomy one at a time.

## Why everything is marked as a draft

Every message a farmer reads was drafted by the build team as a starting point,
not as finished copy. None of it has been checked by a Bahasa Indonesia speaker
for accuracy, tone, or fit with how rice farmers in South Sulawesi actually
talk - some of it may read better in Bugis or Makassarese than in standard
Bahasa Indonesia. Nor has the agronomy been signed off. Until an item is
reviewed it carries a `draft: true` marker, so everyone can tell reviewed
wording from unreviewed wording at a glance.

## Where the text is

One main file:

```
data/content/advice.yaml
```

It holds 13 advice messages, grouped by topic with a comment header before each
group: **salinity**, **water**, **acidity** and **nutrients**. Below those, the
same file has a separate `npk_estimate:` block for the NPK figures the app now
shows (see "The NPK estimate" below).

Each advice message looks like this:

```yaml
salinity_moderate:
  icon: salinity
  headline_id: "Salinitas tanah sedang"
  body_id: "Pertimbangkan pencucian lahan dengan air tawar sebelum fase generatif."
  subtitle_en: "Salinity is moderate, consider flushing the field with fresh water before the reproductive stage"
  when: "Conductivity 2001 to 4000 uS/cm (moderately saline), outside the panicle initiation and flowering stages."
  draft: true
```

What each line is:

- `headline_id` - the short Bahasa Indonesia headline the farmer sees first.
  **Language reviewer edits this.**
- `body_id` - the Bahasa Indonesia sentence underneath it.
  **Language reviewer edits this.**
- `subtitle_en` - an English gloss, for reference. It tells you what the message
  is meant to say, so you can judge whether the Bahasa matches the intent.
- `when` - the exact condition that makes this message appear, for example
  "Conductivity 2001 to 4000 uS/cm (moderately saline)".
  **Agronomy reviewer reads this.** The app does not use the `when` line; it is
  documentation only, so the language reviewer can ignore it.
- `icon` and `draft` - handled below; do not edit `icon`.

## Path A - language reviewer (Bahasa Indonesia)

Go message by message through `advice.yaml`. For each one:

1. Read `subtitle_en` to see what the message is meant to convey.
2. Improve `headline_id` and `body_id` so they say that clearly and naturally
   for a rice farmer in the workshop area. Change the wording freely. Use Bugis
   or Makassarese terms where they land better than standard Bahasa Indonesia.
3. Keep the meaning aligned with the English gloss. If you think the intended
   meaning itself is wrong, change `subtitle_en` too and leave a note for the
   team so the agronomy reviewer sees it.
4. Delete that entry's `draft: true` line once you are happy with it. That is how
   the team knows it has been reviewed.

Then do the same for the wording in the `npk_estimate:` block: improve each
`action_id` (the Bahasa Indonesia action, such as `pertimbangkan urea`) and
delete that band's `draft: true` when done. Leave `band_id` (Rendah / Sedang /
Cukup) and the numbers to the agronomy pass.

## Path B - agronomy reviewer (does the advice fit the condition?)

Go message by message through `advice.yaml`. For each one:

1. Read the `when` line - the exact condition that triggers the message
   (a conductivity range, a pH threshold, a water-table depth, and/or a growth
   stage).
2. Read `subtitle_en` - the advice the farmer is given when that condition holds.
3. Ask: does the advice actually fit the condition? If it does not - wrong
   direction, wrong stage, a range that overlaps another message, a threshold
   that is wrong for local lowland rice - flag it with a short note for the team.
   Do not edit the Bahasa wording; that is the language pass.
4. For the `npk_estimate:` block, check the mg/kg ranges for N, P and K are
   sensible for local lowland rice, and that each band's action is proportionate.
   Note any threshold you think is wrong.

Note on the numbers: the salinity class and the water-table depth in the `when`
lines are **derived** from the probe's bulk conductivity and moisture through a
calibration layer whose defaults are marked provisional, and bulk conductivity
is not the same quantity as the saturated-paste-extract conductivity used in the
published salinity thresholds. So treat the breakpoints as open for review, not
as fixed truth. The evidence behind each rule is in `docs/references.md`.

## The NPK estimate (validate the nutrient bands)

The app's field map now shows an **NPK estimate** on each plot's detail panel,
labelled "estimasi sensor". For nitrogen (N), phosphorus (P) and potassium (K)
it shows a number in mg/kg, a band (Rendah / Sedang / Cukup) and a light action.
Those bands and actions live in the `npk_estimate:` block of `advice.yaml`:

```yaml
npk_estimate:
  nitrogen:
    symbol: "N"
    label_id: "Nitrogen"
    unit: "mg/kg"
    low:
      range: "below 80 mg/kg"
      band_id: "Rendah"
      action_id: "pertimbangkan urea"
      action_en: "consider urea (a nitrogen fertiliser)"
      draft: true
    medium:
      range: "80 up to 200 mg/kg"
      band_id: "Sedang"
      action_id: "pantau"
      action_en: "monitor"
      draft: true
    adequate:
      range: "200 mg/kg and above"
      band_id: "Cukup"
      action_id: "cukup"
      action_en: "adequate, no action needed"
      draft: true
  # phosphorus and potassium follow the same shape
```

Two things to understand before you change it:

- **It is an estimate, never a fertiliser dose.** The probe derives N, P and K
  from a single conductivity measurement, so these are not real nutrient
  measurements. A real dose comes only from a PUTS soil-test kit read against
  Permentan 13/2022. Keep the action words light ("pertimbangkan ..." /
  consider, "pantau" / monitor, "cukup" / adequate) - never a quantity.
- **These thresholds and action words also live in the app code**, at
  `app/web/app.js` (the `NPK_META` array and `BAND_ID_LABEL`). The app does
  **not** read them from `advice.yaml`. So if you change a number or an action
  word here, **tell the developer to mirror the change in `app.js`**, or the
  screen and this file will disagree.

## What not to change

- Do not change the key at the top of each entry, such as `salinity_moderate`,
  or the nutrient/band keys in `npk_estimate` (`nitrogen`, `low`, and so on).
  The application looks messages up by these keys; renaming one breaks the link.
- Do not change the `icon` line. Icons are chosen separately.
- Keep the quotation marks and the indentation exactly as they are. YAML is
  sensitive to indentation: two spaces before `headline_id`, and the text inside
  straight double quotes.

## One hard rule

Do not put the figure "64.5 per cent" (or any single headline yield-loss number)
into farmer-facing text. It comes from an experimental meta-analysis and is a
pooled average across often-severe trials, not a loss a farmer should expect in
their own field. Describe the risk in plain terms instead, as the current drafts
do. The reasoning is in `docs/references.md`, source 1.

## Editing the file safely

Two easy ways:

- On GitHub, open `data/content/advice.yaml`, click the pencil icon to edit in
  the browser, make your changes, and either commit directly or open a pull
  request. This needs only a GitHub account and no software.
- Or download the file, edit it in any plain-text editor (Notepad is fine, or
  VS Code), and send it back to the team.

Please keep everything in plain keyboard characters: straight quotes, ordinary
hyphens, no curly quotes and no special symbols. A word processor such as Word
can quietly turn straight quotes into curly ones, which breaks the file, so a
plain-text editor or the GitHub browser editor is safer than Word.

## Two other places with fixed wording

Almost all farmer-facing text is in `advice.yaml`. A few short fixed labels are
built into the interface itself rather than the content file, and you are welcome
to review these too if you have time:

- The reconnect and sensor-status banners, in `app/web/index.html` and
  `app/web/app.js` (search for "Sambungan" and "Sensor tidak merespons").
- The operator console labels, in `app/web/operator.html`. This screen is for
  the facilitator, not farmers, so its wording matters less, but it is all in
  Bahasa Indonesia as well.

If in doubt, focus on `data/content/advice.yaml`. That is the wording farmers
actually read during a workshop.
