/**
 * Create your thumbnail — 16:9 manual canvas composer (1280×720 export).
 * Modular sections: state, drawing, interaction, export, UI bindings.
 */

const CANVAS_W = 1280;
const CANVAS_H = 720;

/** Safari / privacy mode: document.fonts may be missing; never hang forever. */
function afterFontsReady(fn) {
  try {
    if (typeof document.fonts !== "undefined" && document.fonts.ready) {
      document.fonts.ready.then(fn);
    } else {
      setTimeout(fn, 50);
    }
  } catch {
    setTimeout(fn, 50);
  }
}

function defaultState() {
  return {
    title: "Your Amazing Title",
    fontSize: 64,
    fontFamily: "Inter",
    color: "#ffffff",
    bold: true,
    italic: false,
    textStroke: true,
    bgType: "gradient",
    solidColor: "#0f172a",
    gradStart: "#4f46e5",
    gradEnd: "#db2777",
    gradAngle: 135,
    bgImage: null,
    /** @type {{ id: string, img: HTMLImageElement, x: number, y: number, w: number, h: number }[]} */
    pictureLayers: [],
    selectedLayerId: null,
    textX: 0.5,
    textY: 0.52,
    maxTextWidthRatio: 0.85,
  };
}

const PRESETS = {
  gaming: () => ({
    ...defaultState(),
    title: "EPIC WIN MOMENTS",
    fontSize: 76,
    fontFamily: "Oswald",
    color: "#fde047",
    bgType: "gradient",
    gradStart: "#581c87",
    gradEnd: "#be123c",
    gradAngle: 145,
    bold: true,
    italic: false,
    textY: 0.48,
  }),
  tech: () => ({
    ...defaultState(),
    title: "Tech Deep Dive",
    fontSize: 58,
    fontFamily: "Inter",
    color: "#e2e8f0",
    bgType: "solid",
    solidColor: "#0f172a",
    bold: true,
    textY: 0.5,
  }),
  minimal: () => ({
    ...defaultState(),
    title: "clean & simple",
    fontSize: 52,
    fontFamily: "Montserrat",
    color: "#1e293b",
    bgType: "solid",
    solidColor: "#f8fafc",
    bold: false,
    italic: false,
    textStroke: false,
    textY: 0.5,
  }),
  sunset: () => ({
    ...defaultState(),
    title: "Golden Hour VLOG",
    fontSize: 62,
    fontFamily: "Poppins",
    color: "#fff7ed",
    bgType: "gradient",
    gradStart: "#ea580c",
    gradEnd: "#7c3aed",
    gradAngle: 120,
    textY: 0.55,
  }),
};

let state = defaultState();

let dragMode = "none";
let dragLayerId = null;
/** @type {{ mx: number, my: number, lx: number, ly: number } | null} */
let moveStart = null;
/** @type {{ ax: number, ay: number, ar: number } | null} */
let resizeAnchor = null;
let textPointerOffset = { x: 0, y: 0 };

/** @type {HTMLCanvasElement | null} */
let canvas = null;
/** @type {CanvasRenderingContext2D | null} */
let ctx = null;

function gradientEndpoints(angleDeg, w, h) {
  const rad = (angleDeg * Math.PI) / 180;
  const cx = w / 2;
  const cy = h / 2;
  const len = Math.hypot(w, h) / 2;
  return {
    x0: cx - Math.cos(rad) * len,
    y0: cy - Math.sin(rad) * len,
    x1: cx + Math.cos(rad) * len,
    y1: cy + Math.sin(rad) * len,
  };
}

function drawCover(ctx2, img, w, h) {
  const ir = img.width / img.height;
  const cr = w / h;
  let dw;
  let dh;
  let ox;
  let oy;
  if (ir > cr) {
    dh = h;
    dw = ir * h;
    ox = (w - dw) / 2;
    oy = 0;
  } else {
    dw = w;
    dh = dw / ir;
    ox = 0;
    oy = (h - dh) / 2;
  }
  ctx2.drawImage(img, ox, oy, dw, dh);
}

function buildFontString() {
  const { italic, bold, fontSize, fontFamily } = state;
  const style = `${italic ? "italic " : ""}${bold ? "bold " : ""}`;
  const fam = fontFamily.includes(" ") ? `"${fontFamily}"` : fontFamily;
  return `${style}${fontSize}px ${fam}, sans-serif`;
}

