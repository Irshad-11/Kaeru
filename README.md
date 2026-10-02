<div align="center">

  <img src="https://raw.githubusercontent.com/Irshad-11/Documents/refs/heads/main/kaeru_home.png" alt="Kaeru Banner" width="100%" />

  <br />
  <br />

  <h1 style="font-size: 3rem; margin: 0;">Kaeru <sup>代える</sup></h1>

  <h4 style="font-size: 1rem; margin: 0;">⚠️ Admin Usage Only</h4>

  <p align="center">
    <a href="https://irshad11.pythonanywhere.com">irshad11.pythonanywhere.com</a>
  </p>

  <p>
    <img src="https://img.shields.io/badge/Version-8.4.3-10b981?style=for-the-badge" alt="Version" />
    <img src="https://img.shields.io/badge/PWA-Installable-5A0FC8?style=for-the-badge&logo=pwa&logoColor=white" alt="PWA" />
    <img src="https://img.shields.io/badge/Tailwind-Frontend-38B2AC?style=for-the-badge&logo=tailwindcss&logoColor=white" alt="Tailwind" />
    <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
    <img src="https://img.shields.io/badge/Flask-Backend-000000?style=for-the-badge&logo=flask&logoColor=white" alt="Flask" />
    <img src="https://img.shields.io/badge/SQLite-Database-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite" />
  </p>

</div>

> **This application is designed as a single-user tool.**

Kaeru is **not** a multi-user SaaS application. It is a personal workspace built for a single administrator: tasks, a planner, notes, a timeline and quick links in one place.

* **Security:** Access is protected by one global access key (stored in `password.txt`, created on first run).
* **Data:** Everything lives in a single SQLite file (`kaeru.db`).
* **State:** Changes made by the admin are reflected globally, on every device.

---

## 🖼️ Screenshots

<div align="center">

| Splash | Login |
| :---: | :---: |
| <img src="https://raw.githubusercontent.com/Irshad-11/Documents/refs/heads/main/splash.jpeg" alt="Splash screen" width="100%" /> | <img src="https://raw.githubusercontent.com/Irshad-11/Documents/refs/heads/main/login.jpeg" alt="Login screen" width="100%" /> |

<br />

**Tasks** · dark & light

| Dark | Light |
| :---: | :---: |
| <img src="https://raw.githubusercontent.com/Irshad-11/Documents/refs/heads/main/task-tab-dark.jpeg" alt="Tasks tab (dark)" width="100%" /> | <img src="https://raw.githubusercontent.com/Irshad-11/Documents/refs/heads/main/task-tab-light.jpeg" alt="Tasks tab (light)" width="100%" /> |

<br />

**Planner**

<img src="https://raw.githubusercontent.com/Irshad-11/Documents/refs/heads/main/planner-tab-dark.jpeg" alt="Planner tab (dark)" width="100%" />

<br />
<br />

**Notes**

<img src="https://raw.githubusercontent.com/Irshad-11/Documents/refs/heads/main/notes-tab-dark.jpeg" alt="Notes tab (dark)" width="100%" />

</div>

---

## ✨ Features

### Workspace
* **Tasks:** Timeline view (Overdue / Today / Tomorrow / Upcoming) with projects and subtasks, drag-to-reorder, inline editing and 30-day history.
* **Planner:** Monthly / weekly calendar with dot or heat-map display, a day-detail panel and a mobile bottom sheet.
* **Notes:** Rich-text notes with pinning and drag-to-reorder.
* **Timeless:** A tagged, searchable timeline of nodes with sources (virtualised list for speed).
* **Links:** Quick-link cards with pinning, click counters, drag-to-reorder and import/export.
* **Backup:** Full export / import of all data, protected by the access key.
* **Football sync (optional):** Pulls upcoming UCL / La Liga / World Cup / friendly matches into Tasks.

