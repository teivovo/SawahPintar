# SawahPintar

A soil-sensor teaching tool for rice-farming workshops, built for the Rural AI
project with the University of Newcastle and Universitas Hasanuddin.

One laptop, one soil probe and one RS485-to-USB dongle make a kit. The
application reads the soil, moisture, temperature, conductivity and pH, and
turns those readings into plain-language, growth-stage-aware farming advice in
Bahasa Indonesia. A faculty facilitator drives the laptop; farmers get a
hands-on moment pushing the probe into the soil and watching the screen react.

It runs fully offline, needs no installation and no administrator rights, and
replicates by copying a folder. The Python runtime travels inside the folder,
so a workshop laptop needs nothing pre-installed except Microsoft Edge, which
ships with Windows.

## Quick start

If you have a built kit folder, just run it:

1. Plug in the RS485-to-USB dongle.
2. Double-click `Start Workshop.bat`.
3. The application opens by itself in a clean full-screen window. It starts in
   simulation mode, with demonstration history already loaded, so the screen is
   alive from the first second.

To build a kit from source, on a Windows machine with internet access:

```powershell
scripts\build_portable.ps1
```

This produces a `SawahPintar` folder with its own Python runtime and every
dependency inside it. Copy that whole folder to a workshop laptop and run
`Start Workshop.bat`. The full procedure, including the one step that will break
a kit if you skip it, is in the deployment manual below.

## Documentation

- [Deployment manual](docs/deployment-manual.md). How to build a kit, wire the
  probe, run a workshop, and troubleshoot. Written for faculty, not developers.
- [Reviewing the farmer-facing copy](docs/reviewing-the-copy.md). For the
  Bahasa Indonesia reviewer. Every farmer-facing message is a draft awaiting
  review, and this is where and how to check it.
- [Evidence base and references](docs/references.md). The published agronomy and
  Indonesian government guidance behind every threshold and rule.
- [Project team briefing slides](docs/slides/index.html). Open in a browser.

## For the language reviewer

The wording farmers read is not final. It was drafted by the build team and
none of it has been checked by a Bahasa Indonesia speaker yet, so every message
is marked `draft: true`. All of that copy lives in one plain file,
`data/content/advice.yaml`, which you can edit in a text editor or directly on
GitHub. See [Reviewing the farmer-facing copy](docs/reviewing-the-copy.md) for
exactly what to change and how to hand it back. That review is the single most
useful contribution Hasanuddin can make to the kit before a workshop.

## The honesty position

The probe reports nitrogen, phosphorus and potassium values, but these are not
three measurements. They are three functions of one conductivity reading, which
means they cannot be separated from each other. The application therefore never
shows them as independent nutrient figures and never derives a fertiliser dose
from the probe. A dose comes only from an operator-entered PUTS soil-test result
via the official Permentan 13 of 2022 table. Section 7 of the deployment manual
explains this in full, with the three lines of evidence, so a facilitator can
answer a farmer or a reviewer who asks. The academic backing is source 8 in the
references.

## How it works

- A small Python service using FastAPI and DuckDB, started by the launcher and
  shown in a Microsoft Edge window running in application mode, so it reads as a
  purpose-built device rather than a web page.
- The probe speaks Modbus RTU over RS485. A JSON sensor profile describes the
  register map, so a different vendor's probe can be supported by editing a
  file, with no code change.
- An agronomic rule engine reads the current reading, the recent trend, and the
  growth stage the facilitator has set, and produces ranked advice cards. Every
  threshold lives in a YAML file that faculty can edit without touching code.
- Demonstration history is generated deterministically and clearly marked, so
  charts are alive the moment the application opens without ever passing
  synthetic data off as measured.

## What is deliberately unfinished

Two things are placeholders by design, waiting on local input:

- The Bahasa Indonesia wording, marked `draft: true` in
  `data/content/advice.yaml`, pending the review described above.
- The calibration mapping the probe's conductivity onto a salinity class and
  its moisture onto a water-table depth, marked `provisional: true` in
  `data/calibration/default.yaml`, pending measurement against local South
  Sulawesi paddy soils.

## Requirements

- A Windows laptop with Microsoft Edge (ships with Windows 10 and 11).
- An RS485-to-USB dongle and its driver (commonly CH340 or FTDI).
- An SN-3002-TR five-pin soil probe, or another Modbus RTU probe with a matching
  sensor profile.
- To build a kit: a Windows machine with internet access and PowerShell.