function measureTextBlock(text, maxWidth) {
  if (!ctx || !text.trim()) return { width: 0, height: 0, lines: [] };
  ctx.font = buildFontString();
  const words = text.split(/\s+/).filter(Boolean);
  const lines = [];
  let line = "";
  for (const word of words) {
    const test = line ? `${line} ${word}` : word;
    if (ctx.measureText(test).width > maxWidth && line) {
      lines.push(line);
      line = word;
    } else {
      line = test;
    }
  }
  if (line) lines.push(line);
  let width = 0;
  for (const ln of lines) {
    width = Math.max(width, ctx.measureText(ln).width);
  }
  const lineHeight = state.fontSize * 1.15;
  const height = lines.length * lineHeight;
  return { width, height, lines, lineHeight };
}

function getTextCenterPx() {
  return {
    x: state.textX * CANVAS_W,
    y: state.textY * CANVAS_H,
  };
}

function hitTestTextCanvas(x, y) {
  if (!ctx) return false;
  const text = state.title.trim();
  if (!text) return false;
  const maxW = CANVAS_W * state.maxTextWidthRatio;
  const { width, height } = measureTextBlock(text, maxW);
  const cx = state.textX * CANVAS_W;
  const cy = state.textY * CANVAS_H;
  const pad = state.fontSize * 0.35;
  return (
    x >= cx - width / 2 - pad &&
    x <= cx + width / 2 + pad &&
    y >= cy - height / 2 - pad &&
    y <= cy + height / 2 + pad
  );
}

/** Rough hit region for dragging title (client coords). */
function hitTestText(clientX, clientY) {
  if (!canvas || !ctx) return false;
  const { x, y } = canvasCoords(clientX, clientY);
  return hitTestTextCanvas(x, y);
}

function selectedLayer() {
  return state.pictureLayers.find((l) => l.id === state.selectedLayerId) ?? null;
}

const SE_HANDLE_PX = 26;

function hitSEHandle(layer, x, y) {
  if (!layer || state.selectedLayerId !== layer.id) return false;
  const hx = layer.x + layer.w - SE_HANDLE_PX;
  const hy = layer.y + layer.h - SE_HANDLE_PX;
  return x >= hx && x <= layer.x + layer.w && y >= hy && y <= layer.y + layer.h;
}

/** Top-most layer under point (last in array = drawn on top). */
function hitPictureLayerAt(x, y) {
  for (let i = state.pictureLayers.length - 1; i >= 0; i--) {
    const L = state.pictureLayers[i];
    if (x >= L.x && x <= L.x + L.w && y >= L.y && y <= L.y + L.h) return L;
  }
  return null;
}

function newLayerFromImage(img, offsetIndex = 0) {
  const ar = img.naturalHeight / Math.max(1, img.naturalWidth);
  let w = Math.min(480, CANVAS_W * 0.55);
  let h = w * ar;
  if (h > CANVAS_H * 0.65) {
    h = CANVAS_H * 0.65;
    w = h / ar;
  }
  const ox = (offsetIndex % 5) * 28;
  const oy = (offsetIndex % 5) * 28;
  return {
    id:
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `L${Date.now()}-${Math.floor(Math.random() * 1e6)}`,
    img,
    x: (CANVAS_W - w) / 2 + ox,
    y: (CANVAS_H - h) / 2 + oy,
    w,
    h,
  };
}

function drawPictureLayers(ctx2) {
  for (const L of state.pictureLayers) {
    try {
      ctx2.drawImage(L.img, L.x, L.y, L.w, L.h);
    } catch {
      /* ignore draw errors */
    }
  }
}

function drawLayerChrome(ctx2) {
  const sel = selectedLayer();
  if (!sel) return;
  ctx2.save();
  ctx2.strokeStyle = "rgba(99, 102, 241, 0.95)";
  ctx2.lineWidth = 3;
  ctx2.setLineDash([10, 6]);
  ctx2.strokeRect(sel.x, sel.y, sel.w, sel.h);
  ctx2.setLineDash([]);
  const hs = SE_HANDLE_PX;
  ctx2.fillStyle = "rgba(255,255,255,0.95)";
  ctx2.strokeStyle = "#6366f1";
  ctx2.lineWidth = 2;
  ctx2.beginPath();
  ctx2.rect(sel.x + sel.w - hs, sel.y + sel.h - hs, hs, hs);
  ctx2.fill();
  ctx2.stroke();
  ctx2.restore();
}

function canvasCoords(clientX, clientY) {
  if (!canvas) return { x: 0, y: 0 };
  const r = canvas.getBoundingClientRect();
  const sx = CANVAS_W / r.width;
  const sy = CANVAS_H / r.height;
  return {
    x: (clientX - r.left) * sx,
    y: (clientY - r.top) * sy,
  };
}

