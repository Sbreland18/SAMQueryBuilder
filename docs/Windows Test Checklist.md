# SAM Ad Hoc Query Builder – Windows test checklist

Work through this on the **build PC** (sections A–D) and on **one district PC** (sections E–N). Tick each box when the expected result happens. When something fails, write what you saw in the *Notes* line and send the items listed in **Reporting problems** at the end.

Tester: ____________________ Date: ____________ App version: ________ Data version: ________

---

## A. Build PC prerequisites

- [ ] Python 3.12 or 3.13 from python.org installed (not the Microsoft Store alias). `py --version` works.
- [ ] `Setup Dev Environment.bat` finished without errors (installs PySide6, paramiko, sqlglot, pgpy, pyodbc, pyinstaller, pytest).
- [ ] Inno Setup 6 installed (ISCC.exe found on the Build GUI's Release tab).
- [ ] Git for Windows installed. GitHub CLI: Build GUI → GitHub Setup → **Install GitHub CLI** (or `winget install --id GitHub.cli -e`), then **Check tools** shows `gh OK` and **Sign in to GitHub** finishes in the browser. Only publishing needs gh.
- [ ] Optional: Windows SDK *Signing Tools* (signtool.exe) and your code-signing certificate.
- [ ] Optional: Microsoft ODBC Driver 18 for SQL Server (only for the read-only SAM connection).
- [ ] Optional: Gpg4win (only if a vendor requires PGP; the app also has a built-in fallback).

Notes: ______________________________________________

## B. Build

- [ ] `Build GUI.bat` opens and the text is readable (light theme, also with Windows dark mode on).
- [ ] Release tab → **Build** with *Run unit tests* ticked: tests pass (47 or more).
- [ ] PyInstaller step finishes; `dist\SAM Ad Hoc Query Builder\SAM Ad Hoc Query Builder.exe` exists.
- [ ] Inno Setup step finishes; `installer\Output\SAM_AdHoc_Query_Builder_Setup_<version>.exe` exists.
- [ ] Data tab → **Rebuild platform export packages** runs and reports 55 platforms.

Notes: ______________________________________________

## C. Code signing (skip if you have no certificate yet)

- [ ] Release tab → tick *Sign the EXE and the installer*, choose the certificate (thumbprint or .pfx).
- [ ] Build log shows *Sign the EXE*, *Verify the EXE signature*, *Sign the installer*, *Verify the installer signature* all succeeded, and the .pfx password shows as `********`.
- [ ] Right-click the installer → Properties → **Digital Signatures** shows your organization and a timestamp.
- [ ] Download the installer on another PC (e.g. from the GitHub release): SmartScreen shows your name as publisher (EV) or "unknown publisher" fades after downloads (OV).

Notes: ______________________________________________

## D. Install and updates

- [ ] Installer runs **without admin rights** and installs to your user profile; Start menu shortcut appears.
- [ ] Double-clicking a saved `.samq` file opens it in the app.
- [ ] View → Theme → **Dark** → restart: every screen is readable (start page, all 6 steps, exports, Package & Upload, Query Assistant, template builder, health report, wizard). Repeat with **Match Windows** while Windows is in dark mode and in light mode.
- [ ] Help → Check for updates says you're up to date (or offers the newer version).
- [ ] Publish a small **data update** (Data tab → Publish data update). On the district PC, Check for updates offers *New tables and templates* and installs them without reinstalling.
- [ ] Publish a new **app version**: the district PC is offered it, the installer downloads, the SHA-256 check passes and the app restarts on the new version.

Notes: ______________________________________________

## E. First run and district setup (district PC)

- [ ] The **Setup wizard** opens on first start.
- [ ] Staff username pattern: choose **first initial.last** – the example shows `j.smith`. Try a custom pattern such as `{f}{m}.{last}` and see the example update.
- [ ] **Copy the all-in-one query**, run it in SAM (Ad Hoc Query → Query → paste → Run Query), save as `sam_all_codes.csv` and import it (SAM Codes & Schools → Import CSV files). Every list fills in and schools appear with the right SchoolIDs. If SAM errors, note the message and use each list's **Copy query** / **Import this list** instead.
- [ ] Tick the vendors you use; finish. The CAC Agent walkthrough opens.
- [ ] Tools → **SAM setup check**: save the *SAM setup check* package, run the 7 queries in SAM, choose the folder. Review every red/orange finding; **Apply suggested District Settings** if they look right.
- [ ] District Settings show the owner type codes and enrolled code you expect.

Notes: ______________________________________________

## F. Query builder against real SAM

- [ ] Open the *Homeroom Roster* template; the Results preview shows sample rows.
- [ ] Copy SQL (Step 6) → paste into SAM Ad Hoc Query → it runs without errors and the rows look right.
- [ ] Results preview → **My CSV file...** → open what SAM produced: the columns match.
- [ ] Describe a query (Ctrl+D): "9th - 12th grade students with homeroom, first name, last name and email" builds a sensible query that also runs in SAM.
- [ ] Import existing SQL (Ctrl+I): paste a query you already use in SAM; it opens in the steps and the regenerated SQL gives the same results.
- [ ] Filters → **Schools...** limits to one school by SchoolID.

Notes: ______________________________________________

## G. Export packages (start with Clever and Google)

- [ ] CAC Agent installed and registered on the agent computer, and the *CAS Agent Listener* task created (Help → **CAC Agent setup guide**, Parts 1 and 5).
- [ ] Export to a platform → Clever → **CAC Agent walkthrough**: create every query and job in SAM with the copy buttons; the checklist ticks off.
- [ ] Run the CAC Agent jobs (or wait for the nightly run): all 5 CSV files appear in the folder with the exact names.
- [ ] **Check exported files** → no errors (warnings reviewed).
- [ ] Google: student and staff emails in the files match real accounts (spot-check 10 of each, including a staff `j.smith`-style address).
- [ ] Data cleanup reports: run 2–3 of them in SAM; the records listed really need fixing.
- [ ] Open a package file, change a heading, **File → Save as district version**; the exports page shows *DISTRICT VERSION*; **Reset to standard** puts it back.

Notes: ______________________________________________

## H. Uploads

- [ ] Package & Upload → new profile for the vendor → **Test connection** succeeds (host key accepted).
- [ ] **Run now** uploads; the vendor sees the files; an archive copy and `archive\_last_good_upload` appear.
- [ ] Empty one CSV (keep the header) → Run now → the upload is **HELD** by the safety net; restore the file.
- [ ] Delete a few rows → **What changed?** lists exactly those rows as removed.
- [ ] **Schedule in Windows** → Task Scheduler shows *SAM Ad Hoc Query Builder - Upload ...*; right-click → Run → the log shows a run.
- [ ] In Task Scheduler, set the task to **Run whether user is logged on or not** (same Windows user) and confirm it still runs while you're signed out.
- [ ] Optional: FTPS profile, copy-to-folder profile, SSH key login, PGP-encrypted upload (vendor can decrypt).

Notes: ______________________________________________

## I. Alerts, reports and the health report

- [ ] Tools → Upload alerts → **Send a test alert** arrives by email (Microsoft 365 / Gmail relay) and/or Teams.
- [ ] A held or failed scheduled upload sends an alert.
- [ ] Tools → Report emails → a cleanup report CSV → **Send now** arrives with the table and the attachment; **Schedule** creates the task.
- [ ] Tools → District health report → Email now arrives; **Schedule monthly** creates the task.

Notes: ______________________________________________

## J. Account shutoff (review only – don't disable anything yet)

- [ ] Account shutoff package → run *shutoff_students.csv* in SAM: the students listed really left in the last 14 days; nobody still enrolled is on it.
- [ ] *shutoff_staff.csv* lists only staff terminated in the last 14 days.
- [ ] `Disable-ADUsers.ps1 -CsvPath .\shutoff_students.csv` (no -Apply) only previews.
- [ ] The Google suspend CSV header matches Admin console → Users → Bulk update → blank template.

Notes: ______________________________________________

## K. Optional read-only SAM connection

- [ ] SQL login that is only in **db_datareader** (ask your SAM / database administrator; check with Central Access).
- [ ] Tools → SAM database connection → Test: connects and does **not** warn that the login can change data.
- [ ] Results preview → **Run in SAM (read-only)** shows real rows and the exact count.
- [ ] Import SQL `DELETE FROM Student` → Run in SAM is refused before anything is sent.
- [ ] SAM setup check → **Run in SAM** gives the same findings as the CSV method.

Notes: ______________________________________________

## L. Several districts, PIN, backup

- [ ] District box → Manage districts → add a second district (copy District Settings). Switch: title bar shows it; settings, uploads and saved queries are separate; switching back restores the first.
- [ ] A schedule created in the second district runs (Task Scheduler task name includes the district; the command has `--district`).
- [ ] Tools → Admin PIN → set; Package & Upload asks for it; a wrong PIN is refused and appears in Tools → Change log.
- [ ] File → Back up settings → restore on another PC/user: settings come across, passwords must be re-entered.

Notes: ______________________________________________

## M. Vendor template builder and shared library

- [ ] New package from a vendor template → open a real vendor template → most columns turn green; fix the rest; preview; save. It appears under **My packages** and works with Save package / CAC walkthrough / Check exported files.
- [ ] Change a suggested field and save; start a new package with the same header – your choice is suggested (learned).
- [ ] Share: export package file → on the build PC, Data tab → Shared package library → Add → Publish data update → on another PC it appears under **Shared packages**; *Copy to My packages* works.

Notes: ______________________________________________

## N. Sign-off

- [ ] All sections above pass, or every failure is written down and sent.

Tester signature: ____________________ Date: ____________

---

## Reporting problems

Send:

1. The section and step, what you expected and what happened (a screenshot helps).
2. For uploads: the log in `%APPDATA%\SAM Ad Hoc Query Builder\upload_logs` (and `last_check.txt` in the export folder).
3. For the build: the Build GUI log (select all → copy).
4. For SAM data questions: the *SAM setup check* report (Save report...) – it holds codes and counts, no student names.

**Never send** real student CSV files, passwords or the settings file.
