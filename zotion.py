import csv
import requests
import os
import threading
import traceback
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv, set_key, dotenv_values
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import sys
NOTION_VERSION = "2022-06-28"


def format_date(date_str):
    """Convert various date strings from Zotero to ISO 8601 format (YYYY-MM-DD)."""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%m/%Y", "%Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_zotero_csv(path, logger=print):
    """Parse the Zotero-exported CSV file and return a list of paper items."""
    items = []
    logger(f"Reading Zotero data from: {path}")
    with open(path, mode='r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if not row.get('Title'):
                continue
            authors_raw = row.get('Author', '').split(';')
            authors = []
            for author in authors_raw:
                author = author.strip()
                if ',' in author:
                    try:
                        last, first = [part.strip() for part in author.split(',', 1)]
                        authors.append(f"{first} {last}")
                    except ValueError:
                        authors.append(author)
                elif author:
                    authors.append(author)
            items.append({
                "title": row.get('Title', 'No Title Provided'),
                "authors": authors,
                "date": row.get('Date', ''),
                "doi": row.get('DOI', '')
            })
    logger(f"Parsed {len(items)} items from CSV.")
    return items


def get_existing_notion_titles(notion_token, notion_db_id, logger=print):
    """Fetch all existing titles from the Notion database to prevent duplicates."""
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }
    existing_titles = set()
    url = f"https://api.notion.com/v1/databases/{notion_db_id}/query"

    has_more = True
    next_cursor = None
    while has_more:
        payload = {"page_size": 100}
        if next_cursor:
            payload["start_cursor"] = next_cursor
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=30)
            r.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger(f"Failed to fetch existing pages from Notion: {e}")
            raise

        data = r.json()
        for page in data.get("results", []):
            props = page.get("properties", {})
            for key in ("Title", "Name", "title"):
                title_prop = props.get(key, {}).get("title", [])
                if title_prop:
                    existing_titles.add(title_prop[0].get("text", {}).get("content"))
                    break
        has_more = data.get("has_more", False)
        next_cursor = data.get("next_cursor")

    logger(f"Found {len(existing_titles)} existing titles in Notion.")
    return existing_titles


def get_database_properties(notion_token, notion_db_id, logger=print):
    """Fetch database schema to determine property types."""
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": NOTION_VERSION,
    }
    url = f"https://api.notion.com/v1/databases/{notion_db_id}"

    try:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        prop_types = {k: v.get("type") for k, v in data.get("properties", {}).items()}
        return prop_types
    except requests.exceptions.RequestException as e:
        logger(f"Could not fetch database schema: {e}")
        raise