function drawBackground(ctx2) {
  const { bgType, solidColor, gradStart, gradEnd, gradAngle } = state;
  // If a user-selected background image exists, always render it.
  // This avoids UI state drift where bgType might show gradient while user expects image.
  if (state.bgImage) {
    ctx2.fillStyle = "#000";
    ctx2.fillRect(0, 0, CANVAS_W, CANVAS_H);
    drawCover(ctx2, state.bgImage, CANVAS_W, CANVAS_H);
    return;
  }
  if (bgType === "solid") {
    ctx2.fillStyle = solidColor;
    ctx2.fillRect(0, 0, CANVAS_W, CANVAS_H);
    return;
  }
  const { x0, y0, x1, y1 } = gradientEndpoints(gradAngle, CANVAS_W, CANVAS_H);
  const g = ctx2.createLinearGradient(x0, y0, x1, y1);
  g.addColorStop(0, gradStart);
  g.addColorStop(1, gradEnd);
  ctx2.fillStyle = g;
  ctx2.fillRect(0, 0, CANVAS_W, CANVAS_H);
}

function drawTitle(ctx2) {
  const text = state.title.trim();
  if (!text) return;
  const maxW = CANVAS_W * state.maxTextWidthRatio;
  ctx2.font = buildFontString();
  ctx2.textAlign = "center";
  ctx2.textBaseline = "top";
  const { lines, lineHeight } = measureTextBlock(text, maxW);
  const cx = state.textX * CANVAS_W;
  const cy = state.textY * CANVAS_H;
  const totalH = lines.length * lineHeight;
  let y = cy - totalH / 2;
  ctx2.fillStyle = state.color;
  const lw = Math.max(2, state.fontSize * 0.08);
  for (const ln of lines) {
    if (state.textStroke) {
      ctx2.lineJoin = "round";
      ctx2.lineWidth = lw;
      ctx2.strokeStyle = "rgba(0,0,0,0.55)";
      ctx2.strokeText(ln, cx, y);
    }
    ctx2.fillText(ln, cx, y);
    y += lineHeight;
  }
}

/**
 * @param {{ chrome?: boolean }} [opts] - When chrome is false, selection box is omitted (use for PNG export).
 */
function render(opts) {
  if (!ctx) return;
  const showChrome = !opts || opts.chrome !== false;
  drawBackground(ctx);
  drawPictureLayers(ctx);
  drawTitle(ctx);
  if (showChrome) drawLayerChrome(ctx);
}

function syncFormFromState(els) {
  els.title.value = state.title;
  els.fontSize.value = String(state.fontSize);
  els.fontSizeVal.textContent = `${state.fontSize}px`;
  els.fontFamily.value = state.fontFamily;
  els.textColor.value = state.color;
  els.bold.setAttribute("aria-pressed", String(state.bold));
  if (els.italic) els.italic.setAttribute("aria-pressed", String(state.italic));
  els.bgType.value = state.bgType;
  els.solidColor.value = state.solidColor;
  els.gradStart.value = state.gradStart;
  els.gradEnd.value = state.gradEnd;
  els.gradAngle.value = String(state.gradAngle);
  els.gradAngleVal.textContent = `${state.gradAngle}°`;
  toggleBgPanels(els);
  updateLayerPanel(els);
}

function toggleBgPanels(els) {
  const t = state.bgType;
  els.panelSolid.hidden = t !== "solid";
  els.panelGradient.hidden = t !== "gradient";
  els.panelImage.hidden = t !== "image";
}

function showToast(host, message, type = "info") {
  if (!host) return;
  const el = document.createElement("div");
  el.className = `tsg-toast tsg-toast--${type}`;
  el.setAttribute("role", "status");
  el.textContent = message;
  host.appendChild(el);
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transform = "translateY(8px)";
    setTimeout(() => el.remove(), 300);
  }, 3800);
}

function setLoading(overlay, on) {
  overlay.classList.toggle("is-visible", on);
  overlay.setAttribute("aria-hidden", on ? "false" : "true");
}

