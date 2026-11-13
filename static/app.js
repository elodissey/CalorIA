/**
 * app.js — Logique de l'interface web CalorIA (JavaScript pur, sans bibliothèque externe).
 *
 * Ce script communique avec notre serveur Python `app.py` via `fetch(...)`
 * pour afficher les repas du jour, rechercher des produits et calculer les calories.
 */

// Repères caloriques de l'utilisateur connecté (mis à jour via /api/me)
let GOAL_MIN = 1650;
let GOAL_MAX = 1750;
let REF_KCAL = 1990;

// État courant de la page
let currentDate = getLocalTodayISO();
let localFoods = [];
let ciqualFoods = [];
let offFoods = [];
let userFavorites = [];
let selectedFood = null;

// Récupération des éléments HTML principaux
const currentUsernameEl = document.getElementById("current-username");
const logoutBtn = document.getElementById("logout-btn");
const datePicker = document.getElementById("date-picker");
const prevDayBtn = document.getElementById("prev-day");
const nextDayBtn = document.getElementById("next-day");
const todayBtn = document.getElementById("today-btn");

const dayTotalEl = document.getElementById("day-total-kcal");
const goalStatusEl = document.getElementById("goal-status");
const goalRangeTextEl = document.getElementById("goal-range-text");
const refKcalTextEl = document.getElementById("ref-kcal-text");
const refRemainingEl = document.getElementById("ref-remaining");
const progressGoalZoneEl = document.getElementById("progress-goal-zone");
const progressBarEl = document.getElementById("progress-bar");
const legendGoalEl = document.getElementById("legend-goal");
const legendRefEl = document.getElementById("legend-ref");

// Section Favoris (Option A)
const favoritesBarEl = document.getElementById("favorites-bar");
const favoritesListEl = document.getElementById("favorites-list");
const favoritesCountEl = document.getElementById("favorites-count");

const searchForm = document.getElementById("search-form");
const searchInput = document.getElementById("search-input");
const offSearchBtn = document.getElementById("off-search-btn");
const searchFeedback = document.getElementById("search-feedback");
const resultsContainer = document.getElementById("results-container");

const selectedBox = document.getElementById("selected-box");
const selectedFavBtn = document.getElementById("selected-fav-btn");
const selectedNameEl = document.getElementById("selected-name");
const selectedBrandEl = document.getElementById("selected-brand");
const selectedKcalInfoEl = document.getElementById("selected-kcal-info");
const clearSelectedBtn = document.getElementById("clear-selected");

const addEntryForm = document.getElementById("add-entry-form");
const mealSelect = document.getElementById("meal-select");
const qtyInput = document.getElementById("qty-input");
const unitSelect = document.getElementById("unit-select");
const portionWeightRow = document.getElementById("portion-weight-row");
const customPortionGramsInput = document.getElementById("custom-portion-grams");
const calcPreviewEl = document.getElementById("calc-preview");

const manualDetails = document.getElementById("manual-details");
const manualFoodForm = document.getElementById("manual-food-form");
const mealsContainer = document.getElementById("meals-container");
const historyChartEl = document.getElementById("history-chart");

// ------------------------------------------------------------------
// Utilitaires de dates et formatage
// ------------------------------------------------------------------

/** Renvoie la date d'aujourd'hui au format YYYY-MM-DD (heure locale). */
function getLocalTodayISO() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** Ajoute ou retire `deltaDays` jours à une date YYYY-MM-DD. */
function shiftDate(isoDate, deltaDays) {
  const [y, m, d] = isoDate.split("-").map(Number);
  const dateObj = new Date(y, m - 1, d);
  dateObj.setDate(dateObj.getDate() + deltaDays);
  const ny = dateObj.getFullYear();
  const nm = String(dateObj.getMonth() + 1).padStart(2, "0");
  const nd = String(dateObj.getDate()).padStart(2, "0");
  return `${ny}-${nm}-${nd}`;
}

/** Formate un nombre de calories proprement (ex: 1 650). */
function formatKcal(val) {
  return Math.round(Number(val) || 0).toLocaleString("fr-FR");
}

/** Affiche un message d'info ou d'erreur sous la barre de recherche. */
function showFeedback(message, isError = false) {
  if (!message) {
    searchFeedback.classList.add("hidden");
    searchFeedback.textContent = "";
    searchFeedback.classList.remove("error");
    return;
  }
  searchFeedback.textContent = message;
  searchFeedback.classList.remove("hidden");
  searchFeedback.classList.toggle("error", isError);
}

// ------------------------------------------------------------------
// Chargement des données du jour et de l'historique
// ------------------------------------------------------------------

async function loadDay(dateStr) {
  currentDate = dateStr;
  datePicker.value = currentDate;

  const response = await fetch(`/api/day?date=${encodeURIComponent(currentDate)}`);
  if (response.status === 401) {
    window.location.href = "/login";
    return;
  }
  const data = await response.json();

  renderSummary(data.total_kcal || 0);
  renderMeals(data.menus || [], data.partner || null);
  loadHistory();
  loadFavorites();
}