def push_to_notion(items_to_push, notion_token, notion_db_id, logger=print):
    """Push new items from Zotero to the Notion database."""
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }

    existing_titles = get_existing_notion_titles(notion_token, notion_db_id, logger=logger)
    prop_types = get_database_properties(notion_token, notion_db_id, logger=logger)
    doi_type = prop_types.get("DOI", "rich_text")

    logger(f"DOI property type: {doi_type}")

    pushed, skipped = 0, 0
    for item in items_to_push:
        if item["title"] in existing_titles:
            logger(f"Skipping existing item: {item['title']}")
            skipped += 1
            continue

        authors_text = ", ".join(item["authors"]) if item["authors"] else "Unknown"
        doi_value = item["doi"].strip() if item["doi"] else None
        date_iso = format_date(item["date"]) or None

        properties = {
            "Title": {"title": [{"text": {"content": item["title"]}}]},
            "Authors": {"rich_text": [{"text": {"content": authors_text}}]},
        }

        if date_iso:
            properties["Date"] = {"date": {"start": date_iso}}

        if doi_value:
            doi_url = doi_value if doi_value.startswith("http") else f"https://doi.org/{doi_value}"
            if doi_type == "url":
                properties["DOI"] = {"url": doi_url}
            else:
                properties["DOI"] = {"rich_text": [{"text": {"content": doi_url}}]}

        data = {"parent": {"database_id": notion_db_id}, "properties": properties}

        try:
            response = requests.post("https://api.notion.com/v1/pages", headers=headers, json=data, timeout=30)
            response.raise_for_status()
            logger(f"Pushed: {item['title']}")
            pushed += 1
        except requests.exceptions.RequestException as e:
            logger(f"Failed to push '{item['title']}': {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    logger(f"   Reason: {e.response.text}")
                except Exception:
                    pass

    logger(f"Finished. pushed={pushed}, skipped={skipped}")


class TextRedirector:
    """Redirect prints to a tkinter Text or ScrolledText widget."""
    def __init__(self, widget, tag="stdout"):
        self.widget = widget
        self.tag = tag

    def write(self, str_):
        def inner():
            self.widget.insert(tk.END, str_)
            self.widget.see(tk.END)
        try:
            self.widget.after(0, inner)
        except Exception:
            pass

    def flush(self):
        return None


def get_env_path():
    """Get the appropriate .env file path based on the platform."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        if sys.platform == "darwin":
            app_support = Path.home() / "Library" / "Application Support" / "Zotion"
            app_support.mkdir(parents=True, exist_ok=True)
            return app_support / ".env"
        elif sys.platform == "win32":
            app_data = Path(os.getenv('APPDATA')) / "Zotion"
            app_data.mkdir(parents=True, exist_ok=True)
            return app_data / ".env"
        else:
            config_dir = Path.home() / ".config" / "zotion"
            config_dir.mkdir(parents=True, exist_ok=True)
            return config_dir / ".env"
    else:
        return Path('.env')


ENV_PATH = get_env_path()


class ZoteroNotionApp:
    def __init__(self, root):
        self.root = root
        root.title("Zotion")
        root.geometry("800x600")

        # --- Input Fields ---
        frm = tk.Frame(root)
        frm.pack(fill=tk.X, padx=10, pady=10)

        frm.columnconfigure(1, weight=1)

        tk.Label(frm, text="Notion Token:").grid(row=0, column=0, sticky='w')
        tk.Label(frm, text="Notion DB ID:").grid(row=1, column=0, sticky='w')
        tk.Label(frm, text="Zotero CSV Path:").grid(row=2, column=0, sticky='w')

        self.token_entry = tk.Entry(frm)
        self.db_entry = tk.Entry(frm)
        self.csv_entry = tk.Entry(frm)

        self.token_entry.grid(row=0, column=1, padx=(5, 5), pady=2, sticky='we')
        self.db_entry.grid(row=1, column=1, padx=(5, 5), pady=2, sticky='we')
        self.csv_entry.grid(row=2, column=1, padx=(5, 2), pady=2, sticky='we')

        tk.Button(frm, text="Browse", command=self.browse_csv).grid(row=2, column=2, padx=(2, 0), pady=2, sticky='w')

        # --- Buttons Row ---
        btns = tk.Frame(root)
        btns.pack(fill=tk.X, padx=10, pady=10)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "Red.TButton",
            foreground="white",
            background="#DC143C",
            font=('TkDefaultFont', 11, 'bold'),
            #padding=(10,10),
            borderwidth=0,
        )
        style.map("Red.TButton", background=[("active", "#B22222"), ("pressed", "#8B0000")])

        self.sync_button = ttk.Button(btns, text="Start Sync", command=self.start_sync, style="Red.TButton")
        self.save_button = ttk.Button(btns, text="Save Credentials", command=self.save_env)
        self.load_button = ttk.Button(btns, text="Load Credentials", command=self.load_env)

        self.sync_button.pack(side='left', padx=10)
        self.save_button.pack(side='left', padx=10)
        self.load_button.pack(side='left', padx=10)

        # --- Log Output ---
        log_frame = tk.LabelFrame(root, text="Log")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.log_widget = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD)
        self.log_widget.pack(fill=tk.BOTH, expand=True)

        # Redirect stdout/stderr
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        sys.stdout = TextRedirector(self.log_widget)
        sys.stderr = TextRedirector(self.log_widget)

        self.load_env()
        print(f"Configuration file location: {ENV_PATH.absolute()}")

    def browse_csv(self):
        path = filedialog.askopenfilename(filetypes=[('CSV files', '*.csv'), ('All files', '*.*')])
        if path:
            self.csv_entry.delete(0, tk.END)
            self.csv_entry.insert(0, path)

    def save_env(self):
        token = self.token_entry.get().strip()
        dbid = self.db_entry.get().strip()
        csvp = self.csv_entry.get().strip()

        if not token or not dbid or not csvp:
            if not messagebox.askyesno("Save .env?", "One or more values are empty. Save anyway?"):
                return

        try:
            ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
            ENV_PATH.write_text(
                f"NOTION_TOKEN={token}\nNOTION_DB_ID={dbid}\nZOTERO_CSV_PATH={csvp}\n",
                encoding='utf-8'
            )
            messagebox.showinfo('Saved', 'Configuration saved successfully!')
            print(f"Saved configuration to: {ENV_PATH.resolve()}")
        except Exception as e:
            messagebox.showerror('Error', f'Failed to save configuration: {e}')
            traceback.print_exc()

    def load_env(self):
        try:
            if not ENV_PATH.exists():
                print(f'No configuration file found at: {ENV_PATH.resolve()}')
                return

            vals = {}
            with open(ENV_PATH, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip() and '=' in line and not line.startswith('#'):
                        key, value = line.strip().split('=', 1)
                        vals[key] = value

            self.token_entry.delete(0, tk.END)
            self.db_entry.delete(0, tk.END)
            self.csv_entry.delete(0, tk.END)

            self.token_entry.insert(0, vals.get('NOTION_TOKEN', ''))
            self.db_entry.insert(0, vals.get('NOTION_DB_ID', ''))
            self.csv_entry.insert(0, vals.get('ZOTERO_CSV_PATH', ''))

            print(f"Loaded .env from {ENV_PATH}")
        except Exception as e:
            print(f'Error loading configuration: {e}')
            traceback.print_exc()

    def start_sync(self):
        token = self.token_entry.get().strip()
        dbid = self.db_entry.get().strip()
        csvp = self.csv_entry.get().strip()

        if not token or not dbid:
            messagebox.showwarning('Missing', 'Notion token and DB ID are required.')
            return

        if not csvp or not Path(csvp).is_file():
            messagebox.showwarning('Missing', 'Please select a valid Zotero CSV file.')
            return

        t = threading.Thread(target=self._sync_thread, args=(csvp, token, dbid), daemon=True)
        t.start()

    def _sync_thread(self, csv_path, token, dbid):
        try:
            print('\n=== Starting sync ===')
            items = parse_zotero_csv(csv_path, logger=print)
            if not items:
                print('No items parsed — aborting.')
                return
            print(f'Will attempt to push {len(items)} items')
            push_to_notion(items, notion_token=token, notion_db_id=dbid, logger=print)
            print('Sync complete.')
        except requests.exceptions.HTTPError as e:
            if e.response and e.response.status_code == 401:
                messagebox.showerror('Credential Error', 'Invalid Notion credentials.')
            elif e.response and e.response.status_code == 404:
                messagebox.showerror('Database Error', 'Database not found or access denied.')
            else:
                messagebox.showerror('Sync Error', f'Error: {e}')
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror('Sync Error', f'Unexpected error:\n{e}')

    def on_close(self):
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        self.root.destroy()


def main():
    root = tk.Tk()
    app = ZoteroNotionApp(root)
    root.protocol('WM_DELETE_WINDOW', app.on_close)
    root.mainloop()


if __name__ == '__main__':
    main()