function bindTheme(btn) {
  const root = document.documentElement;
  const stored = localStorage.getItem("tsg-theme");
  if (stored === "light" || stored === "dark") {
    root.setAttribute("data-theme", stored);
  } else {
    root.setAttribute("data-theme", "dark");
  }
  const updateIcon = () => {
    const t = root.getAttribute("data-theme");
    btn.textContent = t === "dark" ? "☀️" : "🌙";
    btn.setAttribute("aria-label", t === "dark" ? "Switch to light mode" : "Switch to dark mode");
    btn.setAttribute("data-tooltip", t === "dark" ? "Light mode" : "Dark mode");
  };
  updateIcon();
  btn.addEventListener("click", () => {
    const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    localStorage.setItem("tsg-theme", next);
    updateIcon();
    render();
  });
}

function loadImageFile(file) {
  return new Promise((resolve, reject) => {
    if (!file) {
      reject(new Error("No file selected."));
      return;
    }
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Could not read that image file."));
    reader.onload = () => {
      const dataUrl = typeof reader.result === "string" ? reader.result : "";
      if (!dataUrl) {
        reject(new Error("Could not read that image data."));
        return;
      }
      const img = new Image();
      img.decoding = "async";
      img.onload = async () => {
        if (typeof img.decode === "function") {
          await img.decode().catch(() => {});
        }
        resolve(img);
      };
      img.onerror = () => reject(new Error("Could not decode that image. Try JPG, PNG, or WebP."));
      img.src = dataUrl;
    };
    reader.readAsDataURL(file);
  });
}

async function applyBackgroundFile(file, els) {
  if (!file) return false;
  if (els.bgStatus) {
    const kb = Math.max(1, Math.round((file.size || 0) / 1024));
    els.bgStatus.textContent = `Background status: loading ${file.name} (${kb} KB)...`;
    els.bgStatus.style.color = "var(--tsg-muted)";
  }
  try {
    const img = await loadImageFile(file);
    state.bgImage = img;
    state.bgType = "image";
    state.pictureLayers = [];
    state.selectedLayerId = null;
    if (els.bgType) els.bgType.value = "image";
    toggleBgPanels(els);
    updateLayerPanel(els);
    render({ chrome: true });
    requestAnimationFrame(() => render({ chrome: true }));
    if (els.bgStatus) {
      els.bgStatus.textContent = `Background status: image loaded (${file.name}).`;
      els.bgStatus.style.color = "var(--tsg-success)";
    }
    showToast(els.toastHost, "Image applied as background.", "success");
    return true;
  } catch (err) {
    const message = err && typeof err.message === "string" ? err.message : "Could not add that picture.";
    if (els.bgStatus) {
      els.bgStatus.textContent = `Background status: ${message}`;
      els.bgStatus.style.color = "var(--tsg-danger)";
    }
    showToast(els.toastHost, message, "error");
    return false;
  }
}

function updateLayerPanel(els) {
  if (!els || !els.layerPanel) return;
  if (els.layerCountLabel) {
    els.layerCountLabel.textContent = state.bgImage
      ? "Background image selected."
      : "No background image selected yet.";
  }
  if (els.bgStatus) {
    if (state.bgImage) {
      els.bgStatus.textContent = "Background status: image loaded.";
      els.bgStatus.style.color = "var(--tsg-success)";
    } else {
      els.bgStatus.textContent = "Background status: using gradient/solid colors.";
      els.bgStatus.style.color = "var(--tsg-muted)";
    }
  }
  els.layerPanel.hidden = true;
}

async function addPictureFiles(files, els) {
  const first = Array.isArray(files) ? files[0] : null;
  if (!first) {
    showToast(els.toastHost, "No images were added. Try JPG/PNG/WebP.", "error");
    return false;
  }
  const ok = await applyBackgroundFile(first, els);
  if (ok) scheduleRenderFn?.();
  return ok;
}

/** Set from init so addPictureFiles can request a render before scheduleRender exists. */
let scheduleRenderFn = null;

function wirePictureDrop(zone, input, els) {
  if (!zone || !input) {
    console.warn("Thumbnail Studio: picture drop (#tsg-drop-layer / #tsg-file-layer) not found — restart the server to reload embedded JS.");
    return;
  }
  zone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      input.click();
    }
  });
  input.addEventListener("change", () => {
    const files = input.files ? Array.from(input.files) : [];
    if (!files.length) return;
    void (async () => {
      try {
        await addPictureFiles(files, els);
      } catch (err) {
        console.error(err);
      } finally {
        input.value = "";
      }
    })();
  });
  const cap = true;
  ["dragenter", "dragover"].forEach((ev) => {
    zone.addEventListener(
      ev,
      (e) => {
        e.preventDefault();
        zone.classList.add("tsg-drop--active");
      },
      cap,
    );
  });
  zone.addEventListener(
    "dragleave",
    (e) => {
      e.preventDefault();
      zone.classList.remove("tsg-drop--active");
    },
    cap,
  );
  zone.addEventListener(
    "drop",
    (e) => {
      e.preventDefault();
      zone.classList.remove("tsg-drop--active");
      const dt = e.dataTransfer?.files;
      if (dt?.length) void addPictureFiles(Array.from(dt), els).catch((err) => console.error(err));
    },
    cap,
  );
}

