/* ─── RecipeSnap — shared frontend JS ─────────────────────────────── */

let currentRecipe = null;

// ─── Home page: Extract recipe ──────────────────────────────────────

async function startExtraction() {
  const urlInput = document.getElementById("video-url");
  const url = (urlInput?.value || "").trim();

  if (!url) {
    showError("Please paste a video URL first.");
    return;
  }

  setLoading(true, "Fetching video info…");
  hideError();
  hidePreview();

  try {
    // Step 1: start extraction
    setLoading(true, "Extracting transcript from video…");

    const res = await authFetch("/api/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url })
    });

    const data = await res.json();

    if (!res.ok || data.error) {
      throw new Error(data.error || "Something went wrong. Please try again.");
    }

    // Step 2: show result
    setLoading(false);
    currentRecipe = data.recipe;
    currentRecipe.source_url = url;
    showRecipePreview(currentRecipe);

  } catch (err) {
    setLoading(false);
    const msg = err.message || "An unexpected error occurred.";
    showError(msg + " You can paste the transcript manually below.");
    showManual();
  }
}

function setLoading(on, message) {
  const statusArea = document.getElementById("status-area");
  const statusText = document.getElementById("status-text");
  const btn = document.getElementById("extract-btn");
  const urlInput = document.getElementById("video-url");

  if (!statusArea) return;

  if (on) {
    statusArea.classList.remove("hidden");
    if (statusText && message) statusText.textContent = message;
    if (btn) { btn.disabled = true; btn.textContent = "Processing…"; }
    if (urlInput) urlInput.disabled = true;
  } else {
    statusArea.classList.add("hidden");
    if (btn) { btn.disabled = false; btn.textContent = "Get Recipe"; }
    if (urlInput) urlInput.disabled = false;
  }
}

function showError(msg) {
  const errorArea = document.getElementById("error-area");
  const errorText = document.getElementById("error-text");
  if (!errorArea) return;
  errorArea.classList.remove("hidden");
  if (errorText) errorText.textContent = msg;
}

function hideError() {
  const errorArea = document.getElementById("error-area");
  if (errorArea) errorArea.classList.add("hidden");
}

function hidePreview() {
  const preview = document.getElementById("recipe-preview");
  if (preview) preview.classList.add("hidden");
}

