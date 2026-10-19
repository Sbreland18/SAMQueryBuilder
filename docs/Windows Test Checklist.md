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
- [ ] Data tab → **Rebuild platform export packages** runs and reports 65 platforms.

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
- [ ] Help → **Report a bug**: *Open on GitHub* opens a pre-filled issue; *Send by email* reaches the support address set in the Build GUI (or opens your mail program). The diagnostics show no student data or passwords.
- [ ] Help menu has no *Pilot plan*, and the GitHub repo has no `docs/Pilot Plan.md` after publishing.
- [ ] Publish a small **data update** (Data tab → Publish data update). On the district PC, Check for updates offers *New tables and templates* and installs them without reinstalling.
- [ ] Publishing when GitHub has changes this folder doesn't (e.g. a file edited on github.com): the log shows *Sync with GitHub → Merged …* and the push succeeds.
- [ ] Publish a new **app version**: the district PC is offered it, the installer downloads, the SHA-256 check passes and the app restarts on the new version.

Notes: ______________________________________________

## E. First run and district setup (district PC)

- [ ] The **Setup wizard** opens on first start.
- [ ] Staff username pattern: choose **first initial.last** – the example shows `j.smith`. Try a custom pattern such as `{f}{m}.{last}` and see the example update.
- [ ] Duplicate staff usernames → *Add 1, 2, 3*. District Settings → **Copy staff check query** → run in SAM: every shared name is listed with the number each person gets; compare with AD / Google accounts (the oldest SAM record keeps the plain name).
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
- [ ] Click **Ask** on a filter, give it a question; Step 6 → Copy SQL asks for the value and the pasted SQL uses it (and remembers it next time).
- [ ] Step 6 shows **In plain English**; a query that links contacts without showing them gets a **Duplicate rows** note. Tools → Explain a query explains a pasted SQL and can open it in the builder.

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
- [ ] CAC Agent walkthrough → set the **Job time** and **Listener runs at**; Tools → **Nightly schedule timeline** shows them with the upload and flags an upload set too early.
- [ ] Optional: FTPS profile, copy-to-folder profile, SSH key login, PGP-encrypted upload (vendor can decrypt).

Notes: ______________________________________________

## I. Alerts, reports and the health report

- [ ] Tools → Upload alerts → **Send a test alert** arrives by email (Microsoft 365 / Gmail relay) and/or Teams.
- [ ] A held or failed scheduled upload sends an alert.
- [ ] Tools → Report emails → a cleanup report CSV → **Send now** arrives with the table and the attachment; **Schedule** creates the task.
- [ ] Tools → District health report → Email now arrives; **Schedule monthly** creates the task. It shows *Change since last week* and the *Nightly schedule* checks.
- [ ] Report emails → **Attach as Excel** → the .xlsx opens with a frozen, filtered header and IDs keep leading zeros.
- [ ] Tools → **Data quality trends** → Take a snapshot; Schedule in Windows creates the weekly task.
- [ ] Vendor privacy register → an agreement ending in under 60 days → **Send due reminders now** emails once (and not again for the same mark).

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
- [ ] File → **Automatic backups** → Back up now writes a dated file; Save and schedule creates the weekly task; only the newest N are kept.
- [ ] File → **Team folder** on two PCs (first PC ticks *copy my settings*): a District Settings change on one shows on the other after reopening; upload passwords stay separate; unplugging the share doesn't stop the app.
- [ ] View → **Text size** → Large: menus, steps and dialogs get bigger and stay readable.

Notes: ______________________________________________

## M. Vendor template builder and shared library

- [ ] New package from a vendor template → open a real vendor template → most columns turn green; fix the rest; preview; save. It appears under **My packages** and works with Save package / CAC walkthrough / Check exported files.
- [ ] Change a suggested field and save; start a new package with the same header – your choice is suggested (learned).
- [ ] Share: export package file → on the build PC, Data tab → Shared package library → Add → Publish data update → on another PC it appears under **Shared packages**; *Copy to My packages* works.

Notes: ______________________________________________

## M3. Versions, library, privacy and accuracy

- [ ] Build GUI → Release to **Beta testers only** → publish: a PC on Help → Update channel → **Beta** is offered it, a stable PC isn't. **Promote beta to everyone** → the stable PC is offered it; the GitHub release is no longer a pre-release.
- [ ] Save a query, change it, save again → File → **Version history** shows the change and **Restore** brings the old one back. Same for a district version (exports page → History).
- [ ] Start page: star a query (it moves to the top), tag two queries, filter by tag, search by a column name.
- [ ] Tools → **Where is this field used?** → Student / DOB lists the packages and vendors in use (in red); double-click opens the package.
- [ ] With the SAM connection on: Step 6 **Count rows in SAM** and the CAC walkthrough's button show rows and time.
- [ ] Exports page → **Data minimization** → blank an optional column → the file still has the column, empty; Reset to standard puts it back.
- [ ] Privacy register → Documents → **Attach** a PDF → Open works; the printable report lists it.
- [ ] Tools → **Compare with the vendor's data** with a real vendor export: the suggested match column is right and the missing lists make sense.

## M2. Community queries

- [ ] File → **Share this query with other districts** → Open on GitHub creates a pre-filled *community-query* issue; your email domain shows as `{{STAFF_EMAIL_DOMAIN}}`.
- [ ] Build GUI → Data → **Add community query** → paste the issue → Review shows the explanation and SQL → Add; Publish data update; another PC sees it under *Community queries* with its own email domain filled in.

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
