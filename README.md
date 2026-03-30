# 🔍 Local Search

> **HR** | Lokalni pretraživač datoteka — brzo pretražuj svoje datoteke kao da koristiš Google.  
> **EN** | Local file search engine — search your files as if you were using Google.

---

## 📸 Screenshot

> *Coming soon*

---

## 🇭🇷 Hrvatski

### Što je Local Search?

Local Search je web aplikacija koja indeksira sve tvoje datoteke i omogućuje brzo pretraživanje po imenu datoteke, nazivu mape i sadržaju (opcionalno). Radi lokalno na tvojem računalu — ništa se ne šalje na internet.

### Značajke

- 🔎 Brza pretraga po imenu datoteke i nazivu mape
- 📁 Pretraga po sadržaju (PDF, Word, tekstualni fajlovi) — opcionalno
- 👁️ Preview slika, PDF-ova, videa i tekstualnih datoteka direktno u browseru
- ⚡ Real-time indeksiranje novih datoteka (Watchdog)
- 🔄 Inkrementalno indeksiranje — pri ponovnom pokretanju indeksira samo nove/izmijenjene datoteke
- 🌐 Preusmjeravanje pretrage na Google, YouTube, GitHub i druge servise
- ⚙️ Postavke — isključi mape iz pretrage, odaberi tipove za full-text indeksiranje

### Instalacija

Debian
```bash
apt update && sudo apt install python3-flask python3-whoosh python3-fitz python3-docx python3-watchdog xdg-utils -y
```

Fedora/RHEL
```bash
sudo dnf install python3-flask python3-whoosh python3-pymupdf python3-python-docx python3-watchdog xdg-utils -y
```

```bash
git clone https://github.com/spidermanhr/local_search.git
cd local_search
pip install flask whoosh pymupdf python-docx watchdog
```

### Pokretanje

```bash
python3 server.py
```

Otvori browser na `http://127.0.0.1:5000`

#### Automatsko pokretanje (dvoklikom)

```bash
chmod +x start.sh
```

Sadržaj `start.sh`:
```bash
#!/bin/bash
cd "$(dirname "$0")"
python3 server.py &
sleep 2
xdg-open http://127.0.0.1:5000
```

### Inotify limit (Linux)

Ako watchdog javlja grešku s inotify limitom, postavi trajno:

```bash
echo "fs.inotify.max_user_watches=524288" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### Struktura projekta

```
local_search/
├── server.py       ← Flask backend, indeksiranje, watchdog
├── index.html      ← Frontend (Jinja2 template)
├── start.sh        ← Pokretač (dvoklikom)
├── config.json     ← Postavke (auto-generirano)
└── ~/.local_search ← Whoosh baza (skrivena, auto-generirano)
```

### Tehnologije

| Komponenta | Tehnologija |
|------------|-------------|
| Backend    | Python, Flask |
| Indeksiranje | Whoosh (full-text search) |
| PDF ekstrakcija | PyMuPDF (fitz) |
| Word ekstrakcija | python-docx |
| Real-time monitoring | Watchdog |
| Frontend | HTML, CSS, JavaScript |

---

## 🇬🇧 English

### What is Local Search?

Local Search is a web application that indexes all your files and enables fast searching by filename, folder name, and content (optional). It runs locally on your machine — nothing is sent to the internet.

### Features

- 🔎 Fast search by filename and folder name
- 📁 Content search (PDF, Word, text files) — optional
- 👁️ Preview images, PDFs, videos and text files directly in the browser
- ⚡ Real-time indexing of new files (Watchdog)
- 🔄 Incremental indexing — on restart, only new/modified files are indexed
- 🌐 Search redirection to Google, YouTube, GitHub and other services
- ⚙️ Settings — exclude folders from search, choose types for full-text indexing

### Installation

Debian
```bash
apt update && sudo apt install python3-flask python3-whoosh python3-fitz python3-docx python3-watchdog xdg-utils -y
```

Fedora/RHEL
```bash
sudo dnf install python3-flask python3-whoosh python3-pymupdf python3-python-docx python3-watchdog xdg-utils -y
```

```bash
git clone https://github.com/spidermanhr/local_search.git
cd local_search
pip install flask whoosh pymupdf python-docx watchdog
```

### Running

```bash
python3 server.py
```

Open your browser at `http://127.0.0.1:5000`

#### Auto-start (double click)

```bash
chmod +x start.sh
```

Contents of `start.sh`:
```bash
#!/bin/bash
cd "$(dirname "$0")"
python3 server.py &
sleep 2
xdg-open http://127.0.0.1:5000
```

### Inotify limit (Linux)

If watchdog reports an inotify limit error, set it permanently:

```bash
echo "fs.inotify.max_user_watches=524288" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### Project structure

```
local_search/
├── server.py       ← Flask backend, indexing, watchdog
├── index.html      ← Frontend (Jinja2 template)
├── start.sh        ← Launcher (double click)
├── config.json     ← Settings (auto-generated)
└── ~/.local_search ← Whoosh database (hidden, auto-generated)
```

### Tech stack

| Component  | Technology |
|------------|------------|
| Backend    | Python, Flask |
| Indexing   | Whoosh (full-text search) |
| PDF extraction | PyMuPDF (fitz) |
| Word extraction | python-docx |
| Real-time monitoring | Watchdog |
| Frontend   | HTML, CSS, JavaScript |

---

## 📄 License

MIT License — free to use, modify and distribute.

---

*Made with ❤️ on Linux*
