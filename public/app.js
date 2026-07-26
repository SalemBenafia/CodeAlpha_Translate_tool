/* Translate tool — UI logic. Talks only to this app's own /api/* endpoints. */

const $ = (id) => document.getElementById(id);

const el = {
  sourceLang: $("sourceLang"),
  targetLang: $("targetLang"),
  sourceText: $("sourceText"),
  targetText: $("targetText"),
  translateBtn: $("translateBtn"),
  swapBtn: $("swapBtn"),
  clearBtn: $("clearBtn"),
  autoTranslate: $("autoTranslate"),
  charCount: $("charCount"),
  detected: $("detected"),
  spinner: $("spinner"),
  error: $("error"),
  toast: $("toast"),
  player: $("player"),
  statusDot: $("statusDot"),
  statusText: $("statusText"),
  engineNote: $("engineNote"),
};

const state = {
  languages: [],       // [{ code, name }]
  piperVoices: [],     // language codes Piper can speak
  lastTranslated: "",  // guards against re-translating identical input
  requestId: 0,        // drops responses from superseded requests
};

const DEFAULTS = { source: "auto", target: "es" };
const PREFS_KEY = "translate-tool:prefs";

/* ------------------------------------------------------------- feedback UI */

let toastTimer;
function toast(message) {
  clearTimeout(toastTimer);
  el.toast.textContent = message;
  el.toast.classList.add("show");
  toastTimer = setTimeout(() => el.toast.classList.remove("show"), 2200);
}

function showError(message) {
  el.error.textContent = message;
  el.error.hidden = !message;
}

function setBusy(busy) {
  el.spinner.hidden = !busy;
  el.translateBtn.disabled = busy;
  el.targetText.classList.toggle("loading", busy);
}

/* --------------------------------------------------------------- api calls */

async function api(path, options) {
  const res = await fetch(path, options);
  const type = res.headers.get("content-type") || "";

  if (type.includes("application/json")) {
    const body = await res.json();
    if (!res.ok) throw Object.assign(new Error(body.error || `Request failed (${res.status})`), { status: res.status });
    return body;
  }
  if (!res.ok) throw Object.assign(new Error(`Request failed (${res.status})`), { status: res.status });
  return res;
}

/* --------------------------------------------------------------- languages */

function nameOf(code) {
  return state.languages.find((l) => l.code === code)?.name || code;
}

function fillLanguageSelects() {
  const prefs = loadPrefs();

  el.sourceLang.innerHTML = '<option value="auto">Detect language</option>';
  el.targetLang.innerHTML = "";

  for (const lang of state.languages) {
    el.sourceLang.add(new Option(lang.name, lang.code));
    el.targetLang.add(new Option(lang.name, lang.code));
  }

  const has = (code) => state.languages.some((l) => l.code === code);
  el.sourceLang.value = prefs.source === "auto" || has(prefs.source) ? prefs.source : "auto";
  el.targetLang.value = has(prefs.target)
    ? prefs.target
    : has(DEFAULTS.target)
      ? DEFAULTS.target
      : state.languages[0]?.code;
}

function loadPrefs() {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(PREFS_KEY) || "{}") };
  } catch {
    return { ...DEFAULTS };
  }
}

function savePrefs() {
  try {
    localStorage.setItem(
      PREFS_KEY,
      JSON.stringify({ source: el.sourceLang.value, target: el.targetLang.value })
    );
  } catch { /* private mode — preferences just won't stick */ }
}

/* --------------------------------------------------------------- translate */

async function translate({ silent = false } = {}) {
  const text = el.sourceText.value.trim();
  const source = el.sourceLang.value;
  const target = el.targetLang.value;

  if (!text) {
    el.targetText.textContent = "";
    el.detected.hidden = true;
    state.lastTranslated = "";
    showError("");
    return;
  }

  const id = ++state.requestId;
  setBusy(true);
  showError("");

  try {
    const data = await api("/api/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ q: text, source, target }),
    });

    if (id !== state.requestId) return; // a newer request already went out

    el.targetText.textContent = data.translatedText;
    state.lastTranslated = `${text}|${source}|${target}`;

    if (data.detected) {
      el.detected.textContent = `Detected: ${nameOf(data.detected.language)} (${data.detected.confidence}%)`;
      el.detected.dataset.lang = data.detected.language; // used by swap + listen
      el.detected.hidden = false;
    } else {
      el.detected.hidden = true;
      delete el.detected.dataset.lang;
    }
  } catch (err) {
    if (id !== state.requestId) return;
    if (!silent) showError(err.message);
    el.targetText.textContent = "";
  } finally {
    if (id === state.requestId) setBusy(false);
  }
}

/* -------------------------------------------------------------------- copy */

async function copy(which, button) {
  const text = which === "source" ? el.sourceText.value : el.targetText.textContent;
  if (!text.trim()) return toast("Nothing to copy");

  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // Fallback for non-secure origins where the clipboard API is unavailable.
    const helper = document.createElement("textarea");
    helper.value = text;
    helper.style.position = "fixed";
    helper.style.opacity = "0";
    document.body.appendChild(helper);
    helper.select();
    const ok = document.execCommand("copy");
    helper.remove();
    if (!ok) return toast("Copy failed — select the text manually");
  }

  button.classList.add("done");
  setTimeout(() => button.classList.remove("done"), 1200);
  toast("Copied to clipboard");
}

