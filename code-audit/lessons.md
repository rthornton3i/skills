# Audit lessons (learned; the orchestrator updates this after every audit run)

Each entry: what was learned and the evidence. Merge duplicates, delete entries proven wrong, keep it short. The auditor reads this file before the slice and puts the highest-yield checks first. Start empty; fill it from real audit reports.

## Where bugs hid
(Areas of the code, and the kind of defect found there, with how to probe for it quickly.)

## Checks that paid off
(Checks that found real defects or turned a suspected bug into a confirmed one.)

## Checks that did not pay off (skip or shrink)
(Checks that repeatedly found nothing.)

## Architecture notes
(What fits the code's design and the weak seams to watch.)

## Calibration
(Typical cost of one audit slice in tokens and time, and tips for running several auditors at once.)

## Review of the implementations
(Reviews that pay, and recurring nits worth grepping for after a cleanup.)