function renderSummary(totalKcal) {
  const rounded = Math.round(totalKcal);
  dayTotalEl.textContent = formatKcal(rounded);

  // Mise à jour du badge d'objectif selon les repères propres à l'utilisateur
  goalStatusEl.className = "badge";
  if (rounded < GOAL_MIN) {
    goalStatusEl.textContent = `Encore ${formatKcal(GOAL_MIN - rounded)} kcal pour atteindre l'objectif`;
  } else if (rounded <= GOAL_MAX) {
    goalStatusEl.textContent = "Dans l'objectif quotidien !";
    goalStatusEl.classList.add("in-goal");
  } else if (rounded <= REF_KCAL) {
    goalStatusEl.textContent = `Au-dessus de l'objectif, sous le repère de ${formatKcal(REF_KCAL)} kcal`;
    goalStatusEl.classList.add("above-goal");
  } else {
    goalStatusEl.textContent = `Repère de ${formatKcal(REF_KCAL)} kcal dépassé`;
    goalStatusEl.classList.add("above-ref");
  }

  // Écart par rapport au repère journalier personnel
  const diffRef = REF_KCAL - rounded;
  if (diffRef >= 0) {
    refRemainingEl.textContent = `Reste ${formatKcal(diffRef)} kcal par rapport au repère`;
  } else {
    refRemainingEl.textContent = `Dépassé de ${formatKcal(Math.abs(diffRef))} kcal`;
  }

  // Largeur de la barre de progression sur l'échelle 0 -> REF_KCAL
  const pct = Math.min(100, Math.max(0, (rounded / REF_KCAL) * 100));
  progressBarEl.style.width = `${pct.toFixed(1)}%`;
}

function renderMeals(menus, partner) {
  mealsContainer.innerHTML = "";

  for (const menu of menus) {
    const card = document.createElement("div");
    card.className = "meal-card";

    // En-tête du menu (nom + total kcal + bouton + rapide)
    const header = document.createElement("div");
    header.className = "meal-header";

    const title = document.createElement("span");
    title.className = "meal-title";
    title.textContent = menu.name;

    const right = document.createElement("div");
    right.className = "meal-right";

    const totalSpan = document.createElement("span");
    totalSpan.className = "meal-total";
    totalSpan.textContent = `${formatKcal(menu.total_kcal)} kcal`;

    const quickAddBtn = document.createElement("button");
    quickAddBtn.type = "button";
    quickAddBtn.className = "btn btn-secondary";
    quickAddBtn.textContent = "+";
    quickAddBtn.title = `Ajouter dans ${menu.name}`;
    quickAddBtn.addEventListener("click", () => {
      mealSelect.value = menu.name;
      searchInput.focus();
    });

    right.appendChild(totalSpan);
    right.appendChild(quickAddBtn);
    header.appendChild(title);
    header.appendChild(right);
    card.appendChild(header);

    // Liste des aliments dans ce menu
    if (!menu.entries || menu.entries.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-msg";
      empty.textContent = "Aucun aliment enregistré.";
      card.appendChild(empty);
    } else {
      const ul = document.createElement("ul");
      ul.className = "entry-list";

      for (const entry of menu.entries) {
        const li = document.createElement("li");
        li.className = "entry-item";

        const leftInfo = document.createElement("div");
        const nameEl = document.createElement("div");
        nameEl.textContent = entry.food_brand
          ? `${entry.food_name} (${entry.food_brand})`
          : entry.food_name;

        const qtyEl = document.createElement("div");
        qtyEl.className = "entry-qty";
        if (entry.unit === "portion") {
          qtyEl.textContent = `${entry.quantity} portion(s) · ${entry.grams_equivalent} g`;
        } else {
          qtyEl.textContent = `${entry.quantity} g`;
        }

        leftInfo.appendChild(nameEl);
        leftInfo.appendChild(qtyEl);

        const actions = document.createElement("div");
        actions.className = "entry-actions";

        const kcalEl = document.createElement("strong");
        kcalEl.textContent = `${formatKcal(entry.kcal_calculated)} kcal`;

        // Bouton Étoile Favori (Option A)
        const isFav = Boolean(entry.is_favorite);
        const favBtn = document.createElement("button");
        favBtn.type = "button";
        favBtn.className = `btn-fav ${isFav ? "active" : ""}`;
        favBtn.title = isFav ? "Retirer de mes favoris" : "Ajouter à mes favoris";
        favBtn.textContent = isFav ? "★" : "☆";
        favBtn.addEventListener("click", async (e) => {
          e.stopPropagation();
          await toggleFavorite({
            food_id: entry.food_id,
            default_meal: entry.meal_type,
            default_qty: entry.quantity,
            default_unit: entry.unit,
          });
        });

        const editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "btn-edit";
        editBtn.title = "Modifier la quantité ou le menu";
        editBtn.textContent = "✎";
        editBtn.addEventListener("click", () => openInlineEdit(li, entry));

        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "btn-delete";
        delBtn.title = "Supprimer cette ligne";
        delBtn.textContent = "×";
        delBtn.addEventListener("click", () => deleteEntry(entry.id));

        actions.appendChild(kcalEl);
        actions.appendChild(favBtn);
        actions.appendChild(editBtn);
        actions.appendChild(delBtn);

        li.appendChild(leftInfo);
        li.appendChild(actions);
        ul.appendChild(li);
      }

      card.appendChild(ul);
    }

    // Section dépliable pour copier aliment par aliment depuis l'autre utilisateur (s'il a saisi ce menu ce jour-là)
    const partnerEntries =
      partner && partner.by_menu && partner.by_menu[menu.name]
        ? partner.by_menu[menu.name]
        : [];
    if (partnerEntries.length > 0) {
      const details = document.createElement("details");
      details.className = "partner-box";

      const summary = document.createElement("summary");
      summary.textContent = `Chez ${partner.username} (${partnerEntries.length})`;
      details.appendChild(summary);

      const pList = document.createElement("ul");
      pList.className = "partner-list";

      for (const pEntry of partnerEntries) {
        const pLi = document.createElement("li");
        pLi.className = "partner-item";

        const pInfo = document.createElement("div");
        const pName = document.createElement("div");
        pName.textContent = pEntry.food_brand
          ? `${pEntry.food_name} (${pEntry.food_brand})`
          : pEntry.food_name;

        const pQty = document.createElement("div");
        pQty.className = "entry-qty";
        const qtyTxt =
          pEntry.unit === "portion"
            ? `${pEntry.quantity} portion(s) · ${pEntry.grams_equivalent} g`
            : `${pEntry.quantity} g`;
        pQty.textContent = `${qtyTxt} · ${formatKcal(pEntry.kcal_calculated)} kcal`;

        pInfo.appendChild(pName);
        pInfo.appendChild(pQty);

        const copyBtn = document.createElement("button");
        copyBtn.type = "button";
        copyBtn.className = "btn btn-secondary btn-sm";
        copyBtn.textContent = "+ Copier";
        copyBtn.addEventListener("click", () => copyFromPartner(pEntry.id, menu.name, copyBtn));

        pLi.appendChild(pInfo);
        pLi.appendChild(copyBtn);
        pList.appendChild(pLi);
      }

      details.appendChild(pList);
      card.appendChild(details);
    }

    mealsContainer.appendChild(card);
  }
}

