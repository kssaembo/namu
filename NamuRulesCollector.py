import json
import re
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup, Tag

APP_NAME = "NamuRulesCollector"
DEFAULT_KEYWORDS = "룰, 게임 규칙, 규칙"
SETTINGS_FILE = "NamuRulesCollector.settings.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}


def app_dir():
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def settings_path():
    return app_dir() / SETTINGS_FILE


def load_settings():
    try:
        p = settings_path()
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        return {}


def save_settings(data):
    try:
        settings_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def normalize_space(text):
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_heading(text):
    text = normalize_space(text)
    text = re.sub(r"\[\s*편집\s*\]$", "", text).strip()
    text = re.sub(r"^\d+(?:\.\d+)*\.?\s*", "", text).strip()
    return text


def sanitize_filename(name):
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"\s+", " ", name).strip().rstrip(".")
    return (name or "namuwiki_game")[:120]


def game_name_from_url(url):
    try:
        path = unquote(urlparse(url).path)
        if "/w/" in path:
            return sanitize_filename(path.split("/w/", 1)[1].split("/", 1)[0])
    except Exception:
        pass
    return "namuwiki_game"


def get_game_name(soup, url):
    h1 = soup.find("h1")
    if h1:
        text = normalize_space(h1.get_text(" ", strip=True))
        if text:
            return sanitize_filename(text)
    if soup.title:
        text = normalize_space(soup.title.get_text(" ", strip=True))
        text = re.sub(r"\s*-\s*나무위키\s*$", "", text).strip()
        if text:
            return sanitize_filename(text)
    return game_name_from_url(url)


def heading_level(tag):
    if tag.name and re.fullmatch(r"h[1-6]", tag.name.lower()):
        return int(tag.name[1])
    for attr in ("data-level", "data-heading-level"):
        value = tag.attrs.get(attr)
        if value and str(value).isdigit() and 1 <= int(value) <= 6:
            return int(value)
    classes = " ".join(tag.get("class", []))
    m = re.search(r"(?:heading|section)[-_ ]?([1-6])\b", classes, re.I)
    return int(m.group(1)) if m else None


def find_headings(soup):
    headings = list(soup.find_all(re.compile(r"^h[1-6]$")))
    if headings:
        return headings
    result = []
    for tag in soup.find_all(True):
        classes = " ".join(tag.get("class", []))
        if re.search(r"wiki[-_ ]?heading|heading[-_ ]?[1-6]|section[-_ ]?[1-6]", classes, re.I) and heading_level(tag):
            result.append(tag)
    return result


def matches_heading(title, keywords):
    title = normalize_heading(title).casefold()
    for keyword in keywords:
        key = normalize_heading(keyword).casefold()
        if key and (title == key or (len(key) >= 2 and key in title)):
            return True
    return False


def clean_soup(soup):
    for selector in ("script", "style", "noscript", "iframe", "svg", "canvas", "nav", "header", "footer", "aside", "form", "button", ".ad", ".ads", ".advertisement"):
        for tag in soup.select(selector):
            tag.decompose()