function initThumbnailStudio() {
  canvas = document.getElementById("tsg-canvas");
  if (!canvas) return;
  ctx = canvas.getContext("2d");
  if (!ctx) {
    console.error("Thumbnail Studio: 2D canvas context not available.");
    return;
  }
  canvas.width = CANVAS_W;
  canvas.height = CANVAS_H;

  const els = {
    title: document.getElementById("tsg-title"),
    fontSize: document.getElementById("tsg-font-size"),
    fontSizeVal: document.getElementById("tsg-font-size-val"),
    fontFamily: document.getElementById("tsg-font-family"),
    textColor: document.getElementById("tsg-text-color"),
    bold: document.getElementById("tsg-bold"),
    italic: document.getElementById("tsg-italic"),
    bgType: document.getElementById("tsg-bg-type"),
    solidColor: document.getElementById("tsg-solid-color"),
    gradStart: document.getElementById("tsg-grad-start"),
    gradEnd: document.getElementById("tsg-grad-end"),
    gradAngle: document.getElementById("tsg-grad-angle"),
    gradAngleVal: document.getElementById("tsg-grad-angle-val"),
    panelSolid: document.getElementById("tsg-panel-solid"),
    panelGradient: document.getElementById("tsg-panel-gradient"),
    panelImage: document.getElementById("tsg-panel-image"),
    dropBg: document.getElementById("tsg-drop-bg"),
    fileBg: document.getElementById("tsg-file-bg"),
    dropLayer: document.getElementById("tsg-drop-layer"),
    fileLayer: document.getElementById("tsg-file-layer"),
    layerPanel: document.getElementById("tsg-layer-controls"),
    layerWidth: document.getElementById("tsg-layer-width"),
    layerWidthVal: document.getElementById("tsg-layer-width-val"),
    layerFront: document.getElementById("tsg-layer-front"),
    layerBack: document.getElementById("tsg-layer-back"),
    layerDelete: document.getElementById("tsg-layer-delete"),
    layerCountLabel: document.getElementById("tsg-layer-count"),
    bgStatus: document.getElementById("tsg-bg-status"),
    btnGenerate: document.getElementById("tsg-generate"),
    btnDownload: document.getElementById("tsg-download"),
    btnReset: document.getElementById("tsg-reset"),
    loading: document.getElementById("tsg-loading"),
    toastHost: document.getElementById("tsg-toast-host"),
    themeToggle: document.getElementById("tsg-theme-toggle"),
  };

  const required = [
    "title",
    "fontSize",
    "fontSizeVal",
    "fontFamily",
    "textColor",
    "bold",
    "bgType",
    "solidColor",
    "gradStart",
    "gradEnd",
    "gradAngle",
    "gradAngleVal",
    "panelSolid",
    "panelGradient",
    "panelImage",
    "dropBg",
    "fileBg",
    "btnGenerate",
    "btnDownload",
    "btnReset",
    "loading",
    "toastHost",
  ];
  for (const key of required) {
    if (!els[key]) {
      console.error("Thumbnail Studio: missing DOM element for", key);
      return;
    }
  }

  const themeBtn = els.themeToggle;
  if (themeBtn) bindTheme(themeBtn);

  syncFormFromState(els);

  const scheduleRender = () => {
    requestAnimationFrame(() => render());
  };
  scheduleRenderFn = scheduleRender;

  afterFontsReady(() => {
    render();
  });

  if (els.fileLayer) {
    els.fileLayer.addEventListener("change", async () => {
      const files = els.fileLayer.files ? Array.from(els.fileLayer.files) : [];
      if (!files.length) return;
      try {
        await addPictureFiles(files, els);
      } catch (err) {
        console.error(err);
      }
    });
  }

  // Hard fallback: direct HTML onchange can call this even if listeners drift.
  window.__tsgApplyBackgroundFromInput = async (inputEl) => {
    try {
      const files = inputEl && inputEl.files ? Array.from(inputEl.files) : [];
      if (!files.length) return false;
      return await addPictureFiles(files, els);
    } catch (err) {
      console.error(err);
      return false;
    }
  };

  if (els.layerWidth) {
    els.layerWidth.addEventListener("input", () => {
      const sel = selectedLayer();
      if (!sel) return;
      const nw = Math.max(48, Number(els.layerWidth.value) || 48);
      const ar = sel.img.naturalHeight / Math.max(1, sel.img.naturalWidth);
      const cx = sel.x + sel.w / 2;
      const cy = sel.y + sel.h / 2;
      sel.w = Math.min(1200, nw);
      sel.h = sel.w * ar;
      sel.x = cx - sel.w / 2;
      sel.y = cy - sel.h / 2;
      if (els.layerWidthVal) els.layerWidthVal.textContent = `${Math.round(sel.w)} px wide`;
      scheduleRender();
    });
  }

  if (els.layerFront) {
    els.layerFront.addEventListener("click", () => {
      const id = state.selectedLayerId;
      const idx = state.pictureLayers.findIndex((l) => l.id === id);
      if (idx < 0 || idx >= state.pictureLayers.length - 1) return;
      const [sp] = state.pictureLayers.splice(idx, 1);
      state.pictureLayers.push(sp);
      scheduleRender();
    });
  }

  if (els.layerBack) {
    els.layerBack.addEventListener("click", () => {
      const id = state.selectedLayerId;
      const idx = state.pictureLayers.findIndex((l) => l.id === id);
      if (idx <= 0) return;
      const [sp] = state.pictureLayers.splice(idx, 1);
      state.pictureLayers.splice(idx - 1, 0, sp);
      scheduleRender();
    });
  }

  if (els.layerDelete) {
    els.layerDelete.addEventListener("click", () => {
      const id = state.selectedLayerId;
      state.pictureLayers = state.pictureLayers.filter((l) => l.id !== id);
      state.selectedLayerId = null;
      updateLayerPanel(els);
      scheduleRender();
    });
  }

  updateLayerPanel(els);

  els.title.addEventListener("input", () => {
    state.title = els.title.value;
    scheduleRender();
  });

  els.fontSize.addEventListener("input", () => {
    state.fontSize = Math.max(16, Math.min(160, Number(els.fontSize.value) || 64));
    els.fontSizeVal.textContent = `${state.fontSize}px`;
    scheduleRender();
  });

  els.fontFamily.addEventListener("change", () => {
    state.fontFamily = els.fontFamily.value;
    afterFontsReady(scheduleRender);
  });

  els.textColor.addEventListener("input", () => {
    state.color = els.textColor.value;
    scheduleRender();
  });

  function toggleChip(btn, key) {
    btn.addEventListener("click", () => {
      state[key] = !state[key];
      btn.setAttribute("aria-pressed", String(state[key]));
      scheduleRender();
    });
  }
  toggleChip(els.bold, "bold");
  if (els.italic) toggleChip(els.italic, "italic");

  els.bgType.addEventListener("change", () => {
    state.bgType = els.bgType.value;
    toggleBgPanels(els);
    scheduleRender();
  });

  els.solidColor.addEventListener("input", () => {
    state.solidColor = els.solidColor.value;
    scheduleRender();
  });
  els.gradStart.addEventListener("input", () => {
    state.gradStart = els.gradStart.value;
    scheduleRender();
  });
  els.gradEnd.addEventListener("input", () => {
    state.gradEnd = els.gradEnd.value;
    scheduleRender();
  });
  els.gradAngle.addEventListener("input", () => {
    state.gradAngle = Number(els.gradAngle.value) || 0;
    els.gradAngleVal.textContent = `${state.gradAngle}°`;
    scheduleRender();
  });

  function wireDrop(zone, input, onFile) {
    if (!zone || !input) return;
    zone.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        input.click();
      }
    });
    input.addEventListener("change", () => {
      const f = input.files?.[0];
      if (!f) return;
      void (async () => {
        try {
          await onFile(f);
        } finally {
          input.value = "";
        }
      })();
    });
    const cap = true;
    ["dragenter", "dragover"].forEach((ev) => {
      zone.addEventListener(
        ev,
        (e) => {
          e.preventDefault();
          zone.classList.add("tsg-drop--active");
        },
        cap,
      );
    });
    zone.addEventListener(
      "dragleave",
      (e) => {
        e.preventDefault();
        zone.classList.remove("tsg-drop--active");
      },
      cap,
    );
    zone.addEventListener(
      "drop",
      (e) => {
        e.preventDefault();
        zone.classList.remove("tsg-drop--active");
        const f = e.dataTransfer?.files?.[0];
        if (f) onFile(f);
      },
      cap,
    );
  }

  wireDrop(els.dropBg, els.fileBg, async (file) => {
    try {
      const img = await loadImageFile(file);
      state.bgImage = img;
      state.bgType = "image";
      els.bgType.value = "image";
      toggleBgPanels(els);
      showToast(els.toastHost, "Background image applied.", "success");
      scheduleRender();
    } catch (err) {
      showToast(els.toastHost, err.message, "error");
    }
  });

  document.querySelectorAll("[data-preset]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.getAttribute("data-preset");
      const fn = PRESETS[key];
      if (!fn) return;
      state = fn();
      state.bgImage = null;
      state.pictureLayers = [];
      state.selectedLayerId = null;
      syncFormFromState(els);
      showToast(els.toastHost, `Applied “${btn.textContent.trim()}” preset.`, "success");
      afterFontsReady(scheduleRender);
    });
  });

  function updateHoverCursor(clientX, clientY) {
    if (!canvas || dragMode !== "none") return;
    const { x, y } = canvasCoords(clientX, clientY);
    const sel = selectedLayer();
    if (sel && hitSEHandle(sel, x, y)) {
      canvas.style.cursor = "nwse-resize";
      return;
    }
    if (hitPictureLayerAt(x, y) || hitTestTextCanvas(x, y)) {
      canvas.style.cursor = "grab";
      return;
    }
    canvas.style.cursor = "";
  }

  function beginDrag(clientX, clientY) {
    const p = canvasCoords(clientX, clientY);
    const sel = selectedLayer();
    if (sel && hitSEHandle(sel, p.x, p.y)) {
      dragMode = "layer-resize";
      dragLayerId = sel.id;
      resizeAnchor = {
        ax: sel.x,
        ay: sel.y,
        ar: sel.img.naturalHeight / Math.max(1, sel.img.naturalWidth),
      };
      canvas.classList.add("tsg-dragging");
      return true;
    }

    if (hitTestTextCanvas(p.x, p.y)) {
      state.selectedLayerId = null;
      updateLayerPanel(els);
      dragMode = "text";
      canvas.classList.add("tsg-dragging");
      const c = getTextCenterPx();
      textPointerOffset = { x: p.x - c.x, y: p.y - c.y };
      scheduleRender();
      return true;
    }

    const layerHit = hitPictureLayerAt(p.x, p.y);
    if (layerHit) {
      state.selectedLayerId = layerHit.id;
      dragMode = "layer-move";
      dragLayerId = layerHit.id;
      moveStart = { mx: p.x, my: p.y, lx: layerHit.x, ly: layerHit.y };
      canvas.classList.add("tsg-dragging");
      updateLayerPanel(els);
      scheduleRender();
      return true;
    }

    state.selectedLayerId = null;
    updateLayerPanel(els);
    scheduleRender();
    return false;
  }

  function moveDrag(clientX, clientY) {
    const p = canvasCoords(clientX, clientY);
    if (dragMode === "layer-move") {
      const L = state.pictureLayers.find((l) => l.id === dragLayerId);
      if (L && moveStart) {
        L.x = moveStart.lx + (p.x - moveStart.mx);
        L.y = moveStart.ly + (p.y - moveStart.my);
        const margin = 120;
        L.x = Math.min(CANVAS_W + margin - L.w, Math.max(-margin, L.x));
        L.y = Math.min(CANVAS_H + margin - L.h, Math.max(-margin, L.y));
      }
      scheduleRender();
      return;
    }
    if (dragMode === "layer-resize" && resizeAnchor) {
      const L = state.pictureLayers.find((l) => l.id === dragLayerId);
      if (L) {
        const { ax, ay, ar } = resizeAnchor;
        const effX = Math.max(ax + 48, Math.min(CANVAS_W, p.x));
        let nw = effX - ax;
        let nh = nw * ar;
        if (ay + nh > CANVAS_H) {
          nh = CANVAS_H - ay;
          nw = nh / ar;
        }
        L.x = ax;
        L.y = ay;
        L.w = nw;
        L.h = nh;
        if (els.layerWidth) els.layerWidth.value = String(Math.round(nw));
        if (els.layerWidthVal) els.layerWidthVal.textContent = `${Math.round(nw)} px wide`;
      }
      scheduleRender();
      return;
    }
    if (dragMode === "text") {
      let nx = (p.x - textPointerOffset.x) / CANVAS_W;
      let ny = (p.y - textPointerOffset.y) / CANVAS_H;
      nx = Math.min(0.94, Math.max(0.06, nx));
      ny = Math.min(0.94, Math.max(0.06, ny));
      state.textX = nx;
      state.textY = ny;
      scheduleRender();
    }
  }

  function endDrag() {
    dragMode = "none";
    dragLayerId = null;
    moveStart = null;
    resizeAnchor = null;
    canvas.classList.remove("tsg-dragging");
    canvas.style.cursor = "";
  }

  canvas.addEventListener("mousedown", (e) => {
    beginDrag(e.clientX, e.clientY);
  });

  canvas.addEventListener("mousemove", (e) => {
    updateHoverCursor(e.clientX, e.clientY);
  });

  window.addEventListener("mousemove", (e) => {
    moveDrag(e.clientX, e.clientY);
  });

  window.addEventListener("mouseup", endDrag);

  canvas.addEventListener(
    "touchstart",
    (e) => {
      const t = e.touches[0];
      if (beginDrag(t.clientX, t.clientY)) e.preventDefault();
    },
    { passive: false },
  );

  window.addEventListener(
    "touchmove",
    (e) => {
      if (dragMode === "none") return;
      e.preventDefault();
      const t = e.touches[0];
      if (t) moveDrag(t.clientX, t.clientY);
    },
    { passive: false },
  );

  window.addEventListener("touchend", endDrag);

  els.btnGenerate.addEventListener("click", async () => {
    if (!state.title.trim()) {
      showToast(els.toastHost, "Add a title or use presets — empty text exports a blank canvas.", "info");
    }
    const fileInputNow = /** @type {HTMLInputElement|null} */ (document.getElementById("tsg-file-layer"));
    if (els.bgStatus) {
      els.bgStatus.textContent = "Background status: Generate clicked, checking selected file...";
      els.bgStatus.style.color = "var(--tsg-muted)";
    }
    if (fileInputNow && fileInputNow.files && fileInputNow.files[0]) {
      try {
        await applyBackgroundFile(fileInputNow.files[0], els);
      } catch (err) {
        console.error(err);
      }
    }
    if (state.bgImage) {
      state.bgType = "image";
      if (els.bgType) els.bgType.value = "image";
      toggleBgPanels(els);
    }
    setLoading(els.loading, true);
    els.btnGenerate.disabled = true;
    await new Promise((r) => setTimeout(r, 450));
    render({ chrome: false });
    setLoading(els.loading, false);
    els.btnGenerate.disabled = false;
    render({ chrome: true });
    showToast(els.toastHost, "Thumbnail rendered at 1280×720.", "success");
  });

  // Inline fallback hook used by button onclick in case normal listeners are stale.
  window.__tsgForceGenerate = async () => {
    const fileInputNow = /** @type {HTMLInputElement|null} */ (document.getElementById("tsg-file-layer"));
    if (fileInputNow && fileInputNow.files && fileInputNow.files[0]) {
      try {
        await applyBackgroundFile(fileInputNow.files[0], els);
      } catch (err) {
        console.error(err);
      }
    }
  };

  els.btnDownload.addEventListener("click", () => {
    void (async () => {
      const fileInputNow = /** @type {HTMLInputElement|null} */ (document.getElementById("tsg-file-layer"));
      if (fileInputNow && fileInputNow.files && fileInputNow.files[0]) {
        try {
          await applyBackgroundFile(fileInputNow.files[0], els);
        } catch (err) {
          console.error(err);
        }
      }
      if (state.bgImage) {
        state.bgType = "image";
        if (els.bgType) els.bgType.value = "image";
        toggleBgPanels(els);
      }
      render({ chrome: false });
      canvas.toBlob(
        (blob) => {
          render({ chrome: true });
          if (!blob) {
            showToast(els.toastHost, "Could not create image file.", "error");
            return;
          }
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = "youtube-thumbnail.png";
          a.click();
          URL.revokeObjectURL(a.href);
          showToast(els.toastHost, "Download started (PNG, 16:9).", "success");
        },
        "image/png",
        1,
      );
    })();
  });

  els.btnReset.addEventListener("click", () => {
    state = defaultState();
    state.bgImage = null;
    state.pictureLayers = [];
    state.selectedLayerId = null;
    syncFormFromState(els);
    showToast(els.toastHost, "Reset to defaults.", "info");
    afterFontsReady(scheduleRender);
  });
}

function bootThumbnailStudio() {
  try {
    initThumbnailStudio();
  } catch (err) {
    console.error("Thumbnail Studio failed to start:", err);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootThumbnailStudio);
} else {
  bootThumbnailStudio();
}
