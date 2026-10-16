# Setting up the SAM CAC Agent

The **CAC Agent** (Central Access's *CAS Agent*) runs SAM queries on a schedule and saves the results as files on a computer in your district. SAM Ad Hoc Query Builder writes those queries for you; this guide covers the SAM side, from installing the agent to the files appearing every night.

**What you need:** a district computer that stays on overnight (most districts use a server), Windows administrator rights on it, and a SAM login that can open *Administration → CAC Agent*.

**How it fits together**

1. **SAM** runs each *job* (a saved query) at the time you set and holds the results.
2. The **CAS Agent Listener** on your computer, started by Windows Task Scheduler, collects those results and saves them as files in a folder.
3. **SAM Ad Hoc Query Builder** checks the files and uploads them to the vendor (Package & Upload).

> Only **one CAC Agent can be installed per computer**, but one agent can run as many jobs as you need, for example every Clever, Google and food-service file.

---

## Part 1 – Install the CAC Agent (once per computer)

1. On the computer that will receive the files, **log into SAM**.
2. Click **Utilities → Downloads**, then **Download CAS Agent**.
3. When asked to *Run* or *Save*, choose **Run**. Accept the publisher warning with **Run**.
4. The *CAS Agent Setup Wizard* opens. Click **Next**.
5. On *Select Installation Folder*, make sure **Everyone** is selected, then **Next**, and **Next** again on *Confirm Installation*.
6. After the install it asks for:
   - **URL** – your district's SAM address, for example `https://ms0000.activeschool.net`
   - **User Name / Password** – your SAM login
   - **Agent Name** – a name describing what this computer pulls, for example `Vendor Exports`
7. Click **Register**. You should see *registration was successful*. Click **OK**, then **Close**.

The program is installed in `C:\Program Files\Central Access Corp\CAS Agent`.

## Part 2 – Create a folder for each vendor

On the same computer, create one folder per vendor package, for example:

```
C:\SAM Exports\Clever
C:\SAM Exports\Google
C:\SAM Exports\SchoolStatus
```

Every file for one vendor goes in **the same folder**. The app's file checker, Package & Upload and *What changed?* all read that folder.

## Part 3 – Add the queries in SAM

Do this for every file in the package. The app's **CAC Agent walkthrough** shows each value with a **Copy** button: *Export to a platform → pick the vendor → CAC Agent walkthrough*.

1. In SAM go to **Administration → CAC Agent → Query Maintenance**.
2. Click **Add New**.
3. **Title** – paste the *Query Title* from the walkthrough (for example `Clever - students.csv`).
4. **Query** – paste the SQL from the walkthrough (right-click → Paste).
5. Click **Save**.
6. Back in the walkthrough, click **Mark done & next** and repeat for the next file.

> You can also save a query in SAM's **Ad Hoc Query → Query Maintenance** first, test it with *Run Query*, then copy its code into CAC Agent Query Maintenance. The SQL is the same either way.

## Part 4 – Add a job for each query

1. In SAM go to **Administration → CAC Agent → Agent Maintenance**.
2. Click **Add Job**.
3. **Query** – choose the query you just added (same title as in the walkthrough).
4. **Agent Name** – a name for the job; using the query title keeps it easy to find.
5. **File Path** – the vendor's folder from Part 2, exactly as it is on the agent computer, for example `C:\SAM Exports\Clever`.
6. **File Name** – the **exact** file name from the walkthrough, for example `students.csv`. Vendors reject files with different names.
7. **Time** – when SAM should run it, for example `1:00 AM`. Give every job in a package the same time.
8. Click **Save Job**. Repeat **Add Job** for every query in the package.

## Part 5 – Schedule the CAS Agent Listener in Windows (once per computer)

The listener collects the results from SAM and writes the files. It needs a Windows scheduled task.

1. Open **Task Scheduler** (Start → type *Task Scheduler*, or *Administrative Tools → Task Scheduler*).
2. Click **Create Basic Task...** and name it, for example `SAM CAC Agent Listener`.
3. **Trigger:** *Daily*. **Start time:** at least **1 hour after** the job time in SAM (jobs at 1:00 AM → listener at 2:00 AM or later).
4. **Action:** *Start a program* → **Browse** → `C:\Program Files\Central Access Corp\CAS Agent\` → **CAS Agent Listener** → **Open** → **Finish**.
5. Open the new task's **Properties**:
   - select **Run whether user is logged on or not**
   - tick **Run with highest privileges**
   - click **OK** and enter the Windows user name and password when asked.

## Part 6 – Schedule the uploads in SAM Ad Hoc Query Builder

Allow at least another hour after the listener:

| Time | What runs | Where it's set |
|---|---|---|
| 1:00 AM | CAC Agent jobs in SAM | SAM → Administration → CAC Agent → Agent Maintenance |
| 2:00 AM | CAS Agent Listener writes the files | Windows Task Scheduler |
| 3:00 AM or later | Check and upload to the vendor | SAM Ad Hoc Query Builder → Package & Upload → *Schedule in Windows* |

In Task Scheduler, set the upload task to **Run whether user is logged on or not** as well, using the same Windows user that saved the upload passwords.

## Part 7 – Test before you trust it

1. In Task Scheduler, right-click the listener task → **Run** (after the SAM jobs have run), or wait for the first night.
2. Check the vendor folder: every file is there, with today's date and the exact names.
3. In the app: **Check exported files** → fix anything it reports. Most problems come from SAM data; the *Data cleanup reports* show which records need fixing.
4. Then **Package & Upload → Run now** and confirm with the vendor.

---

## Troubleshooting

| What you see | Usually means | Fix |
|---|---|---|
| No files in the folder | The listener didn't run, or ran before the jobs finished | Task Scheduler → task history; start the listener later than the jobs |
| Old files (yesterday's date) | The jobs didn't run in SAM, or the listener ran too early | Check the job times in Agent Maintenance; keep at least 1 hour between |
| Files appear only when someone is signed in | The task isn't set to run when signed out | Task properties → *Run whether user is logged on or not* |
| A file has a slightly different name | File Name typed differently in Add Job | Copy the name from the walkthrough; names are exact |
| A file has only the header row | The query found no rows (often a district setting, such as the enrolled code) | Run the query in Ad Hoc Query to see why; check District Settings and **Tools → SAM setup check** |
| The upload says *HELD* | The safety net found an empty or much smaller file | Package & Upload → **What changed?** |
| Registration failed | Wrong SAM URL, user name or password, or no CAC Agent permission | Use the full SAM address (`https://...activeschool.net`); ask your SAM administrator |
| Need to move the agent to another computer | Only one agent per computer | Install and register on the new computer, then change each job's File Path |

**When a query changes** (for example after you save a *district version* in the app or the app updates a package), open the walkthrough again, copy the new SQL, and replace it in **CAC Agent → Query Maintenance**. The job, folder and file name stay the same.