async function copyFromPartner(sourceEntryId, mealType, btn) {
  btn.disabled = true;
  btn.textContent = "Copié !";
  const response = await fetch("/api/entries/copy", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_entry_id: sourceEntryId,
      entry_date: currentDate,
      meal_type: mealType,
    }),
  });
  if (response.ok) {
    loadDay(currentDate);
  } else {
    btn.disabled = false;
    btn.textContent = "+ Copier";
  }
}

/** Affiche un petit formulaire en ligne pour changer la quantité ou déplacer vers un autre menu. */
function openInlineEdit(li, entry) {
  li.className = "entry-item entry-editing";
  li.innerHTML = "";

  const title = document.createElement("div");
  title.className = "edit-title";
  title.textContent = entry.food_brand
    ? `${entry.food_name} (${entry.food_brand})`
    : entry.food_name;

  const form = document.createElement("form");
  form.className = "edit-inline-form";

  const qtyField = document.createElement("input");
  qtyField.type = "number";
  qtyField.step = "any";
  qtyField.min = "0.01";
  qtyField.required = true;
  qtyField.value = String(entry.quantity);
  qtyField.className = "edit-qty-input";

  const unitLabel = document.createElement("span");
  unitLabel.className = "muted small";
  unitLabel.textContent = entry.unit === "portion" ? "portion(s)" : "g";

  const menuDropdown = document.createElement("select");
  for (const m of ["Petit-déjeuner", "Déjeuner", "Dîner", "Collation"]) {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = m;
    if (m === entry.meal_type) opt.selected = true;
    menuDropdown.appendChild(opt);
  }

  const saveBtn = document.createElement("button");
  saveBtn.type = "submit";
  saveBtn.className = "btn btn-success btn-sm";
  saveBtn.textContent = "OK";

  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.className = "btn btn-secondary btn-sm";
  cancelBtn.textContent = "Annuler";
  cancelBtn.addEventListener("click", () => loadDay(currentDate));

  form.appendChild(qtyField);
  form.appendChild(unitLabel);
  form.appendChild(menuDropdown);
  form.appendChild(saveBtn);
  form.appendChild(cancelBtn);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const newQty = parseFloat(qtyField.value);
    if (!newQty || newQty <= 0) return;

    const response = await fetch(`/api/entries/${entry.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        quantity: newQty,
        meal_type: menuDropdown.value,
      }),
    });
    if (response.ok) {
      loadDay(currentDate);
    } else {
      const err = await response.json();
      showFeedback(err.error || "Erreur lors de la modification.", true);
    }
  });

  li.appendChild(title);
  li.appendChild(form);
  qtyField.focus();
  qtyField.select();
}

async function deleteEntry(entryId) {
  const response = await fetch(`/api/entries/${entryId}`, { method: "DELETE" });
  if (response.ok) {
    loadDay(currentDate);
  }
}

async function loadHistory() {
  const response = await fetch("/api/history");
  const data = await response.json();
  const days = data.days || [];

  renderHistoryChart(days);
}

/**
 * Dessine un graphique SVG simple de l'historique :
 * - Axe X : les jours (du plus ancien au plus récent)
 * - Axe Y : les calories (kcal)
 * - Lignes vertes : objectif quotidien (GOAL_MIN et GOAL_MAX)
 * - Ligne bleue : repère journalier (REF_KCAL)
 * - Points orange : total de calories de chaque journée (cliquables)
 */
function renderHistoryChart(days) {
  historyChartEl.innerHTML = "";
  if (days.length === 0) {
    const empty = document.createElement("span");
    empty.className = "empty-msg";
    empty.textContent = "Aucune journée enregistrée pour le moment.";
    historyChartEl.appendChild(empty);
    return;
  }

  // Ordre chronologique de gauche à droite
  const sorted = [...days].reverse();

  const width = 760;
  const height = 270;
  const pad = { top: 24, right: 62, bottom: 42, left: 54 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  // Échelle Y : inclut toujours 0, les repères et la valeur max enregistrée
  const maxDay = Math.max(...sorted.map((d) => Number(d.total_kcal) || 0), 0);
  const rawMax = Math.max(REF_KCAL, GOAL_MAX, maxDay) * 1.12;
  const yMax = Math.ceil(rawMax / 250) * 250;

  const yPos = (kcal) => pad.top + plotH - (Math.max(0, kcal) / yMax) * plotH;
  const xPos = (idx) => {
    if (sorted.length === 1) return pad.left + plotW / 2;
    return pad.left + (idx / (sorted.length - 1)) * plotW;
  };

  const svgNS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs = {}, text = "") => {
    const node = document.createElementNS(svgNS, tag);
    for (const [k, v] of Object.entries(attrs)) {
      node.setAttribute(k, String(v));
    }
    if (text) node.textContent = text;
    return node;
  };

  const svg = el("svg", {
    viewBox: `0 0 ${width} ${height}`,
    class: "history-svg",
    role: "img",
    "aria-label": "Graphique des calories par jour",
  });

  // Grille horizontale Y (tous les 500 kcal)
  for (let val = 0; val <= yMax; val += 500) {
    const y = yPos(val);
    svg.appendChild(
      el("line", {
        x1: pad.left,
        y1: y,
        x2: width - pad.right,
        y2: y,
        stroke: "#e5e7eb",
        "stroke-width": 1,
      })
    );
    svg.appendChild(
      el(
        "text",
        {
          x: pad.left - 8,
          y: y + 4,
          "text-anchor": "end",
          "font-size": "11",
          fill: "#6b7280",
        },
        formatKcal(val)
      )
    );
  }

  // Bande verte translucide entre GOAL_MIN et GOAL_MAX
  const yGoalTop = yPos(GOAL_MAX);
  const yGoalBot = yPos(GOAL_MIN);
  svg.appendChild(
    el("rect", {
      x: pad.left,
      y: yGoalTop,
      width: plotW,
      height: Math.max(1, yGoalBot - yGoalTop),
      fill: "rgba(22, 163, 74, 0.12)",
    })
  );

  // Lignes de repère vertes (objectif quotidien min et max)
  for (const [gVal, dy] of [
    [GOAL_MAX, -3],
    [GOAL_MIN, 11],
  ]) {
    const yg = yPos(gVal);
    svg.appendChild(
      el("line", {
        x1: pad.left,
        y1: yg,
        x2: width - pad.right,
        y2: yg,
        stroke: "#16a34a",
        "stroke-width": 1.6,
        "stroke-dasharray": "5 4",
      })
    );
    svg.appendChild(
      el(
        "text",
        {
          x: width - pad.right + 6,
          y: yg + dy,
          "font-size": "10.5",
          "font-weight": "600",
          fill: "#15803d",
        },
        formatKcal(gVal)
      )
    );
  }

  // Ligne de repère bleue (repère journalier REF_KCAL)
  const yRef = yPos(REF_KCAL);
  svg.appendChild(
    el("line", {
      x1: pad.left,
      y1: yRef,
      x2: width - pad.right,
      y2: yRef,
      stroke: "#2563eb",
      "stroke-width": 2,
    })
  );
  svg.appendChild(
    el(
      "text",
      {
        x: width - pad.right + 6,
        y: yRef + 4,
        "font-size": "11",
        "font-weight": "700",
        fill: "#1d4ed8",
      },
      formatKcal(REF_KCAL)
    )
  );

  // Axes X et Y principaux
  svg.appendChild(
    el("line", {
      x1: pad.left,
      y1: pad.top,
      x2: pad.left,
      y2: pad.top + plotH,
      stroke: "#9ca3af",
      "stroke-width": 1.2,
    })
  );
  svg.appendChild(
    el("line", {
      x1: pad.left,
      y1: pad.top + plotH,
      x2: width - pad.right,
      y2: pad.top + plotH,
      stroke: "#9ca3af",
      "stroke-width": 1.2,
    })
  );

  // Courbe orange reliant les points s'il y a au moins 2 jours
  if (sorted.length >= 2) {
    const pts = sorted.map((d, i) => `${xPos(i)},${yPos(d.total_kcal)}`).join(" ");
    svg.appendChild(
      el("polyline", {
        points: pts,
        fill: "none",
        stroke: "#fb923c",
        "stroke-width": 2.2,
      })
    );
  }

  // Points orange pour chaque journée + étiquettes sur l'axe X
  const labelStep = Math.max(1, Math.ceil(sorted.length / 10));
  sorted.forEach((day, idx) => {
    const cx = xPos(idx);
    const cy = yPos(day.total_kcal);
    const isCurrent = day.entry_date === currentDate;
    const [, mm, dd] = day.entry_date.split("-");

    const group = el("g", { class: "chart-point" });
    group.appendChild(
      el("title", {}, `${day.entry_date} : ${formatKcal(day.total_kcal)} kcal (cliquer pour ouvrir)`)
    );

    // Halo discret sur le jour sélectionné
    if (isCurrent) {
      group.appendChild(
        el("circle", {
          cx,
          cy,
          r: 10,
          fill: "rgba(249, 115, 22, 0.25)",
        })
      );
    }

    // Point orange du jour
    group.appendChild(
      el("circle", {
        cx,
        cy,
        r: isCurrent ? 6.5 : 5,
        fill: "#f97316",
        stroke: "#ffffff",
        "stroke-width": 2,
      })
    );

    // Valeur affichée au-dessus du point si peu de jours ou jour sélectionné
    if (sorted.length <= 12 || isCurrent) {
      group.appendChild(
        el(
          "text",
          {
            x: cx,
            y: cy - 10,
            "text-anchor": "middle",
            "font-size": "10.5",
            "font-weight": isCurrent ? "700" : "600",
            fill: "#c2410c",
          },
          formatKcal(day.total_kcal)
        )
      );
    }

    group.addEventListener("click", () => loadDay(day.entry_date));
    svg.appendChild(group);

    // Étiquette date (JJ/MM) sur l'axe X sans chevauchement
    if (idx % labelStep === 0 || idx === sorted.length - 1 || isCurrent) {
      svg.appendChild(
        el(
          "text",
          {
            x: cx,
            y: pad.top + plotH + 18,
            "text-anchor": "middle",
            "font-size": "11",
            "font-weight": isCurrent ? "700" : "400",
            fill: isCurrent ? "#c2410c" : "#4b5563",
          },
          `${dd}/${mm}`
        )
      );
    }
  });

  historyChartEl.appendChild(svg);

  const hint = document.createElement("p");
  hint.className = "chart-hint";
  hint.textContent = "Cliquez sur un point orange pour afficher le détail de cette journée.";
  historyChartEl.appendChild(hint);
}

// ------------------------------------------------------------------
// Gestion des Favoris (Option A - Étoiles et accès rapide)
// ------------------------------------------------------------------

/** Charge la liste des favoris de l'utilisateur depuis l'API. */
async function loadFavorites() {
  try {
    const response = await fetch("/api/favorites");
    if (!response.ok) return;
    const data = await response.json();
    userFavorites = data.favorites || [];
    renderFavorites();
    updateSelectedFavButton();
  } catch (err) {
    console.error("Erreur chargement favoris:", err);
  }
}

/** Affiche les favoris sous forme de badges rapides cliquables. */
function renderFavorites() {
  if (!favoritesListEl) return;
  favoritesListEl.innerHTML = "";

  if (userFavorites.length === 0) {
    if (favoritesCountEl) favoritesCountEl.textContent = "(0)";
    const empty = document.createElement("span");
    empty.className = "favorites-empty";
    empty.textContent = "Aucun favori pour le moment. Cliquez sur l'étoile ☆ à côté d'un aliment dans vos repas pour l'épingler ici !";
    favoritesListEl.appendChild(empty);
    return;
  }

  if (favoritesCountEl) favoritesCountEl.textContent = `(${userFavorites.length})`;

  for (const fav of userFavorites) {
    const chip = document.createElement("div");
    chip.className = "favorite-chip";
    chip.title = "Cliquer pour pré-remplir le formulaire, ou sur le bouton + pour ajouter directement.";

    // Nom de l'aliment
    const nameSpan = document.createElement("span");
    nameSpan.className = "favorite-chip-name";
    nameSpan.textContent = fav.brand ? `${fav.name} (${fav.brand})` : fav.name;

    // Métadonnées (portion habituelle + repas habituel)
    const metaSpan = document.createElement("span");
    metaSpan.className = "favorite-chip-meta";
    const parts = [];
    if (fav.default_qty) {
      parts.push(`${fav.default_qty} ${fav.default_unit === "portion" ? "portion(s)" : "g"}`);
    }
    if (fav.default_meal) {
      parts.push(fav.default_meal);
    }
    metaSpan.textContent = parts.length > 0 ? `· ${parts.join(" · ")}` : "";

    // Bouton "+" pour ajout direct en 1 clic au repas du jour
    const addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.className = "favorite-chip-add";
    addBtn.textContent = "+";
    addBtn.title = `Ajouter directement à ${fav.default_meal || "ce jour"} (+1 clic)`;
    addBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      await addFavoriteDirect(fav);
    });

    // Bouton "×" pour retirer des favoris
    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "favorite-chip-del";
    delBtn.textContent = "×";
    delBtn.title = "Retirer des favoris";
    delBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      await removeFavorite(fav.fav_id);
    });

    // Un clic sur la puce elle-même pré-remplit le formulaire d'ajout
    chip.addEventListener("click", () => {
      selectFavorite(fav);
    });

    chip.appendChild(nameSpan);
    if (metaSpan.textContent) chip.appendChild(metaSpan);
    chip.appendChild(addBtn);
    chip.appendChild(delBtn);

    favoritesListEl.appendChild(chip);
  }
}

/** Pré-remplit le formulaire d'ajout avec cet aliment favori. */
function selectFavorite(fav) {
  const foodObj = {
    id: fav.food_id,
    name: fav.name,
    brand: fav.brand,
    kcal_per_100g: fav.kcal_per_100g,
    portion_name: fav.portion_name,
    portion_grams: fav.portion_grams,
    source: fav.source,
    external_code: fav.external_code,
  };
  selectFood(foodObj);

  if (fav.default_meal) {
    mealSelect.value = fav.default_meal;
  }
  if (fav.default_unit) {
    unitSelect.value = fav.default_unit;
  }
  if (fav.default_qty) {
    qtyInput.value = String(fav.default_qty);
  }
  updatePreview();
  selectedBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

/** Ajoute immédiatement un aliment favori au menu du jour en 1 clic. */
async function addFavoriteDirect(fav) {
  const meal = fav.default_meal || mealSelect.value || "Petit-déjeuner";
  const unit = fav.default_unit || "g";
  const qty = fav.default_qty || 100;

  try {
    const response = await fetch("/api/entries", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        food_id: fav.food_id,
        meal_type: meal,
        unit: unit,
        quantity: qty,
        entry_date: currentDate,
      }),
    });
    if (response.ok) {
      showFeedback(`Ajouté à ${meal} : ${fav.name} (${qty} ${unit === "portion" ? "portion" : "g"})`);
      loadDay(currentDate);
    } else {
      const err = await response.json();
      showFeedback(err.error || "Erreur lors de l'ajout.", true);
    }
  } catch (err) {
    showFeedback("Erreur de communication avec le serveur.", true);
  }
}

/** Bascule un aliment en favori (ajout ou suppression). */
async function toggleFavorite(payload) {
  try {
    const response = await fetch("/api/favorites/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (response.ok) {
      const data = await response.json();
      userFavorites = data.favorites || [];
      renderFavorites();

      // Met à jour la liste des repas du jour pour synchroniser les étoiles
      const dayResp = await fetch(`/api/day?date=${encodeURIComponent(currentDate)}`);
      if (dayResp.ok) {
        const dayData = await dayResp.json();
        renderMeals(dayData.menus || [], dayData.partner || null);
      }

      updateSelectedFavButton();

      if (searchInput.value.trim()) {
        loadLocalFoods(searchInput.value.trim());
      }
      return data.is_favorite;
    }
  } catch (err) {
    console.error("Erreur toggle favori:", err);
  }
  return false;
}

/** Supprime un favori par son identifiant de favori. */
async function removeFavorite(favId) {
  try {
    const response = await fetch(`/api/favorites/${favId}`, { method: "DELETE" });
    if (response.ok) {
      const data = await response.json();
      userFavorites = data.favorites || [];
      renderFavorites();

      const dayResp = await fetch(`/api/day?date=${encodeURIComponent(currentDate)}`);
      if (dayResp.ok) {
        const dayData = await dayResp.json();
        renderMeals(dayData.menus || [], dayData.partner || null);
      }
      updateSelectedFavButton();
    }
  } catch (err) {
    console.error("Erreur suppression favori:", err);
  }
}

/** Met à jour l'étoile dans le panneau de produit sélectionné. */
function updateSelectedFavButton() {
  if (!selectedFavBtn || !selectedFood) return;
  const isFav = userFavorites.some((fav) => {
    if (selectedFood.id && fav.food_id === selectedFood.id) return true;
    if (fav.name.toLowerCase() === selectedFood.name.toLowerCase() && (fav.brand || "") === (selectedFood.brand || "")) return true;
    return false;
  });

  selectedFavBtn.textContent = isFav ? "★" : "☆";
  selectedFavBtn.classList.toggle("active", isFav);
  selectedFavBtn.title = isFav ? "Retirer de mes favoris" : "Ajouter à mes favoris";
}

// ------------------------------------------------------------------
// Recherche locale + Open Food Facts + sélection de produit
// ------------------------------------------------------------------

async function loadLocalFoods(query = "") {
  const response = await fetch(`/api/foods?q=${encodeURIComponent(query)}`);
  const data = await response.json();
  localFoods = data.foods || [];
  ciqualFoods = data.ciqual || [];
  renderSearchResults();
}

async function searchOpenFoodFacts(query) {
  const q = query.trim();
  if (!q) {
    showFeedback("Tapez d'abord le nom d'un produit à chercher sur Open Food Facts.", true);
    return;
  }

  offSearchBtn.disabled = true;
  offSearchBtn.textContent = "Recherche...";
  showFeedback("Recherche sur Open Food Facts en cours...");

  try {
    const response = await fetch(`/api/openfoodfacts?q=${encodeURIComponent(q)}`);
    const data = await response.json();

    if (data.error) {
      offFoods = [];
      showFeedback(data.error, true);
    } else {
      offFoods = data.results || [];
      if (offFoods.length === 0) {
        showFeedback("Aucun produit avec valeur calorique trouvé sur Open Food Facts pour cette recherche.");
      } else {
        showFeedback(`${offFoods.length} produit(s) trouvé(s) sur Open Food Facts. Cliquez pour sélectionner.`);
      }
    }
  } catch (err) {
    offFoods = [];
    showFeedback("Impossible de contacter le serveur local.", true);
  } finally {
    offSearchBtn.disabled = false;
    offSearchBtn.textContent = "Open Food Facts";
    renderSearchResults();
  }
}

function renderSearchResults() {
  resultsContainer.innerHTML = "";

  if (localFoods.length > 0) {
    appendResultGroup("Mes aliments enregistrés", localFoods);
  }
  if (ciqualFoods.length > 0) {
    appendResultGroup("Table Ciqual (ANSES · hors ligne)", ciqualFoods);
  }
  if (offFoods.length > 0) {
    appendResultGroup("Open Food Facts (en ligne)", offFoods);
  }
}

function appendResultGroup(groupTitle, items) {
  const titleEl = document.createElement("div");
  titleEl.className = "result-group-title";
  titleEl.textContent = groupTitle;
  resultsContainer.appendChild(titleEl);

  for (const item of items) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "result-item";

    const left = document.createElement("div");
    const name = document.createElement("div");
    name.className = "result-name";

    const isFav = Boolean(item.is_favorite) || (item.id && userFavorites.some((f) => f.food_id === item.id));
    name.textContent = `${isFav ? "⭐ " : ""}${item.name}`;

    const meta = document.createElement("div");
    meta.className = "result-meta";
    const details = [];
    if (item.brand) details.push(item.brand);
    if (item.portion_grams) {
      const pName = item.portion_name || "portion";
      details.push(`${pName} = ${item.portion_grams} g`);
    }
    meta.textContent = details.join(" · ");

    left.appendChild(name);
    if (meta.textContent) left.appendChild(meta);

    const kcal = document.createElement("div");
    kcal.className = "result-kcal";
    kcal.textContent = `${item.kcal_per_100g} kcal/100g`;

    btn.appendChild(left);
    btn.appendChild(kcal);
    btn.addEventListener("click", () => selectFood(item));
    resultsContainer.appendChild(btn);
  }
}

function selectFood(food) {
  selectedFood = food;
  selectedNameEl.textContent = food.name;
  selectedBrandEl.textContent = food.brand ? ` (${food.brand})` : "";
  updateSelectedFavButton();

  let info = `${food.kcal_per_100g} kcal pour 100 g`;
  if (food.portion_grams) {
    info += ` · 1 ${food.portion_name || "portion"} = ${food.portion_grams} g`;
  }
  selectedKcalInfoEl.textContent = info;

  // Par défaut : si le produit a un poids de portion connu, on garde l'unité choisie ou grammes
  customPortionGramsInput.value = food.portion_grams ? String(food.portion_grams) : "";
  if (unitSelect.value === "portion") {
    qtyInput.value = "1";
  } else {
    qtyInput.value = "100";
  }

  selectedBox.classList.remove("hidden");
  updatePreview();
}

function clearSelection() {
  selectedFood = null;
  selectedBox.classList.add("hidden");
  updateSelectedFavButton();
}

function updatePreview() {
  if (!selectedFood) return;

  const qty = parseFloat(qtyInput.value) || 0;
  const unit = unitSelect.value;

  // Affiche le champ de poids de portion uniquement si l'unité est "portion" et que le poids manque
  const knownPortion = selectedFood.portion_grams ? Number(selectedFood.portion_grams) : null;
  if (unit === "portion" && !knownPortion) {
    portionWeightRow.classList.remove("hidden");
  } else {
    portionWeightRow.classList.add("hidden");
  }

  let grams = 0;
  if (unit === "g") {
    grams = qty;
  } else {
    const customPortion = parseFloat(customPortionGramsInput.value) || 0;
    const pGrams = knownPortion || customPortion;
    grams = qty * pGrams;
  }

  if (grams > 0) {
    const kcal = (grams / 100) * Number(selectedFood.kcal_per_100g);
    calcPreviewEl.textContent = `Aperçu : ${Math.round(grams * 10) / 10} g → ${formatKcal(kcal)} kcal`;
  } else {
    calcPreviewEl.textContent = "Aperçu : 0 kcal";
  }
}

// ------------------------------------------------------------------
// Événements utilisateur
// ------------------------------------------------------------------

datePicker.addEventListener("change", () => {
  if (datePicker.value) loadDay(datePicker.value);
});
prevDayBtn.addEventListener("click", () => loadDay(shiftDate(currentDate, -1)));
nextDayBtn.addEventListener("click", () => loadDay(shiftDate(currentDate, 1)));
todayBtn.addEventListener("click", () => loadDay(getLocalTodayISO()));

// Filtrer les aliments locaux en direct pendant la frappe
searchInput.addEventListener("input", () => {
  offFoods = [];
  showFeedback("");
  loadLocalFoods(searchInput.value);
});

// Cliquer sur "Open Food Facts" (ou appuyer sur Entrée dans la barre)
searchForm.addEventListener("submit", (e) => {
  e.preventDefault();
  searchOpenFoodFacts(searchInput.value);
});

clearSelectedBtn.addEventListener("click", clearSelection);

unitSelect.addEventListener("change", () => {
  qtyInput.value = unitSelect.value === "portion" ? "1" : "100";
  updatePreview();
});
qtyInput.addEventListener("input", updatePreview);
customPortionGramsInput.addEventListener("input", updatePreview);

// Ajouter le produit sélectionné au menu choisi
addEntryForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!selectedFood) return;

  const unit = unitSelect.value;
  const payload = {
    entry_date: currentDate,
    meal_type: mealSelect.value,
    quantity: parseFloat(qtyInput.value),
    unit: unit,
  };

  if (selectedFood.id) {
    payload.food_id = selectedFood.id;
  } else {
    payload.food = selectedFood;
  }

  if (unit === "portion" && !selectedFood.portion_grams) {
    const customPg = parseFloat(customPortionGramsInput.value);
    if (!customPg || customPg <= 0) {
      showFeedback("Indiquez le poids d'1 portion en grammes (ex: 30).", true);
      return;
    }
    payload.custom_portion_grams = customPg;
  }

  const response = await fetch("/api/entries", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();

  if (!response.ok) {
    showFeedback(data.error || "Erreur lors de l'ajout.", true);
    return;
  }

  showFeedback("Aliment ajouté au menu !");
  clearSelection();
  loadDay(currentDate);
  loadLocalFoods(searchInput.value);
});

// Enregistrer un aliment manuellement
manualFoodForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const payload = {
    name: document.getElementById("manual-name").value.trim(),
    brand: document.getElementById("manual-brand").value.trim(),
    kcal_per_100g: parseFloat(document.getElementById("manual-kcal").value),
    portion_name: document.getElementById("manual-portion-name").value.trim(),
    portion_grams: document.getElementById("manual-portion-grams").value || null,
  };

  const response = await fetch("/api/foods", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();

  if (!response.ok) {
    showFeedback(data.error || "Erreur lors de la création de l'aliment.", true);
    return;
  }

  manualFoodForm.reset();
  manualDetails.open = false;
  showFeedback(`"${data.food.name}" enregistré dans votre catalogue local.`);
  await loadLocalFoods(searchInput.value);
  selectFood(data.food);
});

// Étoile de favori dans le formulaire du produit sélectionné
if (selectedFavBtn) {
  selectedFavBtn.addEventListener("click", async () => {
    if (!selectedFood) return;
    await toggleFavorite({
      food_id: selectedFood.id || null,
      food: selectedFood.id ? null : selectedFood,
      default_meal: mealSelect.value,
      default_qty: parseFloat(qtyInput.value) || 100,
      default_unit: unitSelect.value,
    });
  });
}

// Déconnexion
logoutBtn.addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  window.location.href = "/login";
});

/** Charge le profil et les repères caloriques de l'utilisateur connecté, puis la journée. */
async function initApp() {
  const res = await fetch("/api/me");
  if (res.status === 401) {
    window.location.href = "/login";
    return;
  }
  const data = await res.json();
  const user = data.user;

  GOAL_MIN = Number(user.goal_min) || 1650;
  GOAL_MAX = Number(user.goal_max) || 1750;
  REF_KCAL = Number(user.ref_kcal) || 1990;

  currentUsernameEl.textContent = user.username;
  goalRangeTextEl.textContent = `${formatKcal(GOAL_MIN)} – ${formatKcal(GOAL_MAX)} kcal / jour`;
  refKcalTextEl.textContent = `${formatKcal(REF_KCAL)} kcal / jour`;
  legendGoalEl.textContent = `${formatKcal(GOAL_MIN)} – ${formatKcal(GOAL_MAX)} (objectif)`;
  legendRefEl.textContent = `${formatKcal(REF_KCAL)} (repère)`;

  // Positionne la zone verte de l'objectif sur la barre de progression
  const leftPct = Math.min(100, Math.max(0, (GOAL_MIN / REF_KCAL) * 100));
  const widthPct = Math.min(100 - leftPct, Math.max(1, ((GOAL_MAX - GOAL_MIN) / REF_KCAL) * 100));
  progressGoalZoneEl.style.left = `${leftPct.toFixed(1)}%`;
  progressGoalZoneEl.style.width = `${widthPct.toFixed(1)}%`;

  loadDay(currentDate);
  loadLocalFoods("");
  loadFavorites();
  startMascotAnimation();
}

/**
 * Anime aléatoirement le petit robot extrait du logo sur l'écran :
 * déplacements fluides, petits sauts et bulle de message au clic.
 */
function startMascotAnimation() {
  const bot = document.getElementById("mascot-bot");
  const bubble = document.getElementById("mascot-bubble");
  if (!bot || !bubble) return;

  const messages = [
    "Coucou !",
    "Bon appétit !",
    "Pense à boire de l'eau !",
    "Un fruit ou une tisane ?",
    "Super suivi aujourd'hui !",
    "Bravo pour ta régularité !",
    "Un clic sur tes favoris ⭐ ?",
  ];
  let currentX = 24;
  let bubbleTimer = null;

  function showBubble(text) {
    bubble.textContent = text;
    bubble.classList.remove("hidden");
    clearTimeout(bubbleTimer);
    bubbleTimer = setTimeout(() => bubble.classList.add("hidden"), 2600);
  }

  function moveRandomly() {
    const margin = 18;
    const maxW = Math.max(100, window.innerWidth - 96);
    const maxH = Math.max(100, window.innerHeight - 105);

    // Favorise les bords/coins 70% du temps pour ne pas gêner la lecture centrale
    let targetX;
    let targetY;
    if (Math.random() < 0.7) {
      targetX = Math.random() < 0.5 ? margin : maxW - margin;
      targetY = margin + Math.random() * (maxH - margin);
    } else {
      targetX = margin + Math.random() * (maxW - margin);
      targetY = margin + Math.random() * (maxH - margin);
    }

    bot.classList.toggle("facing-left", targetX < currentX);
    currentX = targetX;
    bot.style.left = `${Math.round(targetX)}px`;
    bot.style.top = `${Math.round(targetY)}px`;

    // Petit saut aléatoire de temps en temps à l'arrivée
    if (Math.random() < 0.45) {
      setTimeout(() => {
        bot.classList.remove("hopping");
        void bot.offsetWidth;
        bot.classList.add("hopping");
      }, 2800);
    }
  }

  function scheduleNextMove() {
    const delay = 4500 + Math.random() * 4500;
    setTimeout(() => {
      moveRandomly();
      if (Math.random() < 0.25) {
        const msg = messages[Math.floor(Math.random() * messages.length)];
        showBubble(msg);
      }
      scheduleNextMove();
    }, delay);
  }

  bot.addEventListener("click", () => {
    bot.classList.remove("hopping");
    void bot.offsetWidth;
    bot.classList.add("hopping");
    const msg = messages[Math.floor(Math.random() * messages.length)];
    showBubble(msg);
    setTimeout(moveRandomly, 350);
  });

  // Premier petit déplacement peu après l'ouverture
  setTimeout(moveRandomly, 1800);
  scheduleNextMove();
}

// Initialisation au chargement de la page
initApp();
