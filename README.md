# SAM Ad Hoc Query Builder

A Windows desktop app that helps staff build SQL for SAM's **Ad Hoc Query** module (and CAC Agent data pulls) without writing SQL by hand. It follows the same steps as SAM's Report Builder:

1. **Tables & Columns** – search 1,006 SAMS tables by table *or* column name; double-click columns to add them.
2. **Link Tables** – *Suggest links* finds the normal SAM path (e.g. Student → Schedule Roster → Course/Section → Course) and adds in-between tables automatically. Inner / Left / Right / Full Outer links.
3. **Format Columns** – rename headings; remove leading zeros, change case, Left N, Replace, dates, age, Yes/No; build **custom columns** (e.g. first initial + last name + `@district.k12.ms.us`).
4. **Filters** – groups of conditions combined with AND / OR (equals, contains, starts with, between, one of, blank, last N days, ...).
5. **Sort & Options** – order by, distinct rows, row limit, name and description.
6. **Review & Copy SQL** – validation (unlinked tables, missing values, sensitive columns), Copy SQL, save `.sql`, plus step-by-step instructions for SAM and the CAC Agent.

**Sample results preview** – a tab under every step runs the query against made-up data (in-memory SQLite, generated for just the tables in the query, with joins and lookup codes lined up) so users see their columns, formats, sort and filters as they build. Real SAM data is never used.

**Export to a platform** – ready-made query packages that produce the exact CSV files each platform expects, with IDs that match across files:

| Platform | Files | Works with |
|---|---|---|
| Clever | schools, students, teachers, sections, enrollments | Clever + apps rostered through it (i-Ready, IXL, Renaissance, Khan, Amplify, Lexia...) |
| OneRoster 1.1 CSV | orgs, academicSessions, courses, classes, users, enrollments, demographics + manifest.csv | ClassLink, Schoology, Canvas, most OneRoster apps |
| Microsoft School Data Sync v2.1 | orgs, users, roles, academicSessions, courses, classes, enrollments | Microsoft 365 / Teams for Education |
| Google Workspace | student and staff bulk-user CSVs | Google Admin console |
| Canvas SIS import | users, terms, courses, enrollments | Canvas LMS |
| NWEA MAP Growth | combined roster file | MAP Growth |
| ParentSquare | schools, students, parents, staff, sections, roster | ParentSquare / StudentSquare |
| SchoolMessenger | contacts (2 guardians' phones/emails), staff | SchoolMessenger, other mass-notification tools |
| Follett Destiny | student and staff patrons | Destiny Patron Import Converter |
| Food service | students (PIN, eligibility, guardian, address), staff | LINQ/TITAN, PrimeroEdge, Heartland, SchoolCafe... |
| Transportation | students with address, lat/long, AM/PM method, bus zone, guardian | Transfinder, Edulog, Versatrans... |
| Raptor | students, guardians, staff | Raptor Visitor Management / Raptor Alert |
| Incident IQ | users (students + staff), locations | Incident IQ help desk / assets |
| School photos (PSPA) | photo roster (students + staff) | Lifetouch, Jostens, Strawbridge... |
| Xello | School, Student, Parent, Educator, EducatorStudent, StudentCourses, CourseCodes | Xello college & career |
| Naviance | student, parent, teacher, student_course | PowerSchool Naviance |
| SchooLinks | CourseMaster, StudentCourses, Caseload | SchooLinks |
| MTSS / early warning | students (program flags), attendance, discipline, grades | Panorama, Branching Minds... |
| Frontline Absence | employees, schools | Frontline Absence & Time (Aesop) |
| DragonFly | grades 7-12 for eligibility | DragonFly MAX |
| ACT state testing | student data upload (grades 10-12) | ACT PAN (MAAP pre-ID comes from MSIS/DRC) |
| Apple School Manager | locations, students, staff, courses, classes, rosters (zipped) | ASM, Jamf, Mosyle, Kandji |
| SchoolStatus | users, classes, enrollments, guardians | SchoolStatus Connect / Attend (MS SB 2103) |
| Active Directory | student + staff accounts + Import-ADUsers.ps1 (preview first, never deletes) | on-prem AD |
| Microsoft Entra ID | bulk-create template (students, staff) | Microsoft 365 cloud accounts |
| PBIS Rewards | students, staff, family members | PBIS Rewards (Navigate360) |
| Behavior apps | students, staff, class roster, parents | SchoolMint Hero, LiveSchool... |
| Ellevation | 64-column students file, schedule courses | Ellevation EL platform |
| School payments | students with homeroom, meal PIN, guardian email | MySchoolBucks, SchoolCash Online, PaySchools... |
| Bus apps | riders with AM/PM bus, route, stop, guardian | Here Comes the Bus, Zonar, Edulog Parent Portal |
| Web filter parent reports | student email + parent email | Securly, Lightspeed, GoGuardian |
| Emergency & reunification | staff with mobile phone, students with pick-up permissions | Centegix, CrisisGo, Rave |
| Athletics registration | students 6-12 with guardian and last physical | Rank One, FinalForms |
| Hall pass & ID kiosks | students, staff, schedules by period | 5-Star Students, SmartPass, Minga |
| Credit recovery / online courses | students, teachers, enrollments (course keyword) | Edmentum, Imagine Edgenuity, Apex |
| Scoir / MajorClarity | students 8-12, parents, staff | Scoir, MajorClarity, Kuder |
| Adobe Admin Console | students, staff | Adobe Express / Creative Cloud |
| Zoom | staff users | Zoom |
| TalkingPoints | classes, students (one row per contact, with language), staff, admins - per school | TalkingPoints |
| Remind (CSV 2.0) | schools, classes, enrollments, users (students + parents + staff), school_enrollments | Remind Hub |
| Renaissance | student/class/teacher roster, demographics | Star, Accelerated Reader, myON |
| Assessment platforms | demographics (reporting groups), class roster | i-Ready, Amplify mCLASS, Istation... |
| College Board | SSOR registration (12 columns, one test per file) | PSAT / SAT School Day |
| Special education case management | students, schedules, staff | Frontline IEP, PCG EasyIEP, SpedTrack... |
| Health office | students, immunizations, conditions | SNAP Health Center, Magnus Health... |
| Alexandria | patrons (students + staff) | COMPanion Alexandria |
| ID cards | students + staff with barcode and photo file name | ID Works, CardExchange, photographers |
| Substitute systems | employees, schools | Red Rover, ESS / Kelly, Swing |
| 1:1 devices | students with homeroom, guardian, asset tag/serial columns | device checkout / asset systems |
| Dual enrollment | students in dual-credit courses with address and guardian | community colleges |
| CTE certification testing | students in your CTE course codes | YouScience / Precision Exams, NOCTI, Certiport |
| Account shutoff | students who left / staff terminated in the last N days, Google suspend file, Disable-ADUsers.ps1 | Google, AD, Entra, Apple, any app |
| Data cleanup reports (tool) | 12 reports: missing contacts/phones/emails/addresses/state IDs/homerooms, duplicate IDs, unscheduled students, sections without teachers, staff without school/number | fix data in SAM |
| Find your SAM codes | enrollment, grade, gender, race, roster, **owner type**, phone type, relationship, attendance codes, **school list** | set up District Settings and SAM Codes & Schools |

Packages marked *confirm with vendor* follow the vendor's published (or SIS-partner) column names but the vendor maps columns at upload – send them a sample first.

*Save package* writes one `.sql` per file, any static files (OneRoster `manifest.csv`) and a `SETUP - read me.txt` with the CAC Agent job names and file names. **File > District Settings** holds email domains, username patterns (first.last, flast, flast+last 4 of ID...), Google OUs, school year and the enrolled-status code. Files such as users.csv that contain students *and* teachers use **combined parts (UNION ALL)** – pick the part to edit from *Editing part* in the builder. Packages live in `data/exports.json` (generated by `tools/make_exports.py`) and update through `latest.json` like the table catalog.

**Owner type codes** – SAM keeps addresses, phones and emails for students, contacts and employees in shared tables (AddressRelationship, PhoneRelationship, EmailAddress) keyed by OwnerType. Enter your district's codes once in *File > District Settings* (look them up with *Find your SAM codes > Owner type codes*); packages that need them won't open until they're set. Links can now carry **extra ON conditions** (Step 2 > Extra conditions) so these rows are matched without dropping students who have no phone/email.

**Query Assistant** (*Describe a query*, Ctrl+D) – type what you need in plain English, e.g. *"all 9th - 12th grade students with their homeroom, first name, last name, studentID and email"*. The built-in helper works offline and:
* uses the columns you list, **in your order** (adds name/ID columns only when you didn't ask for any);
* understands owners – *parent phone*, *homeroom teacher email*, *counselor*, *teacher*, *school*;
* reads grade ranges and lists (9th - 12th, K-2, grades 3 through 5, juniors and seniors, pre-k), school levels and names, boys/girls, enrolled/withdrawn, attendance (absent/tardy, today, last N days, this school year, date ranges), birth years, GPA comparisons, 504/SPED/gifted/Title I/foster/bus riders, missing data ("without an email"), course names ("taking Algebra I"), teacher and homeroom names ("in Mrs. Smith's homeroom"), last-name filters;
* builds **counts and averages** ("how many students in each grade at each school", "average GPA by grade", "number of absences per student"), top N, distinct, and sort order;
* fixes typos (emial → email) without touching names, and fuzzy-matches anything else to real SAMS column names;
* keeps a conversation – **Refine** with "also add birth date", "remove email", "only 10th grade", "sort by homeroom";
* shows a one-sentence summary, what it understood, what to double-check and sample results.

Its vocabulary is in `data/assistant_vocab.json` and ships with data updates, so new phrases can be added without a new app version. Optional **AI helper**: add an Anthropic API key in *File > Settings* to have Claude build the query instead (only the description, table/column names and District Settings codes are sent).

**SAM Codes & Schools** (*File > SAM Codes & Schools*) – type, paste from Excel or import (from the *Find your SAM codes* CSVs) your district's **schools with their SchoolIDs** and your real code lists (grades, enrollment, gender, race, owner types, relationships, phone types, roster status, attendance). Then:
* Step 4 has one-click **Schools...**, **Grades...** and **Enrolled only** quick filters, and every filter on a coded column gets a **Choose...** checklist;
* the Query Assistant understands your school names ("students at West Hancock Elementary") and filters on the SchoolID;
* each export package has a **Schools:** button to limit every file in the package to some schools (e.g. one Raptor or photo file per building);
* District Settings fills in owner-type and enrolled codes for you.

**Export file checker** – *Check exported files...* reads the CSVs SAM/the CAC Agent wrote and checks them against the vendor rules: missing files, header names and order, required values, duplicate IDs, date/email/phone/grade formats and cross-file IDs (e.g. every section's teacher exists in teachers.csv). Save the report or fix and re-check.

**Package & Upload** (*File > Package & Upload*) – upload profiles per vendor: local folder, SFTP host/port/user/password (encrypted with Windows DPAPI), remote folder, optional zip (OneRoster `manifest.csv` added automatically), check first / don't upload on errors, dated archive and log. *Schedule in Windows* creates a daily Task Scheduler job that runs `"SAM Ad Hoc Query Builder.exe" --upload "<profile>"` with no window. Logs: `%APPDATA%\SAM Ad Hoc Query Builder\upload_logs`.

**Import existing SQL** (*Ctrl+I*, start page) – paste or open a query you already use in SAM; it is turned back into builder steps (tables, links and extra ON conditions, columns and formats, aggregates, filters, sort, UNION ALL parts). Anything the builder can't represent stays as an exact SQL expression or the whole query is kept as hand-edited SQL – the *Check* button lists what happened.

**Upload safety net** – before uploading, every profile counts the rows in each file and compares them with the last good upload. An empty file, or a file with more than N% fewer rows (10% by default), holds the upload so a failed CAC Agent job can't make a vendor deactivate students. *Upload anyway once* overrides it for one run; the rollover checklist resets the baselines each summer.

**Alerts and status board** – *Tools > Upload alerts* emails (SMTP: Microsoft 365, Gmail relay or an internal relay) and/or posts to a Teams Workflows, Google Chat or Slack webhook when an upload fails or is held (or after every upload). The start page shows every upload profile's last run, result, row count and last good upload; *History* in Package & Upload lists recent runs.

**More ways to deliver** – SFTP with a password or an SSH key (Ed25519/RSA/ECDSA, passphrase encrypted), FTPS, or copy to a folder (network share, or a Google Drive / OneDrive synced folder).

**District versions of package files** – open any export file, change it, and use *File > Save as district version*. Your version is used for opening, Save package and the CAC Agent walkthrough, survives app and data updates, and is flagged if the standard file changes later. *Reset to standard* removes it.

**District tools** (start page and *Tools* menu):
* **CAC Agent setup walkthrough** – each file of a package with Copy buttons for the Query Title, the SQL, the exact File Name and the folder, plus a saved checklist of what's done.
* **Data cleanup reports** – the cleanup query pack above.
* **Vendor privacy register** – mark vendors in use, record agreement status, signed and expiry dates and contacts; data shared is filled from the packages; expiring agreements turn orange/red; saves a printable HTML report.
* **Year-end rollover checklist** – 12 steps (school year, live schedules, codes and schools, seniors, safety-net baselines, summer uploads, checker, cleanup, agreements, accounts, archives) with buttons and automatic checks, saved per school year.

**Account shutoff** – a daily list of students who are no longer enrolled and had an enrollment change in the last N days (with their last registration code, date, withdrawal reason and school) and staff terminated in the last N days, plus a Google bulk-update file that suspends them and `Disable-ADUsers.ps1` (preview by default, disables, never deletes). Review it before acting.

**What changed?** – every successful upload keeps a copy in `archive\_last_good_upload`; *What changed?* in Package & Upload (or *Tools > Compare two export files*) lists rows added, removed and changed (field by field), with a CSV report - the first thing to check when the safety net holds an upload or a vendor asks why a student disappeared.

**PGP encryption** – add a vendor's public key to an upload profile and every file (or the zip) is encrypted before it is sent (GnuPG / Gpg4win when installed, otherwise the built-in PGPy).

**Back up / restore settings** – *File > Back up settings* saves District Settings, schools and codes, upload profiles, alerts, report jobs, package school limits, district package versions, the privacy register and (optionally) saved queries to one `.samqb-backup` file. Passwords are never included; restoring keeps passwords already on that PC for matching profiles.

**Report emails** – *Tools > Report emails* sends a CSV the CAC Agent writes (or, with the SAM connection on, a query run in SAM) to principals or clerks daily or weekly, with the first rows in the email and the file attached. Scheduled with Windows Task Scheduler (`--report "name"`); failures raise an alert.

**Results preview modes** – the builder's *Results preview* tab shows made-up sample data, **My CSV file...** (open what the CAC Agent wrote and see the real rows plus missing / extra / out-of-order columns) or **Run in SAM (read-only)** when the optional connection is on.

**Change log** – every change to settings, codes and schools, uploads, alerts, report jobs, the SAM connection, the privacy register and district package versions is recorded with the Windows user, PC and time (secrets show only as "changed"). *Tools > Change log* filters and exports it.

**Optional read-only SAM connection** (off by default) – *Tools > SAM database connection*. Uses a db_datareader SQL login or Windows sign-in, ApplicationIntent=ReadOnly and READ UNCOMMITTED, caps rows, and refuses anything that isn't a single SELECT (no INSERT/UPDATE/DELETE/EXEC/INTO/OPENROWSET...) before it leaves the PC. The test warns if the login can write. Needs the Microsoft ODBC Driver for SQL Server.

**Username and email patterns** – District Settings (and the setup wizard) offer 22 ready-made patterns with a live example (first.last, **first initial.last → j.smith**, flast, first_last, last.first, first + middle initial + last, + last 4 of ID, + 2-digit graduation year, s + ID...) or your own pattern with tokens: `{first} {last} {middle}`, initials `{f} {l} {m}`, first N letters `{first3} {last5}`, `{id}` / last N digits `{id4}`, graduation year `{grad} {grad2}`, plus any `. _ -` letters or digits. Separate *email name* patterns are optional for districts whose email differs from the username. Old settings (flast, first.last...) keep working.

**SAM setup check** (*Tools > SAM setup check*) – 7 small queries (codes and counts only, no student names) that you run in SAM once, or live through the optional connection. The analyzer confirms or corrects the owner type codes, enrolled code, live schedules (including last year's schedule still live), primary school / contact flags, roster withdrawals, homerooms and counselors, staff faculty flags, sections without teachers, withdrawal codes for account shutoff, student emails in SAM, grade codes and the values in yes/no flags - and applies suggested District Settings with one click. The last result shows in the health report.

**Shared package library** – packages built with the template builder can be published to every district: districts send a *.samqb-package*, you add it on the Build GUI's Data tab (*Shared package library*) and publish a data update (`data/shared_packages.json` in latest.json). Districts see them under **Shared packages** and can *Copy to My packages* to change one.

**Template builder learns** – when you change a suggested field, the vendor heading is remembered (`learned_fields.json`) and suggested next time; mappings in your own and shared packages teach it too.

**Light and dark mode** – *View > Theme*: Light, Dark or Match Windows (applies after a restart; saved for every district on the PC). The app draws its own colors in both themes, so text stays readable whatever Windows uses; status colors in messages, lists and reports are translated for dark backgrounds automatically, and a test checks every color meets WCAG AA contrast.

**Guides** – *Help > Quick start guide*, *CAC Agent setup guide* (install and register the agent, add queries and jobs, schedule the CAS Agent Listener, timing and troubleshooting - also opened from the CAC Agent walkthrough), *Windows test checklist* (all in `docs/`). Keep private notes in `private/` - it is never pushed or bundled.

**Vendor template builder** (*Export to a platform > New package from a vendor template*, or *Tools*) – open a vendor's template / sample CSV or paste its header row. The builder works out what one row is (students, guardians, staff, class enrollments, sections or schools), suggests the SAM field for every vendor column (about 80 fields: IDs, names, dates in either format, grades as codes or numbers, emails and usernames from your patterns, homeroom / counselor, address, primary guardian, guardian rows, program Y/N flags, classes, teachers, terms, schools) and shows a live sample preview. Fixed-text and blank columns are allowed. The saved package lands under **My packages** and gets the checker rules (required, unique key, formats), Save package, CAC Agent walkthrough, uploads, school limits, district versions and privacy check like the built-in ones. *Share: export package file* / *Import package file* move packages between districts (`.samqb-package`). Custom packages are kept in `%APPDATA%\SAM Ad Hoc Query Builder\custom_packages`, shared by every district on the PC.

**Several districts** – the *District* box on the toolbar switches between districts; *Manage districts* adds (optionally copying District Settings, codes or alert settings), renames or removes them. Each district has its own settings, schools and codes, uploads and schedules, alerts, report emails, privacy register, sign-off, SAM connection, change log, district package versions and saved queries; the table catalog, templates and packages are shared. Scheduled tasks for other districts run with `--district <id>` and include the district name.

**Setup wizard** – runs on first start (and from *Help > Setup wizard*): district name, email domains and username patterns, school year; save and import the SAM code queries and schools; tick the vendors you use (fills the privacy register); alerts; next steps (opens the CAC Agent walkthrough).

**Vendor sign-off** – *Vendor sign-off...* on each package records when a sample was sent and when the vendor approved it, with contact and the changes they asked for. Shown on the exports page and in the health report.

**Admin PIN** (*Tools > Admin PIN*) – locks Package & Upload, alerts, report emails, the SAM connection, District Settings, restore and managing districts behind a PIN (PBKDF2-hashed, asked once per 15 minutes, every unlock and wrong PIN in the change log). It prevents accidental changes on a shared PC; it is not protection against someone who can edit files in %APPDATA%.

**District health report** (*Tools > District health report*) – one page: each upload's last result, problems in the last 30 runs and current checker errors; data-cleanup counts (from the folder where the CAC Agent saves the cleanup reports); vendors in use with agreement status and sign-off; rollover progress; setting changes in the last 30 days. Save as HTML, email it, or schedule it monthly (`--health`).

**Privacy guardrails** – the Review step shows a privacy check that sorts output columns into *Restricted* (SSN, passwords – also a warning), *Protected program data* (special education, 504, meal status, discipline, health, homeless/migrant/foster, custody) and *Personal information* (birth date, address, phone, email, race, state ID), and notes when rows are selected using protected data. The exports page shows what each package shares and every `SETUP - read me.txt` has a *Data shared with this vendor* section to check against your data-privacy agreement.

**Assistant feedback** – *Looks right* / *This isn't right...* in the Query Assistant saves the request, what it built and what you expected to `%APPDATA%\SAM Ad Hoc Query Builder\assistant_feedback.jsonl`. *Help > Export assistant feedback...* saves a copy to send in; new phrases go into `data/assistant_vocab.json` and ship through `latest.json`.

Starter templates: Homeroom Roster, Student Schedule, Teacher Class List, Students by School, Student Contacts, Student Addresses, Daily Attendance (30 days), Staff by School, Transcript Courses & Grades. Queries are saved as `.samq` files in *Documents\SAM Ad Hoc Query Builder\Queries* and can be shared.

## Updates – one `latest.json`

On start-up the app reads
`https://raw.githubusercontent.com/Sbreland18/SAMQueryBuilder/main/latest.json`:

```json
{
  "version": "1.0.1",
  "notes": "What changed",
  "installer_url": "https://github.com/Sbreland18/SAMQueryBuilder/releases/download/v1.0.1/SAM_AdHoc_Query_Builder_Setup_1.0.1.exe",
  "installer_sha256": "…",
  "mandatory": false,
  "data": {
    "version": "2026.10.20.1",
    "notes": "New tables / templates",
    "files": {
      "catalog.json":   { "url": ".../main/data/catalog.json",   "sha256": "…" },
      "templates.json": { "url": ".../main/data/templates.json", "sha256": "…" }
    }
  }
}
```

* **App update** (`version` is higher): users click *Install*, the installer is downloaded, hash-checked, run silently and the app restarts.
* **Data update** (`data.version` is higher): new tables/templates download into `%APPDATA%\SAM Ad Hoc Query Builder\data` automatically – no reinstall.

The repository must be **public** so the app can read `latest.json` without signing in. An alternate URL can be set in *File > Settings*.

## Build PC setup (one time)

1. Install **Python 3.11+**, **Git for Windows** and **Inno Setup 6**. GitHub CLI (`gh`, only needed to publish) can be installed from the Build GUI: GitHub Setup → **Install GitHub CLI** (runs `winget install --id GitHub.cli -e`).
2. Double-click **Setup Dev Environment.bat** (installs PySide6, PyInstaller, pytest).
3. Double-click **Build GUI.bat** → *3. GitHub Setup* → *Sign in to GitHub* → *Connect this folder to the repo*.

## Code signing

Tick *Sign the EXE and the installer* in the Build GUI's Release tab, point it at `signtool.exe` (Windows SDK > Signing Tools; found automatically when installed) and choose the certificate: one in the Windows certificate store or on a USB token (SHA-1 thumbprint, or blank for the best one) or a `.pfx` file (its password is asked at build time and never saved or logged). The build signs the EXE after PyInstaller and the installer after Inno Setup, with an RFC 3161 timestamp (DigiCert by default), and verifies both signatures. An OV or EV code-signing certificate from a public CA (DigiCert, Sectigo, SSL.com...) is needed; EV certificates get SmartScreen reputation immediately, OV certificates build it up over the first downloads.

## Releasing with the Build GUI

**New app version** – tab *1. Build & Release App*: click *+ patch/minor/major*, type what's new, tick *Publish*, click **Build & Publish**. It runs tests → PyInstaller → Inno Setup → pushes code → creates GitHub release `vX.Y.Z` with the installer → writes and pushes `latest.json` (last, so the download always exists first). The installer lands in `dist\installer`.

**New tables or templates only** – tab *2. Tables & Templates*:
* Export a fresh *SAMS Database Object Browser – Tables* CSV, browse to it and click *Rebuild catalog* (new/removed tables are listed in the log).
* Add descriptions, friendly names or links in `data/catalog_overrides.json`.
* Build a query in the app, save it, then *Add from saved query* to make it a template.
* Click **Publish data update**.

## Project layout

```
main.py                     app entry point
sam_qb/query_model.py       query definition + T-SQL generator + validation
sam_qb/catalog.py           table catalog and link path-finding
sam_qb/catalog_builder.py   builds catalog.json from the Object Browser CSV + overrides
sam_qb/preview.py           made-up sample data + SQLite translation for the results preview
sam_qb/exports.py           platform export packages + package writer
sam_qb/district.py          district settings and username/email patterns
sam_qb/assistant.py         built-in plain-English Query Assistant
sam_qb/ai_helper.py         optional Claude-powered assistant
sam_qb/updater.py           latest.json update check / download / install
sam_qb/release.py           version bump + latest.json writer (used by the Build GUI)
sam_qb/ui/                  PySide6 user interface
data/                       catalog.json, templates.json, catalog_overrides.json, source CSV
installer/SAMQueryBuilder.iss  Inno Setup script (per-user install, .samq file association)
tools/build_gui.py          Build & Release GUI
tools/build_catalog.py, tools/make_templates.py   command-line helpers
tests/                      pytest unit tests
```

## Notes

* The SQL is SQL Server (T-SQL). Column names come from the SAMS Object Browser export; data types are not in that export, so filter values are quoted and SQL Server converts them.
* Code-type filters use the stored code (e.g. grade `09`), not the description. Add a lookup table such as `lookupADAGrade` to show descriptions.
* `AddressRelationship` / `PhoneRelationship` hold rows for students, contacts and employees – filter on `OwnerType`.
* SAM's field-level security still applies when the query runs in SAM.

## Round 8 additions

- **Explain this query** (Step 6 panel, Query menu, Tools > Explain a query for pasted SQL) - `sam_qb/explain.py`.
- **Duplicate-row warning** - `sam_qb/dupcheck.py` (links to a table's non-key column that aren't narrowed by a Primary / sequence / live-schedule condition; hidden ones and two multiplying branches are flagged; the preview counts repeated IDs).
- **Fill-in values** - `Condition.ask`; Step 4 *Ask* button; asked when copying / saving (`sam_qb/askvalues.py`).
- **Nightly schedule timeline** - `sam_qb/timeline.py`; CAC job times (`cac_times`) and the listener time in the CAC Agent walkthrough; also in the health report.
- **Data quality trends** - `sam_qb/dqtrend.py`, weekly `--dqsnapshot` task; health report shows change since last week.
- **Agreement reminders** - `register.send_reminders` at 60 / 30 / 0 days, checked once a day by scheduled uploads and the health report.
- **Team folder** - `paths.TEAM_KEYS` shared through `team_settings.json` plus Queries, package_overrides, custom_packages and learned fields; passwords and upload profiles stay local.
- **Community query library** - File > Share this query (GitHub issue / email / file) and Build GUI > Data > Add community query (category *Community queries*; `{{STAFF_EMAIL_DOMAIN}}` placeholders are filled per district).
- **Text size** (View menu), **Excel attachments** for report emails (`sam_qb/xlsx.py`, needs openpyxl), **automatic backups** (`--backup`, keeps the newest N).

## Round 9 additions

- **Beta update channel** - latest.json `beta` section (`release.make_latest(channel="beta")`, `release.promote_beta`); PCs choose Help > Update channel (`ui_prefs.json`); Build GUI *Release to* + *Promote beta to everyone* (GitHub pre-release).
- **Version history** - `sam_qb/history.py`; `.history` folders next to saved queries and district versions (newest 30), compare + restore.
- **Saved-query library** - favorites, tags and search (`sam_qb/library.py`, `_library.json` in the Queries folder).
- **Where is this field used?** - `sam_qb/whereused.py`.
- **Count rows in SAM** - `samdb.count` (Step 6, CAC walkthrough).
- **Data minimization** - `sam_qb/minimize.py`; optional sensitive columns are sent empty via a district version.
- **Agreement documents** - `register.attach_document` (`agreements` folder, shared through the team folder).
- **Compare with the vendor's data** - `sam_qb/reconcile.py` (CSV / XLSX, suggested match column, missing on either side, value differences).
