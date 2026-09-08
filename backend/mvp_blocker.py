"""Desktop recovery surface hosted in the existing persistent tkinter window."""
import threading
import tkinter as tk
from io import BytesIO

import requests
from PIL import Image, ImageTk

from mvp_i18n import LANGUAGES, STRINGS, text
from settings_manager import load_settings


class MvpBlockerView:
    def __init__(self, host, backend_url, task, activity, reason, monitor_rect):
        self.host, self.url = host, backend_url
        self.ui = load_settings().get("ui_language", "en")
        self.task = task
        self.recovery = None
        self.challenge = None
        self.translation_draft = ""
        self.busy = False
        self.controls = []
        host._root.configure(bg="#17243b")
        host._content_frame.configure(bg="#17243b")
        width = min(1060, max(480, monitor_rect[2] - 60))
        height = min(720, max(350, monitor_rect[3] - 80))
        canvas = tk.Canvas(host._content_frame, width=width, height=height, bg="#17243b", highlightthickness=0)
        scrollbar = tk.Scrollbar(host._content_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        content = tk.Frame(canvas, bg="#17243b")
        canvas.create_window((0, 0), window=content, width=width, anchor="nw")
        content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        self.left = tk.Frame(content, bg="#17243b", padx=25, pady=28)
        self.right = tk.Frame(content, bg="#ffffff", padx=25, pady=25)
        stacked = width < 800
        self.left.grid(row=0, column=0, sticky="nsew")
        self.right.grid(row=1 if stacked else 0, column=0 if stacked else 1, sticky="nsew", padx=15, pady=15)
        content.columnconfigure(0, weight=1, uniform="panels")
        if not stacked:
            content.columnconfigure(1, weight=1, uniform="panels")
        self.wrap = int(width - 100 if stacked else width / 2 - 90)
        self.label(self.left, "FocusGuard", 24, "#ffffff", "#17243b")
        self.label(self.left, self.t("blockTitle"), 28, "#ffffff", "#17243b", pady=28)
        self.label(self.left, self.t("blockIntro"), 13, "#bac8dc", "#17243b")
        self.label(self.left, self.t("yourTask"), 11, "#8ea6d0", "#17243b", pady=15)
        self.label(self.left, task, 17, "#ffffff", "#17243b")
        self.label(self.left, activity + "\n" + reason, 12, "#bac8dc", "#17243b", pady=20)
        self.button(self.left, self.t("actuallyWorking"), self.correction, secondary=True)
        self.stop_button = self.button(self.left, self.t("stop"), self.stop, secondary=True)
        self.load_recovery()

    def t(self, key):
        return text(key, self.ui)

    def label(self, parent, value, size=13, fg="#34445b", bg="#ffffff", pady=7):
        widget = tk.Label(parent, text=value, font=("Segoe UI", size), fg=fg, bg=bg,
                          wraplength=self.wrap, justify="left", anchor="w")
        widget.pack(fill="x", pady=pady)
        return widget

    def button(self, parent, value, callback, secondary=False):
        button = tk.Button(parent, text=value, command=callback, font=("Segoe UI", 12),
                           bg="#edf1ff" if secondary else "#4364ec", fg="#3856cb" if secondary else "#ffffff",
                           relief="flat", padx=12, pady=10, wraplength=self.wrap, cursor="hand2")
        button.pack(fill="x", pady=6)
        self.controls.append(button)
        return button

    def clear(self):
        for child in self.right.winfo_children():
            child.destroy()
        self.controls = [c for c in self.controls if c.winfo_exists()]

    def request(self, path, payload=None):
        response = requests.get(self.url + path, timeout=90) if payload is None else requests.post(self.url + path, json=payload, timeout=90)
        if not response.ok:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.status_code
            raise RuntimeError(str(detail))
        return response.json()

    def run(self, work, success):
        if self.busy:
            return
        self.busy = True
        for control in self.controls:
            if control is not self.stop_button:
                control.configure(state="disabled")

        def worker():
            try:
                value, failure = work(), None
            except Exception as e:
                value, failure = None, str(e)
            def done():
                if not self.host.is_showing or getattr(self.host, "_mvp_view", None) is not self:
                    return
                self.busy = False
                for control in self.controls:
                    if control.winfo_exists():
                        control.configure(state="normal")
                if failure:
                    self.error.configure(text=self.t("gradingError") + "\n" + failure)
                else:
                    success(value)
            self.host._command_queue.put(done)
        threading.Thread(target=worker, daemon=True).start()

    def load_recovery(self):
        self.clear()
        self.error = self.label(self.right, self.t("loading"))
        self.button(self.right, self.t("retry"), self.load_recovery, secondary=True)
        self.run(lambda: self.request("/mvp/recovery"), self.render_recovery)

    def render_recovery(self, recovery):
        self.recovery = recovery
        if recovery["mode"] == "translation":
            self.load()
            return
        self.clear()
        key = "quickReturn" if recovery["mode"] == "quick_return" else "nextStep"
        self.label(self.right, self.t(key), 20)
        self.label(self.right, self.t(key + "Hint"), 13)
        self.error = self.label(self.right, "", 12, "#a45d25")
        if recovery["mode"] == "next_step":
            self.label(self.right, self.t("nextStepPrompt"), 12)
            self.next_step = tk.Text(self.right, height=4, width=20, font=("Segoe UI", 15),
                                     wrap="word", relief="solid", borderwidth=1)
            self.next_step.pack(fill="x", pady=10)
            self.next_step.focus_set()
            self.button(self.right, self.t("confirmAndReturn"), self.finish_recovery)
        else:
            self.button(self.right, self.t("returnToWork"), self.finish_recovery)

    def finish_recovery(self):
        step = ""
        if self.recovery["mode"] == "next_step":
            step = self.next_step.get("1.0", "end").strip()
            if not step:
                self.error.configure(text=self.t("nextStepRequired"))
                return
        self.run(lambda: self.request("/mvp/recovery/finish", {
            "recovery_id": self.recovery["recovery_id"], "next_step": step,
        }), lambda _: None)

    def load(self, next_sentence=False):
        self.clear()
        self.error = self.label(self.right, self.t("loading"))
        self.button(self.right, self.t("retry"), lambda: self.load(next_sentence), secondary=True)
        payload = {"challenge_id": self.challenge["challenge_id"]} if next_sentence else None
        self.run(lambda: self.request("/mvp/challenge/next" if next_sentence else "/mvp/challenge", payload), self.render)

    def render(self, challenge):
        if not self.challenge or self.challenge["challenge_id"] != challenge["challenge_id"]:
            self.translation_draft = ""
        self.challenge = challenge
        if challenge.get("accepted") or challenge.get("skipped"):
            return self.review(challenge["result"], challenge.get("skipped"))
        self.clear()
        code = next((k for k,v in LANGUAGES.items() if v == challenge["target_language"]), "ja")
        self.label(self.right, self.t("answerLanguage") + " · " + STRINGS["LANGS"][code], 12)
        self.label(self.right, challenge["source_text"], 20, pady=20)
        self.label(self.right, self.t("yourTranslation"), 12)
        self.answer = tk.Text(self.right, height=4, width=20, font=("Segoe UI", 15), wrap="word", relief="solid", borderwidth=1)
        self.answer.pack(fill="x", pady=10)
        self.answer.insert("1.0", self.translation_draft)
        self.answer.focus_set()
        self.error = self.label(self.right, "", 12, "#a45d25")
        self.button(self.right, self.t("checkAnswer"), self.grade)
        self.button(self.right, self.t("giveUp"), lambda: self.grade(True), secondary=True)

    def grade(self, skip=False):
        answer = self.answer.get("1.0", "end").strip()
        if not skip and not answer:
            self.error.configure(text=self.t("pickAnswer"))
            return
        self.error.configure(text=self.t("loading"))
        self.run(lambda: self.request("/mvp/challenge/explain" if skip else "/mvp/challenge/grade",
                 {"challenge_id": self.challenge["challenge_id"], "answer": answer}),
                 lambda result: self.review(result, skip))

    def review(self, result, skip):
        if result.get("accepted") is not True and not skip:
            self.error.configure(text=result.get("feedback", "") + "\n" + result.get("explanation", ""))
            return
        self.clear()
        self.label(self.right, self.t("giveUpHint" if skip else "right"), 17)
        self.label(self.right, self.challenge["source_text"], 14)
        self.label(self.right, self.t("referenceTranslation"), 12)
        self.label(self.right, result.get("model_translation", ""), 18)
        self.label(self.right, result.get("explanation", ""), 13)
        self.error = self.label(self.right, "", 12, "#a45d25")
        self.button(self.right, self.t("nextQuestion") if skip else self.t("returnToWork"),
                    lambda: self.load(True) if skip else self.run(lambda: self.request("/mvp/challenge/finish", {"challenge_id": self.challenge["challenge_id"]}), lambda _: None))

    def stop(self):
        def stop_current():
            state = self.challenge or self.recovery
            session_id = state["block_key"][0] if state else self.request("/session/status")["session_id"]
            return self.request("/mvp/stop", {"session_id": session_id})
        def worker():
            try:
                stop_current()
            except Exception as e:
                detail = str(e)
                def show_error():
                    if getattr(self.host, "_mvp_view", None) is self:
                        self.error.configure(text=detail)
                self.host._command_queue.put(show_error)
        threading.Thread(target=worker, daemon=True).start()

    def correction(self):
        state = self.challenge or self.recovery
        if not state:
            return
        if hasattr(self, "answer") and self.answer.winfo_exists():
            self.translation_draft = self.answer.get("1.0", "end").strip()
        # Get server-owned history; never capture the blocker itself.
        def fetch():
            data = self.request("/mvp/overview")
            record = next((r for r in data["recent"] if r.get("session_id") == state["block_key"][0]), None)
            if not record:
                raise RuntimeError(self.t("noRecords"))
            response = requests.get(self.url + "/personal-bench/recent-image", params={"path": record["screenshot_path"]}, timeout=10)
            response.raise_for_status()
            return record, response.content
        self.run(fetch, self.render_correction)

    def render_correction(self, value):
        record, image = value
        self.clear()
        self.label(self.right, self.t("correctTitle"), 19)
        picture = Image.open(BytesIO(image))
        picture.thumbnail((self.wrap, 170))
        self.photo = ImageTk.PhotoImage(picture)
        tk.Label(self.right, image=self.photo, bg="#ffffff").pack()
        self.label(self.right, self.t("actualLabel"), 12)
        verdict = tk.StringVar(value="on_task")
        for value, key in [("on_task", "onTask"), ("off_task", "offTask")]:
            tk.Radiobutton(self.right, text=self.t(key), variable=verdict, value=value, bg="#ffffff", font=("Segoe UI", 12)).pack(anchor="w")
        self.label(self.right, self.t("reasonLabel"), 12)
        note = tk.Text(self.right, height=3, width=20, font=("Segoe UI", 13), wrap="word")
        note.pack(fill="x")
        self.error = self.label(self.right, "", 12, "#a45d25")
        def save():
            reason = note.get("1.0", "end").strip()
            if not reason:
                self.error.configure(text=self.t("reasonLabel"))
                return
            selected_label = verdict.get()
            self.run(lambda: self.request("/mvp/feedback", {"record_id": record["id"], "label": selected_label, "reason": reason}),
                     lambda _: self.error.configure(text=self.t("feedbackSaved")))
        self.button(self.right, self.t("saveCase"), save)
        self.button(self.right, self.t("cancel"), self.load_recovery, secondary=True)