def block_to_markdown(tag):
    name = (tag.name or "").lower()
    if name in {"p", "blockquote", "pre"}:
        return normalize_space(tag.get_text(" ", strip=True))
    if name == "li":
        text = normalize_space(tag.get_text(" ", strip=True))
        return f"- {text}" if text else ""
    if name == "table":
        rows = []
        for tr in tag.find_all("tr"):
            cells = [normalize_space(c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"], recursive=False)]
            cells = [c for c in cells if c]
            if cells:
                rows.append(" | ".join(cells))
        return "\n".join(rows)
    if name in {"div", "section", "article"} and not tag.find(["p", "li", "table"]):
        text = normalize_space(tag.get_text(" ", strip=True))
        return text if 0 < len(text) <= 2000 else ""
    return ""


def extract_section(start_heading, start_level):
    chunks, seen = [], set()
    allowed = {"p", "li", "table", "div", "section", "article", "blockquote", "pre"}
    for element in start_heading.next_elements:
        if element is start_heading or not isinstance(element, Tag):
            continue
        level = heading_level(element)
        if level is not None:
            if level <= start_level:
                break
            title = normalize_heading(element.get_text(" ", strip=True))
            key = ("heading", title)
            if title and key not in seen:
                chunks.append(f"{'#' * min(6, max(3, level + 1))} {title}")
                seen.add(key)
            continue
        if element.name not in allowed:
            continue
        text = re.sub(r"\[\s*편집\s*\]", "", block_to_markdown(element)).strip()
        if not text:
            continue
        key = (element.name, text)
        if key not in seen:
            chunks.append(text)
            seen.add(key)
    return re.sub(r"\n{3,}", "\n\n", "\n\n".join(chunks)).strip()


def fetch_and_extract(url, keywords):
    response = requests.get(url, headers=HEADERS, timeout=25)
    response.raise_for_status()
    if not response.encoding or response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding or "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")
    clean_soup(soup)
    game_name = get_game_name(soup, url)
    sections = []
    for heading in find_headings(soup):
        title = normalize_heading(heading.get_text(" ", strip=True))
        if not title or not matches_heading(title, keywords):
            continue
        level = heading_level(heading)
        if level:
            content = extract_section(heading, level)
            if content:
                sections.append((title, content))
    return game_name, sections


def yaml_quote(value):
    return json.dumps(str(value), ensure_ascii=False)


def make_markdown(game_name, url, sections):
    today = datetime.now().astimezone().date().isoformat()
    lines = [
        "---",
        "type: game_reference_source",
        "source: 나무위키",
        f"source_url: {yaml_quote(url)}",
        f"collected_at: {today}",
        "scope: 게임 규칙 관련 섹션",
        "---",
        "",
        f"# {game_name}",
        "",
    ]
    for title, content in sections:
        lines.extend([f"## {title}", "", content, ""])
    return "\n".join(lines).rstrip() + "\n"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("860x700")
        self.minsize(760, 620)
        settings = load_settings()
        self.output_dir = tk.StringVar(value=settings.get("output_dir", ""))
        self.keywords = tk.StringVar(value=settings.get("keywords", DEFAULT_KEYWORDS))
        self.save_mode = tk.StringVar(value=settings.get("save_mode", "separate"))
        self.build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def build_ui(self):
        outer = ttk.Frame(self, padding=18)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="나무위키 URL (한 줄에 하나)", font=("", 11, "bold")).pack(anchor="w")
        self.url_text = tk.Text(outer, height=8, wrap="word")
        self.url_text.pack(fill="x", pady=(6, 14))
        ttk.Label(outer, text="수집할 섹션 제목", font=("", 11, "bold")).pack(anchor="w")
        ttk.Entry(outer, textvariable=self.keywords).pack(fill="x", pady=(6, 6))
        ttk.Label(outer, text="쉼표로 구분합니다. 예: 룰, 게임 규칙, 규칙", foreground="#666666").pack(anchor="w", pady=(0, 14))
        box = ttk.LabelFrame(outer, text="저장 방식", padding=10)
        box.pack(fill="x", pady=(0, 14))
        ttk.Radiobutton(box, text="A. 게임별 Markdown 파일로 저장", variable=self.save_mode, value="separate").pack(anchor="w", pady=2)
        ttk.Radiobutton(box, text="B. 하나의 Markdown 파일에 모두 저장", variable=self.save_mode, value="combined").pack(anchor="w", pady=2)
        ttk.Label(outer, text="저장 위치", font=("", 11, "bold")).pack(anchor="w")
        row = ttk.Frame(outer)
        row.pack(fill="x", pady=(6, 14))
        ttk.Entry(row, textvariable=self.output_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="폴더 선택", command=self.choose_folder).pack(side="left", padx=(8, 0))
        self.collect_btn = ttk.Button(outer, text="수집하기", command=self.start_collection)
        self.collect_btn.pack(fill="x", ipady=10, pady=(2, 14))
        ttk.Label(outer, text="진행 상황", font=("", 11, "bold")).pack(anchor="w")
        self.log_text = tk.Text(outer, height=13, wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True, pady=(6, 0))

    def choose_folder(self):
        folder = filedialog.askdirectory(title="Markdown 저장 폴더 선택", initialdir=self.output_dir.get() or str(Path.home()))
        if folder:
            self.output_dir.set(folder)

    def log(self, message):
        def write():
            self.log_text.config(state="normal")
            self.log_text.insert("end", message.rstrip() + "\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.after(0, write)

    def set_busy(self, busy):
        self.after(0, lambda: self.collect_btn.config(state="disabled" if busy else "normal"))

    def start_collection(self):
        urls = [x.strip() for x in self.url_text.get("1.0", "end").splitlines() if x.strip()]
        keywords = [x.strip() for x in self.keywords.get().split(",") if x.strip()]
        output = self.output_dir.get().strip()
        if not urls:
            messagebox.showwarning(APP_NAME, "나무위키 URL을 한 개 이상 입력하세요.")
            return
        if not keywords:
            messagebox.showwarning(APP_NAME, "수집할 섹션 제목을 한 개 이상 입력하세요.")
            return
        if not output:
            messagebox.showwarning(APP_NAME, "저장 위치를 선택하세요.")
            return
        out_dir = Path(output)
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"저장 폴더를 사용할 수 없습니다.\n{e}")
            return
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")
        save_settings({"output_dir": output, "keywords": self.keywords.get(), "save_mode": self.save_mode.get()})
        self.set_busy(True)
        threading.Thread(target=self.collect_worker, args=(urls, keywords, out_dir, self.save_mode.get()), daemon=True).start()

    def collect_worker(self, urls, keywords, out_dir, mode):
        combined, success = [], 0
        try:
            for i, url in enumerate(urls, 1):
                self.log(f"[{i}/{len(urls)}] {game_name_from_url(url)} 수집 중...")
                if "namu.wiki" not in urlparse(url).netloc.lower():
                    self.log("  건너뜀: namu.wiki 주소가 아닙니다.")
                    continue
                try:
                    game_name, sections = fetch_and_extract(url, keywords)
                except requests.HTTPError as e:
                    code = e.response.status_code if e.response is not None else "HTTP 오류"
                    self.log(f"  실패: 페이지 요청 오류 ({code})")
                    continue
                except requests.RequestException as e:
                    self.log(f"  실패: 네트워크 오류 - {e}")
                    continue
                except Exception as e:
                    self.log(f"  실패: 문서 분석 오류 - {e}")
                    continue
                if not sections:
                    self.log("  규칙 섹션을 찾지 못했습니다.")
                    continue
                self.log(f"  규칙 섹션 발견: {len(sections)}개")
                markdown = make_markdown(game_name, url, sections)
                if mode == "separate":
                    path = out_dir / f"{sanitize_filename(game_name)}.md"
                    path.write_text(markdown, encoding="utf-8-sig")
                    self.log(f"  저장 완료: {path.name}")
                else:
                    combined.append(markdown)
                success += 1
            if mode == "combined" and combined:
                path = out_dir / "NamuRulesCollection.md"
                path.write_text("\n\n---\n\n".join(x.strip() for x in combined) + "\n", encoding="utf-8-sig")
                self.log(f"통합 저장 완료: {path.name}")
            self.log("")
            self.log(f"완료: {success}/{len(urls)}개 문서 저장")
            if success == 0:
                self.log("※ 나무위키가 자동 요청을 차단했거나 문서 구조가 변경된 경우 수집되지 않을 수 있습니다.")
            self.after(0, lambda: messagebox.showinfo(APP_NAME, f"수집이 끝났습니다.\n저장 성공: {success}/{len(urls)}"))
        finally:
            self.set_busy(False)

    def on_close(self):
        save_settings({"output_dir": self.output_dir.get(), "keywords": self.keywords.get(), "save_mode": self.save_mode.get()})
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
