# Evidence base and references

The advice SawahPintar gives is not invented. Every threshold and decision rule
traces to published agronomy, Indonesian government guidance, or the sensor
literature. This document lists those sources and what each one supports, so a
facilitator can answer a reviewer and a colleague can check the reasoning.

The sources below were gathered by a structured research review and cross
checked against each other. Treat the list as a working bibliography for the
project, not as final citations in a paper: before anything here is quoted in a
formal publication, confirm the author list, year and exact figures against the
primary source. A few of the Indonesian government pages moved or were renamed
during 2024 and 2025, which is noted where it applies.

## How the sources map onto the rules

| What the application does | Source |
| --- | --- |
| Treats salinity as the highest-priority alert, weighted by growth stage | 1 |
| Escalates salinity most strongly at panicle initiation and flowering | 1 |
| Triggers lime or dolomite and stronger phosphorus and potassium advice below pH 5.5 | 2 |
| Follows Safe Alternate Wetting and Drying for irrigation, suspended around flowering | 3 |
| Frames nutrient management as site-specific rather than a blanket rate | 4 |
| Gathers field-card inputs a probe cannot supply, in the Rice Crop Manager style | 5 |
| Converts operator-entered PUTS status classes into a fertiliser dose | 6 |
| Uses PUTS classes, not the probe, as the basis for any dose | 7 |
| Refuses to treat the probe's nitrogen, phosphorus and potassium outputs as measurements | 8 |
| Prefers plain, icon-led presentation for a low-literacy audience | 9 |

## The sources

**1. Salinity and rice yield, by growth stage.**
Zheng et al. (2023), European Journal of Agronomy. A meta-analysis of 58
studies reporting a pooled grain-yield loss under salinity stress of about 64.5
per cent, with the reproductive stage, from panicle initiation to flowering,
more sensitive than the seedling stage.
https://www.sciencedirect.com/science/article/abs/pii/S1161030123000333
Caveat, and it matters: 64.5 per cent is a pooled mean across experimental
treatments that were often severe. It is not a typical field loss under mild or
moderate salinity, and the application deliberately does not put that figure in
front of farmers. It is stated here only to justify why salinity is the
top-priority alert and why it is weighted towards the reproductive stage.

**2. Soil pH, phosphorus and potassium response, and site-specific nutrient
management in Indonesia.**
Field Crops Research (2025), a study of 528 lowland-rice on-farm trials in
Indonesia. Rice responds more strongly to added phosphorus and potassium below
pH 5.5, so lime or dolomite and P and K supplementation are more worthwhile on
acid soils. The same study found site-specific nutrient management beat a
blanket fertiliser rate by 0.4 Mg per hectare and 173 US dollars per hectare in
gross return.
https://www.sciencedirect.com/science/article/abs/pii/S0378429025001297
This is the closest source to the exact regional context, lowland paddy in
Indonesia, and the pH 5.5 threshold in the acidity rule comes from it.

**3. Safe Alternate Wetting and Drying.**
IRRI Rice Knowledge Bank, "Saving Water with Alternate Wetting and Drying".
Re-flood when the perched water level falls to about 15 cm below the soil
surface, top up to about 5 cm, and hold the field continuously flooded from one
week before to one week after flowering.
http://www.knowledgebank.irri.org/training/fact-sheets/water-management/saving-water-alternate-wetting-drying-awd
Important: the 15 cm trigger is a water-table depth read from a perforated field
tube, not a volumetric-moisture reading. The application maps the probe's
moisture reading onto this trigger through a calibration layer whose default is
marked provisional. See section 7.3 of the deployment manual.

**4. Site-specific nutrient management, definition.**
IRRI, Site-Specific Nutrient Management. Location-specific principles for
supplying rice with nutrients as needed, rather than uniform application rates.
https://ghgmitigation.irri.org/mitigation-technologies/site-specific-nutrient-management