### Recurring tasks
* **Minimised by default:** Recurring tasks show up only under **Today** and **Tomorrow**. Future repeats are hidden and can be revealed with the `↻` toggle in the Tasks header.
* **Per-date completion:** Ticking a recurring task completes only that day's occurrence, not the whole series.
* **Recurring Task Manager:** A dedicated inner tab inside **Planner** (*Calendar | Recurring*). Search, filter (All / Active / Paused / Ended), pause, resume, edit, stop after today, delete a series, plus bulk actions (*Pause all*, *Resume all*, *Remove ended*).
* **Fixed:** Recurring tasks now correctly appear in the Tasks tab, and are never counted as overdue.

### Sessions & security
* **One session per device:** Devices are recognised with a long-lived cookie, so logging in and out repeatedly on the same device updates one entry instead of adding a new one.
* **Real server-side sessions:** Every login gets a rotating token that is validated on each request. *End Session* really logs that device out, and changing the access key logs out everyone.
* **Device info:** *Security & Sessions* shows OS, browser, IP, last login, last activity and login count per device.
* **Hardening:** Constant-time key comparison, login rate-limiting (5 failures → 60 s lock), HttpOnly / SameSite cookies, `401` JSON for API calls, and no key stored in `localStorage`.
* **Remember me:** Handled on the server (1 day).

### PWA
* **Installable** on desktop and mobile (manifest, icons, service worker).
* **Splash screen** on first launch, with an offline fallback page.
* **Fast:** Network-first pages, cached CDN assets, API responses never cached.

### Live status line & Dot Pet
* **Status line:** The thin line under the navbar shows what the backend is doing. Calm green/blue when idle, yellow while saving or syncing, red when the backend is unreachable.
* **Dot Pet:** The sync dot is a small digital pet. It breathes, blinks, looks around, winks, yawns, hops, bounces, spins and falls asleep when idle. Its eyes follow your cursor and grow when you hover or click. It reacts to saving (busy), success (happy hop) and errors (shaken). Poke it to re-check the connection, poke it too much and it gets dizzy.
* **Theme-aware:** Separate, brighter pet colours for the light theme.

### Login screen
* **Desktop:** Large mascot stage on the left, login on the right. **Mobile:** a compact stacked layout.
* **Mascot story:** The pet "thinks" in a thought bubble, one thought after another, each with its own reaction, then morphs into the redrawn classic **torii gate** (with 代える) and back again.
* **Version reveal:** The pet reveals the current version in the footer badge.

---

## 🛠️ Tech Stack

* **Backend:** Python (Flask, Flask-CORS)
* **Database:** SQLite3 (WAL mode)
* **Frontend:** HTML5, vanilla JavaScript (Fetch API), Tailwind CSS (CDN), Font Awesome, GSAP
* **Deployment Target:** PythonAnywhere

## 📂 Project Structure

```bash
Kaeru/
├── app.py
├── requirements.txt
├── README.md
└── templates/
    └── index.html
```

`kaeru.db` and `password.txt` are created automatically on first run.

## 🚀 How to Run Locally

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/Irshad-11/Kaeru.git
    cd Kaeru
    ```

2.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Start the Server**

    The `app.run(...)` lines at the bottom of `app.py` are commented out (PythonAnywhere runs the app itself). Either uncomment them, or run:
    ```bash
    flask --app app run
    ```
    *You should see: `Running on http://127.0.0.1:5000`*

4.  **Access the App**
    Open your browser and visit: `http://127.0.0.1:5000`

5.  **Log In**
    * Default access key: `kaeru2026` (change it from **Security & Sessions → Change Password**)

### Optional environment variables

| Variable | Purpose |
| :--- | :--- |
| `KAERU_SECRET` | Flask session signing secret. Set your own value in production. |

> After updating from an older version, every device has to log in once again.

---

<h1> Developer Info: </h1>
<div align="center">
  <p>
    <a href="https://github.com/Irshad-11">
      <img src="https://img.shields.io/badge/GitHub-Irshad--11-181717?style=flat&logo=github&logoColor=white" alt="GitHub Profile" />
    </a>
  </p>

  <p style="color: #64748b; font-size: 0.9rem;">
    Built with 💖 by <strong>Irshad Hossain</strong>
  </p>
</div>