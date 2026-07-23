# Reviewing the farmer-facing copy

This guide is for the Universitas Hasanuddin reviewer checking the Bahasa
Indonesia wording. You do not need to be a programmer. The text lives in one
plain file, and you can edit it in any text editor or straight in the GitHub
web interface.

## What needs reviewing, and why it is marked as a draft

Every message a farmer reads on the screen was drafted by the build team as a
starting point, not as finished copy. None of it has been checked by a Bahasa
Indonesia speaker for accuracy, tone, or fit with how rice farmers in South
Sulawesi actually talk. Some of it may read better in Bugis or Makassarese than
in standard Bahasa Indonesia. Until you have reviewed a message, it carries a
`draft: true` marker so everyone can tell reviewed wording from unreviewed
wording at a glance.

Your job is to make each message correct, natural and useful to a farmer, and
then to clear the draft marker so the team knows it has been checked.

## Where the text is

One file:

```
data/content/advice.yaml
```

It holds 13 advice messages, grouped by topic: salinity, water, acidity and
nutrients. Each one looks like this:

```yaml
salinity_moderate:
  icon: salinity
  headline_id: "Salinitas tanah sedang"
  body_id: "Pertimbangkan pencucian lahan dengan air tawar sebelum fase generatif."
  subtitle_en: "Salinity is moderate, consider flushing the field with fresh water before the reproductive stage"
  draft: true
```

Only three lines are wording:

- `headline_id` is the short Bahasa Indonesia headline the farmer sees first.
- `body_id` is the Bahasa Indonesia sentence underneath it.
- `subtitle_en` is an English gloss for visitors and for your reference. It
  tells you what the message is meant to say, so you can judge whether the
  Bahasa matches the intent.

## What to do

For each of the 13 messages:

1. Read the `subtitle_en` to see what the message is meant to convey.
2. Improve `headline_id` and `body_id` so they say that clearly and naturally
   for a rice farmer in the workshop area. Change the wording freely. Use Bugis
   or Makassarese terms where they land better than standard Bahasa Indonesia.
3. Keep the meaning aligned with the English gloss. If you think the intended
   meaning itself is wrong for local conditions, change `subtitle_en` too and
   leave a note for the team.
4. When a message is right, delete its `draft: true` line. That is how the team
   knows it has been reviewed.

## What not to change

- Do not change the key at the top of each entry, such as `salinity_moderate`.
  The application looks messages up by that key; renaming it breaks the link.
- Do not change the `icon` line. Icons are chosen separately.
- Keep the quotation marks and the indentation exactly as they are. YAML is
  sensitive to indentation: two spaces before `headline_id`, and the text
  inside straight double quotes.

## One hard rule

Do not put the figure "64.5 per cent" (or any single headline yield-loss
number) into farmer-facing text. It comes from an experimental meta-analysis and
is a pooled average across often-severe trials, not a loss a farmer should
expect in their own field. Describe the risk in plain terms instead, as the
current drafts do. The reasoning is in `docs/references.md`, source 1.

## Editing the file

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

Almost all farmer-facing text is in the file above. A few short fixed labels are
built into the interface itself rather than the content file, and you are
welcome to review these too if you have time:

- The reconnect and sensor-status banners, in `app/web/index.html` and
  `app/web/app.js` (search for "Sambungan" and "Sensor tidak merespons").
- The operator console labels, in `app/web/operator.html`. This screen is for
  the facilitator, not farmers, so its wording matters less, but it is all in
  Bahasa Indonesia as well.

If in doubt, focus on `data/content/advice.yaml`. That is the wording farmers
actually read during a workshop.
