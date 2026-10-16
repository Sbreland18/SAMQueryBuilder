# SAM Ad Hoc Query Builder – pilot plan

**Goal:** prove the app end to end with real SAM data and real vendors before offering it to other districts.
**Length:** 3 weeks of nightly runs after setup. **Where:** one district (Hancock County SD), one PC that stays on overnight.

## Who

| Role | Person | Does |
|---|---|---|
| Pilot lead | Spencer Breland | Setup, daily check, decisions, sends findings |
| SAM / data contact | | Answers SAM data questions, fixes records from the cleanup reports |
| Vendor contacts | (one per vendor) | Confirm the files load correctly, sign off |

## Pick three vendors

1. **Clever** – rostering most instructional apps; strict, well-documented format and good error reports.
2. **Google Workspace** – account file; tests the username / email patterns (e.g. staff `j.smith@`).
3. **One family-communication vendor** you already use – SchoolStatus, ParentSquare, SchoolMessenger or Remind (tests contacts, phones and owner types).

Optional fourth: **Account shutoff** in review-only mode (compare the list with known withdrawals each week; don't disable anything during the pilot).

## Week 0 – setup (1–2 days)

- [ ] Run the *Windows test checklist* sections A–E.
- [ ] Run the **SAM setup check**; fix or accept every red/orange finding. Keep the saved report.
- [ ] For each vendor: CAC Agent walkthrough → first CAC run → **Check exported files** until there are no errors.
- [ ] Send each vendor a sample (vendor's test / sandbox area if they have one). Record it with **Vendor sign-off → Sample sent**.
- [ ] Create the upload profiles (safety net on, 10%) and turn on **alerts** to your email and/or Teams.
- [ ] Mark the three vendors **in use** in the privacy register and record their agreements.

## Weeks 1–3 – nightly runs

Every school day (5 minutes):

- [ ] Start page → **Nightly uploads** board: every upload OK? Any alert email overnight?
- [ ] If an upload was **held**: open Package & Upload → **What changed?** → decide (real change → *Upload anyway once*; bad data → fix the CAC job or SAM and re-run).
- [ ] Note anything odd in the log below.

Every Friday (20 minutes):

- [ ] **Check exported files** for each vendor; compare a few students/teachers in the vendor's system with SAM.
- [ ] Run (or receive by email) the **data cleanup reports**; pass the lists to the data contact.
- [ ] Account shutoff review: does the list match the week's withdrawals?
- [ ] **District health report** → save or email it.

End of week 3:

- [ ] Each vendor confirms the data is right → **Vendor sign-off → Vendor approved**.
- [ ] Decide: go live / fix and extend / stop (see success criteria).

## Success criteria

- 15 consecutive school nights with no unexplained failures for all three vendors.
- Every safety-net hold was a real change or a caught problem (no false alarms after week 1).
- Vendors confirm students, teachers, classes and contacts match SAM (spot checks agree).
- Alerts reached the right person within the hour every time something failed.
- No student data was sent anywhere except the three vendors (privacy register up to date).

## If something goes wrong

- Turn off the schedule (Package & Upload → **Remove schedule**) – vendors keep the last good data.
- Upload a known-good copy from `archive\_last_good_upload` with **Run now** after fixing the cause.
- Send the details listed under *Reporting problems* in the test checklist.

## Daily log

| Date | Clever | Google | Messaging vendor | Held / failed? What changed? | Action taken |
|---|---|---|---|---|---|
| | | | | | |
| | | | | | |
| | | | | | |