function resetForm() {
  hidePreview();
  hideError();
  const urlInput = document.getElementById("video-url");
  if (urlInput) { urlInput.value = ""; urlInput.focus(); }
  currentRecipe = null;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function showRecipePreview(recipe) {
  const previewSection = document.getElementById("recipe-preview");
  if (!previewSection) return;

  // Platform & source
  const platformBadge = document.getElementById("preview-platform");
  const sourceLink = document.getElementById("preview-source");
  if (platformBadge) platformBadge.textContent = recipe.platform || "";
  if (sourceLink && recipe.source_url) sourceLink.href = recipe.source_url;

  // Title & description
  // Video embed
  const thumbWrap  = document.getElementById("preview-thumb-wrap");
  const embedDiv   = document.getElementById("preview-embed");
  const platform   = recipe.platform || "";
  const sourceUrl  = recipe.source_url || "";
  embedDiv.innerHTML = "";
  if (sourceUrl) {
    let embedHtml = "";
    if (platform === "YouTube") {
      // Extract YouTube video ID
      const ytMatch = sourceUrl.match(/[?&]v=([a-zA-Z0-9_-]{11})/) ||
                      sourceUrl.match(/youtu\.be\/([a-zA-Z0-9_-]{11})/);
      if (ytMatch) {
        embedHtml = `<iframe width="100%" height="280" src="https://www.youtube.com/embed/${ytMatch[1]}" frameborder="0" allowfullscreen style="border-radius:12px;"></iframe>`;
      }
    } else if (platform === "Facebook") {
      const encoded = encodeURIComponent(sourceUrl);
      embedHtml = `<iframe src="https://www.facebook.com/plugins/video.php?href=${encoded}&show_text=false&width=500" width="100%" height="280" frameborder="0" allowfullscreen style="border-radius:12px;"></iframe>`;
    } else if (platform === "TikTok") {
      // TikTok embed — extract video ID
      const ttMatch = sourceUrl.match(/video\/(\d+)/);
      if (ttMatch) {
        embedHtml = `<blockquote class="tiktok-embed" cite="${sourceUrl}" data-video-id="${ttMatch[1]}" style="border-radius:12px;"><section></section></blockquote><script async src="https://www.tiktok.com/embed.js"><\/script>`;
      }
    } else if (platform === "Instagram") {
      embedHtml = `<iframe src="${sourceUrl.replace(/\/$/, '')}/embed" width="100%" height="480" frameborder="0" allowfullscreen style="border-radius:12px;"></iframe>`;
    }
    if (embedHtml) {
      embedDiv.innerHTML = embedHtml;
      thumbWrap.classList.remove("hidden");
    } else if (recipe.thumbnail_url) {
      embedDiv.innerHTML = `<img src="${recipe.thumbnail_url}" style="width:100%;border-radius:12px;max-height:280px;object-fit:cover;" onerror="document.getElementById('preview-thumb-wrap').classList.add('hidden')" />`;
      thumbWrap.classList.remove("hidden");
    } else {
      thumbWrap.classList.add("hidden");
    }
  } else {
    thumbWrap.classList.add("hidden");
  }
  setText("preview-title", recipe.title);
  setText("preview-description", recipe.description);

  // Details
  setDetailItem("detail-servings-wrap", "detail-servings", recipe.servings);
  setDetailItem("detail-prep-wrap", "detail-prep", recipe.prep_time);
  setDetailItem("detail-cook-wrap", "detail-cook", recipe.cook_time);
  setDetailItem("detail-diff-wrap", "detail-difficulty", recipe.difficulty);

  // Ingredients
  const ingList = document.getElementById("ingredients-list");
  if (ingList) {
    ingList.innerHTML = (recipe.ingredients || [])
      .map(i => `<li>${escapeHtml(i)}</li>`)
      .join("");
  }

  // Instructions
  const insList = document.getElementById("instructions-list");
  if (insList) {
    insList.innerHTML = (recipe.instructions || [])
      .map(s => `<li>${escapeHtml(s)}</li>`)
      .join("");
  }

  // Tips
  const tipsBlock = document.getElementById("tips-block");
  const tipsText = document.getElementById("tips-text");
  if (tipsBlock && tipsText) {
    if (recipe.tips && recipe.tips.trim()) {
      tipsText.textContent = recipe.tips;
      tipsBlock.classList.remove("hidden");
    } else {
      tipsBlock.classList.add("hidden");
    }
  }

  previewSection.classList.remove("hidden");
  previewSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

function setDetailItem(wrapId, valueId, value) {
  const wrap = document.getElementById(wrapId);
  const el = document.getElementById(valueId);
  if (!wrap || !el) return;
  if (value && value.trim()) {
    el.textContent = value;
    wrap.classList.remove("hidden");
  } else {
    wrap.classList.add("hidden");
  }
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value || "";
}

// ─── Save recipe ────────────────────────────────────────────────────

async function saveRecipe() {
  if (!currentRecipe) return;

  const saveBtn = document.querySelector(".preview-actions .btn-primary");
  const saveStatus = document.getElementById("save-status");
  if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = "Saving…"; }

  try {
    const res = await authFetch("/api/recipes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentRecipe)
    });
    const data = await res.json();

    if (!res.ok || data.error) throw new Error(data.error || "Save failed");

    if (saveStatus) {
      saveStatus.classList.remove("hidden");
      saveStatus.textContent = "✅ Recipe saved! Redirecting to your library…";
    }

    setTimeout(() => { window.location.href = "/library"; }, 1500);

  } catch (err) {
    if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = "💾 Save to My Recipes"; }
    if (saveStatus) {
      saveStatus.classList.remove("hidden");
      saveStatus.style.color = "var(--hard)";
      saveStatus.textContent = "❌ " + (err.message || "Save failed. Please try again.");
    }
  }
}

// ─── Manual paste flow ──────────────────────────────────────────────

function showManual() {
  const area = document.getElementById("manual-area");
  if (area) {
    area.classList.remove("hidden");
    area.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function hideManual() {
  const area = document.getElementById("manual-area");
  if (area) area.classList.add("hidden");
  hideError();
}

async function extractFromText() {
  const text = (document.getElementById("manual-text")?.value || "").trim();
  const url  = (document.getElementById("video-url")?.value || "").trim();

  if (!text) {
    const err = document.getElementById("manual-error");
    if (err) { err.textContent = "Please paste some text first."; err.classList.remove("hidden"); }
    return;
  }

  const statusEl = document.getElementById("manual-status");
  const errorEl  = document.getElementById("manual-error");
  if (statusEl) statusEl.classList.remove("hidden");
  if (errorEl)  errorEl.classList.add("hidden");

  try {
    const res = await authFetch("/api/extract-text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, url })
    });
    const data = await res.json();

    if (!res.ok || data.error) throw new Error(data.error || "Extraction failed");

    if (statusEl) statusEl.classList.add("hidden");
    currentRecipe = data.recipe;
    currentRecipe.source_url = url;
    hideManual();
    showRecipePreview(currentRecipe);

  } catch (err) {
    if (statusEl) statusEl.classList.add("hidden");
    if (errorEl) {
      errorEl.textContent = err.message || "Something went wrong.";
      errorEl.classList.remove("hidden");
    }
  }
}

// ─── Utilities ──────────────────────────────────────────────────────

function escapeHtml(str) {
  const d = document.createElement("div");
  d.textContent = str || "";
  return d.innerHTML;
}
