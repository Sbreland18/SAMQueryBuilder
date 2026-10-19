# SAM Ad Hoc Query Builder – quick start for district staff

SAM Ad Hoc Query Builder writes the SQL that SAM's **Ad Hoc Query** module and **CAC Agent** run, and sends the resulting files to the vendors your district uses. It does not change anything in SAM.

## 1. First start – the setup wizard (15 minutes)

1. **Your district** – district name, email domains and username patterns. Pick the pattern your district uses (for example *first initial.last* → `j.smith`), or type your own with tokens such as `{f}.{last}`. If emails differ from usernames, fill in the email name pattern too. If two people would get the same name, choose how duplicates are numbered (e.g. *Add 1, 2, 3* → `j.smith`, `j.smith1`), then use **District Settings → Copy staff check query** in SAM to compare with your real accounts.
2. **SAM codes and schools** – click *Copy the all-in-one query*, paste it into SAM (*Ad Hoc Query → Query → paste → Run Query*) and save the result as `sam_all_codes.csv`. Then *Import codes and schools → Import CSV files* and choose that file. If SAM shows an error, each list in *File → SAM Codes & Schools* has its own **Copy query** and **Import this list** buttons.
3. **Vendors** – tick the vendors you send files to.
4. **Alerts** – add your email server or a Teams webhook so you hear about failed uploads.

Then run **Tools → SAM setup check** once. It confirms your owner type codes, enrolled-student code and live schedules and can fix District Settings for you.

## 2. Build a query

- **Describe a query** (Ctrl+D): type what you need, e.g. *"seniors with their counselor and birth date"*, check the result, open it in the builder.
- Or **start from a template**, or **New blank query** and follow Steps 1–6.
- The **Results preview** under every step shows made-up sample data (or your own CSV file).
- **Step 6 → Copy SQL**, paste it into SAM's Ad Hoc Query and run it.
- **Schools...** on Step 4 limits a query to some schools. Click **Ask** next to a filter to be asked for its value (school, date, grade) every time you copy the SQL.
- Step 6 explains the query **in plain English** and warns about **duplicate rows** before you copy it. Inherited a query? **Tools → Explain a query** and paste it in.

## 3. Send files to a vendor

1. **Export to a platform** → pick the vendor (search the list).
2. **CAC Agent walkthrough** – copy each query, title and file name into SAM's CAC Agent. Every job saves to the same folder. First time on this computer? Follow **Help → CAC Agent setup guide** to install the CAC Agent and schedule the *CAS Agent Listener* in Windows.
3. After the first nightly run: **Check exported files** – fix any errors it lists (most come from SAM data; see *Data cleanup reports*).
4. **Upload setup** – SFTP host, user name and password from the vendor; *Test connection*; *Run now*; *Schedule in Windows* (at least an hour after the CAC Agent jobs).
5. **Vendor sign-off** – record when you sent a sample and when the vendor approved it.

Vendor not listed? **New package from a vendor template**: open the vendor's template, check the suggested SAM field for each column, save.

## 4. Every morning

- The **Nightly uploads** board on the start page shows each upload. Green = OK.
- **HELD** means the safety net stopped an upload because a file was empty or much smaller than last time, so the vendor wouldn't remove students. Open Package & Upload → **What changed?** If the change is real, use **Upload anyway once**; if not, fix the CAC job or SAM data and run again.
- **FAILED** – the log says why (password, network, vendor server). You also get an alert.
- **Tools → Nightly schedule timeline** checks that each upload runs after its CAC Agent jobs and the CAS Agent Listener (record the job time in the CAC Agent walkthrough).

## 5. Each month and each summer

- **Tools → District health report** – one page with uploads, data problems, vendor agreements and rollover progress (can be emailed monthly).
- **Tools → Vendor privacy register** – who gets which student data and when agreements expire; you're emailed 60 and 30 days before one ends.
- **Tools → Data quality trends** – are the Data cleanup counts going down? Schedule a weekly snapshot.
- **Tools → Year-end rollover checklist** – work through it each summer before the first nightly uploads.

## Good to know

- Passwords are encrypted for your Windows user. A settings backup (File → Back up settings) never includes them. **File → Automatic backups** saves one every week to a folder you choose.
- Working as a team? **File → Team folder** shares settings, codes, packages and saved queries through a network folder.
- Built a useful query? **File → Share this query with other districts.**
- Right-click a saved query on the start page to **star** it, **tag** it or see its **version history** (every save keeps the previous copy).
- **Tools → Where is this field used?** – who gets a SAM column (e.g. birth date) and in which files.
- **Data minimization** (exports page) – send optional sensitive columns empty. **Tools → Compare with the vendor's data** – find students missing at a vendor.
- **Tools → Admin PIN** locks uploads and settings on a shared PC.
- **Tools → Change log** shows who changed what.
- Several districts? Use the **District** box on the toolbar.
- **View → Theme** switches between Light, Dark and Match Windows; **View → Text size** makes text bigger.
- Help → How to use (F1) explains every screen.
- Something not working? **Help → Report a bug** – describe it, check the details, then open it on GitHub or send it by email. Never include student names or data.