**5. Rice Crop Manager, and why a field card is needed.**
IRRI Rice Crop Manager, known in Indonesia as Layanan Konsultasi Padi, with the
calibration described by Sharma et al. (2019), Field Crops Research.
https://www.irri.org/projects/rice-crop-manager-scale-and-dissemination-digital-tool-promoting-environmental
https://www.sciencedirect.com/science/article/pii/S0378429019301935
This tool generates a one-page fertiliser recommendation from farmer-interview
inputs: field size, variety, seedling age, water management, previous yields,
residue and fertiliser choice. It does not use soil-probe readings. That is
exactly why the operator console has a field card: to capture the inputs a
probe cannot supply, so any fertiliser guidance is honestly site-specific
rather than pretending a probe reading alone can produce it.

**6. Indonesian official fertiliser doses.**
Peraturan Menteri Pertanian Republik Indonesia Nomor 13 Tahun 2022. Fertiliser
doses for lowland paddy keyed to discrete soil nutrient-status classes, with the
status thresholds and the corresponding phosphorus doses the application uses.
Primary text on the Ministry of Agriculture legal portal, with a mirror on the
national legal database:
https://peraturan.bpk.go.id/Download/266850
The status-class thresholds in `data/permentan_2022.yaml` were checked
byte-for-byte against the mirror.

**7. PUTS, the national paddy soil test kit.**
Perangkat Uji Tanah Sawah, a field-usable colorimetric kit developed by the
Indonesian Soil Research Institute (Balai Penelitian Tanah) and distributed by
the Ministry of Agriculture. It sorts nitrogen, phosphorus and potassium into
rendah, sedang or tinggi and reads pH.
https://sulbar.brmp.pertanian.go.id/berita/puts-cara-cepat-untuk-menentukan-rekomendasi-pemupukan-padi-sawah
Note: the agency was renamed from BSIP to BRMP in 2025, so older links carrying
"bsip" in the address may not resolve; the article itself was relocated, not
withdrawn. PUTS is the credible anchor for the application's fertiliser advice,
because it measures plant-available nutrients by chemical extraction rather than
bulk conductivity.

**8. Low-cost nutrient sensing has no validated basis.**
Ameer et al. (2024), Journal of Soils and Sediments, a review of real-time
nitrogen, phosphorus and potassium detection from soil. Quantifying these three
nutrients remains, as of that review, a laboratory procedure. Cross-ion
interference is the core reliability problem, and potassium is the worst case,
commonly exceeding 50 per cent error.
https://link.springer.com/article/10.1007/s11368-024-03827-5
This is the academic backing for the honesty position in section 7 of the
deployment manual: the probe derives its nitrogen, phosphorus and potassium
outputs from one conductivity measurement, so the application never presents
them as independent nutrient figures and never derives a dose from them.

**9. Communicating with low-literacy farmers.**
GSMA Mobile for Development (2025), field testing of AI advisory tools with
Indonesian smallholders in Jakarta and Bali, which found voice and photo
interaction more usable than text for lower-literacy farmers.
https://www.gsma.com/solutions-and-impact/connectivity-for-good/mobile-for-development/blog/ai-for-smallholder-farmers-in-indonesia/
This is a single qualitative field study rather than a controlled trial, so it
is treated as directional, not conclusive. It supports the plain, icon-led,
colour-coded presentation the farmer display uses, and it is one reason the
Bahasa Indonesia wording is held as a draft pending faculty review rather than
treated as finished.

## What the research could not settle

Two things the project needs are not yet backed by a source and remain open for
faculty input:

- The exact Bahasa Indonesia wording, icon vocabulary and colour conventions
  that work best for rice farmers in rural South Sulawesi, possibly including
  Bugis or Makassarese terms. Every farmer-visible string in
  `data/content/advice.yaml` is marked as a draft for this reason.
- Local calibration values mapping the probe's bulk conductivity onto a salinity
  class, and its volumetric moisture onto a water-table depth, for the specific
  soils where the workshops will run. The defaults in
  `data/calibration/default.yaml` are marked provisional.
