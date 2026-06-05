/* ------------------------------------------------------------------ *
 * EAN Pictures — lógica do front-end
 * Faz a busca via fetch, controla loading, erros e renderiza o card
 * do produto e o histórico, sem recarregar a página.
 * ------------------------------------------------------------------ */

const form = document.getElementById("search-form");
const input = document.getElementById("ean-input");
const providerSelect = document.getElementById("provider-select");
const btn = document.getElementById("search-btn");
const spinner = document.getElementById("spinner");
const message = document.getElementById("message");

const productCard = document.getElementById("product-card");
const productImg = document.getElementById("product-img");
const productName = document.getElementById("product-name");
const productEan = document.getElementById("product-ean");
const productDesc = document.getElementById("product-description");
const productExtra = document.getElementById("product-extra");
const productSource = document.getElementById("product-source");

const historyList = document.getElementById("history-list");
const historyEmpty = document.getElementById("history-empty");
const clearHistoryBtn = document.getElementById("clear-history-btn");

/* ---------------------- Placeholder visual (sem foto) ------------------- *
 * Em vez de um "Sem imagem" cinza, gera um card com gradiente colorido
 * (cor derivada do nome), as iniciais do produto e a marca. O SVG é
 * renderizado como <img> (data URI) — não executa script, então é seguro
 * mesmo com dados de terceiros (ainda assim escapamos o texto). */
