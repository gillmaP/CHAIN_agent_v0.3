# Summary output contract v2.2

The experiment emits two top-level fields:

- summary: a short Korean narrative for a person.
- items: individual source-grounded facts for downstream screening and rules.

Each item has category, concept, subject, status, temporality, and source. The
optional reported_by field identifies an explicitly named reporter; if omitted, the
parser sets it to not_stated.
The source has the document ID, note-entry time, and an exact supporting quotation.
Event time is kept separate from note-entry time.

Optional item fields are subject_detail, value, unit, event_time, and event_time_kind.
Omit fields that do not apply. This schema does not use JSON null.

## Status meanings

| Status | Meaning |
|---|---|
| present | The record explicitly says the finding or history is present. |
| absent | The record explicitly says the finding is absent. |
| uncertain | The record says possible, suspected, or unclear. |
| explicitly_unknown | The record explicitly says the information is unknown or could not be determined. |
| recorded | A specific time, measurement, or value is recorded. |
A concept that is not mentioned is omitted from items. If a required checklist is agreed later, missing fields should be returned in a
separate list rather than as an evidence-backed item.

For an explicit negative symptom, use status absent and omit value. Do not encode the
same negative a second time with a separate polarity field. For explicit unknown LKW,
use status explicitly_unknown and omit the time. A missing mention is not an explicit
negative or an explicit unknown.

## Source, subject, reporter, and time

subject means who the fact is about. Symptoms belong to the patient even when a family
member or coworker reports them. reported_by is the person whose statement is explicitly
described, not the note author; use not_stated when the speaker is not specified. For
family history, use subject family_member and include a relationship such as father in
subject_detail.

Use present, absent, uncertain, or explicitly_unknown for symptoms, diagnoses, history,
and medications. Reserve recorded for timeline entries and vital/lab measurements.
Keep a medication name, its full dose/frequency in value, and an explicit last-dose
time in event_time on the same medication item. Reserve unit for vital/lab values.
Preserve stated qualifiers such as laterality and age in value. Keep ambiguous r/o
wording neutral rather than turning it into a definite diagnosis or exclusion.

source.documented_at is when the note was entered. event_time is when the symptom,
last-known-well time, medication dose, or measurement occurred. Do not copy the
note-entry timestamp into event_time. When two sources disagree, keep both items with
their own event time, reporter, source document, and quotation.

## Example

    {
      "summary": "13:40부터 왼쪽 팔 힘 빠짐. 얼굴 처짐은 없다고 기록됨.",
      "items": [
        {
          "category": "symptom",
          "concept": "symptom.left_arm_weakness",
          "subject": "patient",
          "reported_by": "not_stated",
          "status": "present",
          "temporality": "current",
          "source": {
            "document_id": "ER-001",
            "documented_at": "2026-10-06T14:12:00+09:00",
            "quote": "오후 1시 40분부터 왼쪽 팔에 힘이 빠짐"
          },
          "event_time": "2026-10-06T13:40:00+09:00",
          "event_time_kind": "symptom_onset"
        },
        {
          "category": "symptom",
          "concept": "symptom.facial_droop",
          "subject": "patient",
          "reported_by": "not_stated",
          "status": "absent",
          "temporality": "current",
          "source": {
            "document_id": "ER-001",
            "documented_at": "2026-10-06T14:12:00+09:00",
            "quote": "facial droop와 dysarthria는 없다고 함"
          }
        }
      ]
    }

## Scope of this experiment

The four synthetic cases exercise time, symptoms (including an explicit negative and
uncertainty), diagnosis wording, personal and family history, medication and last-dose
time, blood pressure, glucose, and conflicting onset reports. Imaging, allergy, and
other clinical fields can be added after their required fields and extraction
expectations are agreed. Summary extracts facts; it does not decide stroke diagnosis
or treatment eligibility.