/* --------------------------------------------------------- text-to-speech */

let activeButton = null;

function stopSpeech() {
  el.player.pause();
  if (el.player.src) {
    URL.revokeObjectURL(el.player.src);
    el.player.removeAttribute("src");
  }
  window.speechSynthesis?.cancel();
  activeButton?.classList.remove("playing");
  activeButton = null;
}

async function speak(which, button) {
  const text = (which === "source" ? el.sourceText.value : el.targetText.textContent).trim();
  if (!text) return toast("Nothing to read aloud");

  // Second click on the same button stops playback.
  if (activeButton === button) return stopSpeech();
  stopSpeech();

  // With "Detect language" on, the source language is only known once a
  // translation has run; before that, fall back to the target language.
  let lang = which === "source" ? el.sourceLang.value : el.targetLang.value;
  if (lang === "auto") lang = el.detected.dataset.lang || el.targetLang.value;

  activeButton = button;
  button.classList.add("playing");

  try {
    const res = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, lang }),
    });

    if (res.status === 501) {           // no Piper voice for this language
      browserSpeak(text, lang, button);
      return;
    }
    if (!res.ok) throw new Error((await res.json()).error || "Speech failed");

    const url = URL.createObjectURL(await res.blob());
    el.player.src = url;
    el.player.onended = stopSpeech;
    el.player.onerror = () => {
      stopSpeech();
      toast("Could not play audio");
    };
    await el.player.play();
  } catch (err) {
    button.classList.remove("playing");
    activeButton = null;
    toast(err.message);
  }
}

/** Browser speech synthesis — used only when Piper has no voice for a language. */
function browserSpeak(text, lang, button) {
  if (!window.speechSynthesis) {
    button.classList.remove("playing");
    activeButton = null;
    return toast(`No voice available for ${nameOf(lang)}`);
  }

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = lang;
  utterance.onend = stopSpeech;
  utterance.onerror = stopSpeech;
  window.speechSynthesis.speak(utterance);
  toast(`No Piper voice for ${nameOf(lang)} — using browser speech`);
}

/* ------------------------------------------------------------------ events */

function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

const autoTranslate = debounce(() => {
  if (!el.autoTranslate.checked) return;
  const key = `${el.sourceText.value.trim()}|${el.sourceLang.value}|${el.targetLang.value}`;
  if (key === state.lastTranslated) return;
  translate({ silent: true });
}, 700);

el.sourceText.addEventListener("input", () => {
  el.charCount.textContent = el.sourceText.value.length;
  stopSpeech();
  autoTranslate();
});

el.translateBtn.addEventListener("click", () => translate());

el.sourceText.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault();
    translate();
  }
});

el.swapBtn.addEventListener("click", () => {
  // "Detect language" has no counterpart to swap into — use the detected code.
  const from = el.sourceLang.value === "auto" ? el.detected.dataset.lang : el.sourceLang.value;
  if (!from) return toast("Translate once first, or pick a source language");

  el.sourceLang.value = el.targetLang.value;
  el.targetLang.value = from;

  const translated = el.targetText.textContent;
  if (translated) {
    el.sourceText.value = translated;
    el.charCount.textContent = translated.length;
    el.targetText.textContent = "";
  }

  el.detected.hidden = true;
  savePrefs();
  stopSpeech();
  if (el.sourceText.value.trim()) translate();
});

el.clearBtn.addEventListener("click", () => {
  stopSpeech();
  el.sourceText.value = "";
  el.targetText.textContent = "";
  el.charCount.textContent = "0";
  el.detected.hidden = true;
  state.lastTranslated = "";
  showError("");
  el.sourceText.focus();
});

for (const select of [el.sourceLang, el.targetLang]) {
  select.addEventListener("change", () => {
    savePrefs();
    stopSpeech();
    if (el.sourceText.value.trim()) translate();
  });
}

for (const button of document.querySelectorAll("[data-copy]")) {
  button.addEventListener("click", () => copy(button.dataset.copy, button));
}

for (const button of document.querySelectorAll("[data-speak]")) {
  button.addEventListener("click", () => speak(button.dataset.speak, button));
}

/* ------------------------------------------------------------------- boot */

async function init() {
  try {
    const [languages, health] = await Promise.all([
      api("/api/languages"),
      api("/api/health").catch(() => ({ tts: [] })),
    ]);

    state.languages = languages.map((l) => ({ code: l.code, name: l.name }));
    state.piperVoices = health.tts || [];
    fillLanguageSelects();

    el.statusDot.className = "dot online";
    el.statusText.textContent = `${state.languages.length} languages`;
    el.engineNote.textContent = state.piperVoices.length
      ? `LibreTranslate · Piper voices: ${state.piperVoices.length}`
      : "LibreTranslate";
  } catch (err) {
    el.statusDot.className = "dot offline";
    el.statusText.textContent = "engine offline";
    showError(`${err.message} See the README for how to start LibreTranslate.`);
    el.translateBtn.disabled = true;
    el.swapBtn.disabled = true;
    for (const select of [el.sourceLang, el.targetLang]) {
      select.innerHTML = "<option>Unavailable</option>";
      select.disabled = true;
    }
  }

  el.sourceText.focus();
}

init();