function hashHue(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) % 360;
  return h;
}
function escapeXml(s) {
  return String(s).replace(
    /[<>&"']/g,
    (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;", "'": "&apos;" }[c])
  );
}
function initials(name) {
  const words = (name || "").trim().split(/\s+/).filter((w) => /[a-zA-Z0-9]/.test(w));
  if (!words.length) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}
function buildPlaceholder(p) {
  const name = p && p.name ? String(p.name) : "";
  const hue = hashHue(name || "produto");
  const c1 = `hsl(${hue} 62% 55%)`;
  const c2 = `hsl(${(hue + 45) % 360} 68% 40%)`;
  const extra = (p && p.extra) || {};
  const sub = String(extra.Marca || extra.Categoria || "Sem foto").slice(0, 24);
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="220" height="220">` +
    `<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">` +
    `<stop offset="0" stop-color="${c1}"/><stop offset="1" stop-color="${c2}"/>` +
    `</linearGradient></defs>` +
    `<rect width="100%" height="100%" rx="14" fill="url(#g)"/>` +
    `<text x="50%" y="45%" font-family="Inter,Arial,sans-serif" font-size="82" ` +
    `font-weight="700" fill="#fff" text-anchor="middle" dominant-baseline="middle">` +
    `${escapeXml(initials(name))}</text>` +
    `<text x="50%" y="80%" font-family="Inter,Arial,sans-serif" font-size="15" ` +
    `fill="rgba(255,255,255,0.9)" text-anchor="middle">${escapeXml(sub)}</text>` +
    `</svg>`;
  return "data:image/svg+xml;utf8," + encodeURIComponent(svg);
}

/* ------------------------------- Loading ------------------------------- */
function setLoading(loading) {
  btn.disabled = loading;
  spinner.hidden = !loading;
  btn.querySelector(".btn-label").textContent = loading
    ? "Buscando..."
    : "Buscar Produto";
}

/* ------------------------------- Mensagens ----------------------------- */
function showMessage(text, type = "error") {
  message.textContent = text;
  message.className = `message ${type}`;
  message.hidden = false;
}
function clearMessage() {
  message.hidden = true;
  message.textContent = "";
}

/* --------------------------- Render do produto ------------------------- */
function renderProduct(p) {
  const placeholder = buildPlaceholder(p);
  productImg.src = safeImageUrl(p.image) || placeholder;
  // Se a foto falhar ao carregar (proxy 404, link quebrado), cai no card visual.
  productImg.onerror = () => {
    productImg.onerror = null; // evita loop
    productImg.src = placeholder;
  };
  productName.textContent = p.name;
  productEan.textContent = p.ean;
  productDesc.textContent = p.description || "Sem descrição disponível.";

  // Informações extras (chave/valor).
  // Usamos textContent/DOM (nunca innerHTML) porque os valores vêm de
  // bases de terceiros e podem conter HTML malicioso (prevenção de XSS).
  productExtra.replaceChildren();
  const extra = p.extra || {};
  Object.keys(extra).forEach((key) => {
    const li = document.createElement("li");
    const label = document.createElement("span");
    label.textContent = `${key}: `;
    li.appendChild(label);
    li.appendChild(document.createTextNode(String(extra[key])));
    productExtra.appendChild(li);
  });

  productSource.textContent = p.from_cache
    ? `Fonte: ${p.source} (cache)`
    : `Fonte: ${p.source}`;

  productCard.hidden = false;
}

/* --------------------------- Render do histórico ----------------------- */
function renderHistory(items) {
  historyList.replaceChildren();
  if (!items || items.length === 0) {
    historyEmpty.hidden = false;
    return;
  }
  historyEmpty.hidden = true;

  items.forEach((item) => {
    // Tudo via DOM/textContent — dados de terceiros nunca entram como HTML.
    const li = document.createElement("li");
    li.className = "history-item";
    li.dataset.ean = item.ean;

    const img = document.createElement("img");
    img.alt = "";
    img.src = safeImageUrl(item.image);
    img.onerror = (e) => (e.target.style.visibility = "hidden");

    const div = document.createElement("div");
    const strong = document.createElement("strong");
    strong.textContent = item.name || "Produto";
    const small = document.createElement("small");
    small.textContent = `${item.ean} · ${item.timestamp}`;
    div.append(strong, small);

    li.append(img, div);
    li.addEventListener("click", () => {
      input.value = item.ean;
      buscar(item.ean);
    });
    historyList.appendChild(li);
  });
}

/* Aceita só http/https e caminhos same-origin (/img/...).
   Bloqueia javascript:, data:, etc. Protocolo-relativo (//host/...) vira https. */
function safeImageUrl(url) {
  if (typeof url !== "string") return "";
  const u = url.trim();
  if (u.startsWith("//")) return "https:" + u; // protocolo-relativo
  if (u.startsWith("/")) return u; // caminho same-origin (ex.: proxy /img/gtin/...)
  return /^https?:\/\//i.test(u) ? u : "";
}

/* ------------------------------- Busca --------------------------------- */
async function buscar(ean) {
  clearMessage();
  productCard.hidden = true;
  setLoading(true);

  try {
    const provider = providerSelect ? providerSelect.value : "auto";
    const resp = await fetch("/buscar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ean, provider }),
    });
    const data = await resp.json();

    if (data.ok) {
      renderProduct(data.product);
    } else {
      showMessage(data.error || "Ocorreu um erro na busca.");
    }
    if (data.history) renderHistory(data.history);
  } catch (err) {
    showMessage("Falha de conexão com o servidor. Tente novamente.");
  } finally {
    setLoading(false);
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const ean = input.value.trim();
  if (!ean) {
    showMessage("Digite um código EAN para buscar.");
    return;
  }
  buscar(ean);
});

document.querySelectorAll(".history-item").forEach((li) => {
  li.addEventListener("click", () => {
    const ean = li.dataset.ean;
    input.value = ean;
    buscar(ean);
  });
});

// Limpar histórico (binding defensivo: só liga se o botão existir).
if (clearHistoryBtn) {
  clearHistoryBtn.addEventListener("click", async () => {
    if (!confirm("Deseja limpar todo o histórico de consultas?")) return;
    clearHistoryBtn.disabled = true;
    try {
      const resp = await fetch("/api/history", { method: "DELETE" });
      if (resp.ok) {
        renderHistory([]);
      } else {
        showMessage("Não foi possível limpar o histórico.");
      }
    } catch (err) {
      showMessage("Falha de conexão ao limpar o histórico.");
    } finally {
      clearHistoryBtn.disabled = false;
    }
  });
}
