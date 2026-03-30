<div align="center">

  <img src="https://raw.githubusercontent.com/Irshad-11/Documents/refs/heads/main/kaeru.png" alt="Kaeru Banner" width="100%" />

  <br />
  <br />

  <h1 style="font-size: 3rem; margin: 0;">Kaeru</h1>

  <h4 style="font-size: 1rem; margin: 0;">⚠️Admin Usage Only (ALSO IRSAHD-ME)</h4>

  <p align="center">
  <a href="irshad11.pythonanywhere.com">Kaeru</a>
</p>

  <p>
    <img src="https://img.shields.io/badge/Tailwind-Frontend-38B2AC?style=for-the-badge&logo=tailwindcss&logoColor=white" alt="Tailwind" />
    <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
    <img src="https://img.shields.io/badge/Flask-Backend-000000?style=for-the-badge&logo=flask&logoColor=white" alt="Flask" />
    <img src="https://img.shields.io/badge/SQLite-Database-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite" />
  </p>

</div>



> **This application is designed as a single-user tool.**

It is **not** a multi-user SaaS application. It is built for a single administrator to manage a project timeline.
* **Security:** Access is protected by a global password (defined in `app.py`).
* **Data:** All data is stored in a single SQLite file (`kaeru.db`).
* **State:** Changes made by the admin are reflected globally.

---

## ✨ Features

* **Dynamic Active-State Rendering:** The rendering logic automatically compares `today` vs. `checkpoint dates` to expand the current active phase while programmatically collapsing past and future phases into minimal nodes.
* **Time-Based Progress Logic:** Visual progress bars are calculated based on *elapsed time* (Start Date vs. End Date), distinct from task completion status.
* **3-Tier Data Hierarchy:** Implements a strict nested structure: **Checkpoints** (Phases) contain **Segments** (Groups), which contain **Todos** (Items).
* **JSON-over-SQLite Storage:** Bypasses traditional relational tables; stores the entire application state as a single JSON blob inside a SQLite row for atomic saves and schema flexibility.
* **Event-Driven Auto-Save:** Uses `onblur` (focus loss) events on input fields to trigger immediate asynchronous `POST` requests to the API, eliminating "Save" buttons.
* **Stateless Authentication:** Write operations (`/api/save`) require a password payload in the request body; Read operations (`/api/data`) are open for quick loading.
* **Optimistic UI:** The frontend updates instantly to user input while the database syncs in the background, ensuring zero latency interactions.

## 🛠️ Tech Stack

* **Backend:** Python (Flask)
* **Database:** SQLite3 (Native Python support)
* **Frontend:** HTML5, JavaScript (Fetch API), Tailwind CSS (CDN)
* **Deployment Target:** PythonAnywhere (Quick)

## 📂 Project Structure

```bash
Kaeru/
├── app.py             
├── requirements.txt   
└── templates/
    └── index.html
```
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
  *Before running server comment out `app.py` app.run command around 105-6 lines*
    ```bash
    python app.py
    ```
    *You should see: `Running on http://127.0.0.1:5000`*

5.  **Access the App**
    Open your browser and visit: `http://127.0.0.1:5000`

6.  **Log In**
    * Password: admin
---
<h1> Developer Info: </h1>
<div align="center">
  <p>
    <a href="https://github.com/Irshad-11">
      <img src="https://img.shields.io/badge/GitHub-Irshad--11-181717?style=flat&logo=github&logoColor=white" alt="GitHub Profile" />
    </a>
    </p>
  
  <p style="color: #64748b; font-size: 0.9rem;">
    Built with 💖 by <strong>Irshad</strong>
    Improved Readme by <very-strong>Mahbub69 (Fan of Johnny S)</very-strong>
  </p>
</div>
