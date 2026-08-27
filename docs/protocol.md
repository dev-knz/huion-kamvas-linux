# Observed GS1333 protocol

This document records facts observed on a physical Huion Kamvas 13 Gen 3. It
does not assign meanings to unknown bytes.

## Vendor dial report

After `huion-switcher --all`, dial events moved to the vendor `hidraw`
interface. Each observed report was 14 bytes long:

| Offset | Observed value | Meaning |
| --- | --- | --- |
| 0 | `08` | vendor report ID |
| 1 | `f1` | wheel report marker |
| 2 | `01` | wheel report marker |
| 3 | `01` / `02` | top dial / bottom dial |
| 4 | `00` | observed; meaning unknown |
| 5 | `01` / `02` | clockwise / counterclockwise |
| 6–13 | usually `00` | unknown |

Confirmed examples:

```text
08 f1 01 01 00 01 00 00 00 00 00 00 00 00  top clockwise
08 f1 01 01 00 02 00 00 00 00 00 00 00 00  top counterclockwise
08 f1 01 02 00 01 00 00 00 00 00 00 00 00  bottom clockwise
08 f1 01 02 00 02 00 00 00 00 00 00 00 00  bottom counterclockwise
```

The parser intentionally accepts only these known markers, dial indexes, and
directions.

## Apparent duplicate reports

Initial manual testing showed two identical printed reports for what appeared
to be one physical detent. That observation is not enough to define a safe
deduplication rule: two fast real detents can also produce adjacent identical
reports.

The capture tool therefore records monotonic timestamps and marks
`adjacent_identical=yes`, but it does not suppress anything. We need timing
captures from controlled slow and fast rotations before deciding whether the
cause is firmware repetition, detent resolution, or another state transition.

## Upstream comparison

The upstream Linux HID-BPF program independently documents the wheel as a
vendor subtype in the high nibble of byte 1, dial index in byte 3, and direction
in byte 5. This agrees with the reports above. It converts clockwise to `+1`
and counterclockwise to `-1`.
